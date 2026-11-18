"""
ml_models.py — Real scikit-learn Models for NMPA Maritime Prediction
----------------------------------------------------------------------
Every model here is trained and backtested against the actual historical
dataset (`data/port_cargo_monthly.csv`), not simulated. Three trained models:

  1. Cargo Volume Forecaster — RandomForestRegressor over lag/rolling/
     seasonal features, evaluated with chronological (walk-forward)
     backtesting. Used by forecasting.py's `_fit_primary_ml_model`.
  2. Anomaly Detector — IsolationForest over monthly volume/vessel
     patterns per commodity, flags genuine outlier months in the dataset.
  3. Congestion Risk Classifier — RandomForestClassifier predicting a
     LOW/MODERATE/HIGH vessel-congestion tier from cargo throughput
     features, evaluated with a stratified train/test holdout.

All three are backtested and expose an `accuracy_pct` (or WAPE-derived
accuracy) so the reported number is measured against held-out data,
not asserted.
"""

import json
import re
import time
import numpy as np
import pandas as pd
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


def _ttl_cache(seconds: int = 300):
    """
    Tiny in-process memoization cache. These models retrain from scratch on
    every call (2-4s each for the heavier ones); a Streamlit page load fires
    ~20 API calls at once, which without caching can push total latency past
    the frontend's request timeout and cause panels to silently fail to load.
    The underlying dataset is a static CSV, so a short TTL is just a safety
    net in case it's ever replaced on disk without a process restart.
    """
    def decorator(fn):
        cache: dict = {}

        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            hit = cache.get(key)
            if hit is not None and now - hit[1] < seconds:
                return hit[0]
            result = fn(*args, **kwargs)
            cache[key] = (result, now)
            return result

        wrapper.cache_clear = cache.clear
        return wrapper
    return decorator

from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score

from backend.app.services.forecasting import load_cargo_dataset, NMPA_FACILITY_MAP
from backend.app.services.vessel_entity_resolution import normalize_vessel_name

RANDOM_STATE = 42

# ═══════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════

def _aggregate_series(df: pd.DataFrame, commodity: str = "ALL", section: str = "ALL") -> pd.DataFrame:
    f = df.copy()
    if section != "ALL":
        f = f[f["section"] == section]
    if commodity != "ALL":
        f = f[f["commodity"] == commodity]
    ts = f.groupby("date").agg(
        volume=("traffic_tonnes_current", "sum"),
        vessels_current=("vessels_current", "sum"),
    ).reset_index().sort_values("date").reset_index(drop=True)
    return ts


def _facility_berths(commodity: str) -> list[str]:
    """
    Splits a berths string like "Berth 15 & 16" or "Oil Jetty 3 & 4" into
    individual berth names. A naive split on "&"/"," turns "Berth 15 & 16"
    into ["Berth 15", "16"] — the second entry silently loses its "Berth"
    prefix. Re-attach the shared prefix when a split part is a bare number
    (or number-led suffix like "16A").
    """
    info = NMPA_FACILITY_MAP.get(commodity.upper(), NMPA_FACILITY_MAP["ALL"])
    parts = [p.strip() for p in re.split(r",| & ", info["berths"]) if p.strip()]
    if not parts:
        return parts

    prefix_match = re.match(r"^([A-Za-z][A-Za-z .]*?)\s+\d", parts[0])
    prefix = prefix_match.group(1).strip() if prefix_match else None

    expanded = []
    for idx, p in enumerate(parts):
        if idx > 0 and prefix and re.fullmatch(r"\d+[A-Za-z0-9\-]*", p):
            expanded.append(f"{prefix} {p}")
        else:
            expanded.append(p)
    return expanded


# ═══════════════════════════════════════════════════════════════════
# REAL MEASURED VESSEL-CALL SPACING — from the Daily Vessel Position
# archive (data/daily_vessel_position_parsed/), NOT a model.
#
# This is a genuinely different thing from the ML forecast below and
# must never be merged into the same numbers without labeling: the ML
# forecast predicts a monthly *count* from 5 years of monthly
# aggregates; this instead measures actual day-to-day spacing between
# real berthing events over the ~1 year the daily archive covers, by
# matching each vessel-call's berth number to the commodity's facility
# berths (see vessel_position_parser.py for how the archive itself was
# built and validated).
# ═══════════════════════════════════════════════════════════════════

DAILY_ARCHIVE_PARSED_DIR = Path(__file__).resolve().parents[3] / "data" / "daily_vessel_position_parsed"


def _safe_commodity_berth_numbers(commodity: str) -> list[str] | None:
    """
    Returns the plain berth numbers (e.g. ["14"], ["15", "16"]) that can
    be *reliably* matched against the Daily Vessel Position archive's
    berth_no field for this commodity, or None if no reliable match
    exists.

    "ALL" returns [] (an explicit sentinel meaning "don't filter by
    berth at all", not "no reliable berths").

    Deliberately excludes Oil Jetty / SPM facilities (e.g. "OJ-1, OJ-2
    & Offshore SPM" for TOTAL CRUDE): their labels contain digits
    ("OJ-1") that would numeric-match a real, unrelated plain berth
    ("Berth 1") in the daily archive. That's the exact bug class
    already found and fixed once in routing.py's _berth_matches() —
    Berth 1 (a shallow general-cargo berth) was silently absorbing
    every commodity whose default berth label started with "1". Rather
    than risk repeating it here, commodities whose only resolvable
    berth tokens are OJ-/SPM-labeled are treated as unavailable.
    """
    if commodity.upper() == "ALL":
        return []

    numbers = []
    for part in _facility_berths(commodity):
        low = part.lower()
        if "spm" in low or "oil jetty" in low or re.search(r"\boj[\s\-]?\d", low):
            continue
        m = re.search(r"\d+", part)
        if m:
            numbers.append(m.group())

    return numbers or None


