"""
Vessel Intelligence — reference rules and small parsing helpers.

Everything a human may need to correct lives in
data/reference/vessel_intel_reference.json (waiting-reason → account
mapping, cargo-class rules, alert thresholds, linking tolerances).
This module only loads that file and applies it; it holds no
hard-coded business rules of its own.

Also hosts the low-level field parsers shared by the port-call
builder (dates written as 'DD/MM', times as 'HH:MM' / 'AM' / 'PM',
quantities with thousands separators, container box counts, NMPA's
own "0.87 Day" waiting-duration strings) so they are tested once.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services.sor_wharfage import match_commodity
from backend.app.services.vessel_entity_resolution import normalize_vessel_name

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
REFERENCE_PATH = DATA_DIR / "reference" / "vessel_intel_reference.json"
PERMISSIBLE_DRAFT_PATH = DATA_DIR / "reference" / "permissible_draft.csv"
TIDE_PATH = DATA_DIR / "reference" / "tide_panambur.csv"
IMO_LOOKUP_PATH = DATA_DIR / "reference" / "vessel_imo_lookup.csv"
BERTHS_PATH = DATA_DIR / "berths.csv"
BERTH_CAPACITY_PATH = DATA_DIR / "berth_capacity.csv"

CARGO_CLASSES = [
    "dry_bulk_conventional", "dry_bulk_mechanical", "break_bulk",
    "liquid_bulk", "container",
]
CARGO_CLASS_LABELS = {
    "dry_bulk_conventional": "Dry bulk (conventional)",
    "dry_bulk_mechanical": "Dry bulk (mechanical)",
    "break_bulk": "Break bulk",
    "liquid_bulk": "Liquid bulk",
    "container": "Container",
    "cruise": "Cruise",
    "non_cargo": "Non-cargo call",
    "unknown": "Unknown cargo",
}


# ──────────────────────────────────────────────────────────────────────
# Reference file
# ──────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def reference() -> Dict[str, Any]:
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def standard(name: str) -> float:
    return float(reference()["standards"][name]["value"])


def linking(name: str) -> float:
    return float(reference()["linking"][name])


@lru_cache(maxsize=1)
def _reason_rules() -> List[Tuple[re.Pattern, str, str]]:
    rules = reference()["waiting_reason_rules"]["rules"]
    return [(re.compile(r["pattern"], re.I), r["reason"], r["account"]) for r in rules]


def classify_reason(text: Optional[str]) -> Dict[str, str]:
    """Anchorage 'reason_or_note' → {reason, account, raw}.

    account ∈ port | non_port | excluded | unknown — the same split NMPA
    uses in its monthly Operational Performance report ("Port Account"
    vs "Other than Port Account" pre-berthing detention).
    """
    raw = re.sub(r"\s+", " ", (text or "").strip().upper())
    cfg = reference()["waiting_reason_rules"]
    if not raw or raw in ("----", "-"):
        fb = cfg["fallback_blank"]
        return {"reason": fb["reason"], "account": fb["account"], "raw": raw}
    for pattern, reason, account in _reason_rules():
        if pattern.search(raw):
            return {"reason": reason, "account": account, "raw": raw}
    if re.fullmatch(r"[\d\s,./()+IE]+", raw):
        fb = cfg["fallback_numeric"]
        return {"reason": fb["reason"], "account": fb["account"], "raw": raw}
    fb = cfg["fallback_other"]
    return {"reason": fb["reason"], "account": fb["account"], "raw": raw}


def want_of_berth_target(text: Optional[str]) -> Optional[str]:
    """'WANT OF BERTH (B.12)' → '12'; 'WANT OF BERTH(SPM)' → 'SPM'."""
    raw = (text or "").upper()
    if "WANT" not in raw:
        return None
    if "SPM" in raw:
        return "SPM"
    m = re.search(r"\(\s*(?:B\.?\s*(?:NO\.?)?\s*)?(\d{1,2})", raw)
    return m.group(1) if m else None


# ──────────────────────────────────────────────────────────────────────
# Cargo classification
# ──────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=8192)
def classify_cargo(cargo: Optional[str], berth: Optional[str] = None) -> Dict[str, Any]:
    """Cargo text (+ berth) → NMPA Operational-Performance cargo class.

    Returns {cargo_class, sor_code, flow} where flow is discharge/load.
    """
    text = re.sub(r"\s+", " ", (cargo or "").strip().upper())
    cfg = reference()["cargo_class"]
    flow = None
    marks = set(m.upper() for m in re.findall(r"\(\s*([DL])\s*\)", text))
    if marks == {"D"}:
        flow = "discharge"
    elif marks == {"L"}:
        flow = "load"
    elif marks == {"D", "L"}:
        flow = "discharge_and_load"

    if not text:
        return {"cargo_class": "unknown", "sor_code": None, "flow": flow}
    if any(k in text for k in cfg["cruise_keywords"]):
        return {"cargo_class": "cruise", "sor_code": None, "flow": flow}
    if any(k in text for k in cfg["container_keywords"]):
        return {"cargo_class": "container", "sor_code": None, "flow": flow}
    if any(k in text for k in cfg["non_cargo_keywords"]):
        return {"cargo_class": "non_cargo", "sor_code": None, "flow": flow}
    if any(text.startswith(o) for o in cfg["liquid_overrides"]) and "BAG" not in text:
        return {"cargo_class": "liquid_bulk", "sor_code": "A.I.i", "flow": flow}

    match = match_commodity(text)
    code = match.get("code") if isinstance(match, dict) else None
    if not code or code == "E":
        return {"cargo_class": "unknown", "sor_code": code, "flow": flow}
    if code.startswith("A."):
        return {"cargo_class": "liquid_bulk", "sor_code": code, "flow": flow}
    if code.startswith("C."):
        return {"cargo_class": "break_bulk", "sor_code": code, "flow": flow}
    if code.startswith("B."):
        mech = cfg["mechanical_dry_bulk"]
        b = normalize_berth(berth)
        is_mech = b in mech["berths_always"] or (
            b in mech["berths_if_cargo_matches"]
            and any(k in text for k in mech["berths_if_cargo_matches"][b])
        )
        return {
            "cargo_class": "dry_bulk_mechanical" if is_mech else "dry_bulk_conventional",
            "sor_code": code, "flow": flow,
        }
    return {"cargo_class": "unknown", "sor_code": code, "flow": flow}


# ──────────────────────────────────────────────────────────────────────
# Berths
# ──────────────────────────────────────────────────────────────────────

def normalize_berth(raw: Optional[str]) -> Optional[str]:
    """'14', '14W', 'B.14', 'B.NO.14' → '14'; 'SPM' → 'SPM'; else None."""
    s = (raw or "").strip().upper()
    if not s or s in ("-", "----"):
        return None
    if "SPM" in s:
        return "SPM"
    m = re.search(r"(\d{1,2})", s)
    if not m:
        return None
    n = int(m.group(1))
    return str(n) if 1 <= n <= 16 else None


def berth_preferences(raw: Optional[str]) -> List[str]:
    """'13/12' → ['13','12']; '9 / 9 / 9' → ['9']; 'ANY BERTH' → []."""
    s = (raw or "").upper()
    if "SPM" in s and not re.search(r"\d", s):
        return ["SPM"]
    out: List[str] = []
    for tok in re.split(r"[/,&]| OR ", s):
        b = normalize_berth(tok)
        if b and b not in out:
            out.append(b)
    if "SPM" in s and "SPM" not in out:
        out.append("SPM")
    return out


@lru_cache(maxsize=1)
def berths() -> Dict[str, Dict[str, Any]]:
    """berths.csv + berth_capacity.csv keyed by normalized berth id."""
    out: Dict[str, Dict[str, Any]] = {}
    with BERTHS_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bid = normalize_berth(row["berth_id"])
            if not bid:
                continue
            out[bid] = {
                "berth_id": bid,
                "label": row["berth_id"],
                "type": row["type_of_berth"],
                "cargo_types": [c.strip() for c in row["cargo_types"].split(";") if c.strip()],
                "max_draught_m": _float(row["max_draught_m"]),
                "quay_length_m": _float(row["quay_length_m"]),
                "max_dwt": _float(row["max_dwt"]),
                "ownership": row["ownership"],
            }
    if BERTH_CAPACITY_PATH.exists():
        with BERTH_CAPACITY_PATH.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                bid = normalize_berth(row["berth_id"])
                if bid in out:
                    out[bid]["capacity_mmt"] = _float(row["capacity_mmt"])
    return out


def berth_order() -> List[str]:
    ids = list(berths().keys())
    return sorted(ids, key=lambda b: (b == "SPM", int(b) if b.isdigit() else 99))


@lru_cache(maxsize=1)
def permissible_drafts() -> List[Dict[str, Any]]:
    """Optional: data/reference/permissible_draft.csv, transcribed from
    NMPA Marine Dept 'Permissible draft' circulars
    (columns: berth_id,max_draft_m,valid_from,source). Empty if absent."""
    if not PERMISSIBLE_DRAFT_PATH.exists():
        return []
    rows = []
    with PERMISSIBLE_DRAFT_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bid = normalize_berth(row.get("berth_id"))
            d = _float(row.get("max_draft_m"))
            vf = _iso_date(row.get("valid_from"))
            if bid and d and vf:
                rows.append({"berth_id": bid, "max_draft_m": d, "valid_from": vf,
                             "source": (row.get("source") or "").strip()})
    return sorted(rows, key=lambda r: r["valid_from"])


def max_draft_for(berth_id: str, on: date) -> Tuple[Optional[float], str]:
    """Permissible draft in force on a date (circular) else berths.csv design draught."""
    applicable = [r for r in permissible_drafts() if r["berth_id"] == berth_id and r["valid_from"] <= on]
    if applicable:
        r = applicable[-1]
        return r["max_draft_m"], f"Permissible-draft circular ({r['source'] or r['valid_from'].isoformat()})"
    b = berths().get(berth_id)
    if b and b.get("max_draught_m"):
        return b["max_draught_m"], "berths.csv max draught (no permissible-draft circular loaded)"
    return None, "unknown"


@lru_cache(maxsize=1)
def tide_table() -> Dict[datetime, float]:
    """Optional: data/reference/tide_panambur.csv (datetime,height_m), from
    NMPA's 'Predicted Tidal Data of Panambur Area'. Empty if absent."""
    if not TIDE_PATH.exists():
        return {}
    out = {}
    with TIDE_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out[datetime.fromisoformat(row["datetime"].strip())] = float(row["height_m"])
            except (KeyError, ValueError):
                continue
    return out


