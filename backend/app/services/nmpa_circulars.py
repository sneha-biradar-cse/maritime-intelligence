"""
NMPA circulars and trade notices: NMPA's own updates (rules, procedures, tariffs, schemes, weather, statistics), each sorted
by category with the part of the platform it affects and a suggested next step for the officer.

Two ways in:
  * an officer adds a circular (title, date, link) - works today;
  * the weekly refresh reads NMPA's circulars page (scripts/watch_nmpa_circulars.py) - only after NMPA's permission for
    automated reading is recorded here (NMPA's website asks programs not to read it automatically).

Nothing acts on a circular by itself: the list shows what to look at; officers decide and mark each one done.
Stored on this computer (data/nmpa_circulars.json, data/automated_access.json), never uploaded to GitHub.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import threading
from typing import Any

from backend.app.services import trade_market as tmk

STORE = "data/nmpa_circulars.json"
ACCESS = "data/automated_access.json"
_lock = threading.Lock()

# (category, words, affects, suggested next step) - first match wins
CATEGORIES = [
    ("Incentive or concession", r"\b(rebate|incentive|concession|discount|waiver|waive|reduction|harit|green)\b",
     "Incentive Engine", "If it is a new or changed scheme, add it to the scheme register and the notices list."),
    ("Tariff or charges", r"\b(tariff|scale of rates|sor|charges|dues|indexation|rates|fee|fees)\b",
     "Tariff calculator", "Check that the tariff calculator uses the Scale of Rates version this notice sets."),
    ("Weather and safety", r"\b(weather|cyclone|monsoon|signal|advisory|warning|storm|rough sea|safety)\b",
     "Anomaly detection", "Treat delays in this window as weather-related, not as anomalies."),
    ("Rules and procedures", r"\b(procedure|guideline|guidelines|rules|regulation|sop|policy|berthing|priority|norms|"
                             r"instruction|circular|compliance|documentation|pilotage)\b",
     "Ship intelligence and operations", "Check whether berthing, stay or documentation rules change for any cargo."),
    ("Traffic and statistics", r"\b(traffic|statistics|commodity|performance|cargo handled|throughput)\b",
     "Trade intelligence", "Check that the new figures were picked up by the weekly refresh."),
    ("Tenders and land", r"\b(tender|eoi|expression of interest|auction|lease|allotment|plot|bid|rfp|rfq)\b",
     "-", "For information."),
]


def classify(title: str) -> dict[str, str]:
    t = (title or "").lower()
    for cat, words, affects, step in CATEGORIES:
        if re.search(words, t):
            return {"category": cat, "affects": affects, "next_step": step}
    return {"category": "Other", "affects": "-", "next_step": "For information."}


def _p(name: str):
    return tmk.ROOT / name


def _load(name: str, default):
    f = _p(name)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default
    except (OSError, ValueError):
        return default


def _save(name: str, data) -> None:
    f = _p(name)
    f.parent.mkdir(exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def permission() -> dict:
    """NMPA's permission for automated reading of its website, as recorded by an officer (none until recorded)."""
    a = _load(ACCESS, {})
    return {"granted": bool(a.get("nmpa_granted")), "by": a.get("nmpa_recorded_by", ""), "on": a.get("nmpa_recorded_on", ""),
            "reference": a.get("nmpa_reference", "")}


def record_permission(granted: bool, by: str, reference: str) -> dict:
    if granted and not reference.strip():
        raise ValueError("Give the reference of NMPA's permission (for example the email's date and sender).")
    a = _load(ACCESS, {})
    a.update({"nmpa_granted": bool(granted), "nmpa_recorded_by": by, "nmpa_recorded_on": _now(), "nmpa_reference": reference.strip()})
    _save(ACCESS, a)
    return permission()


def add(title: str, date: str, url: str, by: str, note: str = "", category: str | None = None, source: str = "officer") -> dict:
    title = " ".join((title or "").split())
    if len(title) < 8:
        raise ValueError("Give the circular's title as NMPA wrote it.")
    if url and not re.match(r"^https?://", url.strip()):
        raise ValueError("The link should start with http:// or https://")
    with _lock:
        rows = _load(STORE, [])
        for r in rows:
            if (url and r.get("url") == url.strip()) or (r["title"].lower() == title.lower() and r.get("date") == date):
                raise ValueError(f"Already listed: {r['id']} ({r['title'][:60]}).")
        c = classify(title)
        if category and category != c["category"]:
            match = next((x for x in CATEGORIES if x[0] == category), None)
            if match:
                c = {"category": match[0], "affects": match[2], "next_step": match[3]}
        rec = {"id": f"NC-{len(rows) + 1:03d}", "title": title, "date": date or "", "url": (url or "").strip(), **c,
               "status": "Open", "added_by": by, "added_on": _now(), "source": source, "note": note, "done_by": "", "done_on": ""}
        rows.append(rec)
        _save(STORE, rows)
    return rec


def mark_done(cid: str, by: str, note: str = "") -> dict:
    with _lock:
        rows = _load(STORE, [])
        r = next((x for x in rows if x["id"] == cid), None)
        if r is None:
            raise KeyError(cid)
        r.update({"status": "Done", "done_by": by, "done_on": _now(), "note": (r.get("note", "") + " " + note).strip()})
        _save(STORE, rows)
    return r


def get_circulars() -> dict[str, Any]:
    rows = sorted(_load(STORE, []), key=lambda r: (r["status"] != "Open", r.get("date") or "", r["id"]), reverse=False)
    open_ = [r for r in rows if r["status"] == "Open"]
    return {"rows": rows, "open": len(open_),
            "open_by_category": {c[0]: sum(1 for r in open_ if r["category"] == c[0]) for c in CATEGORIES + [("Other",)]},
            "categories": [c[0] for c in CATEGORIES] + ["Other"], "permission": permission(),
            "rule": ("Nothing acts on a circular by itself: each one shows what part of the platform it affects and a suggested "
                     "next step; an officer decides and marks it done. Automatic reading of NMPA's circulars page starts only "
                     "after NMPA's permission is recorded.")}
