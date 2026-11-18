"""
Vessel Intelligence — conformed data layer ("silver/gold").

Turns NMPA's Daily Vessel Position (DVP) archive
(data/daily_vessel_position_parsed/*.json, one file per published day)
into three tables:

    report_calendar  one row per calendar day: published? which sections?
    observations     one row per vessel row per report (berthed / anchorage /
                     tankers_scheduled / expected), fields normalised
    port_calls       one row per PORT CALL = one vessel's visit, stitched
                     from expected → anchorage → berth(s) → sailed

Why a port call (not a berth stay) is the unit
----------------------------------------------
NMPA's own KPIs (monthly Operational Performance report) are per vessel
call: pre-berthing detention = arrival → first berthing, turn-round time
= arrival → departure. A ship that shifts berth is still one call.
The call key is (vessel, arrival date) — arrival date is printed in both
the anchorage list ("DOA") and the berthed list ("arrival date"), and it
stays constant across shifts.

How rows are stitched (all tolerances live in the reference JSON)
-----------------------------------------------------------------
1. Arrival clusters: every anchorage / tankers / berthed row carries an
   arrival date. Rows of the same vessel whose arrival dates are within
   1 day and that are seen within 15 days of each other form one call.
2. Expected episodes: consecutive appearances in "Vessels Expected"
   (gaps ≤ 6 days) form one expectation. Its FIRST declared ETA is kept
   (as-of correct — that is what the planner knew at the time) and is
   matched to the earliest arrival in [first seen − 2 d, ETA + 20 d].
3. Movements (exact HH:MM berths / shifts / sails events, repeated across
   several reports) are de-duplicated and attached to the call whose
   date window contains them.

Precision is reported, never hidden: every derived time carries
'exact' (from an HH:MM stamp), 'half_day' (AM/PM), or 'date' (calendar
date only, taken as 12:00), and every call carries the flags that
explain how it was built.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services import vi_reference as ref

ARCHIVE_DIR = ref.DATA_DIR / "daily_vessel_position_parsed"
DERIVED_DIR = ref.DATA_DIR / "derived"

SECTIONS = ("berthed", "anchorage", "tankers_scheduled", "expected")
MIDDAY = time(12, 0)


# ──────────────────────────────────────────────────────────────────────
# Archive loading
# ──────────────────────────────────────────────────────────────────────

_FP_CACHE: Dict[str, Any] = {"at": -1e9, "fp": (0, 0.0)}
FP_TTL_SECONDS = 30.0


def archive_fingerprint() -> Tuple[int, float]:
    """(file count, newest mtime) of the parsed archive — the cache key for
    every derived table. Re-scanned at most every FP_TTL_SECONDS so that a
    daily update is picked up without restarting the API."""
    import time as _t
    now = _t.monotonic()
    if now - _FP_CACHE["at"] > FP_TTL_SECONDS:
        count, newest = 0, 0.0
        if ARCHIVE_DIR.exists():
            import os
            with os.scandir(ARCHIVE_DIR) as it:
                for e in it:
                    if e.name.endswith(".json"):
                        count += 1
                        newest = max(newest, e.stat().st_mtime)
        _FP_CACHE.update(at=now, fp=(count, newest))
    return _FP_CACHE["fp"]


@dataclass
class Archive:
    reports: Dict[date, Dict[str, Any]]
    first: Optional[date]
    last: Optional[date]

    @property
    def dates(self) -> List[date]:
        return sorted(self.reports)


@lru_cache(maxsize=2)
def _load_archive(fp: Tuple[int, float]) -> Archive:
    reports: Dict[date, Dict[str, Any]] = {}
    for path in ARCHIVE_DIR.glob("*.json"):
        try:
            day = json.loads(path.read_text(encoding="utf-8"))
            reports[date.fromisoformat(day["report_date"])] = day
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    ds = sorted(reports)
    return Archive(reports=reports, first=ds[0] if ds else None, last=ds[-1] if ds else None)


def load_archive() -> Archive:
    return _load_archive(archive_fingerprint())


def report_calendar(archive: Archive) -> List[Dict[str, Any]]:
    if not archive.first:
        return []
    out = []
    d = archive.first
    while d <= archive.last:
        rep = archive.reports.get(d)
        out.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "published": rep is not None,
            "rows": {s: len(rep.get(s, [])) for s in SECTIONS} if rep else None,
            "movements": len(rep.get("movements", [])) if rep else None,
            "unparsed_rows": len(rep.get("unparsed_rows", [])) if rep else None,
        })
        d += timedelta(days=1)
    return out


def coverage(archive: Archive, since: Optional[date] = None, until: Optional[date] = None) -> Dict[str, Any]:
    if not archive.first:
        return {"calendar_days": 0, "published_days": 0, "coverage_pct": 0.0}
    a = max(since or archive.first, archive.first)
    b = min(until or archive.last, archive.last)
    total = (b - a).days + 1 if b >= a else 0
    pub = sum(1 for d in archive.reports if a <= d <= b)
    non_sun = sum(1 for i in range(total) if (a + timedelta(days=i)).weekday() != 6)
    pub_non_sun = sum(1 for d in archive.reports if a <= d <= b and d.weekday() != 6)
    return {
        "from": a.isoformat(), "to": b.isoformat(),
        "calendar_days": total, "published_days": pub,
        "coverage_pct": round(100 * pub / total, 1) if total else 0.0,
        "coverage_excl_sundays_pct": round(100 * pub_non_sun / non_sun, 1) if non_sun else 0.0,
    }


# ──────────────────────────────────────────────────────────────────────
# Observations (one row per vessel row per report)
# ──────────────────────────────────────────────────────────────────────

def _clean(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _observation(section: str, row: Dict[str, Any], rd: date, carried_berth: Optional[str]) -> Optional[Dict[str, Any]]:
    raw_name = _clean(row.get("vessel_name"))
    if raw_name in ("", "----", "-"):
        return None
    vessel = ref.vessel_key(raw_name)
    if ref.is_header_echo(vessel) or len(vessel) < 2:
        return None

    cargo = _clean(row.get("cargo")).upper()
    berth = None
    if section == "berthed":
        berth = ref.normalize_berth(row.get("berth_no")) or carried_berth
    elif section == "tankers_scheduled":
        berth = ref.normalize_berth(row.get("berth_no"))

    obs: Dict[str, Any] = {
        "report_date": rd,
        "section": section,
        "vessel": vessel,
        "vessel_raw": raw_name,
        "cargo": cargo or None,
        "run": _clean(row.get("run")).upper() or None,
        "loa_m": ref._float(row.get("loa")),
        "agent": _clean(row.get("agent")) or None,
        "receiver": _clean(row.get("receiver_shipper")) or None,
        "berth": berth,
    }

    if section == "berthed":
        obs.update({
            "arrival_date": ref.full_date(row.get("arrival_date"), rd),
            "berthing_date": ref.full_date(row.get("berthing_date"), rd),
            "qty_day": ref.parse_qty(row.get("qty_day")),
            "qty_total": ref.parse_qty(row.get("qty_total")),
            "qty_balance": ref.parse_qty(row.get("qty_balance")),
            "boxes_total": ref.parse_boxes(row.get("qty_total")),
            "boxes_day": ref.parse_boxes(row.get("qty_day")),
            "etd_date": ref.full_date(row.get("etd"), rd),
        })
    elif section in ("anchorage", "tankers_scheduled"):
        t, prec = ref.parse_clock(row.get("clock_time"))
        reason = ref.classify_reason(row.get("reason_or_note"))
        qty_text = row.get("qty")
        obs.update({
            "arrival_date": ref.full_date(row.get("doa"), rd),
            "arrival_time": t, "arrival_time_precision": prec,
            "nmpa_wait_days": ref.parse_wait_days(row.get("waiting_duration")),
            "reason_raw": reason["raw"] or None,
            "reason": reason["reason"],
            "account": reason["account"],
            "wob_target": ref.want_of_berth_target(row.get("reason_or_note")),
            "qty": ref.parse_qty(qty_text),
            "boxes": ref.parse_boxes(qty_text),
        })
    elif section == "expected":
        eta_d = ref.full_date(row.get("eta_date"), rd)
        t, prec = ref.parse_clock(row.get("eta_time"))
        obs.update({
            "eta_date": eta_d, "eta_time": t, "eta_precision": prec if eta_d else None,
            "draft_m": ref._float(row.get("draft")),
            "qty": ref.parse_qty(row.get("qty")),
            "boxes": ref.parse_boxes(row.get("qty")),
            "berth_prefs": ref.berth_preferences(row.get("berth_prefer")),
            "berth_prefer_raw": _clean(row.get("berth_prefer")) or None,
        })
    cls = ref.classify_cargo(cargo, berth)
    obs["cargo_class"] = cls["cargo_class"]
    obs["sor_code"] = cls["sor_code"]
    obs["flow"] = cls["flow"]
    return obs


def observations_for_report(rd: date, rep: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for section in SECTIONS:
        carried = None
        for row in rep.get(section, []):
            if section == "berthed":
                b = ref.normalize_berth(row.get("berth_no"))
                if b:
                    carried = b
            o = _observation(section, row, rd, carried)
            if o:
                out.append(o)
    return out


def movements_for_report(rd: date, rep: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Movement lines of one report. NMPA prints two kinds:
      - 'movement'              = the berthing PROGRAMME drawn up at the morning
                                  operations meeting (berths / shifts / sails planned
                                  from ~report time onwards, often 1-3 days ahead)
      - 'post_operation_change' = changes that actually happened after the
                                  previous meeting (re-berthings, unplanned sailings)."""
    out = []
    for m in rep.get("movements", []):
        vessel = ref.vessel_key(m.get("vessel_name"))
        if not vessel:
            continue
        try:
            d = date.fromisoformat(m["date"])
        except (KeyError, ValueError):
            continue
        t, prec = ref.parse_clock(m.get("time"))
        out.append({
            "vessel": vessel, "event": m.get("event_type"),
            "berth": ref.normalize_berth(m.get("berth_no")),
            "dt": datetime.combine(d, t or MIDDAY),
            "precision": prec if t else "date",
            "source": "post_operation_change" if m.get("section") == "post_operation_change" else "programme",
            "reported_in": rd,
        })
    return out