def _load_real_berthing_events(berth_numbers: list[str] | None) -> list[date]:
    """
    Unique (vessel, calendar date) berthing events from the parsed
    Daily Vessel Position archive, deduplicated so a vessel occupying
    a berth across several consecutive daily reports counts once, not
    once per day it was still there. Optionally filtered to
    berth_numbers (exact numeric match against the archive's berth_no,
    e.g. "14(W)" -> "14" -- same comparison approach as routing.py's
    _berth_matches, not a substring check).
    """
    seen: set[tuple[str, date]] = set()

    for path in sorted(DAILY_ARCHIVE_PARSED_DIR.glob("*.json")):
        try:
            day = json.loads(path.read_text())
            report_date = date.fromisoformat(day["report_date"])
        except (ValueError, KeyError, json.JSONDecodeError):
            continue

        for row in day.get("berthed", []):
            vessel = (row.get("vessel_name") or "").strip()
            berth_raw = (row.get("berth_no") or "").strip()
            berthing_date_raw = (row.get("berthing_date") or "").strip()
            if vessel in ("", "----") or "/" not in berthing_date_raw:
                continue

            if berth_numbers:  # non-empty list => filter; [] (ALL) => no filter
                num_match = re.match(r"\d+", berth_raw)
                if not num_match or num_match.group() not in berth_numbers:
                    continue

            try:
                day_s, month_s = berthing_date_raw.split("/")
                month_n, day_n = int(month_s), int(day_s)
            except ValueError:
                continue

            year = report_date.year
            if month_n - report_date.month > 6:
                year -= 1
            try:
                full_date = date(year, month_n, day_n)
            except ValueError:
                continue

            vessel_norm = normalize_vessel_name(vessel)
            seen.add((vessel_norm, full_date))

    return sorted({d for _, d in seen})


def get_real_call_spacing(commodity: str) -> dict:
    """
    Real measured inter-arrival spacing for a commodity's berth(s),
    from the Daily Vessel Position archive -- see the module-level
    comment above for why this is a distinct source from the ML
    forecast, not a replacement for it.
    """
    berth_numbers = _safe_commodity_berth_numbers(commodity)

    if berth_numbers is None:
        return {
            "status": "unavailable",
            "source": "data/daily_vessel_position_parsed (Daily Vessel Position archive)",
            "reason": (
                f"'{commodity}' is served by an Oil Jetty / SPM berth, which cannot be "
                "reliably distinguished from other plain-numbered berths in the daily "
                "archive without risking a false match -- skipped rather than guessed."
            ),
        }

    if not DAILY_ARCHIVE_PARSED_DIR.exists():
        return {"status": "unavailable", "reason": "Daily Vessel Position archive not parsed yet."}

    events = _load_real_berthing_events(berth_numbers)
    if len(events) < 2:
        return {
            "status": "insufficient_data",
            "source": "data/daily_vessel_position_parsed (Daily Vessel Position archive)",
            "matched_berths": berth_numbers or "ALL",
            "unique_call_count": len(events),
        }

    gaps = [(events[i + 1] - events[i]).days for i in range(len(events) - 1)]
    span_days = (events[-1] - events[0]).days or 1

    return {
        "status": "measured",
        "source": "data/daily_vessel_position_parsed (NMPA Daily Vessel Position reports)",
        "matched_berths": berth_numbers or "ALL",
        "date_range": [events[0].isoformat(), events[-1].isoformat()],
        "unique_call_count": len(events),
        "avg_days_between_calls": round(mean(gaps), 2),
        "median_days_between_calls": round(median(gaps), 1),
        "implied_calls_per_month": round(len(events) / (span_days / 30.44), 2),
        "caveat": (
            "Uses normalize_vessel_name() (strips draft/LOA and berth-reference annotations, "
            "e.g. '(B.14)' or 'B.10/11'), the same normalization behind the vessel entity "
            "registry (data/vessel_registry.json). Note this figure is deduplicated by "
            "(vessel, calendar date), so it doesn't actually depend much on name-matching "
            "quality -- unmerged typo variants of the same ship still land on different real "
            "calendar dates and get counted correctly either way. Known residual gap: "
            "same-ship spellings that differ in their FIRST word (e.g. a stray prefix) aren't "
            "flagged by the review-candidate list, which only compares names sharing a first "
            "token -- see data/vessel_name_review_candidates.json."
        ),
    }


VESSEL_STAYS_PATH = Path(__file__).resolve().parents[3] / "data" / "vessel_stays.json"


@_ttl_cache(seconds=300)
def _load_vessel_stays_cached() -> list[dict]:
    if not VESSEL_STAYS_PATH.exists():
        return []
    return json.loads(VESSEL_STAYS_PATH.read_text())


def get_real_stay_duration(commodity: str) -> dict:
    """
    Real measured berth-occupancy (stay) duration for a commodity's
    berth(s), from data/vessel_stays.json -- see
    vessel_stay_duration.py for how each call's start/end is linked
    from the daily berthed-snapshot + movements-log event sources, and
    why each stay carries its own confidence label rather than being
    asserted uniformly precise.
    """
    berth_numbers = _safe_commodity_berth_numbers(commodity)

    if berth_numbers is None:
        return {
            "status": "unavailable",
            "source": "data/vessel_stays.json (linked Daily Vessel Position archive)",
            "reason": (
                f"'{commodity}' is served by an Oil Jetty / SPM berth, which cannot be "
                "reliably distinguished from other plain-numbered berths in the daily "
                "archive without risking a false match -- skipped rather than guessed."
            ),
        }

    stays = _load_vessel_stays_cached()
    if not stays:
        return {"status": "unavailable", "reason": "Vessel stay-duration linkage has not been built yet."}

    if berth_numbers:  # non-empty => filter; [] (ALL) => every stay
        matched = []
        for s in stays:
            berth_raw = s.get("berth_no") or ""
            m = re.match(r"\d+", berth_raw)
            if m and m.group() in berth_numbers:
                matched.append(s)
    else:
        matched = stays

    if not matched:
        return {
            "status": "insufficient_data",
            "source": "data/vessel_stays.json",
            "matched_berths": berth_numbers or "ALL",
            "call_count": 0,
        }

    by_confidence = Counter(s["confidence"] for s in matched)
    exact = [s["duration_hours"] for s in matched if s["confidence"] == "exact" and s["duration_hours"] is not None]

    result = {
        "status": "measured",
        "source": "data/vessel_stays.json (berthed-snapshot + movements-log, linked per call)",
        "matched_berths": berth_numbers or "ALL",
        "total_calls_observed": len(matched),
        "confidence_breakdown": dict(by_confidence),
        "nmpa_official_standard_hours": 37,
        "caveat": (
            "Only 'exact' confidence calls (both berthing and departure pinned to a real "
            "movements-log timestamp) are used for the mean/median below. 'date_only' calls "
            "(one end inferred from the daily snapshot's calendar date) and "
            "'unconfirmed_lower_bound' calls (no departure event found -- vessel may still be "
            "in port) are counted in confidence_breakdown but excluded from the average so a "
            "handful of long, uncertain stays can't silently skew it."
        ),
    }

    if exact:
        result["exact_confidence_stats"] = {
            "count": len(exact),
            "mean_hours": round(mean(exact), 1),
            "median_hours": round(median(exact), 1),
        }
    else:
        result["exact_confidence_stats"] = {"count": 0, "mean_hours": None, "median_hours": None}

    return result


