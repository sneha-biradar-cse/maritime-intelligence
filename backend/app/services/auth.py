"""
Logins and roles for actions that change data (pilot mode).

- No users file (data/users.json) -> DEMO MODE: nothing is required, the screen says so, and actions are not attributable.
- Users file present -> PILOT MODE: every action that changes data needs a logged-in user with the right role. The backend
  checks this on every request (hiding a button is not enough), and the audit trail records the logged-in user, not a typed
  name.

Roles: traffic, finance, approver, viewer, admin. Passwords are stored only as salted PBKDF2 hashes.
Users are managed with: python scripts/manage_users.py add|remove|list
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException

ROOT = Path(__file__).resolve().parents[3]
USERS_FILE = ROOT / "data" / "users.json"
ROLES = ("traffic", "finance", "approver", "viewer", "admin")
TOKEN_HOURS = 10
_tokens: dict[str, dict] = {}
_lock = threading.Lock()

# Who may move a scheme INTO each status
STATUS_ROLES = {"Traffic review": {"traffic"}, "Finance review": {"traffic"}, "Draft": {"traffic", "finance"},
                "Rejected": {"traffic", "approver"}, "Approved": {"approver"}, "Active": {"traffic"}, "Completed": {"traffic"}}
ACTION_ROLES = {"finance_upload": {"finance"}, "create_scheme": {"traffic"}, "rebaseline": {"traffic"}, "amend": {"traffic"}, "scheme_note": {"traffic", "finance", "approver"},
                "customer_notes": {"traffic"}, "alert_feedback": {"traffic", "finance"},
                "set_policy": {"approver"}}


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def load_users() -> dict[str, dict]:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pilot_mode() -> bool:
    return bool(load_users())


def add_user(username: str, full_name: str, role: str, password: str) -> None:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    users = load_users()
    salt = secrets.token_hex(16)
    users[username.strip().lower()] = {"full_name": full_name.strip(), "role": role, "salt": salt, "hash": _hash(password, salt)}
    USERS_FILE.parent.mkdir(exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def remove_user(username: str) -> bool:
    users = load_users()
    if users.pop(username.strip().lower(), None) is None:
        return False
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")
    return True


def login(username: str, password: str) -> dict[str, Any]:
    u = load_users().get(username.strip().lower())
    if not u or not secrets.compare_digest(_hash(password, u["salt"]), u["hash"]):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    tok = secrets.token_urlsafe(32)
    with _lock:
        _tokens[tok] = {"username": username.strip().lower(), "full_name": u["full_name"], "role": u["role"],
                        "expires": time.time() + TOKEN_HOURS * 3600}
    return {"token": tok, "username": username.strip().lower(), "full_name": u["full_name"], "role": u["role"]}


def logout(token: str) -> None:
    with _lock:
        _tokens.pop(token, None)


def current_user(authorization: str | None = Header(None)) -> dict | None:
    """FastAPI dependency: the logged-in user, or None in demo mode. In pilot mode a missing or expired login is refused."""
    if not pilot_mode():
        return None
    tok = (authorization or "").removeprefix("Bearer ").strip()
    with _lock:
        u = _tokens.get(tok)
        if u and u["expires"] < time.time():
            _tokens.pop(tok, None)
            u = None
    if not u:
        raise HTTPException(status_code=401, detail="Please log in (pilot mode: actions need a logged-in user)")
    return u


def require(user: dict | None, allowed: set[str], what: str) -> None:
    """In pilot mode, refuse unless the user's role is allowed (admin is not a substitute for a business role)."""
    if user is None:
        return
    if user["role"] not in allowed:
        raise HTTPException(status_code=403, detail=f"Your role ({user['role']}) cannot {what}. Allowed: {', '.join(sorted(allowed))}.")


def actor(user: dict | None, typed: str = "") -> str:
    """Name recorded in audit trails: the logged-in user in pilot mode; the typed name (marked) in demo mode."""
    if user is not None:
        return f"{user['full_name']} ({user['role']})"
    return (typed.strip() + " [demo, not verified]").strip() if typed.strip() else "[demo, not verified]"
