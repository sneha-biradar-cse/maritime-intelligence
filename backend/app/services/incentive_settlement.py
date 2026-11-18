"""
Monthly settlement list for Finance: which ship calls and exporters qualify for NMPA's rebates in a month, and how much.

Calls come straight from NMPA's daily vessel position reports (one call = one ship at one berth, from its berthing date
to the last report showing it there), so the list is as current as the latest report.

- Container rebate (Comrc/DTM(C)/2026-27/01): container calls at Berth 14 berthed from 3 Nov 2026 to 31 Mar 2027;
  35% (feeder) to 50% (mainline) of port dues, pilotage and berth hire. The notice does not define feeder and
  mainline, so a range is shown.
- Cape-size rebate (12/1/2021-22/ATM Gr.I (Com)/JSW): calls at Berth 16 from 3 Apr 2025 to 2 Apr 2027; 30% of port dues
  and pilotage, only for ships above 80,000 GRT.
- Iron ore export rebate (NMPA/TM/IOF-Exp-Rebate/26-27): 20% of wharfage on each exporter's tonnes above its
  FY 2025-26 quantity; builds up during the year and is paid after 31 Mar 2027, on verification.

An amount is shown only where the ship's GRT is known (NMPA's records, else public records); otherwise the line says
'apply on the bill', because NMPA's port-dues bill carries the GRT. Berth hours are approximate (whole report days).
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import re
from typing import Any

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_market as tmk
from backend.app.services.forecasting import _ttl_cache

CONTAINER = {"notice": "Comrc/DTM(C)/2026-27/01", "from": "2026-11-03", "to": "2027-03-31", "low_pct": 35.0, "high_pct": 50.0}
# The container rebate by period (NMPA notices held). feeder/mainline: (rebate %, charges it applies to)
CONTAINER_PERIODS = [
    {"notice": "1/2/2014-DTM (C)/2023-3", "from": "2024-01-01", "to": "2025-12-31",
     "feeder": (25.0, ("berth_hire_rs", "port_dues_rs")), "mainline": (25.0, ("berth_hire_rs", "port_dues_rs", "pilotage_rs")),
     "extra_new_service_pct": 15.0},
    {"notice": "1/2/2014-DTM (C)/2023-4", "from": "2026-01-01", "to": "2026-11-02",
     "feeder": (25.0, ("berth_hire_rs", "port_dues_rs")), "mainline": (25.0, ("berth_hire_rs", "port_dues_rs", "pilotage_rs")),
     "extra_new_service_pct": 15.0},
    {"notice": "Comrc/DTM(C)/2026-27/01", "from": "2026-11-03", "to": "2027-03-31",
     "feeder": (35.0, ("berth_hire_rs", "port_dues_rs", "pilotage_rs")), "mainline": (50.0, ("berth_hire_rs", "port_dues_rs", "pilotage_rs")),
     "extra_new_service_pct": None},
]


def container_period(day: str) -> dict | None:
    return next((x for x in CONTAINER_PERIODS if x["from"] <= day <= x["to"]), None)
CAPESIZE = {"notice": "12/1/2021-22/ATM Gr.I (Com)/JSW", "from": "2025-04-03", "to": "2027-04-02", "pct": 30.0, "min_grt": 80000}
IRON = {"notice": "NMPA/TM/IOF-Exp-Rebate/26-27", "pct": 20.0, "paid_after": "2027-03-31"}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.split(r"\(", (name or "").upper())[0]).strip()


def _dm(s: str, rep: _dt.date) -> _dt.date | None:
    m = re.match(r"\s*(\d{1,2})[/.-](\d{1,2})", s or "")
    if not m:
        return None
    for y in (rep.year, rep.year - 1, rep.year + 1):
        try:
            d = _dt.date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if abs((d - rep).days) <= 60:
            return d
    return None


@_ttl_cache(seconds=600)
def calls_from_reports() -> list[dict]:
    """Every ship call at a berth, from the daily reports."""
    calls: dict[tuple, dict] = {}
    for f in glob.glob(str(tmk.ROOT / "data" / "daily_vessel_position_parsed" / "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        rep = _dt.date.fromisoformat(d["report_date"])
        for b in d.get("berthed", []):
            v = _norm(b.get("vessel_name"))
            if not v or set(v) <= set("-") or v in ("NIL", "VACANT"):
                continue
            bd = _dm(b.get("berthing_date"), rep) or rep
            key = (v, str(b.get("berth_no", "")).strip(), bd)
            c = calls.setdefault(key, {"vessel": v, "berth": key[1], "berthed": bd, "first_report": rep, "last_report": rep,
                                       "run": "", "cargo": "", "receiver_shipper": "", "loa": "", "agent": ""})
            c["first_report"], c["last_report"] = min(c["first_report"], rep), max(c["last_report"], rep)
            for k_src, k_dst in (("run", "run"), ("cargo", "cargo"), ("receiver_shipper", "receiver_shipper"), ("loa", "loa"),
                                 ("agent", "agent")):
                if b.get(k_src) and not c[k_dst]:
                    c[k_dst] = str(b[k_src]).strip()
    out = []
    for c in calls.values():
        c["hours_approx"] = max(24, ((c["last_report"] - c["berthed"]).days + 1) * 24)
        c["month"] = c["berthed"].strftime("%Y-%m")
        out.append({k: (v.isoformat() if isinstance(v, _dt.date) else v) for k, v in c.items()})
    return sorted(out, key=lambda c: (c["berthed"], c["berth"]))


def _price(c: dict, kind: str) -> dict | None:
    """Port dues, pilotage and berth hire for a call, if the ship's GRT is known."""
    from backend.app.services import vessel_charges as vc
    g = vc.grt_for(c["vessel"])
    if not g or not g.get("grt"):
        return None
    coastal = c["run"].upper().startswith("C")
    fx = None
    if not coastal:
        try:
            fx = vc.fx_for(c["berthed"])
        except Exception:
            fx = None
    try:
        cost = vc.call_cost(float(g["grt"]), coastal, kind, float(c["hours_approx"]), fx)
    except Exception:
        return None
    return {**cost, "grt_source": g.get("source"), "grt_confidence": g.get("confidence")}