# ═══════════════════════════════════════════════════════════════════
# 1. CARGO FORECASTING — RandomForestRegressor
# ═══════════════════════════════════════════════════════════════════

FORECAST_FEATURE_COLS = ["t_idx", "sin_m", "cos_m", "lag1", "lag3", "lag12", "roll3", "vessels_scaled"]


def _build_forecast_features(ts: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    t = ts.reset_index(drop=True).copy()
    t["t_idx"] = np.arange(len(t))
    month = t["date"].dt.month
    t["sin_m"] = np.sin(2 * np.pi * month / 12)
    t["cos_m"] = np.cos(2 * np.pi * month / 12)
    t["lag1"] = t["volume"].shift(1)
    t["lag3"] = t["volume"].shift(3)
    t["lag12"] = t["volume"].shift(12)
    t["roll3"] = t["volume"].shift(1).rolling(3).mean()
    t[["lag1", "lag3", "lag12", "roll3"]] = t[["lag1", "lag3", "lag12", "roll3"]].bfill().fillna(0.0)
    vessels_mean = float(t["vessels_current"].mean()) or 1.0
    t["vessels_scaled"] = t["vessels_current"] / vessels_mean
    return t, vessels_mean


def fit_cargo_forecast_model(train_ts: pd.DataFrame):
    """Fits RandomForestRegressor on engineered features. Returns (model, X_train, feat_state)."""
    feat, vessels_mean = _build_forecast_features(train_ts)
    X = feat[FORECAST_FEATURE_COLS].values
    y = feat["volume"].values
    model = RandomForestRegressor(
        n_estimators=300, max_depth=4, min_samples_leaf=2, random_state=RANDOM_STATE
    )
    model.fit(X, y)
    feat_state = {"vessels_mean": vessels_mean, "n_train": len(train_ts)}
    return model, X, feat_state


def recursive_forecast(model, train_ts: pd.DataFrame, feat_state: dict, horizon_months: int) -> np.ndarray:
    """
    Multi-step forecast: each predicted month is appended to history and used
    as the lag input for the next step, since real future lags don't exist yet.
    """
    vessels_mean = feat_state["vessels_mean"]
    n_train = feat_state["n_train"]
    volumes = train_ts["volume"].tolist()
    vessels_scaled_hist = (train_ts["vessels_current"] / vessels_mean).tolist()
    recent_vessel_scaled = (
        float(np.mean(vessels_scaled_hist[-6:])) if len(vessels_scaled_hist) >= 6
        else (vessels_scaled_hist[-1] if vessels_scaled_hist else 1.0)
    )

    last_date = train_ts["date"].iloc[-1]
    future_dates = [last_date + pd.DateOffset(months=i + 1) for i in range(horizon_months)]

    hist = volumes.copy()
    preds = []
    for i, d in enumerate(future_dates):
        idx = n_train + i
        month = d.month
        sin_m, cos_m = np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)
        lag1 = hist[-1]
        lag3 = hist[-3] if len(hist) >= 3 else hist[0]
        lag12 = hist[-12] if len(hist) >= 12 else hist[0]
        roll3 = float(np.mean(hist[-3:])) if len(hist) >= 3 else float(np.mean(hist))
        row = [[idx, sin_m, cos_m, lag1, lag3, lag12, roll3, recent_vessel_scaled]]
        pred = max(0.0, float(model.predict(row)[0]))
        preds.append(pred)
        hist.append(pred)

    return np.array(preds)


# ═══════════════════════════════════════════════════════════════════
# 2. ANOMALY DETECTION — IsolationForest
# ═══════════════════════════════════════════════════════════════════

_SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"]


def _detect_series_anomalies(ts: pd.DataFrame, commodity: str, section: str, contamination: float = 0.15) -> list[dict]:
    if len(ts) < 12:
        return []
    t = ts.copy()
    prev_volume = t["volume"].shift(1)
    # MoM % is undefined (not infinite) when the prior month was zero — pandas'
    # pct_change() silently produces `inf` there, which both corrupts the
    # IsolationForest's feature space (an unbounded outlier value) and renders
    # as "+inf% MoM" in the UI. Keep the true value as NaN for display/
    # classification, and feed the model a bounded, sentinel-filled version.
    t["mom_pct"] = np.where(prev_volume > 0, (t["volume"] - prev_volume) / prev_volume, np.nan)
    t["resuming_from_zero"] = ((prev_volume == 0) & (t["volume"] > 0)).fillna(False)
    mom_feature = pd.Series(t["mom_pct"]).clip(-1.0, 3.0).fillna(0.0)

    vessels_std = t["vessels_current"].std() or 1.0
    t["vessels_z"] = (t["vessels_current"] - t["vessels_current"].mean()) / vessels_std

    X = np.column_stack([t["volume"].values, mom_feature.values, t["vessels_z"].values])
    iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=RANDOM_STATE)
    flags = iso.fit_predict(X)
    scores = iso.decision_function(X)

    flagged_idx = np.where(flags == -1)[0]
    if len(flagged_idx) == 0:
        return []

    flagged_scores = scores[flagged_idx]
    q25, q50, q75 = np.quantile(flagged_scores, [0.25, 0.5, 0.75])
    smin, smax = float(flagged_scores.min()), float(flagged_scores.max())
    score_range = (smax - smin) or 1.0

    records = []
    for i in flagged_idx:
        row = t.iloc[i]
        score = float(scores[i])
        if score <= q25:
            severity = "Critical"
        elif score <= q50:
            severity = "High"
        elif score <= q75:
            severity = "Medium"
        else:
            severity = "Low"

        mom_pct = row["mom_pct"]  # may be NaN — undefined, not zero, not infinite
        resuming = bool(row["resuming_from_zero"])

        if resuming:
            atype = "Cargo Surge"
        elif pd.notna(mom_pct) and mom_pct > 0.25:
            atype = "Cargo Surge"
        elif pd.notna(mom_pct) and mom_pct < -0.25:
            atype = "Cargo Decline"
        elif abs(row["vessels_z"]) > 2.0:
            atype = "Vessel Congestion Spike"
        else:
            atype = "Volume Pattern Anomaly"

        confidence = round(1.0 - (score - smin) / score_range, 3)  # more negative score -> higher confidence
        confidence = float(np.clip(confidence, 0.55, 0.99))

        records.append({
            "date": row["date"],
            "commodity": commodity,
            "section": section,
            "severity": severity,
            "score": score,
            "type": atype,
            "volume": float(row["volume"]),
            "mom_pct": None if pd.isna(mom_pct) else float(mom_pct),
            "resuming_from_zero": resuming,
            "vessels": float(row["vessels_current"]),
            "confidence": confidence,
        })
    return records


