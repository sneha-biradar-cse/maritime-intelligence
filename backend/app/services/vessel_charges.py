"""
Ship charges: what NMPA bills a ship for entering and using the port (port dues, pilotage, berth hire), and what NMPA's
own rebates on these charges cost.

Why it matters: most port incentives - NMPA's container rebate (35% / 50%), its Cape-size rebate (30%), Rotterdam's
volume discount, VOC's route incentive - are on SHIP charges, not on the cargo charge (wharfage). Without this module the
Incentive Engine could not price NMPA's own live schemes.

Rates: NMPA Scale of Rates, validity from 7 May 2026 (nmpa_public_data/Microsoft Word - NMPA SOR indexation 0.65.doc.pdf):
  2.1.1 Port dues            per GRT per entry: coastal Rs 6.6576, foreign USD 0.4110                       (printed page 17)
  2.2.1 Pilotage             slabs by GRT; minimum Rs 42,194 / USD 1580.7                                     (pages 18-19)
  2.3.1 Berth hire           per GRT per hour or part thereof, by ship type, with a minimum per hour           (pages 27-28)
The test suite checks every number below against the PDF text.

Inputs a bill needs, and where they come from here:
  * Gross tonnage (GRT/GT) of each ship. NOT in NMPA's daily reports. In order of trust:
      1. data/vessel_gt.csv          - from NMPA's own records / the ship's tonnage certificate (official)
      2. data/vessel_gt_public.csv   - from a public register (scripts/fetch_public_incentive_data.py vessel-gt); name match
      3. an estimate from the ship's length (LOA, in the daily reports), fitted on the ships whose GT is known
    Only (1) can support an official proposal; (2) and (3) are labelled and are for planning only.
  * USD -> INR rate. The Scale of Rates uses the RBI reference rate on the day the ship enters (General Terms iii).
    data/fx_usd_inr.csv holds rates with their source; anything other than RBI/FBIL is labelled an estimate.
  * Hours at berth: data/vessel_stays.json (from the daily reports); 'date_only' stays are rough.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import trade_market as tmk
from backend.app.services import trade_split as ts

SOR_NOTE = "NMPA Scale of Rates, validity from 7 May 2026 (Chapter II, Vessel related charges)"
PORT_DUES = {"coastal_rs": 6.6576, "foreign_usd": 0.4110}                        # 2.1.1, per GRT per entry
BALLAST_CONCESSION = 0.25                                                          # 2.1.2 (1)(i)
PILOTAGE = {   # 2.2.1: (up to GRT, fixed amount for the slab, rate per GRT above the slab's start)
    "coastal": [(30000, 0.0, 14.065, 0), (60000, 421950.0, 11.251, 30000), (math.inf, 759480.0, 9.840, 60000)],
    "foreign": [(30000, 0.0, 0.5269, 0), (60000, 15807.0, 0.4217, 30000), (math.inf, 28458.0, 0.3692, 60000)],
}
PILOTAGE_MIN = {"coastal": 42194.0, "foreign": 1580.7}                             # 2.2.1 note 4 (first slab)
BERTH_HIRE = {  # 2.3.1: per GRT per hour or part thereof, and the minimum per hour
    "liquid": {"coastal": (0.10861, 216.52), "foreign": (0.004019, 8.10)},     # POL, crude, other liquids, LPG/LNG, hazardous
    "dry": {"coastal": (0.07602, 262.83), "foreign": (0.002824, 9.82)},        # dry bulk, containers, RoRo, general, other
}
SOR_STRINGS = ["6.6576", "0.4110", "14.065", "0.5269", "4,21,950", "11.251", "15,807", "0.4217", "7,59,480", "9.840",
               "28,458", "0.3692", "1580.7", "42,194", "0.10861", "216.52", "0.004019", "8.10", "0.07602", "262.83",
               "0.002824", "9.82"]
LIQUID_FAMILIES = {"Crude oil", "Petroleum products (fuels)", "LPG", "Fuel oil", "Edible oil", "Bitumen", "Coal tar pitch"}
LIQUID_WORDS = re.compile(r"CRUDE|HSD|MS\b|LPG|PROPANE|BUTANE|NAPHTHA|ATF|SKO|FO\b|VLSFO|BITUMEN|OIL|LIQUID|CHEMICAL|PITCH|"
                          r"AMMONIA|ACID|MOLASSES|LNG|PETROL|DIESEL|METHANOL|ETHANOL|TAR", re.I)
GT_FILE, GT_PUBLIC_FILE, FX_FILE = "data/vessel_gt.csv", "data/vessel_gt_public.csv", "data/fx_usd_inr.csv"
MIN_FIT_PAIRS = 8

# NMPA's own rebates on ship charges (data/nmpa_incentive_notices.csv)
CONTAINER_REBATE = {"notice": "Comrc/DTM(C)/2026-27/01 (02.11.2026)", "feeder_pct": 35.0, "mainline_pct": 50.0,
                    "charges": ["port_dues_rs", "pilotage_rs", "berth_hire_rs"], "from": "2026-11-03", "to": "2027-03-31"}
CAPESIZE_REBATE = {"notice": "12/1/2021-22/ATM Gr.I (Com)/JSW (10.02.2025)", "pct": 30.0, "min_grt": 80000, "berth": "16",
                   "charges": ["port_dues_rs", "pilotage_rs"], "from": "2025-04-03", "to": "2027-04-02"}


# ── the tariff arithmetic ──────────────────────────────────────────────────────────────────────────────
def _side(coastal: bool) -> str:
    return "coastal" if coastal else "foreign"


def port_dues(grt: float, coastal: bool, usd_inr: float | None, ballast: bool = False) -> float:
    amt = grt * PORT_DUES["coastal_rs"] if coastal else grt * PORT_DUES["foreign_usd"] * _fx(usd_inr)
    return amt * (1 - BALLAST_CONCESSION) if ballast else amt


def pilotage(grt: float, coastal: bool, usd_inr: float | None) -> float:
    side = _side(coastal)
    for upto, fixed, rate, start in PILOTAGE[side]:
        if grt <= upto:
            amt = fixed + rate * (grt - start)
            if start == 0:
                amt = max(amt, PILOTAGE_MIN[side])
            return amt if coastal else amt * _fx(usd_inr)
    raise ValueError(grt)


def berth_hire(grt: float, hours: float, kind: str, coastal: bool, usd_inr: float | None) -> float:
    rate, minimum = BERTH_HIRE[kind][_side(coastal)]
    per_hour = max(grt * rate, minimum)
    amt = per_hour * math.ceil(max(hours, 0))          # "per hour or part thereof"
    return amt if coastal else amt * _fx(usd_inr)


def _fx(usd_inr: float | None) -> float:
    if not usd_inr or usd_inr <= 0:
        raise ValueError("a USD to INR rate is needed for a foreign-going ship (Scale of Rates: RBI reference rate on the day of entry)")
    return float(usd_inr)


def kind_of(cargo: str | None, family: str | None = None) -> str:
    if family in LIQUID_FAMILIES:
        return "liquid"
    return "liquid" if cargo and LIQUID_WORDS.search(cargo) else "dry"


def call_cost(grt: float, coastal: bool, kind: str, berth_hours: float, usd_inr: float | None = None,
              ballast: bool = False) -> dict[str, Any]:
    """One ship call: port dues + pilotage (one in and one out move, tugs included) + berth hire. Rupees."""
    if grt <= 0:
        raise ValueError("GRT must be positive")
    if kind not in BERTH_HIRE:
        raise ValueError("kind must be 'liquid' or 'dry'")
    pd_ = port_dues(grt, coastal, usd_inr, ballast)
    pl = pilotage(grt, coastal, usd_inr)
    bh = berth_hire(grt, berth_hours, kind, coastal, usd_inr)
    return {"grt": grt, "coastal": coastal, "kind": kind, "berth_hours": berth_hours, "usd_inr": None if coastal else usd_inr,
            "port_dues_rs": round(pd_), "pilotage_rs": round(pl), "berth_hire_rs": round(bh), "total_rs": round(pd_ + pl + bh),
            "tariff": SOR_NOTE,
            "plain": (f"A {'coastal' if coastal else 'foreign-going'} ship of {grt:,.0f} GRT staying {berth_hours:,.0f} hours at berth "
                      f"pays about \u20b9{pd_ + pl + bh:,.0f}: entry fee (port dues) \u20b9{pd_:,.0f}, pilot and tugs "
                      f"\u20b9{pl:,.0f}, berth rent \u20b9{bh:,.0f}.")}


# ── inputs: ship size, exchange rate, calls ────────────────────────────────────────────────────────────
def _read(path: str) -> pd.DataFrame:
    f = tmk.ROOT / path
    if not f.exists():
        return pd.DataFrame()
    return pd.read_csv(f, comment="#", dtype=str).fillna("")


@lru_cache(maxsize=1)
def _sightings() -> dict[str, dict]:
    """vessel -> {'loa': max LOA seen, 'runs': {date: F/C}} from every table of every daily report."""
    out: dict[str, dict] = {}
    for p in sorted(ts.DAILY_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        day = d.get("report_date", "")
        for tab in ("berthed", "anchorage", "tankers_scheduled", "expected"):
            for r in d.get(tab, []):
                v = ts._vessel_norm(r.get("vessel_name"))
                if not v:
                    continue
                rec = out.setdefault(v, {"loa": None, "runs": {}})
                try:
                    loa = float(str(r.get("loa") or "").strip())
                    if 20 <= loa <= 450:
                        rec["loa"] = max(rec["loa"] or 0, loa)
                except ValueError:
                    pass
                run = str(r.get("run") or "").strip().upper()
                if run in ("F", "C"):
                    rec["runs"][day] = run
    return out


def gt_table() -> dict[str, dict]:
    """vessel -> {'grt', 'source', 'confidence'}; official records win over public ones."""
    out = {}
    for path, conf in ((GT_PUBLIC_FILE, "Public register (name match: confirm with IMO number)"), (GT_FILE, "Official")):
        d = _read(path)
        for r in d.to_dict(orient="records") if not d.empty else []:
            try:
                g = float(str(r.get("gt", "")).replace(",", ""))
            except ValueError:
                continue
            if g > 0:
                out[ts._vessel_norm(r.get("vessel_name"))] = {"grt": g, "source": r.get("source", path), "confidence": conf}
    return out


@lru_cache(maxsize=1)
def _loa_fit() -> dict | None:
    """log(GT) = a + b log(LOA), fitted on ships whose GT is known AND whose LOA is in the daily reports."""
    gts, s = gt_table(), _sightings()
    pairs = [(s[v]["loa"], g["grt"]) for v, g in gts.items() if v in s and s[v]["loa"]]
    if len(pairs) < MIN_FIT_PAIRS:
        return None
    x = np.log([p[0] for p in pairs])
    y = np.log([p[1] for p in pairs])
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    return {"a": float(a), "b": float(b), "pairs": len(pairs), "typical_error_pct": round(float(np.exp(np.std(resid)) - 1) * 100)}


def grt_for(vessel: str) -> dict | None:
    v = ts._vessel_norm(vessel)
    g = gt_table().get(v)
    if g:
        return g
    loa = (_sightings().get(v) or {}).get("loa")
    fit = _loa_fit()
    if loa and fit:
        return {"grt": round(math.exp(fit["a"] + fit["b"] * math.log(loa))), "source": f"Estimate from length {loa:g} m",
                "confidence": f"Estimate (typical error about {fit['typical_error_pct']}%; planning only)"}
    return None


def fx_for(day: str) -> dict | None:
    d = _read(FX_FILE)
    if d.empty:
        return None
    d = d[d["date"] <= day[:10]].sort_values("date")
    if d.empty:
        return None
    r = d.iloc[-1]
    official = bool(re.search(r"RBI|FBIL", r.get("source", ""), re.I))
    return {"usd_inr": float(r["usd_inr"]), "date": r["date"], "source": r.get("source", ""),
            "basis": "Official (Scale of Rates basis)" if official else "Estimate (not the RBI reference rate)"}


def _run_for(vessel: str, start: str, end: str) -> str | None:
    runs = (_sightings().get(ts._vessel_norm(vessel)) or {}).get("runs", {})
    hits = [r for day, r in runs.items() if start[:10] <= day <= end[:10]]
    return hits[-1] if hits else (list(runs.values())[-1] if runs else None)


def _stays() -> list[dict]:
    f = tmk.ROOT / "data" / "vessel_stays.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _berth_nums(b: str | None) -> set[str]:
    return set(re.findall(r"\d+", b or ""))


def price_calls(berth: str | None = None, cargo_pattern: str | None = None, months: int = 12,
                usd_inr: float | None = None) -> dict[str, Any]:
    """Every ship stay at a berth (or all berths) in the last `months` months of stays held, priced where GRT is known."""
    stays = _stays()
    if not stays:
        return {"available": False, "calls": []}
    last = max(s["start_datetime"] for s in stays)
    since = (pd.Timestamp(last) - pd.DateOffset(months=months)).isoformat()
    rows = []
    for s in stays:
        if s["start_datetime"] < since:
            continue
        if berth and berth not in _berth_nums(s.get("berth_no")):
            continue
        if cargo_pattern and not re.search(cargo_pattern, s.get("cargo") or "", re.I):
            continue
        g = grt_for(s["vessel_norm"])
        run = _run_for(s["vessel_norm"], s["start_datetime"], s.get("end_datetime") or s["start_datetime"])
        coastal = run == "C"
        hours = s.get("duration_hours") or 0
        rec = {"vessel": s["vessel_norm"], "berth": s.get("berth_no"), "cargo": s.get("cargo"), "start": s["start_datetime"][:16],
               "hours": hours, "stay_confidence": s.get("confidence"), "run": run or "?", "grt": None, "grt_source": None}
        if g:
            rec.update({"grt": g["grt"], "grt_source": g["confidence"]})
            fx = usd_inr or (None if coastal else (fx_for(s["start_datetime"]) or {}).get("usd_inr"))
            try:
                c = call_cost(g["grt"], coastal, kind_of(s.get("cargo")), hours, fx)
                rec.update({k: c[k] for k in ("port_dues_rs", "pilotage_rs", "berth_hire_rs", "total_rs")})
            except ValueError as e:
                rec["note"] = str(e)
        rows.append(rec)
    priced = [r for r in rows if r.get("total_rs") is not None]
    return {"available": True, "from": since[:10], "to": last[:10], "calls": rows, "calls_total": len(rows),
            "calls_priced": len(priced), "calls_missing_grt": sum(1 for r in rows if r["grt"] is None),
            "total_rs": sum(r["total_rs"] for r in priced)}


def container_rebate(usd_inr: float | None = None) -> dict[str, Any]:
    """What NMPA's container rebate (35% feeder / 50% mainline on port dues, pilotage and berth hire) costs on a year's
    container calls at Berth 14. The notice does not define feeder vs mainline, so a range is shown."""
    p = price_calls(berth="14", usd_inr=usd_inr)
    base = sum(sum(r.get(k, 0) or 0 for k in CONTAINER_REBATE["charges"]) for r in p.get("calls", []) if r.get("total_rs") is not None)
    low, high = base * CONTAINER_REBATE["feeder_pct"] / 100, base * CONTAINER_REBATE["mainline_pct"] / 100
    n, k = p.get("calls_total", 0), p.get("calls_priced", 0)
    plain = (f"{n} container ship calls at Berth 14 from {p.get('from')} to {p.get('to')}. "
             + (f"For the {k} calls whose size is known, the ship charges were about \u20b9{base:,.0f}; the rebate would cost "
                f"\u20b9{low:,.0f} (all feeder, 35%) to \u20b9{high:,.0f} (all mainline, 50%) a year."
                if k else "No ship size (GRT) is known for these calls yet, so the rebate cannot be priced: add GRTs to "
                          "data/vessel_gt.csv or run scripts/fetch_public_incentive_data.py vessel-gt."))
    if k and k < n:
        plain += f" {n - k} calls are not priced (size unknown), so the true cost is higher."
    return {"notice": CONTAINER_REBATE["notice"], "calls": p.get("calls", []), "calls_total": n, "calls_priced": k,
            "charges_before_rebate_rs": round(base), "rebate_low_rs": round(low), "rebate_high_rs": round(high), "plain": plain,
            "limits": ["The notice does not define 'feeder' and 'mainline': the range covers both ends.",
                       "Whether NMPA or the PPP terminal bills berth hire at Berth 14 is to be confirmed by Finance.",
                       "Calls are from a past year of daily reports, used to show the cost of a typical year."]}


def capesize_rebate(usd_inr: float | None = None) -> dict[str, Any]:
    """30% on port dues and pilotage for Cape-size ships (GRT above 80,000) at Berth 16."""
    p = price_calls(berth=CAPESIZE_REBATE["berth"], usd_inr=usd_inr)
    elig = [r for r in p.get("calls", []) if r.get("grt") and r["grt"] > CAPESIZE_REBATE["min_grt"] and r.get("total_rs") is not None]
    base = sum((r.get("port_dues_rs") or 0) + (r.get("pilotage_rs") or 0) for r in elig)
    cost = base * CAPESIZE_REBATE["pct"] / 100
    unknown = sum(1 for r in p.get("calls", []) if r.get("grt") is None)
    if not elig and unknown:
        plain = (f"{p.get('calls_total', 0)} ship calls at Berth 16, none with a known size (GRT), so the 30% Cape-size rebate cannot "
                 "be priced yet: add GRTs to data/vessel_gt.csv or run scripts/fetch_public_incentive_data.py vessel-gt.")
    else:
        plain = (f"{p.get('calls_total', 0)} ship calls at Berth 16; {len(elig)} known to be above 80,000 GRT. The 30% rebate on "
                 f"their port dues and pilotage costs about \u20b9{cost:,.0f} a year."
                 + (f" {unknown} calls have no known size, so the true cost may be higher." if unknown else ""))
    return {"notice": CAPESIZE_REBATE["notice"], "eligible_calls": len(elig), "calls_total": p.get("calls_total", 0),
            "calls_size_unknown": unknown, "charges_before_rebate_rs": round(base), "rebate_rs": round(cost), "plain": plain}


def summary(usd_inr: float | None = None) -> dict[str, Any]:
    fit = _loa_fit()
    gts = gt_table()
    fx = _read(FX_FILE)
    return {"tariff": SOR_NOTE,
            "inputs": {"ships_with_official_grt": sum(1 for g in gts.values() if g["confidence"] == "Official"),
                       "ships_with_public_grt": sum(1 for g in gts.values() if g["confidence"] != "Official"),
                       "length_estimate": fit or "Not available (needs at least 8 ships with both a known GRT and a length)",
                       "fx_rates_held": 0 if fx.empty else len(fx)},
            "container_rebate": container_rebate(usd_inr), "capesize_rebate": capesize_rebate(usd_inr),
            "how_to_complete": ["Ask NMPA Finance/Marine for the GRT of each ship (it is on every port dues bill) and put it in "
                                "data/vessel_gt.csv.",
                                "Or run: python scripts/fetch_public_incentive_data.py vessel-gt (public register, name match; "
                                "planning only).",
                                "For foreign-going ships, add USD-INR rates: python scripts/fetch_public_incentive_data.py fx"]}
