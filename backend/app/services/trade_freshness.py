"""How current each trade data source is (read from the files themselves), and the customer-name list to confirm."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services import trade_customers as tcu
from backend.app.services import trade_intelligence as ti
from backend.app.services.forecasting import _ttl_cache

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"


def _latest_month(path: Path, col: str = "month") -> str | None:
    if not path.exists():
        return None
    d = pd.read_csv(path)
    return str(d[col].max()) if col in d else None


@_ttl_cache(seconds=300)
def get_freshness() -> dict[str, Any]:
    daily = sorted(pd.to_datetime([p.stem for p in (DATA / "daily_vessel_position_parsed").glob("*.json")],
                                  format="%d-%m-%Y", errors="coerce").dropna())
    perf = DATA / "nmpa_performance_monthly.csv"
    sources = {
        "nmpa_commodity_statements": ti._prepared()["latest"].strftime("%Y-%m"),
        "ministry_major_ports": _latest_month(DATA / "major_ports_monthly.csv"),
        "nmpa_container_statements": _latest_month(DATA / "nmpa_container_commodities.csv"),
        "nmpa_traffic_performance": _latest_month(perf, "report_month"),
        "nmpa_daily_reports": daily[-1].strftime("%Y-%m-%d") if daily else None,
    }
    last_run = None
    log = DATA / "last_update.json"
    if log.exists():
        last_run = json.loads(log.read_text()).get("finished")
    return {"sources": sources, "last_update_run": last_run}


def customer_names_csv() -> str:
    """Every spelling seen in the daily reports, the customer it is counted under, and how many ship calls.
    For the NMPA Traffic department to confirm or correct (then edit data/customer_aliases.csv)."""
    b = tcu.build()
    v = b["voyages"]
    rows = (v.groupby(["receiver", "customer"]).size().reset_index(name="ship_calls")
              .rename(columns={"receiver": "written_in_daily_report", "customer": "counted_as"}))
    rows = rows[rows["written_in_daily_report"].str.strip() != ""]
    aliases = pd.read_csv(tcu.ALIAS_FILE, comment="#", dtype=str).fillna("")
    notes = {tcu._key(a): n for a, n in zip(aliases["variant"], aliases["note"]) if n}
    rows["how_merged"] = rows.apply(
        lambda r: "as written" if r["written_in_daily_report"].strip().upper() == r["counted_as"]
        else ("joint entry" if " + " in r["counted_as"] else "spelling merged"), axis=1)
    rows["note"] = rows["written_in_daily_report"].map(lambda x: notes.get(tcu._key(x), ""))
    rows["confirmed_by_nmpa"] = ""
    rows = rows.sort_values(["counted_as", "ship_calls"], ascending=[True, False])
    buf = io.StringIO()
    rows.to_csv(buf, index=False)
    return buf.getvalue()



def get_data_status() -> dict[str, Any]:
    """Status of every dataset (Original obtained / Extraction checked / Reconciled / NMPA-confirmed / Estimated / Unresolved),
    and of the daily reports one by one."""
    reg = pd.read_csv(DATA / "data_status.csv")
    man = pd.read_csv(DATA / "daily_reports_manifest.csv")
    counts = man["status"].value_counts().to_dict()
    return {"datasets": reg.to_dict(orient="records"),
            "daily_reports": {"total": int(len(man)), "by_status": {k: int(v) for k, v in counts.items()},
                              "not_checked": int((man["status"].str.startswith("Original not obtained")).sum())},
            "statuses": ["Original obtained", "Extraction checked", "Reconciled", "NMPA-confirmed", "Estimated", "Unresolved"],
            "claim": ("Verified against the available sources, with unresolved fields marked and excluded from official figures. "
                      "Not a claim of 100% accuracy: a record that matches its PDF proves the reading, not that the publisher's "
                      "figure is final or that two reports use the same definitions.")}
