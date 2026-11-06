"""
Responses to Action-list items - so the port team can mark a signal as known, record why, and stop seeing it at the top.

Stored in data/alert_feedback.json:  {"<item key>": {"status": "...", "note": "...", "by": "...", "at": "ISO time"}}
Item keys are stable across days: "cargo|<COMMODITY>|<direction>" or "customer|<CUSTOMER>".
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / "data" / "alert_feedback.json"
STATUSES = ("Open", "Looking into it", "Explained", "Not relevant")
_lock = threading.Lock()


def _load() -> dict[str, Any]:
    if not FILE.exists():
        return {}
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get_feedback() -> dict[str, Any]:
    return {"statuses": list(STATUSES), "items": _load()}


def set_feedback(key: str, status: str, note: str = "", by: str = "") -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    key = key.strip()[:200]
    if not key:
        raise ValueError("key is required")
    with _lock:
        data = _load()
        if status == "Open" and not note.strip():
            data.pop(key, None)                      # back to the default: nothing to keep
        else:
            data[key] = {"status": status, "note": note.strip()[:500], "by": by.strip()[:80],
                         "at": datetime.now().isoformat(timespec="minutes")}
        FILE.parent.mkdir(exist_ok=True)
        FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"key": key, **data.get(key, {"status": "Open"})}


# ── Customer notes: account owner, follow-up date and a running notes history per customer ──
NOTES_FILE = ROOT / "data" / "customer_notes.json"


def _load_notes() -> dict[str, Any]:
    if not NOTES_FILE.exists():
        return {}
    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get_customer_notes() -> dict[str, Any]:
    data = _load_notes()
    today = datetime.now().date().isoformat()
    due = sorted([{"customer": c, "follow_up": v["follow_up"], "owner": v.get("owner", "")}
                  for c, v in data.items() if v.get("follow_up") and v["follow_up"] <= today], key=lambda x: x["follow_up"])
    return {"customers": data, "follow_ups_due": due, "stages": list(OPPORTUNITY_STAGES), "actions": list(ACTIONS)}


OPPORTUNITY_STAGES = ("Statistical gap (from the figures only)", "Confirmed by Traffic with the customer",
                      "Committed by agreement")
ACTIONS = ("Commercial follow-up with the customer", "Documentation or process improvement",
           "Receiver / shipper readiness coordination", "Equipment or evacuation coordination",
           "Tariff incentive (only where approved by NMPA)", "No action: monitor")


def update_customer_notes(customer: str, owner: str | None = None, follow_up: str | None = None,
                          note: str = "", by: str = "", stage: str | None = None, reason: str | None = None,
                          action: str | None = None) -> dict[str, Any]:
    customer = customer.strip().upper()[:120]
    if not customer:
        raise ValueError("customer is required")
    if follow_up:
        datetime.strptime(follow_up, "%Y-%m-%d")          # raises ValueError if not a date
    with _lock:
        data = _load_notes()
        rec = data.setdefault(customer, {"owner": "", "follow_up": "", "notes": []})
        if stage is not None:
            if stage and stage not in OPPORTUNITY_STAGES:
                raise ValueError(f"stage must be one of {OPPORTUNITY_STAGES}")
            rec["stage"] = stage
        if reason is not None:
            rec["reason"] = reason.strip()[:300]
        if action is not None:
            if action and action not in ACTIONS:
                raise ValueError(f"action must be one of {ACTIONS}")
            rec["action"] = action
        if owner is not None:
            rec["owner"] = owner.strip()[:80]
        if follow_up is not None:
            rec["follow_up"] = follow_up
        if note.strip():
            rec["notes"].insert(0, {"at": datetime.now().isoformat(timespec="minutes"), "by": by.strip()[:80], "text": note.strip()[:1000]})
        NOTES_FILE.parent.mkdir(exist_ok=True)
        NOTES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"customer": customer, **data[customer]}
