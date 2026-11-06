"""
Ship Waiting Analyzer - why ships wait at New Mangalore, and who or what causes it.

Data: NMPA Daily Vessel Positions (data/daily_vessel_position_parsed/), sections
"anchorage" and "tankers_scheduled". Only ships that were actually waiting are counted.

Simple rules (nothing is invented):
1. One waiting EVENT = one ship + cargo + date of arrival. If the ship shows up on many daily
   sheets, we keep the LONGEST wait written for it.
2. The reason is the text written by port staff. We only group spellings into three buckets:
   "Receiver / shipper / vessel not ready", "No berth free", "Other / not stated".
   We never guess a reason for a blank row.
3. Waiting days written on the sheet are used as they are.

NOTE: this counts only ships that waited. It is NOT comparable with NMPA's official
"pre-berthing detention", which averages over all ships.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services import trade_split as ts

DAILY_DIR = ts.DAILY_DIR
MIN_EVENTS_FOR_RANKING = 5

CUSTOMER_RE = re.compile(r"(RECEIVER|SHIPPER|VESSEL|CARGO)\s+NOT\s+RE[A]?DY|DOCUMENT|CUSTOM", re.I)
BERTH_RE = re.compile(r"WANT\s+OF\s+BERTH|BERTH\s+(NOT|UNAVAIL)|JETTY\s+OCCUPIED", re.I)
BUCKET_CUSTOMER = "Receiver / shipper / vessel not ready"
BUCKET_BERTH = "No berth free"
BUCKET_OTHER = "Other / not stated"


def _bucket(reason: str) -> str:
    r = re.sub(r"\s+", " ", str(reason or "").upper()).strip()
    if CUSTOMER_RE.search(r):
        return BUCKET_CUSTOMER
    if BERTH_RE.search(r):
        return BUCKET_BERTH
    return BUCKET_OTHER


def _mode(s: pd.Series) -> str:
    s = s[s.fillna("") != ""]
    return str(s.mode().iloc[0]) if len(s) else ""


def build_waiting_events(daily_dir: Path | None = None) -> pd.DataFrame:
    folder = daily_dir or DAILY_DIR
    rows: list[dict] = []
    for path in sorted(folder.glob("*.json")):
        day = json.loads(path.read_text(encoding="utf-8"))
        for sec in ("anchorage", "tankers_scheduled"):
            for r in day.get(sec, []):
                rows.append({**r, "report_date": day["report_date"]})
    if not rows:
        return pd.DataFrame()
    a = pd.DataFrame(rows)
    for col in ("waiting_duration", "reason_or_note", "receiver_shipper", "cargo", "doa", "vessel_name"):
        if col not in a:
            a[col] = ""
    a["report_date"] = pd.to_datetime(a["report_date"])
    a["wait"] = a["waiting_duration"].astype(str).str.extract(r"(\d+(?:\.\d+)?)")[0].astype(float)
    a["vessel"] = a["vessel_name"].map(ts._vessel_norm)
    a["cargo"] = a["cargo"].fillna("").astype(str).map(ts._clean_code)
    a["family"] = [f for f, _ in a["cargo"].map(ts.classify_cargo)]
    a["reason"] = a["reason_or_note"].fillna("").astype(str)
    a["doa"] = a["doa"].fillna("").astype(str)
    a = a[a["vessel"] != ""]
    ev = (a.sort_values("report_date").groupby(["vessel", "cargo", "doa"], dropna=False)
          .agg(first_seen=("report_date", "min"), wait=("wait", "max"),
               reason=("reason", _mode), family=("family", "first"),
               receiver=("receiver_shipper", _mode)).reset_index())
    ev = ev[ev["wait"].notna()].copy()
    ev["bucket"] = ev["reason"].map(_bucket)
    ev["month"] = ev["first_seen"].dt.strftime("%Y-%m")
    return ev


def _partial_months(daily_dir: Path | None, first: pd.Timestamp, last: pd.Timestamp) -> list[str]:
    """First and last month, plus any month with fewer than 15 daily reports (e.g. a gap in the archive)."""
    folder = daily_dir or DAILY_DIR
    dates = []
    for p in folder.glob("*.json"):
        try:
            dates.append(pd.to_datetime(p.stem, format="%d-%m-%Y"))
        except ValueError:
            try:
                dates.append(pd.to_datetime(p.stem))
            except ValueError:
                continue
    per = pd.Series(1, index=pd.DatetimeIndex(dates)).groupby(lambda d: d.strftime("%Y-%m")).sum() if dates else pd.Series(dtype=int)
    out = {first.strftime("%Y-%m"), last.strftime("%Y-%m")} | {m for m, n in per.items() if n < 15}
    return sorted(out)


def _stats(g: pd.DataFrame) -> dict[str, Any]:
    return {"events": int(len(g)), "avg_wait_days": round(float(g["wait"].mean()), 2),
            "ship_days": round(float(g["wait"].sum()), 1)}


def get_waiting_analysis(daily_dir: Path | None = None) -> dict[str, Any]:
    ev = build_waiting_events(daily_dir)
    if ev.empty:
        return {"available": False}
    total_days = float(ev["wait"].sum())
    pct = lambda x: round(float(x) / total_days * 100, 1) if total_days else None

    by_reason = []
    for b, g in ev.groupby("bucket"):
        by_reason.append({"reason": b, **_stats(g), "share_of_waiting_days_pct": pct(g["wait"].sum())})
    by_reason.sort(key=lambda r: -r["ship_days"])

    def rank(col: str, label: str, blank_ok: bool = False):
        out = []
        for k, g in ev.groupby(col):
            if (not blank_ok and k == "") or len(g) < MIN_EVENTS_FOR_RANKING:
                continue
            cust = g[g["bucket"] == BUCKET_CUSTOMER]["wait"].sum()
            out.append({label: k, **_stats(g), "share_of_waiting_days_pct": pct(g["wait"].sum()),
                        "not_ready_share_pct": round(float(cust / g["wait"].sum() * 100), 1) if g["wait"].sum() else None})
        return sorted(out, key=lambda r: -r["ship_days"])

    by_month = [{"month": m, **_stats(g)} for m, g in ev.groupby("month")]
    first, last = ev["first_seen"].min(), ev["first_seen"].max()
    return {
        "available": True,
        "period": {"from": first.strftime("%Y-%m-%d"), "to": last.strftime("%Y-%m-%d")},
        "overall": {**_stats(ev), "median_wait_days": round(float(ev["wait"].median()), 2),
                    "p90_wait_days": round(float(ev["wait"].quantile(0.9)), 2)},
        "by_reason": by_reason,
        "by_cargo": rank("family", "cargo"),
        "by_customer": rank("receiver", "customer"),
        "by_month": by_month,
        "partial_months": _partial_months(daily_dir, first, last),
        "how_it_works": [
            "Counts ships listed at anchorage or waiting for a berth in NMPA's daily vessel reports.",
            "One ship + cargo + arrival date = one waiting event; the longest wait written for it is kept.",
            "Reasons are the words written by port staff, grouped into three buckets. Blank or unclear rows stay in 'Other / not stated'.",
        ],
        "limits": [
            "Only ships that waited are counted, so averages are higher than NMPA's official all-ship pre-berthing detention.",
            "Some rows have no reason, or a quantity written in the reason field. These stay in 'Other / not stated'.",
            "First and last months of the data are partial.",
            "Which side caused the wait is as written by port staff; it is not independently verified.",
        ],
    }
