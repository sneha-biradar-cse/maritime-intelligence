"""
Container lines and services - which container operators call at New Mangalore, how often, and who is new or has stopped.

Data (real): NMPA Daily Vessel Positions (data/daily_vessel_position_parsed/), container ships (cargo 'BOXES'),
from both the berthed list and the 'vessels expected' list. Container ships often berth and sail between two daily
reports, so the expected list (ship, ETA, agent, boxes planned) is needed to see every call.
The report names the shipping agent of each ship; for container ships the agent represents the line or service
(e.g. MSC, CMA / ML). Boxes = import + export boxes handled, from the quantity columns ('574(I)+300(E)').
One call = one ship's visit (a gap of more than 20 days between sightings starts a new call).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services import trade_split as ts
from backend.app.services.forecasting import _ttl_cache

NEW_DAYS = 90       # first call within this many days of the latest report = new service
STOPPED_DAYS = 60   # no call for this long, after calling regularly = stopped


def _agent(a: Any) -> str:
    s = re.sub(r"\s*/\s*", " / ", str(a or "").upper()).strip(" /")
    return s or "Not stated"


def _boxes(text: Any) -> int:
    return sum(int(x) for x in re.findall(r"(\d+)\s*\(", str(text or "")))


def _calls(folder: Path) -> pd.DataFrame:
    rows = []
    for p in folder.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        day = pd.Timestamp(d["report_date"])
        for r in d.get("berthed", []):
            if not re.search(r"BOX|CONTAIN", str(r.get("cargo") or "").upper()):
                continue
            name = ts._vessel_norm(r.get("vessel_name"))
            if not name:
                continue
            rows.append({"day": day, "vessel": name, "agent": _agent(r.get("agent")), "run": str(r.get("run") or "").strip().upper(),
                         "boxes": _boxes(r.get("qty_total")) + _boxes(r.get("qty_balance"))})
        for r in d.get("expected", []):
            if not re.search(r"BOX|CONTAIN", str(r.get("cargo") or "").upper()):
                continue
            name = ts._vessel_norm(r.get("vessel_name"))
            if not name:
                continue
            from backend.app.services.trade_lookahead import _day
            eta = _day(r.get("eta_date"), day)
            if eta is None or abs((eta - day).days) > 10:
                eta = day
            rows.append({"day": eta, "vessel": name, "agent": _agent(r.get("agent")), "run": str(r.get("run") or "").strip().upper(),
                         "boxes": _boxes(r.get("qty"))})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("day")
    gap = df.groupby("vessel")["day"].diff().dt.days.fillna(999)
    df["call"] = (gap > 20).astype(int).groupby(df["vessel"]).cumsum()
    first = lambda s: s.mode().iloc[0] if not s.mode().empty else ""
    return (df.groupby(["vessel", "call"]).agg(first_seen=("day", "min"), last_seen=("day", "max"), agent=("agent", first),
                                               run=("run", first), boxes=("boxes", "max")).reset_index())


@_ttl_cache(seconds=300)
def get_container_lines(daily_dir: Path | None = None) -> dict[str, Any]:
    folder = daily_dir or ts.DAILY_DIR
    c = _calls(folder)
    if c.empty:
        return {"available": False}
    latest = max(pd.Timestamp(json.loads(p.read_text(encoding="utf-8"))["report_date"]) for p in folder.glob("*.json"))
    upcoming = c[c["first_seen"] > latest]
    c = c[c["first_seen"] <= latest].copy()
    c["last_seen"] = c["last_seen"].clip(upper=latest)      # an ETA after the latest report is not a call yet
    c["month"] = c["last_seen"].dt.strftime("%Y-%m")
    months = sorted(c["month"].unique())
    complete = [m for m in months if pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0) < latest]
    recent, prev = complete[-3:], complete[-6:-3]
    rows = []
    for agent, g in c.groupby("agent"):
        first, last = g["first_seen"].min(), g["last_seen"].max()
        r_c, p_c = int(g["month"].isin(recent).sum()), int(g["month"].isin(prev).sum())
        active_months = g["month"].nunique()
        # The daily reports see only about a third of container calls (ships often berth and sail between two
        # reports), so counts are not compared month to month; only who calls, and who is new or no longer seen.
        if (latest - first).days <= NEW_DAYS:
            status = "New"
        elif (latest - last).days >= STOPPED_DAYS:
            status = "Not seen for 60+ days"
        else:
            status = "Calling"
        flagged = g[g["run"].isin(["F", "C"])]
        rows.append({"line_or_agent": agent, "calls": int(len(g)), "recent_calls": r_c, "previous_calls": p_c,
                     "vessels": sorted(g["vessel"].unique()), "vessel_count": int(g["vessel"].nunique()),
                     "boxes": int(g["boxes"].sum()), "coastal_share_pct": round(float((flagged["run"] == "C").mean() * 100)) if len(flagged) else None,
                     "first_call": first.strftime("%Y-%m-%d"), "last_call": last.strftime("%Y-%m-%d"),
                     "days_since_last_call": int((latest - last).days), "status": status})
    rows.sort(key=lambda r: (-r["calls"], r["line_or_agent"]))
    monthly = (c.groupby(["month", "agent"]).size().unstack(fill_value=0))
    lab = lambda ms: f"{pd.Timestamp(ms[0] + '-01'):%b %Y} to {pd.Timestamp(ms[-1] + '-01'):%b %Y}" if ms else ""
    # Check against NMPA's official count of container vessels (Traffic & Performance reports), where held.
    check = []
    perf = Path(__file__).resolve().parents[3] / "data" / "nmpa_performance_monthly.csv"
    if perf.exists():
        pf = pd.read_csv(perf)
        off = pf[(pf.metric == "vessels") & (pf.category == "container") & (pf.period == "month") & (pf.year == "current")]
        off = off.set_index("report_month")["value"]
        per_month = c.groupby("month").size()
        for m in complete:
            if m in off.index and pd.notna(off[m]) and off[m] > 0:
                check.append({"month": m, "official_container_vessels": int(off[m]), "traced_calls": int(per_month.get(m, 0)),
                              "traced_pct": round(per_month.get(m, 0) / off[m] * 100)})
    return {"available": True, "latest_report": latest.strftime("%Y-%m-%d"), "total_calls": int(len(c)),
            "expected_calls": [{"vessel": r.vessel, "agent": r.agent, "eta": r.first_seen.strftime("%Y-%m-%d")} for r in upcoming.itertuples()],
            "check_against_official": check,
            "recent_label": lab(recent), "previous_label": lab(prev),
            "recent_calls": int(c["month"].isin(recent).sum()), "previous_calls": int(c["month"].isin(prev).sum()),
            "lines": rows, "monthly_calls": [{"month": m, **{k: int(v) for k, v in monthly.loc[m].items()}} for m in monthly.index],
            "source": "NMPA daily vessel positions (container ships; agent as written)",
            "official_monthly": [{"month": x["month"], "container_vessels": x["official_container_vessels"]} for x in check],
            "limits": ["The daily reports capture only about a third of container calls (see the check against NMPA's official "
                       "count), so this list shows which lines and agents call, not how many calls each makes.",
                       "The daily report names the shipping agent; for most container services this identifies the line, "
                       "but one agent can represent more than one line.",
                       "Boxes are as written in the daily report (import + export), not official TEU."]}