def _resolve_movements(entries: List[Dict[str, Any]], ref_time: time) -> List[Dict[str, Any]]:
    """The same berthing/sailing appears in several reports' programmes, often
    revised (15:00 → 18:00). Group revisions of one event — same vessel,
    event type and berth within 24 h — and keep the best evidence:
      1. a post-operation change (an actual record), else
      2. the LAST programme revision issued before the event time
         (what the port expected right before it happened), else
      3. the earliest programme entry (a plan nobody revised).
    Events still in the future relative to the newest report stay 'planned'."""
    groups: Dict[tuple, List[List[Dict[str, Any]]]] = defaultdict(list)
    for e in sorted(entries, key=lambda e: e["dt"]):
        bucket = groups[(e["vessel"], e["event"], e["berth"])]
        if bucket and (e["dt"] - bucket[-1][0]["dt"]).total_seconds() <= 24 * 3600:
            bucket[-1].append(e)
        else:
            bucket.append([e])
    out = []
    for buckets in groups.values():
        for revs in buckets:
            actual = [r for r in revs if r["source"] == "post_operation_change"]
            if actual:
                best = min(actual, key=lambda r: r["reported_in"])
                basis = "actual (post-operation change)"
            else:
                before = [r for r in revs if datetime.combine(r["reported_in"], ref_time) <= r["dt"]]
                best = max(before, key=lambda r: r["reported_in"]) if before else min(revs, key=lambda r: r["reported_in"])
                basis = "programme (last revision before the event)"
            dts = [r["dt"] for r in revs]
            out.append({**best, "basis": basis, "revisions": len({(r["reported_in"], r["dt"]) for r in revs}),
                        "revision_spread_h": round((max(dts) - min(dts)).total_seconds() / 3600, 1),
                        "first_reported_in": min(r["reported_in"] for r in revs)})
    return sorted(out, key=lambda m: m["dt"])


