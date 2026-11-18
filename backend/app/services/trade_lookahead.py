"""
Next 7 days - ships due at New Mangalore, where they will berth, and who is waiting now.

Data (real): the latest NMPA Daily Vessel Positions report (data/daily_vessel_position_parsed/):
  * VESSELS EXPECTED   ship, ETA, cargo, quantity, receiver/shipper, preferred berth
  * BERTHED            which ship is on which berth, cargo still to handle, expected departure (ETD)
  * ANCHORAGE / TANKERS SCHEDULED   ships waiting now, how long, and the reason written by port staff
Earlier reports are used for two checks: how close listed ETAs were to actual arrival, and how long ships of
each cargo usually stay at berth.

Berth outlook (an estimate, stated as such): ships are taken in ETA order; each goes to the preferred berth
that frees up first. A berth frees at the berthed ship's ETD, or, for a ship this outlook has just placed
there, at its arrival plus the usual stay for its cargo. If no preferred berth is free at the ETA, the ship
is shown as likely to wait.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import trade_customers as tcu
from backend.app.services import trade_split as ts
from backend.app.services.forecasting import _ttl_cache

HORIZON_DAYS = 7
LIKELY_WAIT_DAYS = 0.5
DEFAULT_STAY_DAYS = 2.0


def _day(text: Any, ref: pd.Timestamp) -> pd.Timestamp | None:
    """'27/10' or '27/10/2026' -> date, choosing the year closest to the report date."""
    m = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", str(text or ""))
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= d <= 31 and 1 <= mo <= 12):
        return None
    if m.group(3):
        y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        return pd.Timestamp(y, mo, d) if d <= pd.Timestamp(y, mo, 1).days_in_month else None
    best = None
    for y in (ref.year - 1, ref.year, ref.year + 1):
        try:
            t = pd.Timestamp(y, mo, d)
        except ValueError:
            continue
        if best is None or abs((t - ref).days) < abs((best - ref).days):
            best = t
    return best


def _hour(text: Any) -> float:
    m = re.search(r"(\d{1,2}):(\d{2})", str(text or ""))
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    s = str(text or "").upper()
    return 9.0 if "AM" in s else 15.0 if "PM" in s else 12.0


def _berths(text: Any) -> list[str]:
    """'12 / 13', '10/11/SPM', '14W', '14(W )', '13/12/9' -> ['12','13'] etc."""
    s = str(text or "").upper().replace("(", "").replace(")", "").replace(" ", "")
    out = []
    for tok in re.split(r"[/,&]", s):
        tok = tok.replace("B.", "").replace("B", "") if tok.startswith("B") else tok
        if tok == "SPM":
            out.append(tok)
            continue
        m = re.match(r"^(\d{1,2}[EW]?)", tok)          # '12P' (preferred) -> '12', '14W' stays '14W'
        if m:
            out.append(m.group(1))
    return out


def _berth_key(b: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(b).upper())


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _reports(folder: Path) -> list[tuple[pd.Timestamp, Path]]:
    out = []
    for p in folder.glob("*.json"):
        try:
            out.append((pd.to_datetime(p.stem, format="%d-%m-%Y"), p))
        except ValueError:
            continue
    return sorted(out)


def _usual_stay_days(folder: Path) -> dict[str, float]:
    """Median days a ship of each cargo group stays at berth (days it appears in the berthed list)."""
    v = ts.build_voyages(folder)
    if v.empty:
        return {}
    stay = (v["last_seen"] - v["first_seen"]).dt.days + 1
    return stay.groupby(v["family"]).median().clip(lower=1).to_dict()


def _eta_reliability(reports: list[tuple[pd.Timestamp, Path]], lookback_days: int = 90) -> dict | None:
    """For ships in the 'expected' list, compare the listed ETA with the first report they appear as arrived."""
    if len(reports) < 10:
        return None
    latest = reports[-1][0]
    seen_days: dict[str, list[pd.Timestamp]] = {}
    for d, p in reports:
        x = _load(p)
        names = {ts._vessel_norm(r.get("vessel_name")) for sec in ("berthed", "anchorage", "tankers_scheduled")
                 for r in x.get(sec, [])}
        for n in names:
            if n and not re.fullmatch(r"-+|NIL", n):
                seen_days.setdefault(n, []).append(d)
    deltas = []
    for d, p in reports:
        if d < latest - pd.Timedelta(days=lookback_days) or d > latest - pd.Timedelta(days=10):
            continue
        for r in _load(p).get("expected", []):
            n = ts._vessel_norm(r.get("vessel_name"))
            eta = _day(r.get("eta_date"), d)
            if not n or eta is None or n not in seen_days:
                continue
            after = [s for s in seen_days[n] if s >= d]
            if after and (min(after) - eta).days <= 20:
                deltas.append((min(after) - eta).days)
    if len(deltas) < 20:
        return None
    a = np.array(deltas)
    return {"ships_checked": int(len(a)), "within_1_day_pct": round(float((np.abs(a) <= 1).mean() * 100), 1),
            "later_than_eta_pct": round(float((a > 1).mean() * 100), 1),
            "median_days_late": float(np.median(a)), "lookback_days": lookback_days}


@_ttl_cache(seconds=300)
def get_lookahead(daily_dir: Path | None = None) -> dict[str, Any]:
    folder = daily_dir or ts.DAILY_DIR
    reps = _reports(folder)
    if not reps:
        return {"available": False}
    ref, path = reps[-1]
    rep = _load(path)
    aliases = tcu.load_aliases()
    cust = lambda r: tcu.canonical_customer(r, aliases)
    stay = _usual_stay_days(folder)

    # Berths now: who is on them and when they leave.
    berth_free: dict[str, pd.Timestamp] = {}
    on_berth: dict[str, str] = {}
    for r in rep.get("berthed", []):
        b = _berth_key(r.get("berth_no"))
        name = ts._vessel_norm(r.get("vessel_name"))
        if not b:
            continue
        if not name or re.fullmatch(r"-+", name):
            berth_free.setdefault(b, ref)
            continue
        etd = _day(r.get("etd"), ref)
        berth_free[b] = max(etd + pd.Timedelta(hours=12), ref) if etd is not None else ref + pd.Timedelta(days=1)
        on_berth[b] = name

    # Ships due.
    due = []
    for r in rep.get("expected", []):
        name = ts._vessel_norm(r.get("vessel_name"))
        eta = _day(r.get("eta_date"), ref)
        if not name or eta is None:
            continue
        eta = eta + pd.Timedelta(hours=_hour(r.get("eta_time")))
        if eta > ref + pd.Timedelta(days=HORIZON_DAYS):
            continue
        cargo = ts._clean_code(str(r.get("cargo") or ""))
        if not cargo or ts.NON_CARGO.search(cargo) or re.search(r"CONVERSION|SLOP|BUNKER|REPAIR|CREW", cargo):
            continue                                   # not a cargo call
        fam, direction = ts.classify_cargo(cargo)
        boxes = bool(re.search(r"BOX|CONTAIN", cargo))
        qty = None if boxes else ts._qty(r.get("qty"))
        due.append({"vessel": name, "eta": eta, "cargo": cargo, "cargo_group": fam, "direction": direction,
                    "tonnes": qty, "boxes": str(r.get("qty") or "") if boxes else "", "customer": cust(r.get("receiver_shipper")),
                    "run": str(r.get("run") or "").strip(), "preferred_berths": _berths(r.get("berth_prefer")),
                    "preferred_berth_text": str(r.get("berth_prefer") or "").strip()})
    due.sort(key=lambda x: x["eta"])

    # Berth outlook (greedy, in ETA order).
    for s in due:
        cands = [_berth_key(b) for b in s["preferred_berths"]]
        if not cands:
            s.update({"berth_outlook": "No preferred berth given", "likely_wait_days": None, "berth": None})
            continue
        best = min(cands, key=lambda b: berth_free.get(b, ref))
        free_at = berth_free.get(best, ref)
        wait = max(0.0, (free_at - s["eta"]).total_seconds() / 86400)
        start = max(free_at, s["eta"])
        berth_free[best] = start + pd.Timedelta(days=float(stay.get(s["cargo_group"], DEFAULT_STAY_DAYS)))
        occupant = on_berth.get(best)
        s["berth"] = best
        s["likely_wait_days"] = round(wait, 1)
        if wait >= LIKELY_WAIT_DAYS:
            who = f"{occupant} until about {free_at.strftime('%d %b')}" if occupant else "ships due before it"
            s["berth_outlook"] = f"Likely to wait about {wait:.1f} days: berth {best} is taken by {who}"
        else:
            s["berth_outlook"] = f"Berth {best} should be free"
        on_berth[best] = s["vessel"]

    # Waiting now.
    waiting = []
    for sec in ("anchorage", "tankers_scheduled"):
        for r in rep.get(sec, []):
            name = ts._vessel_norm(r.get("vessel_name"))
            if not name or name in ("NIL",) or re.fullmatch(r"-+", name):
                continue
            days = ts._qty(r.get("waiting_duration"))
            days = None if days is None or pd.isna(days) else float(days)
            reason = str(r.get("reason_or_note") or "").strip()
            waiting.append({"vessel": re.sub(r"\s+B\.[\w/ ]+$", "", name), "cargo": ts._clean_code(str(r.get("cargo") or "")),
                            "customer": cust(r.get("receiver_shipper")), "days_waiting": days,
                            "reason": reason, "customer_not_ready": bool(re.search(r"NOT READY|LAY ?CAN", reason.upper())),
                            "tonnes": ts._qty(r.get("qty"))})
    waiting.sort(key=lambda x: -(x["days_waiting"] or 0))

    # What needs attention (short list).
    attention = []
    for s in [x for x in due if (x["likely_wait_days"] or 0) >= LIKELY_WAIT_DAYS][:3]:
        attention.append({"kind": "Berth", "text": f"{s['vessel']} ({s['cargo_group'].lower()}, {s['customer']}), due "
                                                    f"{s['eta'].strftime('%a %d %b')}: {s['berth_outlook'][0].lower()}{s['berth_outlook'][1:]}."})
    for w in [x for x in waiting if (x["days_waiting"] or 0) >= 2][:3]:
        attention.append({"kind": "Waiting", "text": f"{w['vessel']} ({w['customer']}) has waited {w['days_waiting']:.1f} days: "
                                                      f"{w['reason'].lower() or 'no reason written'}."})
    waiting_customers = {w["customer"] for w in waiting if w["customer_not_ready"]}
    for c in sorted({s["customer"] for s in due} & waiting_customers):
        n = sum(1 for s in due if s["customer"] == c)
        attention.append({"kind": "Customer", "text": f"{c} has {n} more ship{'s' if n > 1 else ''} due this week while one "
                                                       "of its ships is already waiting because it is not ready."})

    days = pd.date_range(ref.normalize(), periods=HORIZON_DAYS + 1, freq="D")
    by_day = []
    for d in days:
        g = [s for s in due if s["eta"].normalize() == d]
        groups: dict[str, float] = {}
        for s in g:
            if s["tonnes"]:
                groups[s["cargo_group"]] = groups.get(s["cargo_group"], 0) + s["tonnes"]
        by_day.append({"day": d.strftime("%Y-%m-%d"), "ships": len(g), "tonnes_by_group": groups})

    out_due = [{**s, "eta": s["eta"].strftime("%Y-%m-%d %H:%M")} for s in due]
    return {
        "available": True,
        "report_date": ref.strftime("%Y-%m-%d"),
        "report_age_days": int((pd.Timestamp.today().normalize() - ref).days),
        "horizon_days": HORIZON_DAYS,
        "totals": {"ships_due": len(due), "tonnes_due": round(sum(s["tonnes"] or 0 for s in due)),
                   "ships_waiting": len(waiting), "waiting_customer_not_ready": sum(1 for w in waiting if w["customer_not_ready"]),
                   "likely_to_wait": sum(1 for s in due if (s["likely_wait_days"] or 0) >= LIKELY_WAIT_DAYS)},
        "attention": attention[:6],
        "due": out_due,
        "by_day": by_day,
        "waiting_now": waiting,
        "eta_reliability": _eta_reliability(reps),
        "source": f"NMPA Daily Vessel Positions, {ref.strftime('%d %B %Y')}",
        "limits": [
            "Berth outlook is an estimate: it uses the listed ETA, the berthed ship's ETD and the usual stay for each cargo. "
            "The Traffic department's actual berthing plan can differ.",
            "Containers are counted as ships, not tonnes.",
        ],
    }
