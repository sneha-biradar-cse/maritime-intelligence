"""
Rebate claims: each claim followed from submission to payment, ready for audit.

    Submitted  ->  Verified  ->  Approved  ->  Paid
        \\-----------\\-------------\\----> Rejected (with a reason)

Rules
- No double claims: the same scheme, customer and an overlapping period cannot be claimed twice (unless the earlier
  claim was rejected).
- Separation of duties (pilot mode, with logins): the person who verifies a claim is not the one who submitted it, and
  the approver is neither of them. In demo mode names are typed and recorded as "[demo, not verified]".
- Amounts can only go down along the way: verified <= claimed, approved <= verified, paid = approved.
- Budget: a claim cannot be approved if the scheme's approved and paid claims would then exceed the scheme's budget
  (for schemes in the register, whose budget the Board approved). For NMPA notices without a budget held here, a warning.
- Every step records who, when, the amounts and a note. The file stays on this computer (data/incentive_claims.json,
  kept out of GitHub).
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import threading as _threading
from typing import Any

import pandas as pd

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_market as tmk

CLAIMS_FILE = "data/incentive_claims.json"
STATUSES = ["Submitted", "Verified", "Approved", "Paid", "Rejected"]
NEXT = {"Submitted": ["Verified", "Rejected"], "Verified": ["Approved", "Rejected"], "Approved": ["Paid", "Rejected"],
        "Paid": [], "Rejected": []}
ACTION_FOR = {"Verified": "claim_verify", "Approved": "claim_approve", "Paid": "claim_pay", "Rejected": "claim_reject"}
_lock = _threading.Lock()


def _path():
    return tmk.ROOT / CLAIMS_FILE


def _load() -> list[dict]:
    f = _path()
    if not f.exists():
        return []
    try:
        return _json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(rows: list[dict]) -> None:
    f = _path()
    f.parent.mkdir(exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(_json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)                                              # write then swap: a crash never leaves half a file


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def schemes_for_claims() -> list[dict]:
    """Schemes a claim can be made under: NMPA's rebate schemes in force (its notices) and approved or active schemes
    in the register (with their Board-approved budget)."""
    out = []
    n = pd.read_csv(tmk.ROOT / "data" / "nmpa_incentive_notices.csv", dtype=str).fillna("")
    year_ago = (_dt.date.today() - _dt.timedelta(days=365)).isoformat()
    for _, r in n.iterrows():
        recent = r["valid_to"] and r["valid_to"] >= year_ago and not r["status"].startswith(("Reference",))
        if r["status"].startswith("In force") or recent:                 # customers often claim after a scheme ends
            label = "" if r["status"].startswith("In force") else f" (ended {r['valid_to']})"
            out.append({"ref": r["notice"], "name": ((r["type"] or r["benefit"])[:80] + label), "budget_rs": None, "source": "NMPA notice"})
    for s in ie._load_schemes():
        if s.get("status") in ("Approved", "Active", "Completed"):
            out.append({"ref": s["id"], "name": f"{s['scope']} {s['discount_pct']:g}% on {s['cargo']}",
                        "budget_rs": s.get("budget_cap_rs") or None, "source": "Scheme register"})
    return out


def _overlaps(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    return not (a_to < b_from or b_to < a_from)


def _committed(rows: list[dict], ref: str, exclude: str | None = None) -> float:
    """Approved or paid amount already committed under a scheme."""
    return sum(c.get("paid_rs") or c.get("approved_rs") or 0 for c in rows
               if c["scheme_ref"] == ref and c["status"] in ("Approved", "Paid") and c["id"] != exclude)


def submit(scheme_ref: str, customer: str, period_from: str, period_to: str, claimed_tonnes: float, claimed_rs: float,
           by: str, note: str = "") -> dict:
    schemes = {s["ref"]: s for s in schemes_for_claims()}
    if scheme_ref not in schemes:
        raise ValueError(f"Unknown or inactive scheme: {scheme_ref}")
    customer = customer.strip()
    if not customer:
        raise ValueError("Name the customer making the claim.")
    if not (period_from and period_to) or period_to < period_from:
        raise ValueError("The claim period is not valid (the end is before the start).")
    if claimed_tonnes < 0 or claimed_rs <= 0:
        raise ValueError("Claimed tonnes cannot be negative and the amount must be above zero.")
    with _lock:
        rows = _load()
        for c in rows:
            if (c["scheme_ref"] == scheme_ref and c["customer"].lower() == customer.lower() and c["status"] != "Rejected"
                    and _overlaps(period_from, period_to, c["period_from"], c["period_to"])):
                raise ValueError(f"Already claimed: {c['id']} covers {c['period_from']} to {c['period_to']} for this customer "
                                 f"under this scheme ({c['status']}). Reject it first if it was wrong.")
        cid = f"CLM-{len(rows) + 1:03d}"
        rec = {"id": cid, "scheme_ref": scheme_ref, "scheme_name": schemes[scheme_ref]["name"],
               "scheme_budget_rs": schemes[scheme_ref]["budget_rs"], "customer": customer,
               "period_from": period_from, "period_to": period_to, "claimed_tonnes": float(claimed_tonnes),
               "claimed_rs": float(claimed_rs), "verified_tonnes": None, "verified_rs": None, "approved_rs": None,
               "paid_rs": None, "payment_ref": "", "status": "Submitted", "submitted_by": by,
               "history": [{"status": "Submitted", "by": by, "at": _now(), "note": note,
                            "amount_rs": float(claimed_rs)}]}
        rows.append(rec)
        _save(rows)
    return rec


def move(cid: str, to: str, by: str, amount_rs: float | None = None, tonnes: float | None = None,
         payment_ref: str = "", note: str = "", pilot: bool = False) -> dict:
    """Move a claim one step. pilot=True enforces separation of duties on the recorded names."""
    with _lock:
        rows = _load()
        c = next((x for x in rows if x["id"] == cid), None)
        if c is None:
            raise KeyError(cid)
        if to not in NEXT[c["status"]]:
            raise ValueError(f"A {c['status'].lower()} claim cannot go to {to}. Next steps: {', '.join(NEXT[c['status']]) or 'none'}.")
        steps = {h["status"]: h["by"] for h in c["history"]}
        if pilot and to == "Verified" and by == steps.get("Submitted"):
            raise PermissionError("The person who submitted a claim cannot also verify it.")
        if pilot and to == "Approved" and by in (steps.get("Submitted"), steps.get("Verified")):
            raise PermissionError("The approver must be someone other than the person who submitted or verified the claim.")
        warning = ""
        if to == "Verified":
            if amount_rs is None or tonnes is None:
                raise ValueError("Enter the verified tonnes and amount (from NMPA's statements and bills).")
            if amount_rs > c["claimed_rs"] + 0.5:
                raise ValueError("The verified amount cannot be more than the amount claimed.")
            c["verified_tonnes"], c["verified_rs"] = float(tonnes), float(amount_rs)
        elif to == "Approved":
            amount_rs = c["verified_rs"] if amount_rs is None else amount_rs
            if amount_rs > c["verified_rs"] + 0.5:
                raise ValueError("The approved amount cannot be more than the verified amount.")
            budget = c.get("scheme_budget_rs")
            if budget:
                if _committed(rows, c["scheme_ref"], exclude=c["id"]) + amount_rs > budget + 0.5:
                    raise ValueError(f"Approving this would take the scheme over its budget of Rs {budget / 1e7:,.2f} crore.")
            else:
                warning = "No budget is held here for this scheme: check the approved total against the Board's approval."
            c["approved_rs"] = float(amount_rs)
        elif to == "Paid":
            if not payment_ref.strip():
                raise ValueError("Enter the payment or credit note reference.")
            c["paid_rs"], c["payment_ref"] = float(c["approved_rs"]), payment_ref.strip()
        elif to == "Rejected":
            if not note.strip():
                raise ValueError("Give the reason for rejecting the claim.")
        c["status"] = to
        c["history"].append({"status": to, "by": by, "at": _now(), "note": note, "amount_rs": amount_rs,
                             "tonnes": tonnes, "payment_ref": payment_ref or None})
        _save(rows)
    return {**c, "warning": warning}


def get_claims() -> dict[str, Any]:
    rows = _load()
    by_scheme = {}
    for c in rows:
        s = by_scheme.setdefault(c["scheme_ref"], {"scheme_ref": c["scheme_ref"], "scheme_name": c["scheme_name"],
                                                    "budget_rs": c.get("scheme_budget_rs"), "claims": 0, "claimed_rs": 0.0,
                                                    "approved_rs": 0.0, "paid_rs": 0.0})
        s["claims"] += 1
        s["claimed_rs"] += c["claimed_rs"] if c["status"] != "Rejected" else 0
        s["approved_rs"] += (c.get("approved_rs") or 0) if c["status"] in ("Approved", "Paid") else 0
        s["paid_rs"] += c.get("paid_rs") or 0
    for s in by_scheme.values():
        s["budget_left_rs"] = (s["budget_rs"] - s["approved_rs"]) if s["budget_rs"] else None
    count = {st: sum(1 for c in rows if c["status"] == st) for st in STATUSES}
    return {"claims": sorted(rows, key=lambda c: c["id"], reverse=True), "by_scheme": list(by_scheme.values()),
            "count": count, "waiting": count["Submitted"] + count["Verified"] + count["Approved"],
            "schemes": schemes_for_claims(), "next": NEXT,
            "rules": ("No double claims for the same scheme, customer and period; amounts can only go down (verified <= "
                      "claimed, approved <= verified, paid = approved); the person who submits cannot verify or approve; "
                      "approval is refused if it would take a register scheme over its Board-approved budget.")}
