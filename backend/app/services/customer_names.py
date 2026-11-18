"""
Customer name review for NMPA Traffic: the engine's name merges and proposals in one list, biggest cargo first, each with
the evidence an officer needs to say Same / Different / Not sure.

Three kinds of item:
  * spelling   - a spelling seen in the daily reports that the engine counts under another name (data/customer_aliases.csv,
                 inferred from spelling only);
  * identity   - a proposed company identity (rename or merger) with documentary evidence (data/customer_identity_proposals.csv);
  * candidate  - two names the engine thinks may be the same company (initials or one name inside the other), not merged.

Nothing changes in any figure when a decision is recorded. An officer applies the confirmed decisions with apply(); that
writes the alias file (a backup is kept first), and the next figures use it. Decisions are kept in
data/customer_name_decisions.json with who decided and when.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import threading
from typing import Any

import pandas as pd

from backend.app.services import trade_customers as tcu
from backend.app.services import trade_market as tmk

DECISIONS = "data/customer_name_decisions.json"
CHOICES = ("same", "different", "not_sure")
_lock = threading.Lock()


def _dec_path():
    return tmk.ROOT / DECISIONS


def _load_decisions() -> dict[str, dict]:
    f = _dec_path()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def _save_decisions(d: dict) -> None:
    f = _dec_path()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def _initials(name: str) -> str:
    words = [w for w in re.split(r"[^A-Z]+", name.upper()) if w and w not in ("LTD", "LIMITED", "PVT", "PRIVATE", "AND", "OF", "THE", "M", "S")]
    return "".join(w[0] for w in words)


def _evidence(v: pd.DataFrame, name: str) -> dict[str, Any]:
    x = v[v["customer"] == name]
    if x.empty:
        return {"tonnes_12m": 0, "ships": 0, "cargo": "", "months": ""}
    last12 = sorted(v["month"].unique())[-12:]
    y = x[x["month"].isin(last12)]
    return {"tonnes_12m": round(float(y["tonnes"].fillna(0).sum())), "ships": int(x["vessel"].nunique()),
            "cargo": ", ".join(sorted(set(x["family"].dropna().astype(str)))[:3]),
            "months": f"{min(x['month'])} to {max(x['month'])}"}


def review_list() -> dict[str, Any]:
    b = tcu.build()
    v = b["voyages"]
    raw = b.get("raw_by_customer", {})
    dec = _load_decisions()
    items = []
    # 1. spelling merges the engine already applies (customer_aliases.csv), one item per customer with merged spellings
    for cust, spellings in raw.items():
        if cust == tcu.NOT_STATED:
            continue
        others = sorted({s for s in spellings if tcu._key(s) != tcu._key(cust)})
        if others:
            items.append({"id": f"spelling|{cust}", "kind": "spelling", "names": [cust] + others,
                          "question": f"Are these spellings all the same customer, '{cust}'?",
                          "applied_now": True, "evidence": _evidence(v, cust),
                          "basis": "Merged by spelling only (data/customer_aliases.csv)"})
    # 2. identity proposals with documents
    try:
        idp = pd.read_csv(tmk.ROOT / "data" / "customer_identity_proposals.csv", dtype=str).fillna("")
        for r in idp.itertuples():
            labels = [p.strip() for p in r.label_in_daily_reports.split("/") if p.strip()]
            ev = _evidence(v, labels[0]) if labels else {}
            items.append({"id": f"identity|{r.label_in_daily_reports}", "kind": "identity", "names": labels + [r.proposed_identity],
                          "question": f"Is '{r.label_in_daily_reports}' the company {r.proposed_identity}?",
                          "applied_now": r.applied_in_dashboard.strip().lower() == "yes", "evidence": ev, "basis": r.evidence})
    except FileNotFoundError:
        pass
    # 3. candidates: initials or one name inside another, among customers seen in the last 12 months, not already merged
    last12 = sorted(v["month"].unique())[-12:]
    names = sorted({c for c in v.loc[v["month"].isin(last12), "customer"].dropna() if c != tcu.NOT_STATED and " + " not in c})
    for i, a in enumerate(names):
        for bname in names[i + 1:]:
            short, long_ = (a, bname) if len(a) <= len(bname) else (bname, a)
            ks, kl = tcu._key(short), tcu._key(long_)
            ws = [w for w in re.split(r"[^A-Z0-9]+", short.upper()) if w]
            wl = [w for w in re.split(r"[^A-Z0-9]+", long_.upper()) if w]
            whole_words = bool(ws) and len(wl) > len(ws) and wl[:len(ws)] == ws          # 'AGARWAL' + 'AGARWAL COAL', not 'IOCL' in 'KIOCL'
            hit = (len(ks) >= 2 and ks == _initials(long_)) or (len(ks) >= 4 and whole_words)
            if hit:
                items.append({"id": f"candidate|{short}|{long_}", "kind": "candidate", "names": [short, long_],
                              "question": f"Are '{short}' and '{long_}' the same company?", "applied_now": False,
                              "evidence": {**_evidence(v, short), "other": _evidence(v, long_)},
                              "basis": "Found by the engine (initials or one name inside the other); not merged"})
    for it in items:
        it["decision"] = dec.get(it["id"])
    items.sort(key=lambda it: (it["decision"] is not None,
                               -(it["evidence"].get("tonnes_12m", 0) + it["evidence"].get("other", {}).get("tonnes_12m", 0))))
    done = sum(1 for it in items if it["decision"] and it["decision"]["choice"] != "not_sure")
    to_apply = sum(1 for it in items if it["decision"] and not it["decision"].get("applied") and it["decision"]["choice"] != "not_sure"
                   and ((it["kind"] == "spelling" and it["decision"]["choice"] == "different") or
                        (it["kind"] in ("identity", "candidate") and it["decision"]["choice"] == "same")))
    return {"items": items, "total": len(items), "decided": done, "to_apply": to_apply,
            "by_kind": {k: sum(1 for it in items if it["kind"] == k) for k in ("spelling", "identity", "candidate")},
            "rule": ("Recording a decision changes nothing. Confirmed decisions take effect only when an officer presses "
                     "'Apply confirmed decisions'; a backup of the name list is kept first.")}


def decide(item_id: str, choice: str, by: str, note: str = "", keep_name: str = "") -> dict:
    if choice not in CHOICES:
        raise ValueError(f"Choose one of: {', '.join(CHOICES)}")
    ids = {it["id"] for it in review_list()["items"]}
    if item_id not in ids:
        raise KeyError(item_id)
    with _lock:
        d = _load_decisions()
        d[item_id] = {"choice": choice, "by": by, "at": _dt.datetime.now().isoformat(timespec="seconds"),
                      "note": note, "keep_name": keep_name, "applied": False}
        _save_decisions(d)
    return d[item_id]


def apply(by: str) -> dict:
    """Apply confirmed decisions to data/customer_aliases.csv (backup first):
       spelling + different  -> remove the merged spellings, so each spelling counts on its own again;
       identity/candidate + same -> add rows mapping each name to the confirmed name."""
    lst = review_list()
    todo = [it for it in lst["items"] if it["decision"] and not it["decision"].get("applied") and
            ((it["kind"] == "spelling" and it["decision"]["choice"] == "different") or
             (it["kind"] in ("identity", "candidate") and it["decision"]["choice"] == "same"))]
    if not todo:
        return {"applied": 0, "message": "Nothing to apply."}
    f = tcu.ALIAS_FILE
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f.with_name(f"customer_aliases.backup-{stamp}.csv")
    shutil.copy2(f, backup)
    lines = f.read_text(encoding="utf-8").splitlines()
    removed = added = 0
    with _lock:
        dec = _load_decisions()
        for it in todo:
            if it["kind"] == "spelling":
                cust = it["names"][0]
                keys = {tcu._key(n) for n in it["names"][1:]}
                keep = []
                for ln in lines:
                    parts = ln.split(",")
                    if (not ln.startswith("#") and len(parts) >= 2 and parts[1].strip() == cust
                            and tcu._key(parts[0]) in keys):
                        removed += 1
                        continue
                    keep.append(ln)
                lines = keep
            else:
                target = it["decision"].get("keep_name") or it["names"][-1]
                note = f"Confirmed by {it['decision']['by']} on {it['decision']['at'][:10]}"
                for n in it["names"]:
                    if tcu._key(n) != tcu._key(target):
                        lines.append(f"{n},{target},{note}")
                        added += 1
            dec[it["id"]]["applied"] = True
            dec[it["id"]]["applied_by"], dec[it["id"]]["applied_at"] = by, _dt.datetime.now().isoformat(timespec="seconds")
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _save_decisions(dec)
    try:
        tcu.build.cache_clear()
    except AttributeError:
        pass
    return {"applied": len(todo), "spellings_unmerged": removed, "names_merged": added, "backup": backup.name,
            "message": f"Applied {len(todo)} decision(s). Backup of the previous list: {backup.name}."}