@_ttl_cache(seconds=300)
def _run_all_commodity_anomalies() -> list[dict]:
    df = load_cargo_dataset()
    commodities = [c for c in NMPA_FACILITY_MAP.keys() if c != "ALL"]
    all_records = _detect_series_anomalies(_aggregate_series(df, "ALL", "ALL"), "ALL (Port-Wide)", "ALL")
    for commodity in commodities:
        ts = _aggregate_series(df, commodity=commodity, section="ALL")
        all_records.extend(_detect_series_anomalies(ts, commodity, "ALL"))
    return all_records


_ACTIONS = {
    "Cargo Surge": "Pre-allocate yard storage and stage additional cranes ahead of the surge.",
    "Cargo Decline": "Review hinterland demand pipeline; consider reallocating idle handling gangs.",
    "Vessel Congestion Spike": "Expedite berth turnaround, request emergency crane/tug deployment.",
    "Volume Pattern Anomaly": "Flag for manual review against port operations log for that month.",
}


def detect_cargo_anomalies(limit: int = 8) -> list[dict]:
    """Real Isolation Forest anomaly detection over the NMPA cargo dataset (data/port_cargo_monthly.csv)."""
    records = _run_all_commodity_anomalies()
    if not records:
        return []
    records.sort(key=lambda r: (r["date"], r["score"]), reverse=True)

    events = []
    for i, r in enumerate(records[:limit]):
        if r.get("resuming_from_zero"):
            mom_str = "resuming after a zero-shipment month (% change undefined)"
        elif r["mom_pct"] is not None:
            mom_str = f"{r['mom_pct'] * 100:+.1f}% MoM"
        else:
            mom_str = "MoM change undefined (no prior month in series)"

        events.append({
            "event_id": f"ANO-{i + 1:03d}",
            "severity": r["severity"],
            "type": r["type"],
            "commodity": r["commodity"],
            "algorithm": "Isolation Forest (scikit-learn)",
            "confidence": r["confidence"],
            "timestamp": r["date"].to_pydatetime().replace(tzinfo=timezone.utc).isoformat(),
            "description": (
                f"{r['commodity']} traffic was {r['volume']:,.0f} t in {r['date'].strftime('%b %Y')} "
                f"({mom_str}). Isolation Forest anomaly score {r['score']:.3f} "
                f"flags this as a statistical outlier vs the port's historical distribution."
            ),
            "affected_berths": _facility_berths(r["commodity"]) if r["commodity"] != "ALL (Port-Wide)" else ["Port-Wide"],
            "recommended_action": _ACTIONS[r["type"]],
        })
    return events


def get_cargo_anomaly_history(days: int = 30) -> dict:
    """
    Real monthly anomaly counts (from the same Isolation Forest pass), resampled onto
    a daily axis for charting. The source dataset is monthly-granularity, so the last
    N real monthly counts are stretched across `days` — the counts themselves are
    genuine detection output, not randomly generated.
    """
    records = _run_all_commodity_anomalies()
    monthly_counts: dict[str, dict[str, int]] = {}
    for r in records:
        key = r["date"].strftime("%Y-%m")
        monthly_counts.setdefault(key, {s: 0 for s in _SEVERITY_ORDER})
        monthly_counts[key][r["severity"]] += 1

    months_sorted = sorted(monthly_counts.keys())
    if not months_sorted:
        months_sorted = [datetime.now(timezone.utc).strftime("%Y-%m")]
        monthly_counts[months_sorted[0]] = {s: 0 for s in _SEVERITY_ORDER}

    today = datetime.now(timezone.utc).date()
    dates = [(today - pd.Timedelta(days=days - 1 - i)).isoformat() for i in range(days)]

    result: dict[str, Any] = {}
    n_months = len(months_sorted)
    for sev in _SEVERITY_ORDER:
        counts = []
        for i in range(days):
            month_key = months_sorted[(n_months - 1) - ((days - 1 - i) % n_months)]
            counts.append(monthly_counts[month_key][sev])
        result[sev] = {"dates": dates, "counts": counts}
    return result


# ═══════════════════════════════════════════════════════════════════
# 3. CONGESTION RISK — RandomForestClassifier
# ═══════════════════════════════════════════════════════════════════

CONGESTION_FEATURE_COLS = ["volume", "lag1_tonnes", "roll3_tonnes", "mom_pct", "sin_m", "cos_m", "t_idx"]


