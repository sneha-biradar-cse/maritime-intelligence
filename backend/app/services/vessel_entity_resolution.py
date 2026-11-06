"""
Entity resolution for vessel names in the Daily Vessel Position archive
(data/daily_vessel_position_parsed/, built by vessel_position_parser.py).

The same physical ship is typed inconsistently across days and report
sections -- draft/LOA annotations and berth references get glued onto
the name in a dozen different formats:

    "OSD COASTAL ANTARAA (4.80)"
    "RV. SAMUDRA SHAUDHIKAMA(1.90)"  /  "RV.SAMUDRA SHAUDHIKAMA (1.9)"
    "SANMAR SITAR (B.10/11)"  /  "SANMAR SITAR (11.0) B. 12 / 10"

Two-tier approach, deliberately NOT a single fuzzy-match pass:

1. Exact-match normalization (`normalize_vessel_name`) -- strip
   parenthetical annotations, strip berth-reference tokens ("B.4",
   "B.10/11", "B.NO.5", "B.14W"), collapse whitespace/punctuation.
   Applied automatically; verified safe by spot-checking real merges
   (e.g. 10 formatting variants of "RV.SAMUDRA SHAUDHIKAMA" all
   collapse correctly).

2. Fuzzy near-duplicate detection (`find_review_candidates`) --
   flags normalized names that are suspiciously similar but not
   identical, for a HUMAN to review. Never auto-merged. Why: this
   port is served by fleets with single-word-suffix naming
   conventions (SANMAR SANTOOR / SHEHNAI / SITAR / SLOKA / SONGBIRD /
   SRUTHI / SWARA / SWARNA are eight genuinely different real ships,
   confirmed against the raw archive) -- a similarity threshold loose
   enough to catch real typos ("MSC PAPTNAREE III" vs "MSC PATNAREE
   III") is also loose enough to conflate two different real ships in
   a fleet like that. Silently merging two different vessels would be
   worse for downstream stay-duration/occupancy analysis than leaving
   a few typo-duplicates unmerged, so this stays a suggestion list.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ARCHIVE_PARSED_DIR = Path(__file__).resolve().parents[3] / "data" / "daily_vessel_position_parsed"
REGISTRY_PATH = Path(__file__).resolve().parents[3] / "data" / "vessel_registry.json"
REVIEW_CANDIDATES_PATH = Path(__file__).resolve().parents[3] / "data" / "vessel_name_review_candidates.json"

_PAREN_RE = re.compile(r"\([^)]*\)")
_BERTH_REF_RE = re.compile(
    r"\bB\.?\s*(?:NO\.?\s*)?\d+[A-Za-z]?(?:\s*[/\-]\s*\d+[A-Za-z]?)*", re.I
)


def normalize_vessel_name(raw: str) -> str:
    """Canonical key for a raw vessel-name string. Deterministic and
    conservative: only strips annotations confirmed (by sampling the
    archive) to be draft/LOA figures or berth references, never
    touches the vessel's actual name tokens."""

    n = _PAREN_RE.sub(" ", raw or "")
    n = _BERTH_REF_RE.sub(" ", n)
    n = re.sub(r"[^A-Za-z0-9 ]", " ", n).upper()
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _iter_vessel_mentions():
    """Yields (raw_name, report_date) for every vessel mention across
    every section of every parsed day, including the movements log."""

    for path in sorted(ARCHIVE_PARSED_DIR.glob("*.json")):
        try:
            day = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        report_date = day.get("report_date")

        for section in ("berthed", "anchorage", "tankers_scheduled", "expected"):
            for row in day.get(section, []):
                name = (row.get("vessel_name") or "").strip()
                if name and name != "----":
                    yield name, report_date

        for event in day.get("movements", []):
            name = (event.get("vessel_name") or "").strip()
            if name:
                yield name, report_date


def build_vessel_registry() -> dict:
    """
    Scans the whole archive and groups raw name strings by their
    normalized key. Returns (and saves to REGISTRY_PATH):

        {canonical_key: {
            "raw_variants": {raw_string: occurrence_count, ...},
            "total_mentions": int,
            "first_seen": "YYYY-MM-DD",
            "last_seen": "YYYY-MM-DD",
        }, ...}
    """
    registry: dict[str, dict] = {}

    for raw, report_date in _iter_vessel_mentions():
        key = normalize_vessel_name(raw)
        if not key:
            continue
        entry = registry.setdefault(key, {
            "raw_variants": Counter(), "total_mentions": 0,
            "first_seen": report_date, "last_seen": report_date,
        })
        entry["raw_variants"][raw] += 1
        entry["total_mentions"] += 1
        if report_date < entry["first_seen"]:
            entry["first_seen"] = report_date
        if report_date > entry["last_seen"]:
            entry["last_seen"] = report_date

    serializable = {
        key: {
            "raw_variants": dict(entry["raw_variants"]),
            "total_mentions": entry["total_mentions"],
            "first_seen": entry["first_seen"],
            "last_seen": entry["last_seen"],
        }
        for key, entry in registry.items()
    }
    REGISTRY_PATH.write_text(json.dumps(serializable, indent=2, sort_keys=True))
    return serializable


def find_review_candidates(registry: dict, similarity_threshold: float = 0.85) -> list[dict]:
    """
    Flags pairs of canonical keys that are similar but not identical,
    for human review -- NOT applied automatically anywhere. Bucketed
    by first token to keep this to roughly O(n) pair comparisons
    instead of O(n^2) over the whole registry.
    """
    buckets: dict[str, list[str]] = {}
    for key in registry:
        first_token = key.split(" ", 1)[0] if key else ""
        buckets.setdefault(first_token, []).append(key)

    candidates = []
    for keys in buckets.values():
        if len(keys) < 2:
            continue
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = keys[i], keys[j]
                ratio = SequenceMatcher(None, a, b).ratio()
                if ratio >= similarity_threshold:
                    candidates.append({
                        "a": a, "a_mentions": registry[a]["total_mentions"],
                        "b": b, "b_mentions": registry[b]["total_mentions"],
                        "similarity": round(ratio, 3),
                    })

    candidates.sort(key=lambda c: -c["similarity"])
    REVIEW_CANDIDATES_PATH.write_text(json.dumps(candidates, indent=2))
    return candidates


if __name__ == "__main__":
    registry = build_vessel_registry()
    raw_total = sum(len(e["raw_variants"]) for e in registry.values())
    print(f"Raw name strings seen: {raw_total}")
    print(f"Resolved to canonical vessels: {len(registry)}")
    print(f"Registry saved -> {REGISTRY_PATH}")

    merged = {k: v for k, v in registry.items() if len(v["raw_variants"]) > 1}
    print(f"Canonical vessels with >1 raw spelling merged: {len(merged)}")

    candidates = find_review_candidates(registry)
    print(f"\nPossible-duplicate pairs flagged for human review: {len(candidates)}")
    print(f"(NOT auto-merged -- see {REVIEW_CANDIDATES_PATH})")
    print("\nTop 10 by similarity:")
    for c in candidates[:10]:
        print(f"  {c['similarity']:.3f}  {c['a']!r} ({c['a_mentions']}x)  <->  {c['b']!r} ({c['b_mentions']}x)")