def settlement_list(month: str | None = None) -> dict[str, Any]:
    calls = calls_from_reports()
    months = sorted({c["month"] for c in calls})
    if not months:
        return {"available": False, "reason": "No daily reports are held."}
    month = month if month in months else months[-1]
    in_month = [c for c in calls if c["month"] == month]
    # container rebate, Berth 14
    cont = []
    for c in in_month:
        per = container_period(c["berthed"])
        if c["berth"].startswith("14") and per and re.search(r"BOX|CONT|TEU", c["cargo"].upper()):
            p = _price(c, "dry")
            feeder = round(sum(p[k] for k in per["feeder"][1]) * per["feeder"][0] / 100) if p else None
            mainline = round(sum(p[k] for k in per["mainline"][1]) * per["mainline"][0] / 100) if p else None
            cont.append({**c, "grt": p["grt"] if p else None, "notice": per["notice"],
                         "rule": (f"{per['feeder'][0]:g}% feeder / {per['mainline'][0]:g}% mainline"
                                  + (f"; +{per['extra_new_service_pct']:g}% if a new international service (not Colombo)"
                                     if per["extra_new_service_pct"] else "")),
                         "rebate_low_rs": min(feeder, mainline) if p else None, "rebate_high_rs": max(feeder, mainline) if p else None,
                         "apply": "Priced from the GRT held" if p else "Apply on the bill (GRT is on the bill)"})
    # Cape-size rebate, Berth 16
    cape = []
    for c in in_month:
        if c["berth"] == "16" and CAPESIZE["from"] <= c["berthed"] <= CAPESIZE["to"]:
            p = _price(c, "dry")
            if p and p["grt"] <= CAPESIZE["min_grt"]:
                status, reb = f"Not eligible: GRT {p['grt']:,.0f} is not above {CAPESIZE['min_grt']:,}", 0
            elif p:
                status, reb = "Eligible", round((p["port_dues_rs"] + p["pilotage_rs"]) * CAPESIZE["pct"] / 100)
            else:
                status, reb = f"Check the GRT on the bill: eligible only above {CAPESIZE['min_grt']:,}", None
            cape.append({**c, "grt": p["grt"] if p else None, "status": status, "rebate_rs": reb})
    # iron ore: builds up over the year
    try:
        m = ie.iron_ore_rebate_monitor()
        iron = {"rate_rs_per_t": m["rate_rs_per_t"], "rebate_per_extra_t_rs": m["rebate_per_extra_t_rs"],
                "months": m["months"], "exporters": m["exporters"], "since_scheme_t": m["since_scheme_t"],
                "since_scheme_prev_t": m["since_scheme_prev_t"]}
    except Exception:
        iron = None
    lbl = lambda mm: _dt.date.fromisoformat(mm + "-01").strftime("%B %Y")
    priced_c = [x for x in cont if x["rebate_low_rs"] is not None]
    return {
        "available": True, "month": month, "month_label": lbl(month), "months": months,
        "latest_report": max(c["last_report"] for c in calls),
        "container": {**CONTAINER, "notice": (" and ".join(sorted({x["notice"] for x in cont}, key=lambda nn: nn.startswith("Comrc")))
                                              if cont else (container_period(month + "-15") or CONTAINER)["notice"]),
                      "calls": cont, "priced": len(priced_c),
                      "rebate_low_rs": sum(x["rebate_low_rs"] for x in priced_c),
                      "rebate_high_rs": sum(x["rebate_high_rs"] for x in priced_c),
                      "rule": ("From 3 Nov 2026 (Comrc/DTM(C)/2026-27/01): 35% (feeder) or 50% (mainline) of berth hire, port dues "
                               "and pilotage. 1 Jan 2024 to 2 Nov 2026 (2023-3, 2023-4): 25% of berth hire and port dues (feeder) or of "
                               "berth hire, port dues and pilotage (mainline), plus 15% for a new international service other than "
                               "Colombo for a year from its first call (the previous port is not in the daily reports: check on the "
                               "bill). Berth 14 container calls; applied at billing.")},
        "capesize": {**CAPESIZE, "calls": cape, "rule": "30% of port dues and pilotage at Berth 16, only for ships above "
                                                        "80,000 GRT; 3 Apr 2025 to 2 Apr 2027."},
        "iron_ore": {**IRON, "monitor": iron, "rule": "20% of wharfage on each exporter's tonnes above its FY 2025-26 quantity; "
                                                      "builds up during FY 2026-27 and is paid after 31 Mar 2027, on verification."},
        "not_listed": ["New export cargo concession (NMPA/TM/SM/2026): identify on the bill by cargo type (not handled at NMPA in "
                       "the preceding 5 years).",
                       "Harit green cargo concession (NMPA/Traffic/Com/Green Policy/01): identify on the bill by the green-fuel "
                       "certificate."],
        "method": ("Calls from NMPA's daily vessel position reports: one ship at one berth, from its berthing date to the last "
                   "report showing it there. Amounts only where the ship's GRT is known; otherwise apply on the bill. Berth hours "
                   "are approximate (whole report days), so amounts are estimates for planning; the bill is the authority."),
        "source": "NMPA daily vessel position reports; NMPA trade notices; NMPA Scale of Rates 2026-27",
    }


def monthly_summary() -> dict[str, Any]:
    """Qualifying calls month by month: container rebate calls at Berth 14 (the notice in force on each date) and calls at
    Berth 16 to check for the Cape-size rebate."""
    calls = calls_from_reports()
    out = {}
    for c in calls:
        m = c["month"]
        row = out.setdefault(m, {"month": m, "container_calls": 0, "capesize_calls": 0})
        if c["berth"].startswith("14") and container_period(c["berthed"]) and re.search(r"BOX|CONT|TEU", c["cargo"].upper()):
            row["container_calls"] += 1
        if c["berth"] == "16" and CAPESIZE["from"] <= c["berthed"] <= CAPESIZE["to"]:
            row["capesize_calls"] += 1
    rows = [out[m] for m in sorted(out)]
    return {"rows": rows, "source": "NMPA daily vessel position reports"}