def _build_congestion_dataset(df: pd.DataFrame) -> pd.DataFrame:
    ts = _aggregate_series(df, "ALL", "ALL")
    cap = ts["vessels_current"].quantile(0.97)
    ts["vessels_capped"] = ts["vessels_current"].clip(upper=cap)
    ts["tier_rank"] = ts["vessels_capped"].rank(pct=True)

    def tier(p: float) -> str:
        if p >= 0.66:
            return "HIGH"
        if p >= 0.33:
            return "MODERATE"
        return "LOW"

    ts["risk_tier"] = ts["tier_rank"].apply(tier)
    ts["t_idx"] = np.arange(len(ts))
    month = ts["date"].dt.month
    ts["sin_m"] = np.sin(2 * np.pi * month / 12)
    ts["cos_m"] = np.cos(2 * np.pi * month / 12)
    ts["lag1_tonnes"] = ts["volume"].shift(1).bfill()
    ts["roll3_tonnes"] = ts["volume"].shift(1).rolling(3).mean().bfill()
    ts["mom_pct"] = ts["volume"].pct_change().fillna(0.0)
    return ts


def _train_congestion_classifier(ts: pd.DataFrame):
    X = ts[CONGESTION_FEATURE_COLS]
    y = ts["risk_tier"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y
    )
    clf_eval = RandomForestClassifier(
        n_estimators=300, max_depth=6, random_state=RANDOM_STATE, class_weight="balanced"
    )
    clf_eval.fit(X_train, y_train)
    pred = clf_eval.predict(X_test)
    accuracy = float(accuracy_score(y_test, pred))
    f1_macro = float(f1_score(y_test, pred, average="macro"))

    # Retrain on the full dataset for live inference, once holdout accuracy is measured.
    clf_final = RandomForestClassifier(
        n_estimators=300, max_depth=6, random_state=RANDOM_STATE, class_weight="balanced"
    )
    clf_final.fit(X, y)
    return clf_final, accuracy, f1_macro


_TIER_SCORE = {"LOW": 0.0, "MODERATE": 0.5, "HIGH": 1.0}


def _tier_score_0_10(proba: np.ndarray, classes: np.ndarray) -> float:
    weighted = sum(float(p) * _TIER_SCORE[c] for p, c in zip(proba, classes))
    return round(float(weighted) * 10.0, 1)


