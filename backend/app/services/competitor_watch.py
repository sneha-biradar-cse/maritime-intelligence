"""Reads the results of scripts/watch_competitor_notices.py for the dashboard: new incentive and tariff notices at
competitor ports (Cochin, VOC Tuticorin, Mormugao), which pages were read, and which could not be."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from backend.app.services.trade_market import ROOT

STORE = ROOT / "data" / "competitor_notices.csv"
STATUS = ROOT / "data" / "competitor_watch_status.json"
SOURCES = ROOT / "data" / "competitor_sources.csv"
RECENT_DAYS = 60


def get_watch(today: pd.Timestamp | None = None) -> dict[str, Any]:
    sources = pd.read_csv(SOURCES).to_dict(orient="records") if SOURCES.exists() else []
    if not STATUS.exists():
        return {"available": False, "sources": sources,
                "how": "Run  python scripts\\watch_competitor_notices.py  (it also runs in scripts\\refresh_all.py)."}
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    d = pd.read_csv(STORE, dtype=str).fillna("") if STORE.exists() else pd.DataFrame(columns=["first_seen", "baseline"])
    today = today or pd.Timestamp.today().normalize()
    if len(d):
        d["first_seen_ts"] = pd.to_datetime(d["first_seen"], errors="coerce")
        new = d[(d["baseline"] == "no") & (d["first_seen_ts"] >= today - pd.Timedelta(days=RECENT_DAYS))]
    else:
        new = d
    cols = ["port", "title", "kind", "date_on_page", "first_seen", "url"]
    return {"available": True, "last_run": status.get("last_run"), "pages": status.get("pages", []), "sources": sources,
            "new": new.sort_values("first_seen", ascending=False)[cols].to_dict(orient="records") if len(new) else [],
            "all": d.sort_values(["port", "first_seen"], ascending=[True, False])[cols].to_dict(orient="records") if len(d) else [],
            "recent_days": RECENT_DAYS, "pages_failed": status.get("pages_failed", 0),
            "source": "Public notice pages of the competitor ports (data/competitor_sources.csv)"}