@lru_cache(maxsize=2)
def _observations(fp: Tuple[int, float]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    arch = _load_archive(fp)
    obs: List[Dict[str, Any]] = []
    raw_moves: List[Dict[str, Any]] = []
    for rd in arch.dates:
        rep = arch.reports[rd]
        obs.extend(observations_for_report(rd, rep))
        raw_moves.extend(movements_for_report(rd, rep))
    ref_t = _reference_time_from(obs)
    moves = _resolve_movements(raw_moves, ref_t)
    horizon = datetime.combine(arch.last, ref_t) if arch.last else None
    for m in moves:
        m["planned_only"] = bool(horizon and m["dt"] > horizon)
    return obs, moves


def _reference_time_from(obs: List[Dict[str, Any]]) -> time:
    """When in the day is a DVP report 'as of'? NMPA prints its own waiting
    clock (e.g. '0.87 Day') next to DOA + HH:MM, so arrival + waiting =
    report time; take the median across the archive (≈ 10:00 IST)."""
    mins = []
    for o in obs:
        if o["section"] in ("anchorage", "tankers_scheduled") and o.get("arrival_date") \
                and o.get("arrival_time_precision") == "exact" and o.get("nmpa_wait_days") is not None:
            ref_dt = datetime.combine(o["arrival_date"], o["arrival_time"]) + timedelta(days=o["nmpa_wait_days"])
            if ref_dt.date() == o["report_date"]:
                mins.append(ref_dt.hour * 60 + ref_dt.minute)
    if len(mins) < 20:
        return time(10, 0)
    m = int(median(mins))
    return time(m // 60, m % 60)


def observations() -> List[Dict[str, Any]]:
    return _observations(archive_fingerprint())[0]


def movements() -> List[Dict[str, Any]]:
    return _observations(archive_fingerprint())[1]


@lru_cache(maxsize=2)
def _report_reference_time(fp: Tuple[int, float]) -> time:
    return _reference_time_from(_observations(fp)[0])


def report_reference_time() -> time:
    return _report_reference_time(archive_fingerprint())


# ──────────────────────────────────────────────────────────────────────
# Port calls
# ──────────────────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", s.upper()).strip("-")


def _most_common(values: List[Any]) -> Any:
    vals = [v for v in values if v not in (None, "", [])]
    return Counter(vals).most_common(1)[0][0] if vals else None


def _cluster_arrivals(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for o in sorted(rows, key=lambda r: r["report_date"]):
        arr = o.get("arrival_date") or (o.get("berthing_date") if o["section"] == "berthed" else None)
        inferred = o.get("arrival_date") is None
        target = None
        if arr is not None:
            for c in reversed(clusters):
                if abs((c["arrival_date"] - arr).days) <= 1 and (o["report_date"] - c["last_report"]).days <= 15:
                    target = c
                    break
        else:
            for c in reversed(clusters):
                if (o["report_date"] - c["last_report"]).days <= 3:
                    target = c
                    break
        if target is None:
            target = {
                "arrival_date": arr or o["report_date"],
                "arrival_inferred": inferred or arr is None,
                "first_report": o["report_date"], "last_report": o["report_date"],
                "rows": [],
            }
            clusters.append(target)
        target["rows"].append(o)
        target["last_report"] = max(target["last_report"], o["report_date"])
        if not inferred and target.get("arrival_inferred"):
            target["arrival_date"], target["arrival_inferred"] = arr, False
    clusters.sort(key=lambda c: c["arrival_date"])
    return clusters


def _expected_episodes(rows: List[Dict[str, Any]], in_port_days: Optional[set] = None) -> List[Dict[str, Any]]:
    """Consecutive 'Vessels Expected' appearances of one ship = one expectation.
    A new expectation starts after a gap of > 6 days, when the ship was seen
    in port in between (liner vessels call weekly), or when the printed ETA
    jumps by > 4 days (a new voyage, not a revision)."""
    eps: List[Dict[str, Any]] = []
    for o in sorted(rows, key=lambda r: r["report_date"]):
        cur = eps[-1] if eps else None
        same = False
        if cur and (o["report_date"] - cur["last_seen"]).days <= 6:
            same = True
            prev_eta = next((r["eta_date"] for r in reversed(cur["rows"]) if r.get("eta_date")), None)
            if prev_eta and o.get("eta_date") and abs((o["eta_date"] - prev_eta).days) > 4:
                same = False
            if in_port_days and any(cur["last_seen"] < d < o["report_date"] or d == o["report_date"] for d in in_port_days):
                same = False
        if same:
            cur["rows"].append(o)
            cur["last_seen"] = o["report_date"]
        else:
            eps.append({"first_seen": o["report_date"], "last_seen": o["report_date"], "rows": [o]})
    for e in eps:
        with_eta = [r for r in e["rows"] if r.get("eta_date")]
        first = with_eta[0] if with_eta else None
        last = with_eta[-1] if with_eta else None
        e["declared_eta_first"] = datetime.combine(first["eta_date"], first["eta_time"] or MIDDAY) if first else None
        e["declared_eta_first_precision"] = (first["eta_precision"] if first and first["eta_time"] else "date") if first else None
        e["declared_eta_last"] = datetime.combine(last["eta_date"], last["eta_time"] or MIDDAY) if last else None
        e["declared_eta_reported_on"] = first["report_date"] if first else None
    return eps


def _qty_manifest(rows: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[str]]:
    both = [(o["report_date"], o["qty_total"], o["qty_balance"]) for o in rows
            if o["section"] == "berthed" and o.get("qty_total") is not None and o.get("qty_balance") is not None]
    if both:
        d, t, b = max(both, key=lambda x: x[0])
        return t + b, "handled + balance (berthed list)"
    handled = [(o["report_date"], o["qty_total"]) for o in rows if o["section"] == "berthed" and o.get("qty_total") is not None]
    if handled:
        return max(handled)[1], "handled to date (berthed list, no balance)"
    other = [o.get("qty") for o in rows if o["section"] in ("anchorage", "tankers_scheduled", "expected") and o.get("qty")]
    if other:
        return other[-1], "declared quantity (anchorage / expected list)"
    return None, None


def _build_calls(fp: Tuple[int, float]) -> List[Dict[str, Any]]:
    arch = _load_archive(fp)
    obs, moves = _observations(fp)
    latest = arch.last
    tol_before = int(ref.linking("expected_to_arrival_max_days_before_first_seen"))
    tol_after = int(ref.linking("expected_to_arrival_max_days_after_eta"))
    move_after = int(ref.linking("movement_after_last_seen_days"))

    by_vessel: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for o in obs:
        by_vessel[o["vessel"]].append(o)
    moves_by_vessel: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in moves:
        if not m["planned_only"]:
            moves_by_vessel[m["vessel"]].append(m)

    calls: List[Dict[str, Any]] = []
    for vessel, rows in by_vessel.items():
        port_rows = [r for r in rows if r["section"] != "expected"]
        clusters = _cluster_arrivals(port_rows)
        in_port_days = {r["report_date"] for r in port_rows}
        episodes = _expected_episodes([r for r in rows if r["section"] == "expected"], in_port_days)

        # movements → call windows
        vmoves = moves_by_vessel.get(vessel, [])
        used = set()
        for i, c in enumerate(clusters):
            nxt = clusters[i + 1]["arrival_date"] if i + 1 < len(clusters) else None
            lo = c["arrival_date"] - timedelta(days=1)
            hi = c["last_report"] + timedelta(days=move_after)
            if nxt:
                hi = min(hi, nxt - timedelta(days=1))
            c["moves"] = [m for m in vmoves if lo <= m["dt"].date() <= hi]
            used.update(id(m) for m in c["moves"])

        # calls seen ONLY in the movement log: the ship berthed and sailed between
        # two daily snapshots (typical for container liners) — no berthed/anchorage row
        orphan = [m for m in vmoves if id(m) not in used]
        for m in orphan:
            if m["event"] not in ("berths", "re_berthed"):
                continue
            if any(m in c["moves"] for c in clusters):
                continue
            later = [x for x in orphan if x["dt"] >= m["dt"] and (x["dt"] - m["dt"]).days <= 4]
            c = {"arrival_date": m["dt"].date(), "arrival_inferred": False, "movement_only": True,
                 "first_report": m["reported_in"], "last_report": max(x["reported_in"] for x in later),
                 "rows": [], "moves": later}
            clusters.append(c)
        clusters.sort(key=lambda c: c["arrival_date"])

        # expected → arrival
        for e in episodes:
            eta = e["declared_eta_last"] or e["declared_eta_first"]
            lo = e["first_seen"] - timedelta(days=tol_before)
            hi = (eta.date() if eta else e["last_seen"]) + timedelta(days=tol_after)
            for c in clusters:
                if c.get("expected") is None and lo <= c["arrival_date"] <= hi:
                    c["expected"] = e
                    e["matched"] = True
                    break

        for c in clusters:
            calls.append(_derive_call(vessel, c, latest))
        for e in episodes:
            if not e.get("matched"):
                calls.append(_derive_expected_only(vessel, e, latest))

    calls.sort(key=lambda c: (c["arrival_dt"] or c["declared_eta"] or datetime.min, c["vessel"]))
    return calls


def _derive_call(vessel: str, c: Dict[str, Any], latest: date) -> Dict[str, Any]:
    rows = c["rows"]
    anch = [r for r in rows if r["section"] in ("anchorage", "tankers_scheduled")]
    berthed = [r for r in rows if r["section"] == "berthed"]
    flags: List[str] = []

    if c.get("movement_only"):
        flags.append("movement_only_call (berthed and sailed between two daily snapshots)")
    # arrival
    exact_anch = [r for r in anch if r.get("arrival_time_precision") in ("exact", "half_day") and r.get("arrival_date")]
    if exact_anch:
        r0 = min(exact_anch, key=lambda r: r["report_date"])
        arrival_dt = datetime.combine(r0["arrival_date"], r0["arrival_time"])
        arrival_prec = r0["arrival_time_precision"]
    elif c.get("movement_only") and c["moves"]:
        arrival_dt = min(m["dt"] for m in c["moves"])
        arrival_prec = "assumed_at_berthing"
    else:
        arrival_dt = datetime.combine(c["arrival_date"], MIDDAY)
        arrival_prec = "date"
    if c.get("arrival_inferred"):
        flags.append("arrival_date_inferred_from_berthing_date")

    # berthing / departure from movements
    mv = sorted(c.get("moves", []), key=lambda m: m["dt"])
    berth_events = [m for m in mv if m["event"] in ("berths", "re_berthed") and m["dt"] >= arrival_dt - timedelta(hours=12)]
    first_berth_dt, first_berth_prec, first_berth_basis = None, None, None
    berthing_dates = sorted({r["berthing_date"] for r in berthed if r.get("berthing_date")})
    if berth_events:
        first_berth_dt, first_berth_prec = berth_events[0]["dt"], berth_events[0]["precision"]
        first_berth_basis = berth_events[0]["basis"]
        if berthing_dates and berth_events[0]["dt"].date() > berthing_dates[0] + timedelta(days=1):
            first_berth_dt, first_berth_prec = datetime.combine(berthing_dates[0], MIDDAY), "date"
            first_berth_basis = "berthed list (date only)"
            flags.append("berthing_event_missing_used_berthing_date")
    elif berthing_dates:
        first_berth_dt, first_berth_prec = datetime.combine(berthing_dates[0], MIDDAY), "date"
        first_berth_basis = "berthed list (date only)"

    sail_events = [m for m in mv if m["event"] == "sails" and (first_berth_dt is None or m["dt"] >= first_berth_dt)]
    shift_events = [m for m in mv if m["event"] == "shifts_to"]
    last_seen = c["last_report"]
    depart_dt, depart_prec, depart_basis, depart_rep = None, None, None, None
    if sail_events:
        depart_dt, depart_prec, depart_basis = sail_events[-1]["dt"], sail_events[-1]["precision"], sail_events[-1]["basis"]
        depart_rep = sail_events[-1]["reported_in"]
    if last_seen >= latest:
        status = "in_port"
        depart_dt, depart_prec, depart_basis = None, None, None
    elif depart_dt is not None:
        status = "sailed"
    else:
        status = "departed_unrecorded"
        flags.append("no_sailing_event_in_archive")

    if first_berth_dt is None:
        stage = "never_berthed"
    else:
        stage = "berthed"
    if first_berth_dt and first_berth_dt < arrival_dt:
        if arrival_prec == "exact" and first_berth_prec == "exact":
            flags.append("berthing_before_arrival_check")
        first_berth_dt = max(first_berth_dt, arrival_dt)

    # berths visited
    berth_seq: List[str] = []
    for r in sorted(berthed, key=lambda r: r["report_date"]):
        if r.get("berth") and (not berth_seq or berth_seq[-1] != r["berth"]):
            berth_seq.append(r["berth"])
    primary_berth = _most_common([r.get("berth") for r in berthed]) or (berth_seq[0] if berth_seq else None)
    if primary_berth is None:
        primary_berth = _most_common([r.get("berth") for r in anch]) or _most_common([r.get("wob_target") for r in anch])
    if primary_berth is None and berth_events and berth_events[0].get("berth"):
        primary_berth = berth_events[0]["berth"]

    exp = c.get("expected")
    exp_rows = exp["rows"] if exp else []
    cargo = _most_common([r["cargo"] for r in berthed]) or _most_common([r["cargo"] for r in anch]) or _most_common([r["cargo"] for r in exp_rows])
    cls = dict(ref.classify_cargo(cargo, primary_berth))
    if cls["cargo_class"] == "unknown" and not cargo and primary_berth:
        inferred = ref.reference()["cargo_class"].get("berth_default_class", {}).get(primary_berth)
        if inferred:
            cls["cargo_class"] = inferred
            flags.append("cargo_class_inferred_from_berth")
    qty, qty_basis = _qty_manifest(rows + exp_rows)

    # waiting
    wait_h, wait_prec = None, None
    if first_berth_dt is not None:
        wait_h = ref.hours_between(arrival_dt, first_berth_dt)
        wait_prec = "exact" if (arrival_prec == "exact" and first_berth_prec == "exact") else "approx"
        if c.get("movement_only"):
            wait_h, wait_prec = None, None  # arrival never observed — waiting time unknown, not zero
        elif not anch and c["arrival_date"] == first_berth_dt.date():
            wait_h, wait_prec = 0.0, "direct_berthing_assumed"
    elif anch and status != "in_port":
        flags.append("left_from_anchorage_without_berthing")
    acc = Counter(r["account"] for r in anch)
    reasons = Counter(r["reason"] for r in anch if r["account"] != "unknown")
    known = sum(v for k, v in acc.items() if k != "unknown")
    port_share = acc.get("port", 0) / known if known else None
    wait_port_h = wait_non_port_h = None
    if wait_h is not None:
        if not anch or wait_h == 0:
            wait_port_h, wait_non_port_h = 0.0, 0.0
        elif port_share is not None:
            wait_port_h = round(wait_h * port_share, 2)
            wait_non_port_h = round(wait_h - wait_port_h, 2)
    nmpa_wait = max([r["nmpa_wait_days"] for r in anch if r.get("nmpa_wait_days") is not None], default=None)

    at_berth_h = ref.hours_between(first_berth_dt, depart_dt) if (first_berth_dt and depart_dt) else None
    trt_h = ref.hours_between(arrival_dt, depart_dt) if depart_dt else None
    if at_berth_h is not None and at_berth_h > 24 * ref.linking("max_plausible_call_days"):
        flags.append("implausibly_long_stay")

    declared_eta = exp["declared_eta_first"] if exp else None
    eta_err_h = ref.hours_between(declared_eta, arrival_dt) if declared_eta else None

    run = _most_common([r["run"] for r in rows + exp_rows])
    call = {
        "call_id": f"{_slug(vessel)}-{c['arrival_date'].isoformat()}",
        "vessel": vessel,
        "vessel_raw_names": sorted({r["vessel_raw"] for r in rows + exp_rows}),
        "status": status,
        "stage": stage,
        "arrival_dt": arrival_dt, "arrival_precision": arrival_prec,
        "first_berth_dt": first_berth_dt, "first_berth_precision": first_berth_prec, "first_berth_basis": first_berth_basis,
        "depart_dt": depart_dt, "depart_precision": depart_prec, "depart_basis": depart_basis,
        "depart_reported_in": depart_rep,
        "first_report": c["first_report"], "last_report": last_seen,
        "berths": berth_seq, "primary_berth": primary_berth,
        "shifts": len(shift_events),
        "cargo": cargo, "cargo_class": cls["cargo_class"], "sor_code": cls["sor_code"], "flow": cls["flow"],
        "qty_t": qty, "qty_basis": qty_basis,
        "run": run, "trade": "foreign" if run and run.startswith("F") else ("coastal" if run and run.startswith("C") else None),
        "loa_m": _most_common([r["loa_m"] for r in rows + exp_rows]),
        "draft_m": _most_common([r.get("draft_m") for r in exp_rows]),
        "agent": _most_common([r["agent"] for r in rows + exp_rows]),
        "receiver": _most_common([r["receiver"] for r in rows + exp_rows]),
        "berth_prefs": exp_rows[0].get("berth_prefs") if exp_rows else [],
        "declared_eta": declared_eta,
        "declared_eta_precision": exp["declared_eta_first_precision"] if exp else None,
        "declared_eta_reported_on": exp["declared_eta_reported_on"] if exp else None,
        "expected_first_seen": exp["first_seen"] if exp else None,
        "eta_error_h": eta_err_h,
        "eta_lead_h": ref.hours_between(datetime.combine(exp["declared_eta_reported_on"], report_reference_time()), declared_eta) if exp and declared_eta and exp.get("declared_eta_reported_on") else None,
        "anchorage_days_observed": len({r["report_date"] for r in anch}),
        "wait_h": wait_h, "wait_precision": wait_prec,
        "wait_port_h": wait_port_h, "wait_non_port_h": wait_non_port_h,
        "wait_accounts": dict(acc),
        "wait_main_reason": reasons.most_common(1)[0][0] if reasons else None,
        "wait_reasons": dict(reasons),
        "nmpa_wait_days_last_seen": nmpa_wait,
        "wob_target": _most_common([r.get("wob_target") for r in anch]),
        "at_berth_h": at_berth_h,
        "turnaround_h": trt_h,
        "flags": flags,
    }
    call.update(ref.vessel_identity(vessel, call["loa_m"]))
    if call["imo_match"] in ("ambiguous", "loa_mismatch"):
        flags.append(f"imo_{call['imo_match']} (same name as {'/'.join(call['imo_candidates'])}; check LOA)")
    call["_rows"] = rows
    return call


def _derive_expected_only(vessel: str, e: Dict[str, Any], latest: date) -> Dict[str, Any]:
    rows = e["rows"]
    cargo = _most_common([r["cargo"] for r in rows])
    prefs = rows[-1].get("berth_prefs") or []
    cls = ref.classify_cargo(cargo, prefs[0] if prefs else None)
    qty, qty_basis = _qty_manifest(rows)
    run = _most_common([r["run"] for r in rows])
    status = "expected" if e["last_seen"] >= latest else "expected_not_seen_arriving"
    first_seen = e["first_seen"]
    call = {
        "call_id": f"{_slug(vessel)}-EXP-{first_seen.isoformat()}",
        "vessel": vessel,
        "vessel_raw_names": sorted({r["vessel_raw"] for r in rows}),
        "status": status, "stage": "expected",
        "arrival_dt": None, "arrival_precision": None,
        "first_berth_dt": None, "first_berth_precision": None, "first_berth_basis": None,
        "depart_dt": None, "depart_precision": None, "depart_basis": None, "depart_reported_in": None,
        "first_report": first_seen, "last_report": e["last_seen"],
        "berths": [], "primary_berth": prefs[0] if prefs else None, "shifts": 0,
        "cargo": cargo, "cargo_class": cls["cargo_class"], "sor_code": cls["sor_code"], "flow": cls["flow"],
        "qty_t": qty, "qty_basis": qty_basis,
        "run": run, "trade": "foreign" if run and run.startswith("F") else ("coastal" if run and run.startswith("C") else None),
        "loa_m": _most_common([r["loa_m"] for r in rows]),
        "draft_m": _most_common([r.get("draft_m") for r in rows]),
        "agent": _most_common([r["agent"] for r in rows]),
        "receiver": _most_common([r["receiver"] for r in rows]),
        "berth_prefs": prefs,
        "declared_eta": e["declared_eta_first"], "declared_eta_precision": e["declared_eta_first_precision"],
        "declared_eta_reported_on": e["declared_eta_reported_on"],
        "expected_first_seen": first_seen,
        "eta_error_h": None, "eta_lead_h": None,
        "anchorage_days_observed": 0,
        "wait_h": None, "wait_precision": None, "wait_port_h": None, "wait_non_port_h": None,
        "wait_accounts": {}, "wait_main_reason": None, "wait_reasons": {},
        "nmpa_wait_days_last_seen": None, "wob_target": None,
        "at_berth_h": None, "turnaround_h": None,
        "flags": [] if status == "expected" else ["expected_but_no_arrival_found (coverage gap, diversion or name mismatch)"],
        "_rows": rows,
    }
    call.update(ref.vessel_identity(vessel, call["loa_m"]))
    return call


@lru_cache(maxsize=2)
def _calls_cached(fp: Tuple[int, float]) -> List[Dict[str, Any]]:
    return _build_calls(fp)


def port_calls() -> List[Dict[str, Any]]:
    return _calls_cached(archive_fingerprint())


def clear_caches() -> None:
    _FP_CACHE["at"] = -1e9
    for fn in (_load_archive, _observations, _report_reference_time, _calls_cached, ref.imo_lookup):
        fn.cache_clear()


# ──────────────────────────────────────────────────────────────────────
# Export (for review / reverse engineering)
# ──────────────────────────────────────────────────────────────────────

EXPORT_FIELDS = [
    "call_id", "vessel", "imo", "imo_match", "imo_confidence", "status", "stage", "cargo", "cargo_class", "sor_code", "flow", "qty_t", "qty_basis",
    "trade", "run", "loa_m", "draft_m", "agent", "receiver", "primary_berth", "berths", "shifts", "berth_prefs",
    "declared_eta", "declared_eta_precision", "declared_eta_reported_on", "eta_error_h", "eta_lead_h",
    "arrival_dt", "arrival_precision", "first_berth_dt", "first_berth_precision", "first_berth_basis",
    "depart_dt", "depart_precision", "depart_basis",
    "wait_h", "wait_precision", "wait_port_h", "wait_non_port_h", "wait_main_reason", "nmpa_wait_days_last_seen",
    "at_berth_h", "turnaround_h", "first_report", "last_report", "anchorage_days_observed", "flags", "vessel_raw_names",
]


def _fmt(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v)
    return v


def export(out_dir: Path = DERIVED_DIR) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    calls = port_calls()
    with (out_dir / "port_calls.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_FIELDS)
        w.writeheader()
        for c in calls:
            w.writerow({k: _fmt(c.get(k)) for k in EXPORT_FIELDS})
    arch = load_archive()
    cal = report_calendar(arch)
    with (out_dir / "report_calendar.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "weekday", "published", "rows", "movements", "unparsed_rows"])
        w.writeheader()
        for r in cal:
            w.writerow({k: _fmt(r[k]) for k in w.fieldnames})
    return {"port_calls": len(calls), "calendar_days": len(cal), "out_dir": str(out_dir)}


if __name__ == "__main__":
    info = export()
    calls = port_calls()
    print(json.dumps(info, indent=2))
    print(Counter(c["status"] for c in calls))
    print(Counter(c["cargo_class"] for c in calls))
    print("report reference time:", report_reference_time())