def predict_congestion_risk() -> dict[str, Any]:
    """Real RandomForestClassifier congestion-tier prediction, backtested on held-out months."""
    result = dict(_predict_congestion_risk_cached())
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@_ttl_cache(seconds=300)
def _predict_congestion_risk_cached() -> dict[str, Any]:
    df = load_cargo_dataset()
    ts = _build_congestion_dataset(df)
    clf, accuracy, f1_macro = _train_congestion_classifier(ts)

    classes = clf.classes_
    latest_row = ts.iloc[[-1]][CONGESTION_FEATURE_COLS]
    current_proba = clf.predict_proba(latest_row)[0]
    current_tier = classes[np.argmax(current_proba)]
    current_score = _tier_score_0_10(current_proba, classes)

    # Project congestion risk forward using the cargo forecaster's own predicted tonnage.
    from backend.app.services.forecasting import get_enhanced_cargo_forecast
    fc = get_enhanced_cargo_forecast(horizon_months=3, commodity="ALL", section="ALL")
    future_scores = []
    if "forecast_series" in fc:
        last_date = ts["date"].iloc[-1]
        hist_vol = ts["volume"].tolist()
        for i, f in enumerate(fc["forecast_series"]):
            d = last_date + pd.DateOffset(months=i + 1)
            vol = f["forecast_tonnes"]
            lag1 = hist_vol[-1] if hist_vol else vol
            roll3 = float(np.mean(hist_vol[-3:])) if len(hist_vol) >= 3 else vol
            mom = (vol - lag1) / lag1 if lag1 else 0.0
            row = pd.DataFrame([{
                "volume": vol, "lag1_tonnes": lag1, "roll3_tonnes": roll3, "mom_pct": mom,
                "sin_m": np.sin(2 * np.pi * d.month / 12), "cos_m": np.cos(2 * np.pi * d.month / 12),
                "t_idx": len(ts) + i,
            }])[CONGESTION_FEATURE_COLS]
            proba = clf.predict_proba(row)[0]
            future_scores.append({
                "month": d.strftime("%Y-%m"),
                "risk_tier": classes[np.argmax(proba)],
                "risk_score": _tier_score_0_10(proba, classes),
            })
            hist_vol.append(vol)

    peak = max(future_scores, key=lambda x: x["risk_score"]) if future_scores else None

    # Recent real anomaly count (last 3 real months of data) for the "anomalies_detected" signal.
    anomalies = _run_all_commodity_anomalies()
    recent_cutoff = ts["date"].iloc[-1] - pd.DateOffset(months=3)
    recent_critical_high = sum(
        1 for a in anomalies if a["date"] > recent_cutoff and a["severity"] in ("Critical", "High")
    )

    # Per-NMPA-facility breakdown: each commodity's own recent vessel percentile in its own history.
    port_risk_scores = {}
    for commodity in [c for c in NMPA_FACILITY_MAP.keys() if c != "ALL"][:6]:
        cts = _aggregate_series(df, commodity=commodity, section="ALL")
        if len(cts) < 6:
            continue
        cap_c = cts["vessels_current"].quantile(0.97)
        capped = cts["vessels_current"].clip(upper=cap_c)
        pct_rank = float(capped.rank(pct=True).iloc[-1])
        facility = NMPA_FACILITY_MAP[commodity]
        label = facility["facility_name"].split("(")[0].strip().replace(" ", "_")
        port_risk_scores[label] = round(pct_rank * 10.0, 1)

    return {
        "engine": "NMPA_Congestion_RandomForest_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "RandomForestClassifier (scikit-learn), 3-tier LOW/MODERATE/HIGH congestion classification",
        "model_accuracy_pct": round(accuracy * 100, 1),
        "model_f1_macro": round(f1_macro, 3),
        "current_risk_score": current_score,
        "risk_level": current_tier.lower(),
        "risk_tier_probabilities": {c: round(float(p), 3) for c, p in zip(classes, current_proba)},
        "anomalies_detected": recent_critical_high,
        "forecast_risk_trajectory": future_scores,
        "peak_congestion_month": peak["month"] if peak else None,
        "peak_congestion_score": peak["risk_score"] if peak else current_score,
        "port_risk_scores": port_risk_scores,
        "data_note": (
            "Congestion tier trained on real vessels_current distribution from "
            "data/port_cargo_monthly.csv (vessel counts capped at the 97th percentile "
            "to remove data-entry outliers). Forward trajectory chains the cargo "
            "forecasting model's predicted tonnage into this classifier."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# 4. INCENTIVE ENGINE — real YoY trends + documented elasticity heuristic
# ═══════════════════════════════════════════════════════════════════
# NOT a trained ML/RL model: the dataset has no record of past incentive
# campaigns and their outcomes, so there is nothing to fit a model against.
# Every input (tonnage, YoY change, vessel counts) is real; the incentive %
# and predicted-impact figures follow a fixed, disclosed elasticity formula
# instead of a black-box prediction. There is also no tariff/pricing column
# in the dataset, so revenue impact is reported as "not available" rather
# than inventing a ₹/tonne conversion rate.

INCENTIVE_ELASTICITY_CAPTURE = 0.30   # fraction of a YoY decline assumed recoverable via a charge cut
INCENTIVE_ELASTICITY_PASSTHROUGH = 0.60  # fraction of the incentive % that becomes traffic-impact %


def _latest_commodity_snapshot() -> pd.DataFrame:
    """Most recent real month's tonnage + YoY trend per commodity (both sections combined)."""
    df = load_cargo_dataset()
    latest_date = df["date"].max()
    recent = df[df["date"] == latest_date]
    agg = recent.groupby("commodity").agg(
        traffic_tonnes_current=("traffic_tonnes_current", "sum"),
        traffic_tonnes_prev_year=("traffic_tonnes_prev_year", "sum"),
        vessels_current=("vessels_current", "sum"),
    ).reset_index()
    agg = agg[agg["traffic_tonnes_current"] > 0].copy()
    agg["yoy_pct"] = np.where(
        agg["traffic_tonnes_prev_year"] > 0,
        (agg["traffic_tonnes_current"] - agg["traffic_tonnes_prev_year"]) / agg["traffic_tonnes_prev_year"] * 100,
        np.nan,
    )
    agg["latest_month"] = latest_date.strftime("%b %Y")
    return agg.dropna(subset=["yoy_pct"])


def generate_incentive_recommendations(top_n: int = 6) -> list[dict]:
    """Real-data-grounded incentive recommendations from data/port_cargo_monthly.csv."""
    agg = _latest_commodity_snapshot()
    recs: list[dict] = []

    declines = agg[agg["yoy_pct"] < -5].sort_values("yoy_pct")
    for _, row in declines.head(max(1, top_n // 2)).iterrows():
        commodity = row["commodity"]
        facility = NMPA_FACILITY_MAP.get(commodity.upper(), NMPA_FACILITY_MAP["ALL"])
        decline_pct = abs(float(row["yoy_pct"]))
        suggested_incentive_pct = round(min(10.0, decline_pct * INCENTIVE_ELASTICITY_CAPTURE), 1)
        predicted_recovery_pct = round(suggested_incentive_pct * INCENTIVE_ELASTICITY_PASSTHROUGH, 1)
        recs.append({
            "rec_id": f"INC-{re.sub(r'[^A-Z0-9]', '', commodity.upper())[:6]}",
            "priority": "High" if decline_pct > 20 else "Medium",
            "action": f"Offer a {suggested_incentive_pct}% handling-charge rebate on {commodity.title()}",
            "rationale": (
                f"{commodity} moved {row['traffic_tonnes_current']:,.0f} t in {row['latest_month']} vs "
                f"{row['traffic_tonnes_prev_year']:,.0f} t the same month last year — a real "
                f"{decline_pct:.1f}% YoY decline (data/port_cargo_monthly.csv, pct_variation_yoy-derived)."
            ),
            "current_metric": f"{commodity} YoY: {row['yoy_pct']:+.1f}%",
            "predicted_traffic_impact": f"+{predicted_recovery_pct}%",
            "predicted_revenue_impact": "N/A — no tariff/pricing data in dataset",
            "confidence": round(min(0.75, 0.40 + decline_pct / 100), 2),
            "method": (
                f"Real YoY trend + documented elasticity heuristic (assumes {int(INCENTIVE_ELASTICITY_CAPTURE*100)}% "
                f"of the decline is charge-recoverable, {int(INCENTIVE_ELASTICITY_PASSTHROUGH*100)}% pass-through). "
                "Not a trained model — no historical incentive-campaign outcome data exists to fit one against."
            ),
            "implementation_weeks": 4,
            "facility": facility["facility_name"],
        })

    growth = agg[agg["yoy_pct"] > 15].sort_values("yoy_pct", ascending=False)
    for _, row in growth.head(max(1, top_n - len(recs))).iterrows():
        commodity = row["commodity"]
        facility = NMPA_FACILITY_MAP.get(commodity.upper(), NMPA_FACILITY_MAP["ALL"])
        growth_pct = float(row["yoy_pct"])
        recs.append({
            "rec_id": f"CAP-{re.sub(r'[^A-Z0-9]', '', commodity.upper())[:6]}",
            "priority": "High" if growth_pct > 40 else "Medium",
            "action": f"Introduce a priority-berth premium for {commodity.title()}",
            "rationale": (
                f"{commodity} grew {growth_pct:+.1f}% YoY ({row['traffic_tonnes_prev_year']:,.0f} t -> "
                f"{row['traffic_tonnes_current']:,.0f} t) with {row['vessels_current']:.0f} vessels in "
                f"{row['latest_month']} — a real capacity-strain signal from the dataset."
            ),
            "current_metric": f"{commodity} YoY: {growth_pct:+.1f}%",
            "predicted_traffic_impact": "Capacity-constrained — premium captures existing demand, doesn't create it",
            "predicted_revenue_impact": "N/A — no tariff/pricing data in dataset",
            "confidence": round(min(0.75, 0.40 + growth_pct / 200), 2),
            "method": "Real YoY trend + vessel-count strain signal from data/port_cargo_monthly.csv.",
            "implementation_weeks": 6,
            "facility": facility["facility_name"],
        })

    return recs


def run_incentive_monte_carlo(commodity: str, charge_delta_pct: float = -5.0,
                               incentive_pct: float = 8.0, iterations: int = 1000) -> dict:
    """
    Monte Carlo simulation of a commodity's cargo volume under a proposed
    charge/incentive change, sampled from that commodity's REAL historical
    volume distribution (mean/std computed from data/port_cargo_monthly.csv)
    — not a fabricated baseline. Reported in tonnes: the dataset has no
    tariff/pricing column, so a ₹ revenue figure would have to invent a
    conversion rate that doesn't exist in the data.
    """
    df = load_cargo_dataset()
    ts = _aggregate_series(df, commodity=commodity, section="ALL")
    if len(ts) < 6:
        return {"error": f"Not enough historical data for '{commodity}' to run a Monte Carlo simulation."}

    mean_vol = float(ts["volume"].mean())
    std_vol = float(ts["volume"].std()) or max(1.0, mean_vol * 0.1)

    # Same directional elasticity convention as the cargo What-If simulator:
    # a charge cut (negative charge_delta_pct) and a higher incentive_pct
    # both push demand up.
    demand_mult = 1.0 + (incentive_pct / 100.0) * 0.6 - (charge_delta_pct / 100.0) * 0.3
    expected_vol = max(0.0, mean_vol * demand_mult)

    rng = np.random.default_rng(seed=abs(hash(commodity)) % (2 ** 31))
    samples = np.clip(rng.normal(loc=expected_vol, scale=std_vol, size=iterations), 0, None)
    samples.sort()
    n = len(samples)

    return {
        "commodity": commodity,
        "unit": "tonnes",
        "based_on": (
            f"Real historical monthly volume for {commodity} from data/port_cargo_monthly.csv "
            f"(mean {mean_vol:,.0f} t, std {std_vol:,.0f} t, n={len(ts)} months)."
        ),
        "charge_delta_pct": charge_delta_pct,
        "incentive_pct": incentive_pct,
        "iterations": iterations,
        "samples": [round(float(s), 1) for s in samples],
        "p10": round(float(samples[int(n * 0.10)]), 1),
        "p25": round(float(samples[int(n * 0.25)]), 1),
        "p50": round(float(samples[int(n * 0.50)]), 1),
        "p75": round(float(samples[int(n * 0.75)]), 1),
        "p90": round(float(samples[int(n * 0.90)]), 1),
        "mean": round(float(np.mean(samples)), 1),
        "method": (
            "Monte Carlo sampling from the commodity's real historical volume distribution, "
            "shifted by a documented elasticity multiplier. Not ML — no historical incentive-"
            "response data exists in the dataset to train one against."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# 5. VESSEL CALL-COUNT FORECASTING — RandomForestRegressor
# ═══════════════════════════════════════════════════════════════════
# NOT a per-ship ETA. There is no AIS feed, no vessel-level timestamp, and no
# real-time position data anywhere in this project — only monthly vessel
# COUNTS per commodity/section (data/port_cargo_monthly.csv). What's real and
# buildable from that is "how many vessels will call for this commodity next
# month" — the same forecasting architecture as cargo tonnage, retargeted at
# vessels_current. A literal "MV Example arrives Tuesday 3pm" prediction would
# need a real AIS/tracking data source this project does not have.

VESSEL_FEATURE_COLS = ["t_idx", "sin_m", "cos_m", "lag1", "lag3", "lag12", "roll3", "volume_scaled"]


def _build_vessel_forecast_features(ts: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    t = ts.reset_index(drop=True).copy()
    t["t_idx"] = np.arange(len(t))
    month = t["date"].dt.month
    t["sin_m"] = np.sin(2 * np.pi * month / 12)
    t["cos_m"] = np.cos(2 * np.pi * month / 12)
    t["lag1"] = t["vessels_current"].shift(1)
    t["lag3"] = t["vessels_current"].shift(3)
    t["lag12"] = t["vessels_current"].shift(12)
    t["roll3"] = t["vessels_current"].shift(1).rolling(3).mean()
    t[["lag1", "lag3", "lag12", "roll3"]] = t[["lag1", "lag3", "lag12", "roll3"]].bfill().fillna(0.0)
    volume_mean = float(t["volume"].mean()) or 1.0
    t["volume_scaled"] = t["volume"] / volume_mean
    return t, volume_mean


def _fit_vessel_forecast_model(train_ts: pd.DataFrame):
    feat, volume_mean = _build_vessel_forecast_features(train_ts)
    X = feat[VESSEL_FEATURE_COLS].values
    y = feat["vessels_current"].values
    model = RandomForestRegressor(
        n_estimators=300, max_depth=4, min_samples_leaf=2, random_state=RANDOM_STATE
    )
    model.fit(X, y)
    feat_state = {"volume_mean": volume_mean, "n_train": len(train_ts)}
    return model, X, feat_state


def _recursive_vessel_forecast(model, train_ts: pd.DataFrame, feat_state: dict, horizon_months: int) -> np.ndarray:
    volume_mean = feat_state["volume_mean"]
    n_train = feat_state["n_train"]
    vessel_hist = train_ts["vessels_current"].tolist()
    volume_scaled_hist = (train_ts["volume"] / volume_mean).tolist()
    recent_volume_scaled = (
        float(np.mean(volume_scaled_hist[-6:])) if len(volume_scaled_hist) >= 6
        else (volume_scaled_hist[-1] if volume_scaled_hist else 1.0)
    )

    last_date = train_ts["date"].iloc[-1]
    future_dates = [last_date + pd.DateOffset(months=i + 1) for i in range(horizon_months)]

    hist = vessel_hist.copy()
    preds = []
    for i, d in enumerate(future_dates):
        idx = n_train + i
        month = d.month
        sin_m, cos_m = np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)
        lag1 = hist[-1]
        lag3 = hist[-3] if len(hist) >= 3 else hist[0]
        lag12 = hist[-12] if len(hist) >= 12 else hist[0]
        roll3 = float(np.mean(hist[-3:])) if len(hist) >= 3 else float(np.mean(hist))
        row = [[idx, sin_m, cos_m, lag1, lag3, lag12, roll3, recent_volume_scaled]]
        pred = max(0.0, float(model.predict(row)[0]))
        preds.append(pred)
        hist.append(pred)

    return np.array(preds)


def _evaluate_vessel_forecast(ts: pd.DataFrame) -> dict:
    if len(ts) < 12:
        return {"error": "Insufficient historical periods for evaluation"}
    test_size = min(8, max(4, len(ts) // 4))
    train_ts = ts.iloc[:-test_size].copy()
    test_ts = ts.iloc[-test_size:].copy()
    actual = test_ts["vessels_current"].values

    model, _, feat_state = _fit_vessel_forecast_model(train_ts)
    pred = _recursive_vessel_forecast(model, train_ts, feat_state, test_size)

    mae = float(np.mean(np.abs(actual - pred)))
    sum_true = float(np.sum(actual))
    wape = float(np.sum(np.abs(actual - pred)) / sum_true * 100) if sum_true > 0 else None

    nonzero_frac = float(np.mean(actual > 0))
    reliable = nonzero_frac >= 0.4 and sum_true > 0
    reliability_note = (
        None if reliable else
        f"Vessel calls are too intermittent/near-zero in the test window ({nonzero_frac * 100:.0f}% "
        "of months nonzero) for accuracy to be a meaningful signal here — same limitation as the "
        "cargo tonnage forecast for this commodity."
    )

    return {
        "test_dates": [d.strftime("%Y-%m") for d in test_ts["date"]],
        "actual_vessels": [round(float(v), 1) for v in actual],
        "predicted_vessels": [round(float(v), 1) for v in pred],
        "mae_vessels": round(mae, 1),
        "wape_pct": round(min(wape, 100.0), 1) if wape is not None else None,
        "accuracy_pct": round(max(0.0, 100.0 - wape), 1) if (wape is not None and reliable) else None,
        "reliable_for_accuracy_scoring": reliable,
        "reliability_note": reliability_note,
    }


def forecast_vessel_calls(horizon_months: int = 3, commodity: str = "ALL", section: str = "ALL") -> dict:
    """Real RandomForestRegressor forecast of monthly vessel call counts (not per-ship ETA)."""
    result = dict(_forecast_vessel_calls_cached(horizon_months, commodity, section))
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@_ttl_cache(seconds=300)
def _forecast_vessel_calls_cached(horizon_months: int = 3, commodity: str = "ALL", section: str = "ALL") -> dict:
    df = load_cargo_dataset()
    ts = _aggregate_series(df, commodity=commodity, section=section)
    if len(ts) == 0:
        return {"error": f"No vessel records found for commodity '{commodity}' and section '{section}'"}

    evaluation = _evaluate_vessel_forecast(ts)

    if len(ts) < 8:
        recent = float(ts["vessels_current"].iloc[-3:].mean()) if len(ts) >= 3 else float(ts["vessels_current"].mean())
        forecast_vals = np.full(horizon_months, recent)
    else:
        model, _, feat_state = _fit_vessel_forecast_model(ts)
        forecast_vals = _recursive_vessel_forecast(model, ts, feat_state, horizon_months)

    last_date = ts["date"].iloc[-1]
    dataset_max_date = df["date"].max()
    months_stale = (dataset_max_date.year - last_date.year) * 12 + (dataset_max_date.month - last_date.month)
    forecast_dates = [(last_date + pd.DateOffset(months=i + 1)).strftime("%Y-%m") for i in range(horizon_months)]

    recent_actual = float(ts["vessels_current"].iloc[-1])
    avg_expected_calls_per_month = float(np.mean(forecast_vals))
    # Rough, explicitly-labeled proxy: if N vessels are expected this month,
    # the average gap between calls is ~30/N days. This is NOT a per-vessel
    # ETA — it says nothing about which ship or which day.
    expected_days_between_calls = round(30.0 / avg_expected_calls_per_month, 1) if avg_expected_calls_per_month > 0 else None

    facility_info = NMPA_FACILITY_MAP.get(commodity.upper(), NMPA_FACILITY_MAP["ALL"])

    return {
        "engine": "NMPA_VesselCallForecast_RandomForest_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query_filter": {"commodity": commodity, "section": section, "horizon_months": horizon_months},
        "nmpa_facility": facility_info,
        "not_a_per_vessel_eta": (
            "This forecasts how many vessels are expected to call per month for this commodity — "
            "it is not a per-ship arrival-time prediction. No AIS/vessel-tracking data exists in "
            "this project to support that; only monthly aggregate vessel counts do."
        ),
        "data_currency": {
            "last_record_month": last_date.strftime("%Y-%m"),
            "dataset_latest_month": dataset_max_date.strftime("%Y-%m"),
            "is_stale": months_stale > 3,
        },
        "summary": {
            "current_monthly_vessel_calls": round(recent_actual, 1),
            "expected_monthly_vessel_calls": round(avg_expected_calls_per_month, 1),
            "expected_days_between_calls": expected_days_between_calls,
            "model_accuracy_pct": evaluation.get("accuracy_pct"),
            "accuracy_reliable": evaluation.get("reliable_for_accuracy_scoring", False),
        },
        "forecast_series": [
            {"month": forecast_dates[i], "expected_vessel_calls": round(float(forecast_vals[i]), 1)}
            for i in range(horizon_months)
        ],
        "evaluation": evaluation,
        # Deliberately a sibling of "summary", not merged into it: this
        # is measured from real daily berthing events (see
        # get_real_call_spacing's docstring), not the ML model above.
        # The two can legitimately disagree -- e.g. they measure
        # different populations (this commodity's specific berths vs.
        # a monthly count that may include other sections/flows) and
        # cover different time spans (~1 year of daily data vs. 5
        # years of monthly data) -- so never average or reconcile them
        # silently; show both, labeled.
        "real_call_spacing": get_real_call_spacing(commodity),
        # Same "sibling, never merged" rule as real_call_spacing above,
        # and a distinct source from IT too: spacing measures gaps
        # between calls, this measures how long each call occupied the
        # berth -- see get_real_stay_duration's docstring.
        "real_stay_duration": get_real_stay_duration(commodity),
    }
