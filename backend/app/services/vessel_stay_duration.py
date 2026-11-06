"""
Links a vessel's journey across the Daily Vessel Position archive to
compute real per-call berth-occupancy (stay) duration -- the actual
unlock behind "Vessel Stay & Berth Occupancy" (see
PROJECT_DOCUMENTATION/22_NMPA_VISIT_BRIEFING.md), previously blocked
because the only NMPA data available was monthly aggregates with no
per-vessel signal at all.

Two data sources, combined because neither is sufficient alone:

  - The `berthed` section is a daily snapshot: every report says which
    vessel occupies which berth *that day*, with berthing_date/
    arrival_date at DAY precision only (no time-of-day). A vessel
    berthed for a week appears in ~7 consecutive daily reports.
  - The `movements` section has exact HH:MM timestamps for berthing/
    sailing/shifting events, but only covers a rolling few-day window
    per report, and the SAME real event is repeated across several
    overlapping daily reports (must be deduplicated before use).

Algorithm, per vessel (normalized identity, see
vessel_entity_resolution.py):

  1. Group the vessel's `berthed` observations into distinct calls,
     keyed by (vessel, berthing_date) -- a later, different
     berthing_date is a separate call, not a continuation.
  2. Deduplicate that vessel's movement events and sort them
     chronologically.
  3. Walk the vessel's calls in chronological order, consuming
     movement events in order too (each event can only belong to one
     call) -- for each call, look for a same-day "berths"/"re_berthed"
     event to pin an exact start time, and the next "sails" or
     "shifts_to" event at/after the berthing date as the call's end.

Confidence is reported per stay, not asserted uniformly:
  - "exact": both start and end come from real movement timestamps.
  - "date_only": start and/or end falls back to the daily snapshot's
    calendar date (implied midnight) because no matching movement
    event was found.
  - "unconfirmed_lower_bound": no departure event found at all -- the
    vessel may still be in port, or the movements window (which only
    covers a few days per report) never captured its sailing. The
    reported duration is a floor, not a real stay length.

Never silently drops calls with weak confidence -- they're returned
and labeled, not filtered out, so downstream consumers decide how
much to trust each one.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median

from backend.app.services.vessel_entity_resolution import normalize_vessel_name

ARCHIVE_PARSED_DIR = Path(__file__).resolve().parents[3] / "data" / "daily_vessel_position_parsed"
STAYS_OUTPUT_PATH = Path(__file__).resolve().parents[3] / "data" / "vessel_stays.json"

DEPARTURE_EVENT_TYPES = {"sails", "shifts_to"}
ARRIVAL_EVENT_TYPES = {"berths", "re_berthed"}

# A "departure" event found many weeks after a call's berthing_date is
# far more likely to be a sequential-matching mismatch (the real
# departure event is simply missing -- e.g. it fell in one of the
# archive's uncovered days, roughly 12% of the year) than a genuine
# multi-month stay. NMPA's own SOR only defines penal rates for
# "unauthorized occupation" starting at 3+ days and escalating past 9
# (Chapter II, 2.2 Note 5) -- there's no tariff mechanism that assumes
# routine stays anywhere near a month, so a match beyond this is
# treated as unreliable rather than a real outlier stay.
MAX_PLAUSIBLE_STAY_DAYS = 30


def _to_iso_datetime(date_str: str, time_str: str) -> str:
    """'HH:MM' -> ISO datetime, handling the source document's
    occasional use of '24:00' for midnight (invalid for
    datetime.fromisoformat, which only accepts hour 00-23)."""

    hour_s, minute_s = time_str.split(":")
    if hour_s == "24":
        d = date.fromisoformat(date_str) + timedelta(days=1)
        return f"{d.isoformat()}T00:{minute_s}:00"
    return f"{date_str}T{time_str}:00"


def _full_date(partial: str, report_date: date) -> date | None:
    """Reconstructs a full date from a 'DD/MM' fragment using the
    report's own date as context, with year-wraparound handling (a
    vessel berthed since December showing up in a January report)."""

    if not partial or "/" not in partial:
        return None
    try:
        day_s, month_s = partial.split("/")
        day_n, month_n = int(day_s), int(month_s)
    except ValueError:
        return None

    year = report_date.year
    if month_n - report_date.month > 6:
        year -= 1
    elif report_date.month - month_n > 6:
        year += 1
    try:
        return date(year, month_n, day_n)
    except ValueError:
        return None


def _collect_dedup_movements() -> list[dict]:
    """All movement events archive-wide, deduplicated -- the same real
    event is repeated verbatim across several overlapping daily
    reports' Post-Operation-Changes/Movements sections."""

    seen: dict[tuple, dict] = {}
    for path in sorted(ARCHIVE_PARSED_DIR.glob("*.json")):
        day = json.loads(path.read_text())
        for e in day.get("movements", []):
            vessel_norm = normalize_vessel_name(e.get("vessel_name", ""))
            if not vessel_norm:
                continue
            key = (vessel_norm, e["event_type"], e.get("berth_no"), e["date"], e["time"])
            seen[key] = {**e, "vessel_norm": vessel_norm}
    return list(seen.values())


