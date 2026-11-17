"""
Real past vessel calls at NMPA, priced with the SOR 2026-27.

Source: NMPA's Daily Vessel Position reports (one PDF per day, parsed to
data/daily_vessel_position_parsed/*.json) plus the linked berth stays in
data/vessel_stays.json (see vessel_stay_duration.py).

For each call (vessel + berthing date) we take, straight from the reports:
    berth, cargo as written ("IOF(D)"), discharge / load marker,
    run (C = coastal, F = foreign-going), LOA, agent, receiver / shipper,
    manifest quantity = cumulative handled + balance on the last report
    that shows both, and the berth hours from the linked stay.

What the reports do NOT contain is the vessel's GRT, so vessel related
charges (port dues, pilotage, berth hire) are never estimated here; the
calculator asks for GRT from the vessel's tonnage certificate.

Nothing in this module invents a value: a field that is missing in the
reports stays None and is reported as missing.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.services.sor_wharfage import calculate_commodity_wharfage, match_commodity
from backend.app.services.vessel_entity_resolution import normalize_vessel_name

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
ARCHIVE_DIR = DATA_DIR / "daily_vessel_position_parsed"
STAYS_PATH = DATA_DIR / "vessel_stays.json"
TRAFFIC_PATH = DATA_DIR / "nmpa_commodity_traffic_2024_2026.csv"

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_FLOW_RE = re.compile(r"\(\s*([DL])\s*\)", re.IGNORECASE)
_BOX_RE = re.compile(r"(\d+)\s*\(\s*([IE])\s*\)", re.IGNORECASE)


def _num(value: Optional[str]) -> Optional[float]:
    text = (value or "").replace(",", "").strip()
    return float(text) if _NUM_RE.match(text) else None


def _full_date(partial: str, report_date: date) -> Optional[date]:
    """'DD/MM' or 'DD/MM(DD/MM)' -> date, using the report date for the year."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})", partial or "")
    if not m:
        return None
    day_n, month_n = int(m.group(1)), int(m.group(2))
    year = report_date.year
    if month_n - report_date.month > 6:
        year -= 1
    elif report_date.month - month_n > 6:
        year += 1
    try:
        return date(year, month_n, day_n)
    except ValueError:
        return None


def _run_status(run: str) -> Dict[str, Any]:
    """'C' coastal, 'F' foreign, 'C(A)/F(D)' arrived coastal / departs foreign."""
    r = (run or "").upper().replace(" ", "")
    if r in ("C", ")C"):
        return {"vessel_trade_type": "coastal", "status_changed": False}
    if r in ("F", "F(A)"):
        return {"vessel_trade_type": "foreign", "status_changed": False}
    if r.startswith("C(A)/F") or r == "F/C":
        return {"vessel_trade_type": "coastal", "status_changed": True}
    return {"vessel_trade_type": None, "status_changed": False}


def _cargo_flow(cargo: str) -> Optional[str]:
    marks = {m.upper() for m in _FLOW_RE.findall(cargo or "")}
    if marks == {"D"}:
        return "discharge"
    if marks == {"L"}:
        return "load"
    if marks == {"D", "L"}:
        return "discharge_and_load"
    return None


def _berth_vessel_type(sor_code: Optional[str], match_method: str) -> str:
    """Berth-hire class from the cargo line (SOR 2.3.1 items 1-10)."""
    if match_method == "container":
        return "container"
    if not sor_code:
        return "other"
    if sor_code.startswith("A."):
        return "liquid"
    if sor_code.startswith("B."):
        return "dry_bulk"
    return "general_cargo"


@lru_cache(maxsize=1)
def _stays_index() -> Dict[tuple, Dict[str, Any]]:
    if not STAYS_PATH.exists():
        return {}
    index: Dict[tuple, Dict[str, Any]] = {}
    for stay in json.loads(STAYS_PATH.read_text()):
        key = (stay["vessel_norm"], stay["berthing_date"])
        # keep the stay with the strongest confidence for this call
        rank = {"exact": 0, "date_only": 1, "unconfirmed_lower_bound": 2}
        if key not in index or rank[stay["confidence"]] < rank[index[key]["confidence"]]:
            index[key] = stay
    return index


