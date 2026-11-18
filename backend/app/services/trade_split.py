"""
Trade Intelligence - cargo-level foreign vs coastal ESTIMATE from NMPA's daily vessel position reports.

Why: the official monthly statements split foreign (overseas) and coastal cargo only for the whole port.
NMPA's daily vessel reports (data/daily_vessel_position_parsed/, from 2025-09-01) list every berthed ship
with its cargo, receiver/shipper, quantity and a "run" flag. The flag is read here as F = foreign-going,
C = coastal, the same overseas/coastal split the Ministry publishes for every major port. Checked against the data: imported
LPG and coal are all F, KIOCL's inbound iron ore is almost all C, and the whole-port coastal share from these flags tracks
the Ministry's official monthly figure (see _validation).

What this module does:
  1. Builds one row per ship "voyage" (vessel + cargo, a new voyage if the ship has not been seen for >30 days).
  2. Groups the cargo codes into families (e.g. "IOF(D)", "IOP(L)" -> Iron ore) and direction
     (D = discharged = inbound, L = loaded = outbound).
  3. Reports, per cargo family, how many voyages were foreign vs coastal, the customers named, and the quantity.
  4. Checks the whole-port monthly coastal share against the Ministry of Ports' official figures and states how
     far apart they are. The result is an ESTIMATE of the pattern, never official tonnes.

Everything here is derived from real files in the repository. Nothing is invented or assumed.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import trade_intelligence as ti

DAILY_DIR = Path(__file__).resolve().parents[3] / "data" / "daily_vessel_position_parsed"
NEW_VOYAGE_GAP_DAYS = 30
MIN_VOYAGES_FOR_PATTERN = 8        # fewer voyages than this -> "too few to tell"
MIXED_SPLIT_BAND = (25.0, 75.0)    # coastal share inside this band = "Mixed"
VALIDATION_OK_POINTS = 8.0         # average monthly miss (percentage points) still called "close enough for patterns"

# Rows that are not cargo handling (tugs, bunkering, dredging, trials ...)
NON_CARGO = re.compile(
    r"SPM OP|BUNKER|DREDG|CONVERSION|SEA TRIAL|PORT OP|BARGE|CLEARANCE|CREW|REPAIR|ANCHOR|CALIBRAT|SURVEY|DRYDOCK|PILOT|CHANGE",
    re.I,
)

# Ordered rules: first match wins. (regex on the cleaned code, family name)
FAMILY_RULES: list[tuple[str, str]] = [
    (r"CRUDE", "Crude oil"),
    (r"^LPG", "LPG"),
    (r"^IO[FP]", "Iron ore"),
    (r"COAL TAR", "Coal tar pitch"),
    (r"COAL", "Coal"),
    (r"CPO|PALM|EDIBLE|SOYA|SUNFLOWER|VEG", "Edible oil"),
    (r"^(MS|HSD|ATF|SKO|NAPHTHA|MS/HSD|HSD/MS)\b", "Petroleum products (fuels)"),
    (r"FO\b|CSFO|CSFSO|VLSFO|LSFO|FUEL OIL", "Fuel oil"),
    (r"BITUMEN", "Bitumen"),
    (r"CEMENT|CLINKER", "Cement"),
    (r"UREA|MOP|DAP|FERT|POTASH|PHOS|AMMONIA|SULPH", "Fertilizer and chemicals"),
    (r"BOXES|CONTAINER", "Containers"),
    (r"CASHEW", "Raw cashew"),
    (r"LIMESTONE|GYPSUM|LIME", "Limestone and minerals"),
    (r"SUGAR|RICE|WHEAT|GRAIN|MAIZE", "Food grains and sugar"),
]


def _vessel_norm(name: Any) -> str:
    """Ship name without the notes port staff add to it: draft '(12.50-A)', berth 'B.8', 'BACK LDG', '/PMC'."""
    n = re.sub(r"\(.*?\)", "", str(name or "")).upper()
    n = re.sub(r"\s*BACK\s*LDG.*$", "", n)              # 'VISHVA PRERNA (BACK LDG)' / 'VISHVA BANDHANBACK LDG'
    n = re.sub(r"\s+B\.\s*\d.*$", "", n)                # 'HANSA ANHOLT B.7', 'UNION GLORY B.3/ 2/ 6/ 7'
    n = re.sub(r"\s*/\s*PMC\s*$", "", n)
    n = re.sub(r"\s+\d+\.\d+(-?A)?\)?\s*$", "", n)       # stray draft '8.0', '12.0-A)' (names like 'SEA GULL 18' are kept)
    return re.sub(r"\s+", " ", n).strip()


def _qty(value: Any) -> float:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)", str(value or "").replace(",", ""))
    return float(m.group(1)) if m else np.nan


def _clean_code(code: str) -> str:
    return re.sub(r"\s+", " ", code.upper()).strip()


def classify_cargo(code: str) -> tuple[str, str]:
    """Return (family, direction) for a cargo code. direction is inbound / outbound / both / unknown."""
    c = _clean_code(code)
    if re.search(r"\(\s*D\s*\)\s*$|\bD\)$", c):
        direction = "inbound"
    elif re.search(r"\(\s*L\s*\)\s*$", c):
        direction = "outbound"
    elif re.search(r"BOXES|CONTAINER", c):
        direction = "both"
    else:
        direction = "unknown"
    for pattern, family in FAMILY_RULES:
        if re.search(pattern, c):
            return family, direction
    return "Other cargo", direction


def build_voyages(daily_dir: Path | None = None) -> pd.DataFrame:
    """
    One row per ship voyage with cargo, run flag, quantity and receiver/shipper.

    qty         = the ship's cargo parcel (largest 'handled so far' + 'balance' seen in the daily sheets).
    qty_handled = largest 'handled so far' figure seen (lower bound if the last day is missing).
    """
    folder = daily_dir or DAILY_DIR
    rows: list[dict] = []
    for path in sorted(folder.glob("*.json")):
        day = json.loads(path.read_text(encoding="utf-8"))
        for r in day.get("berthed", []):
            rows.append({**r, "report_date": day["report_date"]})
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    d["report_date"] = pd.to_datetime(d["report_date"])
    d["vessel"] = d["vessel_name"].map(_vessel_norm)
    d = d[(d["vessel"] != "") & ~d["vessel"].str.fullmatch(r"-+")]
    d["cargo"] = d["cargo"].fillna("").astype(str).map(_clean_code)
    d["run"] = d["run"].fillna("").astype(str).str.strip().str.upper()
    d = d[(d["cargo"] != "") & ~d["cargo"].str.contains(NON_CARGO)]
    # qty_total is what has been handled SO FAR and qty_balance what is still left, so on any one day
    # total + balance = the ship's whole cargo parcel. The largest such sum over the stay is the parcel size.
    # Using qty_total alone under-counts every ship whose last day is missing from the reports.
    handled = d["qty_total"].map(_qty)
    balance = (d["qty_balance"] if "qty_balance" in d else pd.Series("", index=d.index)).map(_qty)
    d["qty_handled"] = handled
    d["qty_parcel"] = np.where(handled.notna() | balance.notna(), handled.fillna(0) + balance.fillna(0), np.nan)
    d["recv"] = d["receiver_shipper"].fillna("").astype(str).str.strip().str.upper()
    d = d.sort_values("report_date")
    gap = d.groupby(["vessel", "cargo"])["report_date"].diff().dt.days.fillna(NEW_VOYAGE_GAP_DAYS + 1)
    # Number voyages WITHIN each ship + cargo. (A plain cumsum over all rows gave a ship's later days the
    # number of whichever other ship had just started a voyage, splitting one call into several.)
    d["voyage"] = (gap > NEW_VOYAGE_GAP_DAYS).astype(int).groupby([d["vessel"], d["cargo"]]).cumsum()

    def first_value(s: pd.Series) -> str:
        s = s[s != ""]
        return s.mode().iloc[0] if len(s) else ""

    v = d.groupby(["vessel", "cargo", "voyage"]).agg(
        first_seen=("report_date", "min"), last_seen=("report_date", "max"),
        run=("run", first_value), receiver=("recv", first_value),
        qty=("qty_parcel", "max"), qty_handled=("qty_handled", "max"),
        report_days=("report_date", "nunique"),
    ).reset_index()
    fam = v["cargo"].map(classify_cargo)
    v["family"] = [f for f, _ in fam]
    v["direction"] = [dr for _, dr in fam]
    v["month"] = v["first_seen"].dt.strftime("%Y-%m")
    return v


def _share(c: int, total: int) -> float | None:
    return round(c / total * 100, 1) if total else None


def _pattern(coastal_pct: float | None, n: int) -> str:
    if coastal_pct is None or n < MIN_VOYAGES_FOR_PATTERN:
        return "Too few ships to tell"
    lo, hi = MIXED_SPLIT_BAND
    if coastal_pct < lo:
        return "Mostly foreign"
    if coastal_pct > hi:
        return "Mostly coastal"
    return "Mixed"


def _top_customers(s: pd.Series, k: int = 3) -> list[dict]:
    """Most frequent receivers/shippers. Joint entries such as 'HP/IOC/BPC' count once for each name."""
    names: list[str] = []
    for cell in s:
        for part in re.split(r"[/&,]", cell or ""):
            part = re.sub(r"\s+", " ", part).strip()
            if part and part not in {"VARIOUS", "-", "0", "OTHERS"}:
                names.append(part)
    return [{"customer": n, "ships": c} for n, c in Counter(names).most_common(k)]


def _validation(v: pd.DataFrame) -> dict[str, Any]:
    """Compare the whole-port monthly coastal share (this estimate) with the Ministry's official figure."""
    oc = ti.get_overseas_coastal()
    official = {r["month"][:7]: r["coastal_share_pct"] for r in oc["series"] if r.get("coastal_share_pct") is not None}
    fc = v[v["run"].isin(["F", "C"])]
    rows = []
    for month, s in fc.groupby("month"):
        if month not in official:
            continue
        q = s[(s["direction"] != "both") & s["qty"].notna()]
        by_qty = round(q.loc[q["run"] == "C", "qty"].sum() / q["qty"].sum() * 100, 1) if q["qty"].sum() else None
        rows.append({
            "month": month, "official_coastal_share_pct": round(float(official[month]), 1),
            "estimate_by_ships_pct": _share(int((s["run"] == "C").sum()), len(s)),
            "estimate_by_quantity_pct": float(by_qty) if by_qty is not None else None, "ships_counted": int(len(s)),
        })
    out: dict[str, Any] = {"months": rows}
    if rows:
        miss_ships = [abs(r["estimate_by_ships_pct"] - r["official_coastal_share_pct"]) for r in rows if r["estimate_by_ships_pct"] is not None]
        miss_qty = [abs(r["estimate_by_quantity_pct"] - r["official_coastal_share_pct"]) for r in rows if r["estimate_by_quantity_pct"] is not None]
        out["avg_miss_points_by_ships"] = round(float(np.mean(miss_ships)), 1) if miss_ships else None
        out["avg_miss_points_by_quantity"] = round(float(np.mean(miss_qty)), 1) if miss_qty else None
        candidates = {"ships": miss_ships, "quantity": miss_qty}
        candidates = {k: v for k, v in candidates.items() if v}
        better = min(candidates, key=lambda k: float(np.mean(candidates[k])))
        best = round(float(np.mean(candidates[better])), 1)
        out["better_method"] = better
        out["largest_monthly_miss_points"] = round(float(max(candidates[better])), 1)
        out["verdict"] = (
            f"Over {len(rows)} months the estimate of the whole-port coastal share differs from the Ministry's official "
            f"figure by about {best} percentage points on average (largest single month: {out['largest_monthly_miss_points']}). That is close enough to see which cargos are mostly "
            "foreign or coastal, but not to quote exact tonnes."
            if best is not None and best <= VALIDATION_OK_POINTS else
            "The estimate differs a lot from the Ministry's official figure, so treat the pattern with caution."
        )
    else:
        out["verdict"] = "No month overlaps with the Ministry file, so the estimate could not be checked."
    return out