def _collect_berthed_calls() -> dict[tuple[str, str], dict]:
    """Groups `berthed` daily observations into per-call spans keyed
    by (vessel_norm, berthing_date)."""

    calls: dict[tuple[str, str], dict] = {}

    for path in sorted(ARCHIVE_PARSED_DIR.glob("*.json")):
        day = json.loads(path.read_text())
        report_date = date.fromisoformat(day["report_date"])

        for row in day.get("berthed", []):
            vessel = (row.get("vessel_name") or "").strip()
            if vessel in ("", "----"):
                continue
            berthing_full = _full_date(row.get("berthing_date", ""), report_date)
            if berthing_full is None:
                continue

            vessel_norm = normalize_vessel_name(vessel)
            key = (vessel_norm, berthing_full.isoformat())
            entry = calls.setdefault(key, {
                "vessel_norm": vessel_norm,
                "berthing_date": berthing_full.isoformat(),
                "berth_nos": Counter(),
                "observed_report_dates": set(),
                "cargo": Counter(),
            })
            entry["observed_report_dates"].add(report_date.isoformat())
            if row.get("berth_no"):
                entry["berth_nos"][row["berth_no"]] += 1
            if row.get("cargo"):
                entry["cargo"][row["cargo"]] += 1

    return calls


@dataclass
class VesselStay:
    vessel_norm: str
    berth_no: str | None
    cargo: str | None
    berthing_date: str
    last_seen_date: str
    start_datetime: str
    end_datetime: str | None
    duration_hours: float | None
    status: str  # "sailed" | "shifted_berth" | "unconfirmed"
    confidence: str  # "exact" | "date_only" | "unconfirmed_lower_bound"