@lru_cache(maxsize=1)
def build_calls() -> List[Dict[str, Any]]:
    """Every berthed call in the archive, with real fields only."""

    calls: Dict[tuple, Dict[str, Any]] = {}

    for path in sorted(ARCHIVE_DIR.glob("*.json")):
        day = json.loads(path.read_text())
        report_date = date.fromisoformat(day["report_date"])

        for row in day.get("berthed", []):
            name = (row.get("vessel_name") or "").strip()
            if name in ("", "----"):
                continue
            berthing = _full_date(row.get("berthing_date", ""), report_date)
            if berthing is None:
                continue
            vessel = normalize_vessel_name(name)
            key = (vessel, berthing.isoformat())
            call = calls.setdefault(key, {
                "vessel": vessel,
                "vessel_raw": name,
                "berthing_date": berthing.isoformat(),
                "berth": None,
                "cargo_raw": None,
                "run_raw": None,
                "loa_m": None,
                "agent": None,
                "receiver_shipper": None,
                "first_report": report_date.isoformat(),
                "last_report": report_date.isoformat(),
                "_qty": [],
                "_boxes": [],
            })
            call["last_report"] = max(call["last_report"], report_date.isoformat())
            for field, src in (("berth", "berth_no"), ("cargo_raw", "cargo"), ("run_raw", "run"),
                               ("agent", "agent"), ("receiver_shipper", "receiver_shipper")):
                if (row.get(src) or "").strip():
                    call[field] = row[src].strip()
            loa = _num(row.get("loa"))
            if loa:
                call["loa_m"] = loa

            total, balance = _num(row.get("qty_total")), _num(row.get("qty_balance"))
            if total is not None or balance is not None:
                call["_qty"].append((report_date.isoformat(), total, balance))

            boxes = _BOX_RE.findall(row.get("qty_total") or "")
            if boxes:
                call["_boxes"].append((report_date.isoformat(), boxes))

    stays = _stays_index()
    out: List[Dict[str, Any]] = []

    for (vessel, berthing), call in calls.items():
        qty = None
        qty_basis = None
        if call["_qty"]:
            # manifest = handled so far + balance, on the last report that has both
            both = [(d, t, b) for d, t, b in call["_qty"] if t is not None and b is not None]
            if both:
                d, t, b = max(both)
                qty, qty_basis = t + b, f"handled {t:,.0f} + balance {b:,.0f} on {d}"
            else:
                handled = [(d, t) for d, t, _ in call["_qty"] if t is not None]
                if handled:
                    d, t = max(handled)
                    qty, qty_basis = t, f"handled to date {t:,.0f} on {d} (no balance shown)"
                else:
                    d, _, b = max(call["_qty"])
                    qty, qty_basis = b, f"balance {b:,.0f} on {d} (handled not shown)"

        boxes = None
        if call["_boxes"]:
            d, parts = max(call["_boxes"])
            boxes = {"import": 0, "export": 0}
            for n, side in parts:
                boxes["import" if side.upper() == "I" else "export"] += int(n)

        match = match_commodity(call["cargo_raw"] or "")
        stay = stays.get((vessel, berthing))
        run = _run_status(call["run_raw"])

        record = {
            "id": f"{berthing}|{vessel}",
            "vessel": vessel,
            "vessel_raw": call["vessel_raw"],
            "berthing_date": berthing,
            "berth": call["berth"],
            "cargo_raw": call["cargo_raw"],
            "cargo_flow": _cargo_flow(call["cargo_raw"] or ""),
            "run_raw": call["run_raw"],
            **run,
            "loa_m": call["loa_m"],
            "agent": call["agent"],
            "receiver_shipper": call["receiver_shipper"],
            "quantity": qty,
            "quantity_basis": qty_basis,
            "container_boxes": boxes,
            "sor_match": {k: match.get(k) for k in ("code", "item", "method", "needs_review", "ambiguity")},
            "berth_hours": stay["duration_hours"] if stay else None,
            "berth_hours_confidence": stay["confidence"] if stay else None,
            "stay_start": stay["start_datetime"] if stay else None,
            "stay_end": stay["end_datetime"] if stay else None,
            "first_report": call["first_report"],
            "last_report": call["last_report"],
            "vessel_grt": None,  # not in NMPA's reports — must come from the tonnage certificate
        }
        record["berth_vessel_type"] = _berth_vessel_type(match.get("code"), match.get("method"))
        out.append(record)

    out.sort(key=lambda r: (r["berthing_date"], r["vessel"]), reverse=True)
    return out