# ──────────────────────────────────────────────────────────────────────
# Vessel identity
# ──────────────────────────────────────────────────────────────────────

_LEADING_SERIAL_RE = re.compile(r"^\d{1,2}\s+(?=[A-Z])")
_TRAILING_RUN_RE = re.compile(r"\s+[FC]$")


def vessel_key(raw: Optional[str]) -> str:
    """normalize_vessel_name() plus two clean-ups found while profiling:
    a serial number glued to the front ('10 BARROW ISLAND') and the
    run code glued to the end ('MSC MANASA F'). Never merges two
    different names — fuzzy look-alikes stay in the human review list."""
    n = normalize_vessel_name(raw or "")
    n = _LEADING_SERIAL_RE.sub("", n)
    n = _TRAILING_RUN_RE.sub("", n)
    return n.strip()


def imo_check_digit_ok(imo: Any) -> bool:
    """IMO number check: first six digits x weights 7..2, last digit of the sum
    must equal the seventh digit (e.g. 9731195: 63+42+15+4+3+18 = 145 -> 5)."""
    s = str(imo or "").strip()
    if not re.fullmatch(r"\d{7}", s):
        return False
    return sum(int(d) * w for d, w in zip(s[:6], range(7, 1, -1))) % 10 == int(s[6])


@lru_cache(maxsize=1)
def imo_lookup() -> Dict[str, List[Dict[str, Any]]]:
    """data/reference/vessel_imo_lookup.csv, keyed by vessel_key(name).

    Hand-curated: DVP reports carry no IMO number, so each row was looked up in
    public registries (source_url) and its check digit verified. Rows that fail
    the check digit are ignored. Several rows may share a name (BEAGLE,
    OCEAN PIONEER): length overall (dvp_loa_m) tells them apart."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not IMO_LOOKUP_PATH.exists():
        return out
    with IMO_LOOKUP_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            imo = (row.get("imo_number") or "").strip()
            key = vessel_key(row.get("vessel_name"))
            if not key or not imo_check_digit_ok(imo):
                continue
            out.setdefault(key, []).append({
                "imo": imo, "loa_m": _float(row.get("dvp_loa_m")),
                "ship_type": (row.get("ship_type") or "").strip(),
                "confidence": (row.get("confidence") or "").strip() or None,
                "source_url": (row.get("source_url") or "").strip() or None,
                "looked_up_on": (row.get("looked_up_on") or "").strip() or None,
            })
    return out


def _loa_close(a: Optional[float], b: Optional[float]) -> bool:
    """LOA agreement: within 10 m or 7 %, whichever is larger (DVP LOAs are
    typed by agents and carry small rounding differences)."""
    return a is not None and b is not None and abs(a - b) <= max(10.0, 0.07 * max(a, b))


def vessel_identity(vessel: str, loa_m: Optional[float]) -> Dict[str, Any]:
    """Attach the IMO number to a DVP vessel name.

    Matching is name + LOA, never name alone when the name is shared:
      name_and_loa       one candidate whose LOA agrees with the DVP LOA
      name_only          one candidate, DVP row has no LOA (accepted, lower trust)
      ambiguous          several same-name ships and LOA can't separate them
      loa_mismatch       same name but different size: probably a different
                         ship not yet in the lookup, so no IMO is assigned
      not_looked_up      name not in the lookup file yet
    """
    cands = imo_lookup().get(vessel, [])
    blank = {"imo": None, "imo_confidence": None, "imo_source": None, "imo_ship_type": None}
    if not cands:
        return {**blank, "imo_match": "not_looked_up", "imo_candidates": []}
    if loa_m is not None:
        close = [c for c in cands if c["loa_m"] is None or _loa_close(c["loa_m"], loa_m)]
        if len(close) == 1:
            c = close[0]
            return {"imo": c["imo"], "imo_confidence": c["confidence"], "imo_source": c["source_url"],
                    "imo_ship_type": c["ship_type"], "imo_match": "name_and_loa", "imo_candidates": []}
        if not close:
            return {**blank, "imo_match": "loa_mismatch", "imo_candidates": [c["imo"] for c in cands]}
        return {**blank, "imo_match": "ambiguous", "imo_candidates": [c["imo"] for c in close]}
    if len(cands) == 1:
        c = cands[0]
        return {"imo": c["imo"], "imo_confidence": c["confidence"], "imo_source": c["source_url"],
                "imo_ship_type": c["ship_type"], "imo_match": "name_only", "imo_candidates": []}
    return {**blank, "imo_match": "ambiguous", "imo_candidates": [c["imo"] for c in cands]}


def is_header_echo(name: str) -> bool:
    """Column-header text repeated as a data row at a PDF page break."""
    return name in {"", "VESSEL", "VESSEL NAME", "NAME OF THE VESSEL", "NAME OF VESSEL", "ETA", "B PREFER", "B.PREFER",
                    "NIL", "NILL", "NONE", "NA", "N A"}


# ──────────────────────────────────────────────────────────────────────
# Field parsers
# ──────────────────────────────────────────────────────────────────────

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _float(value: Any) -> Optional[float]:
    s = str(value or "").replace(",", "").strip()
    return float(s) if _NUM_RE.match(s) else None


def _iso_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def parse_qty(value: Any) -> Optional[float]:
    s = str(value or "").replace(",", "").strip()
    m = re.match(r"^[A-Z]?\s*\.?\s*(\d+(?:\.\d+)?)\s*(?:MT|T|TONNES)?$", s, re.I)
    return float(m.group(1)) if m else None


def parse_boxes(value: Any) -> Optional[int]:
    parts = re.findall(r"(\d+)\s*\(\s*[IE]\s*\)", str(value or ""), re.I)
    return sum(int(p) for p in parts) if parts else None


def full_date(partial: Optional[str], report_date: date) -> Optional[date]:
    """'DD/MM', 'DD/MM(DD/MM)', 'D/M' → date, year inferred from the
    report date (a December arrival seen in a January report belongs
    to the previous year)."""
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", partial or "")
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    year = report_date.year
    if mo - report_date.month > 6:
        year -= 1
    elif report_date.month - mo > 6:
        year += 1
    try:
        return date(year, mo, d)
    except ValueError:
        return None


def parse_clock(value: Optional[str]) -> Tuple[Optional[time], str]:
    """'HH:MM' → exact; 'AM'/'PM'/'NOON' → coarse (06:00 / 18:00 / 12:00)."""
    s = (value or "").strip().upper().replace(";", ":").lstrip("'")
    m = re.match(r"^(\d{1,2})\s*:\s*(\d{2})", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h == 24:
            h = 23
            mi = 59
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return time(h, mi), "exact"
    if s.startswith("AM"):
        return time(6, 0), "half_day"
    if s.startswith("PM"):
        return time(18, 0), "half_day"
    if "NOON" in s:
        return time(12, 0), "half_day"
    return None, "date"


def parse_wait_days(value: Optional[str]) -> Optional[float]:
    """NMPA's own waiting clock, e.g. '0.87 Day', '12.46 Days'."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*\.?\s*D", (value or ""), re.I)
    return float(m.group(1)) if m else None


def combine(d: Optional[date], t: Optional[time]) -> Optional[datetime]:
    if d is None:
        return None
    return datetime.combine(d, t or time(0, 0))


def hours_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 3600.0, 2)


def day_floor(dt: datetime) -> date:
    return dt.date()


def add_days(d: date, n: float) -> date:
    return d + timedelta(days=n)
