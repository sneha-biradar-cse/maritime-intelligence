"""
Baseline KPIs for the Incentive Engine (asked for by MIF): what is measured, its current value, the source, and whether it is
measured from data held or pending data only NMPA can provide. Values are computed live; nothing is entered by hand.
"""
from __future__ import annotations

import subprocess
from typing import Any

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_customers as tc
from backend.app.services import trade_target as tt
from backend.app.services.forecasting import _ttl_cache

VESSEL_RATE_STRINGS: list[str] = []   # vessel-related charges are calculated in the Cargo Forecasting module


@_ttl_cache(seconds=3600)
def _sor_text() -> str:
    """Text of the tariff PDF: Poppler's pdftotext if installed, otherwise pdfplumber (pure Python, works on Windows)."""
    f = str(ie.tmk.ROOT / ie.SOR_FILE)
    try:
        out = subprocess.run(["pdftotext", "-layout", f, "-"], capture_output=True, text=True).stdout
        if out.strip():
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    import pdfplumber
    with pdfplumber.open(f) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _tariff_check() -> tuple[int, int]:
    txt = _sor_text()
    found = sum(1 for s in VESSEL_RATE_STRINGS if s in txt)
    keys = {c["rate"] for c in ie.CARGO.values()} | {c["berth_rate"] for c in ie.CARGO.values() if c.get("berth_rate")}
    for k in keys:
        r = ie._rate(k)
        found += int(f"{r['foreign']:.2f}" in txt and f"{r['coastal']:.2f}" in txt)
    return found, len(VESSEL_RATE_STRINGS) + len(keys)


@_ttl_cache(seconds=300)
def get_module_kpis() -> dict[str, Any]:
    try:
        found, total = _tariff_check()
        tariff_value, tariff_status = f"{found} of {total}", "Measured"
    except Exception as e:                    # never fail the whole page because the PDF could not be read here
        tariff_value, tariff_status = f"Not checked on this computer ({type(e).__name__})", "Pending NMPA data"
    acc = ie.get_accounts_check()
    within = [r for r in acc["rows"] if r["difference_pct_vs_2023_24"] is not None and abs(r["difference_pct_vs_2023_24"]) <= 15]
    worst = max(acc["rows"], key=lambda r: abs(r["difference_pct_vs_2023_24"] or 0))
    rev = ie.get_revenue()
    target = tt.get_target_tracker()
    cov = tc.get_customer_watch()["coverage_vs_official"]
    import pandas as pd
    man = pd.read_csv(ie.tmk.ROOT / "data" / "daily_reports_manifest.csv")
    opp = ie.get_opportunities()
    losing = [o for o in opp["cargos"] if o.get("tonnes_not_won")]
    at_stake = sum(o.get("wharfage_at_stake_rs") or 0 for o in opp["cargos"])
    schemes = ie._load_schemes()
    by_status = {}
    for s in schemes:
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
    rows = [
        {"area": "Accuracy", "kpi": "Tariff rates used, found in NMPA's Scale of Rates PDF", "value": tariff_value,
         "status": tariff_status, "source": "NMPA Scale of Rates (checked automatically on every run)"},
        {"area": "Accuracy", "kpi": "Wharfage rate used vs income per tonne in NMPA's accounts (2023-24)",
         "value": f"{len(within)} of {len(acc['rows'])} cargos within 15% (largest gap: {worst['cargo']}, {worst['difference_pct_vs_2023_24']:+.0f}%)",
         "status": "Measured", "source": "NMPA budget document; NMPA monthly statements"},
        {"area": "Accuracy", "kpi": "Estimated wharfage vs wharfage actually billed, by cargo", "value": "Not yet measured",
         "status": "Pending NMPA data", "source": "Needs NMPA Finance billing totals by cargo"},
        {"area": "Coverage", "kpi": "Cargo priced in the wharfage estimate (this financial year)",
         "value": f"{rev['total']['tonnes'] / 1e6:.1f} MMT of {target['done_tonnes'] / 1e6:.1f} MMT ({rev['total']['tonnes'] / target['done_tonnes'] * 100:.0f}%)",
         "status": "Measured", "source": "Rest: PPP berths (royalty), own arrangements (KIOCL, Adani Power), mixed-rate cargo groups"},
        {"area": "Coverage", "kpi": "Official tonnes traced to a named customer (daily reports)", "value": f"{cov['named_customer_pct']:.0f}%",
         "status": "Measured", "source": "NMPA daily reports vs NMPA monthly statements, 13 months"},
        {"area": "Coverage", "kpi": "Daily-report days with the original PDF held",
         "value": f"{int((man.status != 'Original not obtained (record not checked)').sum())} of {len(man)}",
         "status": "Measured", "source": "data/daily_reports_manifest.csv"},
        {"area": "Insight", "kpi": "Cargos losing market share (to investigate before any incentive)",
         "value": f"{len(losing)}: " + ", ".join(o["cargo"] for o in losing), "status": "Measured",
         "source": "Ministry of Ports monthly reports; NMPA statements"},
        {"area": "Insight", "kpi": "Wharfage at stake in cargo not won (statistical gap, not a forecast)", "value": ie_cr(at_stake),
         "status": "Estimated", "source": "Last year's share x this year's all-port volume, priced at the tariff"},
        {"area": "Process", "kpi": "Schemes in the register, by status",
         "value": ", ".join(f"{k}: {v}" for k, v in by_status.items()) or "None yet", "status": "Measured",
         "source": "data/incentive_schemes.json"},
        {"area": "Process", "kpi": "Time to prepare a draft proposal for one customer", "value": "Not yet measured",
         "status": "Pending NMPA data", "source": "Needs the time NMPA's Traffic team takes today (baseline from the nodal officer)"},
    ]
    return {"available": True, "rows": rows,
            "note": ("Baseline KPIs for the Incentive Engine. 'Measured' values are computed from the documents held each time the "
                     "page loads; 'Pending NMPA data' rows need data only NMPA can provide; 'Estimated' rows rest on stated assumptions. "
                     "Projected benefits are not shown as achieved benefits.")}


def ie_cr(v: float) -> str:
    return f"Rs {v / 1e7:,.2f} cr" if abs(v) >= 1e6 else f"Rs {v / 1e5:,.1f} lakh"