def calculator_inputs(call: Dict[str, Any]) -> Dict[str, Any]:
    """Map a real call onto /cost/calculate inputs. GRT stays empty."""
    vtt = call["vessel_trade_type"]
    flow = call["cargo_flow"]
    if vtt == "coastal":
        cargo_flow = "coastal"
    elif flow == "load":
        cargo_flow = "export"
    else:
        cargo_flow = "import"
    return {
        "cargo_type": call["cargo_raw"] or "",
        "cargo_quantity_mt": call["quantity"],
        "trade_type": "coastal" if vtt == "coastal" else "foreign",
        "vessel_trade_type": vtt or "foreign",
        "cargo_flow": cargo_flow,
        "vessel_type": call["berth_vessel_type"],
        "vessel_grt": None,
        "berth": call["berth"],
        "berth_hours": call["berth_hours"],
        "receiver_shipper": call["receiver_shipper"],
    }


def price_call_wharfage(call: Dict[str, Any]) -> Dict[str, Any]:
    """Wharfage for a past call at SOR 2026-27 rates (GRT-free part only)."""
    m = call["sor_match"]
    if not m.get("code") or not call["quantity"] or call["vessel_trade_type"] is None:
        return {"status": "not_priced", "amount": None}
    code = "A.I.j" if m["code"] == "A.I.d" and (call["berth"] or "").upper().startswith("SPM") else m["code"]
    trade = "coastal" if call["vessel_trade_type"] == "coastal" else "foreign"
    w = calculate_commodity_wharfage(call["cargo_raw"], call["quantity"], trade, sor_code=code)
    return {"status": w["status"], "sor_code": code, "trade_type": trade,
            "rate": w.get("rate_per_unit"), "amount": w.get("amount")}


# ------------------------------------------------------------
# Reconciliation against NMPA's official monthly traffic statement
# ------------------------------------------------------------

def traffic_group(sor_code: Optional[str], method: str) -> Optional[str]:
    """Commodity heading used in NMPA's monthly commodity-wise traffic statement."""
    if method == "container":
        return "CONTAINER (JSW)"
    if not sor_code:
        return None
    if sor_code in ("A.I.d", "A.I.j"):
        return "TOTAL CRUDE"
    if sor_code.startswith("A.I."):
        return "POL PRODUCTS"
    if sor_code.startswith("A.IV"):
        return "TOTAL LPG"
    if sor_code.startswith("A.V"):
        return "EDIBLE OIL"
    if sor_code.startswith(("A.II", "A.III")):
        return "CHEMICALS & OTHER LIQUIDS"
    if sor_code in ("B.III.i", "B.III.j"):
        return "IRON ORE"
    if sor_code.startswith("B.IV"):
        return "TOTAL COAL"
    if sor_code == "B.II.a":
        return "FERTILIZER"
    if sor_code == "B.II.b":
        return "F.R.M. (DRY)"
    if sor_code in ("B.V.a", "B.V.b", "B.V.c"):
        return "TOTAL CEMENT"
    return "OTHER CARGO"


_OFFICIAL_ALIASES = {
    "OTH. LIQ. CARGOES": "CHEMICALS & OTHER LIQUIDS",
    "OTH.LIQ.CARGOES": "CHEMICALS & OTHER LIQUIDS",
    "PETROCHEMICALS": "CHEMICALS & OTHER LIQUIDS",
    "CRUDE - ISPRL": "TOTAL CRUDE",
    "FOOD GRAINS": "OTHER CARGO",
}