def build_vessel_stays() -> list[VesselStay]:
    movements = _collect_dedup_movements()
    moves_by_vessel: dict[str, list[dict]] = defaultdict(list)
    for m in movements:
        moves_by_vessel[m["vessel_norm"]].append(m)
    for v in moves_by_vessel.values():
        v.sort(key=lambda m: (m["date"], m["time"]))

    calls_by_vessel: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for (vessel_norm, berthing_date), info in _collect_berthed_calls().items():
        calls_by_vessel[vessel_norm].append((berthing_date, info))
    for v in calls_by_vessel.values():
        v.sort(key=lambda c: c[0])

    stays: list[VesselStay] = []

    for vessel_norm, calls in calls_by_vessel.items():
        moves = moves_by_vessel.get(vessel_norm, [])
        move_ptr = 0

        for berthing_date, info in calls:
            last_seen = max(info["observed_report_dates"])
            berth_no = info["berth_nos"].most_common(1)[0][0] if info["berth_nos"] else None
            cargo = info["cargo"].most_common(1)[0][0] if info["cargo"] else None

            while move_ptr < len(moves) and moves[move_ptr]["date"] < berthing_date:
                move_ptr += 1  # events strictly before this call belong to an earlier one

            exact_start = None
            departure = None
            scan_ptr = move_ptr
            while scan_ptr < len(moves):
                m = moves[scan_ptr]
                if exact_start is None and m["date"] == berthing_date and m["event_type"] in ARRIVAL_EVENT_TYPES:
                    exact_start = m
                if m["event_type"] in DEPARTURE_EVENT_TYPES:
                    departure_days_out = (date.fromisoformat(m["date"]) - date.fromisoformat(berthing_date)).days
                    if departure_days_out > MAX_PLAUSIBLE_STAY_DAYS:
                        # Almost certainly this call's real departure event is
                        # simply missing from the archive (coverage gap), not
                        # a genuine month-plus stay -- don't claim this event
                        # (leave it unconsumed so a later call for the same
                        # vessel can still match it correctly), and report
                        # this call as unconfirmed instead of a false "exact".
                        break
                    departure = m
                    break
                scan_ptr += 1

            if exact_start:
                start_dt = _to_iso_datetime(exact_start["date"], exact_start["time"])
                start_precision = "exact"
            else:
                start_dt = f"{berthing_date}T00:00:00"
                start_precision = "date_only"

            if departure:
                move_ptr = scan_ptr + 1  # this event is consumed; next call starts scanning after it
                end_dt = _to_iso_datetime(departure["date"], departure["time"])
                status = "sailed" if departure["event_type"] == "sails" else "shifted_berth"
                end_precision = "exact"
            else:
                end_dt = f"{last_seen}T23:59:00"
                status = "unconfirmed"
                end_precision = "date_only_lower_bound"

            confidence = (
                "exact" if start_precision == "exact" and end_precision == "exact"
                else "unconfirmed_lower_bound" if status == "unconfirmed"
                else "date_only"
            )

            duration_hours = None
            try:
                delta = datetime.fromisoformat(end_dt) - datetime.fromisoformat(start_dt)
                if delta.total_seconds() >= 0:
                    duration_hours = round(delta.total_seconds() / 3600, 2)
            except ValueError:
                pass

            stays.append(VesselStay(
                vessel_norm=vessel_norm, berth_no=berth_no, cargo=cargo,
                berthing_date=berthing_date, last_seen_date=last_seen,
                start_datetime=start_dt, end_datetime=end_dt if departure else None,
                duration_hours=duration_hours, status=status, confidence=confidence,
            ))

    return stays


def save_vessel_stays(stays: list[VesselStay]) -> None:
    STAYS_OUTPUT_PATH.write_text(json.dumps([asdict(s) for s in stays], indent=2))


def summarize(stays: list[VesselStay]) -> dict:
    by_confidence = Counter(s.confidence for s in stays)
    exact = [s.duration_hours for s in stays if s.confidence == "exact" and s.duration_hours is not None]
    date_only = [s.duration_hours for s in stays if s.confidence == "date_only" and s.duration_hours is not None]

    return {
        "total_calls": len(stays),
        "by_confidence": dict(by_confidence),
        "exact_confidence": {
            "count": len(exact),
            "mean_hours": round(mean(exact), 1) if exact else None,
            "median_hours": round(median(exact), 1) if exact else None,
        },
        "date_only_confidence": {
            "count": len(date_only),
            "mean_hours": round(mean(date_only), 1) if date_only else None,
            "median_hours": round(median(date_only), 1) if date_only else None,
        },
        "nmpa_official_standard_hours": 37,  # SOR Annexure-II: Average Turnaround Time of Vessels
    }


if __name__ == "__main__":
    stays = build_vessel_stays()
    save_vessel_stays(stays)
    summary = summarize(stays)
    print(json.dumps(summary, indent=2))
    print(f"\nSaved {len(stays)} linked vessel calls -> {STAYS_OUTPUT_PATH}")