def get_cargo_split() -> dict[str, Any]:
    v = build_voyages()
    if v.empty:
        return {"available": False, "note": "No daily vessel position files found."}
    flagged = v[v["run"].isin(["F", "C"])]
    families = []
    for (family, direction), s in flagged.groupby(["family", "direction"]):
        n = len(s)
        coastal = int((s["run"] == "C").sum())
        q = s[(s["direction"] != "both") & s["qty"].notna()]
        qty_total = float(q["qty"].sum())
        coastal_pct_ships = _share(coastal, n)
        families.append({
            "cargo": family, "direction": direction, "ships": n,
            "foreign_ships": n - coastal, "coastal_ships": coastal,
            "coastal_share_by_ships_pct": coastal_pct_ships,
            "coastal_share_by_quantity_pct": round(float(q.loc[q["run"] == "C", "qty"].sum() / qty_total * 100), 1) if qty_total else None,
            "ships_with_quantity": int(len(q)),
            "direction_known": direction in {"inbound", "outbound", "both"},
            "pattern": _pattern(coastal_pct_ships, n),
            "top_customers": _top_customers(s["receiver"]),
        })
    families.sort(key=lambda r: -r["ships"])
    return {
        "available": True,
        "label": "ESTIMATE from daily vessel reports - not official tonnes",
        "data_source": "data/daily_vessel_position_parsed/ (NMPA Daily Vessel Positions)",
        "period": {"from": v["first_seen"].min().strftime("%Y-%m-%d"), "to": v["last_seen"].max().strftime("%Y-%m-%d")},
        "voyages_total": int(len(v)),
        "voyages_with_run_flag": int(len(flagged)),
        "voyages_mixed_or_blank_flag": int(len(v) - len(flagged)),
        "families": families,
        "validation_against_ministry": _validation(v),
        "how_it_works": [
            "Each ship in NMPA's daily berthed list is counted once per cargo voyage.",
            "The run flag is F = foreign-going, C = coastal. This matches the cargo (imported LPG and coal are all F) and the Ministry's official coastal share.",
            "D after a cargo code = discharged (inbound), L = loaded (outbound).",
            "Ships with a blank or mixed flag are left out of the split.",
        ],
        "limits": [
            "Counts ships, not official tonnes. Quantities are each ship's cargo parcel (handled so far + balance) from the daily sheet and are missing for a few ships.",
            "Covers only the months in the daily reports (about 13 months).",
            "Cargo codes in the daily sheets are short codes and are grouped by hand-written rules, so some groups are approximate.",
        ],
    }