def reconcile_with_traffic_statement() -> Dict[str, Any]:
    """
    Compare tonnage summed from individual real calls (by month the vessel
    berthed) with NMPA's published monthly commodity-wise traffic, for
    the months both sources cover. This shows how complete the per-call
    quantities are before they are used for any revenue figure.
    """
    import pandas as pd

    calls = build_calls()
    rows = []
    for c in calls:
        if not c["quantity"] or c["cargo_flow"] not in ("discharge", "load"):
            continue
        grp = traffic_group(c["sor_match"]["code"], c["sor_match"]["method"])
        if grp is None or grp == "CONTAINER (JSW)":
            continue
        rows.append({
            "month": c["berthing_date"][:7],
            "section": "UNLOADED" if c["cargo_flow"] == "discharge" else "LOADED",
            "group": grp,
            "tonnes": c["quantity"],
        })
    calls_df = pd.DataFrame(rows)

    t = pd.read_csv(TRAFFIC_PATH)
    t["month_num"] = pd.to_datetime(t["month"], format="%B").dt.month
    t["month"] = t["year"].astype(str) + "-" + t["month_num"].map("{:02d}".format)
    t["group"] = t["commodity"].map(lambda c: _OFFICIAL_ALIASES.get(c, c))
    t = t[t["group"] != "CONTAINER (JSW)"]
    official = t.groupby(["month", "section", "group"], as_index=False)["traffic_tonnes_current"].sum()

    # full months only: at least 20 daily reports in the archive
    counts = defaultdict(int)
    for d in ARCHIVE_DIR.glob("*.json"):
        dd, mm, yyyy = d.stem.split("-")
        counts[f"{yyyy}-{mm}"] += 1
    months = sorted(m for m, n in counts.items() if n >= 20 and m in set(official["month"]))

    cdf = calls_df[calls_df["month"].isin(months)].groupby(["month", "section", "group"], as_index=False)["tonnes"].sum()
    odf = official[official["month"].isin(months)]
    merged = odf.merge(cdf, on=["month", "section", "group"], how="outer").fillna(0)
    merged = merged.rename(columns={"traffic_tonnes_current": "official_tonnes", "tonnes": "calls_tonnes"})

    by_group = merged.groupby(["section", "group"], as_index=False)[["official_tonnes", "calls_tonnes"]].sum()
    by_group["coverage_pct"] = (by_group["calls_tonnes"] / by_group["official_tonnes"].where(by_group["official_tonnes"] > 0) * 100).round(1)
    by_group = by_group[(by_group["official_tonnes"] > 0) | (by_group["calls_tonnes"] > 0)]
    by_group = by_group.sort_values("official_tonnes", ascending=False)
    by_group = by_group.astype(object).where(by_group.notna(), None)

    tot_o = float(merged["official_tonnes"].sum())
    tot_c = float(merged["calls_tonnes"].sum())
    return {
        "months_compared": months,
        "daily_reports_per_month": {m: counts[m] for m in months},
        "official_total_tonnes": round(tot_o),
        "calls_total_tonnes": round(tot_c),
        "coverage_pct": round(tot_c / tot_o * 100, 1) if tot_o else None,
        "by_group": by_group.to_dict(orient="records"),
        "note": (
            "Calls are dated by berthing day, the statement by month of handling, so a call "
            "that spans a month end lands in the earlier month. Crude via SPM is in both "
            "sources only when the SPM tanker appears in the berthed list."
        ),
    }


def calls_summary() -> Dict[str, Any]:
    calls = build_calls()
    cargo_calls = [c for c in calls if c["sor_match"]["method"] not in ("non_cargo",) and c["cargo_raw"]]
    priced = [c for c in cargo_calls if c["quantity"] and c["sor_match"]["code"]]
    return {
        "total_calls": len(calls),
        "cargo_calls": len(cargo_calls),
        "with_quantity_and_sor_line": len(priced),
        "with_berth_hours": sum(1 for c in calls if c["berth_hours"] is not None),
        "berth_hours_exact": sum(1 for c in calls if c["berth_hours_confidence"] == "exact"),
        "first_berthing": min(c["berthing_date"] for c in calls) if calls else None,
        "last_berthing": max(c["berthing_date"] for c in calls) if calls else None,
        "grt_available": 0,
    }
