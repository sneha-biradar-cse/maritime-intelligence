"""
Official performance - NMPA's own monthly Traffic & Performance figures, and who is behind the delay that is
"other than port account".

Data (real):
  * data/nmpa_performance_monthly.csv  read from nmpa_public_data/operational performance *.pdf by
                                       scripts/parse_nmpa_performance.py (pre-berthing detention split into port
                                       account / other than port account, turn-round time, idle time, output per
                                       berth-day, vessels, tonnes - each for this month, same month last year,
                                       year to date and same period last year).
  * NMPA daily vessel reports (trade_waiting / trade_customers) for the same month: which customers' liquid-bulk
    ships waited because the receiver or shipper was not ready.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services import trade_customers as tcu
from backend.app.services import trade_waiting as tw
from backend.app.services.forecasting import _ttl_cache

ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / "data" / "nmpa_performance_monthly.csv"
CATEGORY_LABEL = {"dry_bulk": "Dry bulk", "break_bulk": "Break bulk", "liquid_bulk": "Liquid bulk",
                  "container": "Container", "overall": "Whole port"}
LIQUID_FAMILIES = {"Crude oil", "Petroleum products (fuels)", "LPG", "Edible oil", "Fuel oil", "Bitumen"}
CHARTER_OUTPUT_NORM_T = 16000   # NMPA Citizen's Charter: average ship berth-day output


def _v(d: pd.DataFrame, metric: str, cat: str, period: str, year: str, basis: str = "") -> float | None:
    x = d[(d["metric"] == metric) & (d["category"] == cat) & (d["period"] == period) & (d["year"] == year)
          & (d["basis"].fillna("") == basis)]
    return None if x.empty or pd.isna(x["value"].iloc[0]) else float(x["value"].iloc[0])


@_ttl_cache(seconds=300)
def get_official_performance() -> dict[str, Any]:
    if not FILE.exists():
        return {"available": False, "note": "Run scripts/parse_nmpa_performance.py after adding Traffic & Performance PDFs."}
    all_ = pd.read_csv(FILE)
    reports = sorted(all_["report_month"].unique())
    month = reports[-1]
    d = all_[all_["report_month"] == month]
    trt_basis = "readiness" if not d[(d["metric"] == "turn_round_time_hrs") & (d["basis"] == "readiness")].empty else "pilot"

    cats = []
    for c, label in CATEGORY_LABEL.items():
        row = {"category": c, "label": label}
        for per in ("month", "ytd"):
            for yr in ("current", "previous"):
                k = f"{per}_{yr}"
                row[f"pbd_port_{k}"] = _v(d, "pre_berthing_detention_days", c, per, yr, "port_account")
                row[f"pbd_other_{k}"] = _v(d, "pre_berthing_detention_days", c, per, yr, "other_than_port_account")
                row[f"pbd_total_{k}"] = _v(d, "pre_berthing_detention_days", c, per, yr, "total")
                row[f"trt_hrs_{k}"] = _v(d, "turn_round_time_hrs", c, per, yr, trt_basis)
                row[f"idle_pct_{k}"] = _v(d, "idle_time_pct", c, per, yr)
                row[f"output_t_{k}"] = _v(d, "output_per_berth_day_t", c, per, yr)
                row[f"vessels_{k}"] = _v(d, "vessels", c, per, yr)
                row[f"tonnes_{k}"] = _v(d, "traffic_t", c, per, yr)
        cats.append(row)

    # Who is behind liquid-bulk delay in the same month (daily vessel reports).
    behind = []
    ev = tw.build_waiting_events()
    if not ev.empty:
        aliases = tcu.load_aliases()
        e = ev[(ev["month"] == month) & ev["family"].isin(LIQUID_FAMILIES)].copy()
        if not e.empty:
            e["customer"] = e["receiver"].map(lambda r: tcu.canonical_customer(r, aliases))
            total_days = float(e["wait"].sum())
            for (cust, bucket), g in e.groupby(["customer", "bucket"]):
                behind.append({"customer": cust, "reason": bucket, "ships": int(len(g)),
                               "ship_days": round(float(g["wait"].sum()), 1),
                               "share_of_liquid_waiting_pct": round(float(g["wait"].sum()) / total_days * 100, 1) if total_days else None,
                               "cargo": ", ".join(sorted(g["family"].unique()))})
            behind.sort(key=lambda r: -r["ship_days"])

    # Monthly trend: each report's own month (not its prior-year column), so every figure is as first reported.
    trend = []
    for rm in reports:
        r = all_[all_["report_month"] == rm]
        tb = "readiness" if not r[(r["metric"] == "turn_round_time_hrs") & (r["basis"] == "readiness")].empty else "pilot"
        trend.append({
            "month": rm,
            "liquid_pbd_port": _v(r, "pre_berthing_detention_days", "liquid_bulk", "month", "current", "port_account"),
            "liquid_pbd_other": _v(r, "pre_berthing_detention_days", "liquid_bulk", "month", "current", "other_than_port_account"),
            "overall_pbd_port": _v(r, "pre_berthing_detention_days", "overall", "month", "current", "port_account"),
            "overall_pbd_other": _v(r, "pre_berthing_detention_days", "overall", "month", "current", "other_than_port_account"),
            "overall_trt_hrs": _v(r, "turn_round_time_hrs", "overall", "month", "current", tb),
            "overall_output_t": _v(r, "output_per_berth_day_t", "overall", "month", "current"),
            "overall_idle_pct": _v(r, "idle_time_pct", "overall", "month", "current"),
            "vessels": _v(r, "vessels", "overall", "month", "current"),
            "traffic_t": _v(r, "traffic_t", "overall", "month", "current"),
        })

    liq = next(c for c in cats if c["category"] == "liquid_bulk")
    allp = next(c for c in cats if c["category"] == "overall")
    mlabel = pd.Timestamp(month + "-01").strftime("%B %Y")
    headline = None
    if liq["pbd_other_month_current"] is not None:
        headline = (f"In {mlabel}, liquid-bulk ships waited {liq['pbd_other_month_current']:.2f} days on average before berthing "
                    f"for reasons outside the port's control, against {liq['pbd_other_month_previous']:.2f} a year earlier; "
                    f"delay on the port's own account was {liq['pbd_port_month_current']:.2f} days")
    return {
        "available": True,
        "month": month, "month_label": mlabel, "reports_held": reports,
        "turn_round_basis": "as per readiness" if trt_basis == "readiness" else "as per pilot boarding",
        "categories": cats,
        "trend": trend,
        "overall": allp,
        "headline": headline,
        "charter_output_norm_t": CHARTER_OUTPUT_NORM_T,
        "liquid_waiting_by_customer": behind[:12],
        "liquid_families": sorted(LIQUID_FAMILIES),
        "source": f"NMPA Traffic & Performance report, {mlabel} (data/nmpa_performance_monthly.csv)",
        "limits": [
            "Official figures are averages over every ship; the customer table counts only ships listed waiting at anchorage "
            "in the daily reports, so the two are related but not the same measure.",
            f"Reports held: {reports[0]} to {reports[-1]} ({len(reports)} months). Add new PDFs to nmpa_public_data/ and rerun "
            "scripts/parse_nmpa_performance.py.",
        ],
    }
