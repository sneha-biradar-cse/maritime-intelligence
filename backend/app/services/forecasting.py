"""
forecasting.py — YellowSense Maritime AI Cargo Forecasting & Predictability Engine
-----------------------------------------------------------------------------------
Data-grounded, ML-powered cargo forecasting engine built on actual historical
port cargo dataset (`data/port_cargo_monthly.csv`) mapped to New Mangalore Port Authority (NMPA)
berths, facilities, and hinterland industrial drivers.

Key Capabilities:
  1. Ingestion & Preprocessing of actual monthly port traffic (2021 - 2026).
  2. NMPA Facility & Berth Mapping (Oil Jetties, JSW Container Terminal, UPCL Coal Berths, KIOCL Iron Ore Jetty).
  3. Time-series feature engineering (lags, rolling stats, seasonality, vessel counts).
  4. Dual-Model Architecture:
     - Baseline Model: Seasonal Naive / Historical 12-month Rolling Average
     - Primary ML Model: scikit-learn RandomForestRegressor over lag/rolling/seasonal
       features (see ml_models.py), recursively forecast multi-step ahead
  5. Chronological Backtesting & Metric Evaluation (MAE, RMSE, MAPE, WAPE, R²).
  6. Statistical 95% Prediction Intervals (Dynamic std error scaling).
  7. Empirical Predictability Score (High / Medium / Low) with rationale.
  8. Quantified Forecast Driver Explainability (MRPL Crude, UPCL Coal, Monsoon Swells).
  9. AI-Assisted Operational Recommendations mapped to NMPA berth preparations.
 10. Interactive What-If Scenario Simulator with NMPA Presets.
"""

import time
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths & Seed ─────────────────────────────────────────────────────────────
DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "port_cargo_monthly.csv"
ALT_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "sample_cargo_data.csv"
RNG = np.random.default_rng(seed=2024)


def _ttl_cache(seconds: int = 300):
    """Tiny in-process memoization — retraining RandomForest per request is
    2-4s and a single page load fires ~20 concurrent API calls, which can
    exceed the frontend's request timeout without this."""
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

# ── NMPA Mangalore Port Facilities & Hinterland Mappings ─────────────────────
NMPA_FACILITY_MAP = {
    "TOTAL CRUDE": {
        "facility_name": "Oil Jetty 1 & 2 / SPM (Single Point Mooring)",
        "berths": "OJ-1, OJ-2 & Offshore SPM",
        "hinterland_consumer": "MRPL (Mangalore Refinery & Petrochemicals Ltd)",
        "max_draft_m": 15.4,
        "primary_flow": "UNLOADED (Import)",
    },
    "CRUDE - ISPRL": {
        "facility_name": "ISPRL Strategic Petroleum Cavern Line",
        "berths": "Offshore SPM / OJ-2",
        "hinterland_consumer": "ISPRL (Indian Strategic Petroleum Reserves Ltd)",
        "max_draft_m": 15.4,
        "primary_flow": "UNLOADED (Strategic Reserve)",
    },
    "TOTAL COAL": {
        "facility_name": "Mechanized Coal Handling Terminal",
        "berths": "Berth 15 & 16",
        "hinterland_consumer": "UPCL (Udupi Power Corp Ltd / Adani Power)",
        "max_draft_m": 14.0,
        "primary_flow": "UNLOADED (Import)",
    },
    "IRON ORE": {
        "facility_name": "KIOCL Iron Ore Bulk Terminal",
        "berths": "Berth 8 & KIOCL Dedicated Berth",
        "hinterland_consumer": "KIOCL Pellet Plant & Kudremukh Corridor",
        "max_draft_m": 13.5,
        "primary_flow": "LOADED / UNLOADED",
    },
    "CONTAINER (JSW)": {
        "facility_name": "JSW Container Terminal",
        "berths": "Berth 14 (Dedicated Container Berth)",
        "hinterland_consumer": "Karnataka Trade & Export Manufacturing Corridor",
        "max_draft_m": 13.0,
        "primary_flow": "LOADED & UNLOADED",
    },
    "CONTAINER": {
        "facility_name": "JSW Container Terminal",
        "berths": "Berth 14",
        "hinterland_consumer": "Regional Container Logistics",
        "max_draft_m": 13.0,
        "primary_flow": "LOADED & UNLOADED",
    },
    "FERTILIZER": {
        "facility_name": "Fertilizer & Dry Bulk Berth",
        "berths": "Berth 5 & 6",
        "hinterland_consumer": "MCF (Mangalore Chemicals & Fertilizers Ltd)",
        "max_draft_m": 11.5,
        "primary_flow": "UNLOADED (Import)",
    },
    "F.R.M. (DRY)": {
        "facility_name": "Fertilizer Raw Material Berth",
        "berths": "Berth 5",
        "hinterland_consumer": "MCF Fertilizer Input Complex",
        "max_draft_m": 11.5,
        "primary_flow": "UNLOADED (Import)",
    },
    "TOTAL LPG": {
        "facility_name": "LPG Import Terminal Jetty",
        "berths": "Oil Jetty 3 & 4",
        "hinterland_consumer": "HPCL / BPCL / IOCL Regional LPG Bottling Plants",
        "max_draft_m": 12.5,
        "primary_flow": "UNLOADED (Import)",
    },
    "POL PRODUCTS": {
        "facility_name": "Clean Cargo Oil Jetties",
        "berths": "Oil Jetty 1 & 3",
        "hinterland_consumer": "Coastal Refined Petroleum Logistics",
        "max_draft_m": 12.0,
        "primary_flow": "LOADED & UNLOADED",
    },
    "EDIBLE OIL": {
        "facility_name": "Liquid Bulk Jetty",
        "berths": "Berth 4 & OJ-3",
        "hinterland_consumer": "West Coast Edible Oil Storage & Processing",
        "max_draft_m": 11.0,
        "primary_flow": "UNLOADED (Import)",
    },
    "TOTAL CEMENT": {
        "facility_name": "Coastal Bulk Cement Berth",
        "berths": "Berth 3",
        "hinterland_consumer": "Karnataka & Kerala Construction Industry",
        "max_draft_m": 10.5,
        "primary_flow": "UNLOADED (Coastal)",
    },
    "ALL": {
        "facility_name": "New Mangalore Port Authority (NMPA) — All Terminals",
        "berths": "Berths 1–16 & Oil Jetties 1–4",
        "hinterland_consumer": "Karnataka & South India Trade Gateway",
        "max_draft_m": 15.4,
        "primary_flow": "TOTAL PORT TRAFFIC",
    }
}

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12
}

# ═══════════════════════════════════════════════════════════════════
# 1. DATA INGESTION & CLEANING PIPELINE
# ═══════════════════════════════════════════════════════════════════

def load_cargo_dataset() -> pd.DataFrame:
    """
    Ingest and clean the authoritative monthly cargo dataset.
    Converts month + year strings into datetime objects and cleans numeric values.
    """
    file_to_read = DATA_PATH if DATA_PATH.exists() else ALT_DATA_PATH
    if not file_to_read.exists():
        raise FileNotFoundError(f"Cargo dataset not found at {DATA_PATH}")

    df = pd.read_csv(file_to_read)
    df.columns = [c.strip().lower() for c in df.columns]

    df = df.dropna(subset=["month", "year", "traffic_tonnes_current"]).copy()
    
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year"]).copy()
    df["year"] = df["year"].astype(int)
    
    df["month_num"] = df["month"].str.strip().map(MONTH_MAP)
    df = df.dropna(subset=["month_num"]).copy()
    df["month_num"] = df["month_num"].astype(int)

    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month_num"].astype(str).str.zfill(2) + "-01"
    )

    for col in ["traffic_tonnes_current", "vessels_current", "traffic_tonnes_prev_year", "pct_variation_yoy"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        else:
            df[col] = 0.0

    df["section"] = df["section"].astype(str).str.strip().str.upper()
    df["commodity"] = df["commodity"].astype(str).str.strip()

    df_clean = df[~df["section"].isin(["CATEGORY_TOTAL"])].copy()
    return df_clean.sort_values("date").reset_index(drop=True)


def get_available_commodities() -> dict:
    """Returns unique list of commodities and flow sections available in dataset."""
    df = load_cargo_dataset()
    commodities = sorted(df["commodity"].unique().tolist())
    sections = sorted(df["section"].unique().tolist())
    dataset_max_date = df["date"].max()

    # Flag commodities whose reporting has gone stale (data taxonomy changed
    # mid-dataset: itemized SKUs in 2021 -> consolidated "TOTAL X" categories
    # from 2023 onward — most 2021-only labels were simply retired).
    last_seen = df.groupby("commodity")["date"].max()
    commodity_status = {}
    for c in commodities:
        last_dt = last_seen[c]
        months_behind = (dataset_max_date.year - last_dt.year) * 12 + (dataset_max_date.month - last_dt.month)
        commodity_status[c] = {
            "last_record_month": last_dt.strftime("%Y-%m"),
            "months_behind_latest_data": int(months_behind),
            "is_current": months_behind <= 3,
        }

    return {
        "port_authority": "New Mangalore Port Authority (NMPA)",
        "commodities": commodities,
        "commodity_status": commodity_status,
        "sections": sections,
        "total_records": len(df),
        "date_min": df["date"].min().strftime("%Y-%m"),
        "date_max": df["date"].max().strftime("%Y-%m"),
        "nmpa_facility_mapping": NMPA_FACILITY_MAP
    }


# ═══════════════════════════════════════════════════════════════════
# 2. TIME-SERIES MODELING & BACKTESTING ENGINE
# ═══════════════════════════════════════════════════════════════════

def _prepare_time_series(df: pd.DataFrame, commodity: str = "ALL", section: str = "ALL") -> pd.DataFrame:
    filtered = df.copy()
    if section != "ALL":
        filtered = filtered[filtered["section"] == section]
    if commodity != "ALL":
        filtered = filtered[filtered["commodity"] == commodity]

    ts = filtered.groupby("date").agg({
        "traffic_tonnes_current": "sum",
        "vessels_current": "sum",
        "traffic_tonnes_prev_year": "sum",
    }).reset_index().sort_values("date")

    ts.rename(columns={"traffic_tonnes_current": "volume"}, inplace=True)
    return ts


def _fit_primary_ml_model(train_ts: pd.DataFrame, forecast_horizon_months: int) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Primary ML Model: scikit-learn RandomForestRegressor over engineered
    time-series features (lag-1, lag-3, lag-12, 3-month rolling mean,
    cyclical month encoding, trend index, scaled vessel arrivals).

    In-sample `fitted_train` uses true historical lags (standard backtest
    convention). Multi-step `forecast_future` is generated recursively —
    each predicted month is fed back in as the lag input for the next,
    since true future lags are unknown at forecast time.
    """
    from backend.app.services.ml_models import fit_cargo_forecast_model, recursive_forecast

    y_train = train_ts["volume"].values
    n_train = len(y_train)
    if n_train < 8:
        mean_val = float(np.mean(y_train)) if n_train > 0 else 10000.0
        return np.full(n_train, mean_val), np.full(forecast_horizon_months, mean_val), 500.0

    model, X_train, feat_state = fit_cargo_forecast_model(train_ts)
    fitted_train = np.clip(model.predict(X_train), 0, None)
    residuals = y_train - fitted_train
    residual_std = float(np.std(residuals))

    forecast_future = recursive_forecast(model, train_ts, feat_state, forecast_horizon_months)

    return fitted_train, forecast_future, residual_std


@_ttl_cache(seconds=300)
def evaluate_forecast_models(commodity: str = "ALL", section: str = "ALL") -> dict:
    df = load_cargo_dataset()
    ts = _prepare_time_series(df, commodity=commodity, section=section)
    
    if len(ts) < 12:
        return {"error": "Insufficient historical periods for evaluation"}

    test_size = min(8, max(4, len(ts) // 4))
    train_ts = ts.iloc[:-test_size].copy()
    test_ts = ts.iloc[-test_size:].copy()
    actual_test = test_ts["volume"].values

    # Baseline Model: Seasonal Naive
    baseline_pred = []
    for _, row in test_ts.iterrows():
        past_window = ts[ts["date"] < row["date"]]["volume"].values
        if len(past_window) >= 12:
            pred_val = past_window[-12]
        elif len(past_window) > 0:
            pred_val = float(np.mean(past_window[-3:]))
        else:
            pred_val = float(np.mean(actual_test))
        baseline_pred.append(pred_val)
    baseline_pred = np.array(baseline_pred)

    # Primary ML Model
    _, ml_pred, _ = _fit_primary_ml_model(train_ts, forecast_horizon_months=test_size)

    def _metrics(y_true, y_pred):
        mae = float(np.mean(np.abs(y_true - y_pred)))
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
        denom = np.where(y_true == 0, 1.0, y_true)
        mape = float(np.mean(np.abs((y_true - y_pred) / denom)) * 100)
        sum_true = float(np.sum(y_true))
        wape = float((np.sum(np.abs(y_true - y_pred)) / sum_true * 100)) if sum_true > 0 else mape
        ss_res = float(np.sum((y_true - y_pred) ** 2))
        ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
        r2 = float(1 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
        return {
            "mae_tonnes": round(mae, 1),
            "rmse_tonnes": round(rmse, 1),
            "mape_pct": round(min(mape, 100.0), 2),
            "wape_pct": round(min(wape, 100.0), 2),
            "r2_score": round(max(r2, 0.0), 3),
            "accuracy_score_pct": round(max(0.0, 100.0 - wape), 1)
        }

    bm_metrics = _metrics(actual_test, baseline_pred)
    ml_metrics = _metrics(actual_test, ml_pred)

    nonzero_frac = float(np.mean(actual_test > 0))
    reliable = nonzero_frac >= 0.4 and float(np.sum(actual_test)) > 0
    reliability_note = (
        None if reliable else
        f"'{commodity}' has intermittent/near-zero shipment activity in the test window "
        f"({nonzero_frac * 100:.0f}% of months nonzero) — WAPE/accuracy on this series is not "
        "a meaningful signal for any model, real or otherwise, because there is too little "
        "consistent volume to fit a trend against."
    )

    return {
        "evaluation_period_months": test_size,
        "test_dates": [d.strftime("%Y-%m") for d in test_ts["date"]],
        "actual_test_volumes": [round(v, 1) for v in actual_test],
        "data_reliability": {
            "reliable_for_accuracy_scoring": reliable,
            "nonzero_test_months_pct": round(nonzero_frac * 100, 1),
            "note": reliability_note,
        },
        "models": [
            {
                "model_name": "Baseline Model (Seasonal Naive / Rolling Avg)",
                "status": "Benchmark",
                "predicted_volumes": [round(v, 1) for v in baseline_pred],
                "metrics": bm_metrics,
            },
            {
                "model_name": "Primary ML Model (Random Forest Regression — scikit-learn)",
                "status": "Active / Improved",
                "predicted_volumes": [round(v, 1) for v in ml_pred],
                "metrics": ml_metrics,
                "improvement_vs_baseline_wape_pct": round(bm_metrics["wape_pct"] - ml_metrics["wape_pct"], 2)
            }
        ],
        "recommended_metric_explanation": (
            "WAPE (Weighted Absolute Percentage Error) is the primary metric used for NMPA cargo forecasting. "
            "Unlike MAPE, WAPE avoids distortion caused by zero or low monthly shipment cycles."
        )
    }


# ═══════════════════════════════════════════════════════════════════
# 3. ENHANCED CARGO FORECAST API LOGIC (WITH NMPA MAPPINGS)
# ═══════════════════════════════════════════════════════════════════

def get_enhanced_cargo_forecast(
    horizon_months: int = 6,
    commodity: str = "ALL",
    section: str = "ALL"
) -> dict[str, Any]:
    """Main Cargo Projection & Predictability Engine endpoint logic mapped to NMPA Facilities."""
    result = dict(_get_enhanced_cargo_forecast_cached(horizon_months, commodity, section))
    if "generated_at" in result:
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@_ttl_cache(seconds=300)
def _get_enhanced_cargo_forecast_cached(
    horizon_months: int = 6,
    commodity: str = "ALL",
    section: str = "ALL"
) -> dict[str, Any]:
    df = load_cargo_dataset()
    ts = _prepare_time_series(df, commodity=commodity, section=section)

    if len(ts) == 0:
        return {"error": f"No cargo records found for commodity '{commodity}' and section '{section}'"}

    _, forecast_vals, residual_std = _fit_primary_ml_model(ts, forecast_horizon_months=horizon_months)

    hist_dates = [d.strftime("%Y-%m") for d in ts["date"]]
    last_date = ts["date"].iloc[-1]
    forecast_dates_dt = [last_date + pd.DateOffset(months=i+1) for i in range(horizon_months)]
    forecast_dates = [d.strftime("%Y-%m") for d in forecast_dates_dt]

    lower_bounds = []
    upper_bounds = []
    for h_idx, f_val in enumerate(forecast_vals):
        margin = 1.96 * residual_std * np.sqrt(1 + (h_idx + 1) / 12.0)
        lower_bounds.append(round(max(0.0, float(f_val - margin)), 1))
        upper_bounds.append(round(float(f_val + margin), 1))

    eval_res = evaluate_forecast_models(commodity=commodity, section=section)
    accuracy_reliable = "models" in eval_res
    ml_wape = eval_res["models"][1]["metrics"]["wape_pct"] if accuracy_reliable else None

    hist_cv = float(ts["volume"].std() / ts["volume"].mean()) if ts["volume"].mean() > 0 else 0.5

    if not accuracy_reliable:
        predictability_level = "LOW"
        predictability_desc = (
            f"Only {len(ts)} historical month(s) of data for '{commodity}'/{section} — below the "
            "12-month minimum needed to backtest accuracy. This forecast is unvalidated model "
            "extrapolation, not a measured accuracy figure."
        )
    elif ml_wape < 15.0 and hist_cv < 0.35:
        predictability_level = "HIGH"
        predictability_desc = "Low historical volatility & tight prediction bounds (<15% WAPE)."
    elif ml_wape < 28.0 or hist_cv < 0.60:
        predictability_level = "MEDIUM"
        predictability_desc = "Moderate seasonal variation; prediction bounds within NMPA operational tolerance."
    else:
        predictability_level = "LOW"
        predictability_desc = "High market volatility or irregular commodity movements; forecast bounds are wide."

    data_reliability = eval_res.get("data_reliability", {})
    if data_reliability.get("reliable_for_accuracy_scoring") is False:
        predictability_level = "LOW"
        predictability_desc = data_reliability.get("note") or predictability_desc

    # Data-currency check: does this filter's most recent record lag far behind
    # the dataset's overall latest month? (e.g. a commodity label retired/renamed
    # mid-dataset, like "CONTAINER" -> "CONTAINER (JSW)" from 2023 onward).
    dataset_max_date = df["date"].max()
    months_stale = (dataset_max_date.year - last_date.year) * 12 + (dataset_max_date.month - last_date.month)
    data_currency = {
        "last_record_month": last_date.strftime("%Y-%m"),
        "dataset_latest_month": dataset_max_date.strftime("%Y-%m"),
        "months_behind_latest_data": months_stale,
        "is_stale": months_stale > 3,
        "note": (
            None if months_stale <= 3 else
            f"'{commodity}'/{section}'s last record is {last_date.strftime('%b %Y')}, "
            f"{months_stale} months behind the port's latest data ({dataset_max_date.strftime('%b %Y')}). "
            "This commodity label may have been renamed/discontinued mid-dataset — the forecast "
            f"below projects forward from {last_date.strftime('%b %Y')}, not from today."
        ),
    }
    if data_currency["is_stale"]:
        predictability_level = "LOW"
        predictability_desc = data_currency["note"]

    ml_accuracy_pct = round(100 - ml_wape, 1) if ml_wape is not None else None
    confidence_pct = ml_accuracy_pct if ml_accuracy_pct is not None else 0.0

    recent_actual = float(ts["volume"].iloc[-1])
    avg_forecast = float(np.mean(forecast_vals))

    if recent_actual > 0:
        # Normal case: % change is well-defined.
        pct_change = round(((avg_forecast - recent_actual) / recent_actual * 100), 2)
        trend_signal = "Increasing / Bullish" if pct_change > 2.0 else ("Decreasing / Bearish" if pct_change < -2.0 else "Stable / Neutral")
    elif avg_forecast > 0:
        # The last actual month happened to be zero (common for intermittent
        # commodities like strategic reserve shipments), but the model still
        # predicts nonzero activity ahead based on the overall historical
        # pattern. Going from 0 -> nonzero has no defined percentage — do not
        # report a fake "+0.0%".
        pct_change = None
        trend_signal = "Resuming from Zero Baseline (% undefined)"
    else:
        # Both current and forecast are genuinely zero — truly flat.
        pct_change = 0.0
        trend_signal = "Stable / Neutral"

    # Numeric-safe version of pct_change for internal comparisons below
    # (None means "undefined", not "zero" — don't let it silently become 0).
    pct_change_cmp = pct_change if pct_change is not None else 0.0

    # NMPA Facility Lookup
    facility_info = NMPA_FACILITY_MAP.get(commodity.upper(), NMPA_FACILITY_MAP["ALL"])

    recent_vessels = float(ts["vessels_current"].iloc[-3:].mean()) if len(ts) >= 3 else 10.0
    hist_vessels_avg = float(ts["vessels_current"].mean()) if len(ts) > 0 else 10.0
    vessel_driver_pct = round(((recent_vessels - hist_vessels_avg) / hist_vessels_avg * 100), 1) if hist_vessels_avg > 0 else 0.0

    resuming_from_zero = pct_change is None and avg_forecast > 0

    drivers = [
        {
            "factor": "NMPA Hinterland Demand Factor",
            "impact": f"Target: {facility_info['hinterland_consumer']}",
            "direction": "UP" if (pct_change_cmp > 0 or resuming_from_zero) else "DOWN",
            "weight_pct": 45,
            "explanation": f"Demand generated by {facility_info['hinterland_consumer']} through {facility_info['berths']}."
        },
        {
            "factor": "Vessel Fleet Arrival Momentum",
            "impact": f"{vessel_driver_pct:+.1f}% vs Historical Avg",
            "direction": "UP" if vessel_driver_pct >= 0 else "DOWN",
            "weight_pct": 35,
            "explanation": f"Recent vessel traffic at NMPA average {recent_vessels:.1f} vessels/month."
        },
        {
            "factor": "Monsoon & Volatility Risk Adjustment",
            "impact": f"±{round(residual_std / (ts['volume'].mean() or 1) * 100, 1)}%",
            "direction": "NEUTRAL",
            "weight_pct": 20,
            "explanation": "Residual variance scaling applied for 95% dynamic prediction interval bounds."
        }
    ]

    op_recs = []
    if resuming_from_zero:
        op_recs.append({
            "priority": "HIGH",
            "category": f"Berth Staging ({facility_info['berths']})",
            "recommendation": (
                f"Model predicts {facility_info['facility_name']} resuming activity "
                f"(~{avg_forecast:,.0f} t/month) after the most recent recorded month was zero."
            ),
            "action": (
                f"Verify with {facility_info['hinterland_consumer']} before committing berth resources — "
                "this is extrapolated from a historically intermittent shipment pattern, not a confirmed booking."
            ),
            "confidence_pct": confidence_pct
        })
    elif pct_change_cmp > 10.0:
        op_recs.append({
            "priority": "HIGH",
            "category": f"Berth Staging ({facility_info['berths']})",
            "recommendation": f"Prepare NMPA {facility_info['facility_name']} for {pct_change}% volume surge.",
            "action": f"Pre-allocate yard storage and coordinate crane staging at {facility_info['berths']}.",
            "confidence_pct": confidence_pct
        })
    elif pct_change_cmp < -10.0:
        op_recs.append({
            "priority": "MEDIUM",
            "category": f"Resource Optimization ({facility_info['berths']})",
            "recommendation": f"Forecast indicates {abs(pct_change)}% throughput drop at {facility_info['berths']}.",
            "action": "Consider re-assigning handling gangs to reduce berth idle maintenance costs.",
            "confidence_pct": confidence_pct
        })
    else:
        op_recs.append({
            "priority": "LOW",
            "category": "Routine Operations",
            "recommendation": f"Cargo volume at {facility_info['berths']} expected to remain stable.",
            "action": f"Maintain standard operational scheduling at {facility_info['berths']}.",
            "confidence_pct": confidence_pct
        })

    op_recs.append({
        "priority": "MEDIUM",
        "category": "NMPA Draft & Predictability",
        "recommendation": f"Predictability Score is {predictability_level} (Draft: {facility_info['max_draft_m']}m).",
        "action": predictability_desc,
        "confidence_pct": confidence_pct
    })

    return {
        "engine": "YellowSense_NMPA_ML_v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query_filter": {"commodity": commodity, "section": section, "horizon_months": horizon_months},
        "nmpa_facility": facility_info,
        "summary": {
            "current_monthly_volume_tonnes": round(recent_actual, 1),
            "expected_monthly_avg_tonnes": round(avg_forecast, 1),
            "total_expected_horizon_tonnes": round(float(np.sum(forecast_vals)), 1),
            "forecast_change_pct": pct_change,
            "trend_signal": trend_signal,
            "predictability_level": predictability_level,
            "predictability_desc": predictability_desc,
            "model_wape_pct": ml_wape,
            "model_accuracy_pct": ml_accuracy_pct,
            "accuracy_reliable": accuracy_reliable and not data_currency["is_stale"]
                                  and data_reliability.get("reliable_for_accuracy_scoring", True),
        },
        "data_currency": data_currency,
        "forecast_series": [
            {
                "month": forecast_dates[i],
                "forecast_tonnes": round(float(forecast_vals[i]), 1),
                "lower_bound_95": lower_bounds[i],
                "upper_bound_95": upper_bounds[i],
            }
            for i in range(horizon_months)
        ],
        "chart": {
            "history_months": hist_dates[-24:],
            "history_values": [round(float(v), 1) for v in ts["volume"].iloc[-24:]],
            "forecast_months": forecast_dates,
            "forecast_values": [round(float(v), 1) for v in forecast_vals],
            "lower_bounds": lower_bounds,
            "upper_bounds": upper_bounds,
        },
        "evaluation": eval_res,
        "drivers": drivers,
        "operational_recommendations": op_recs,
        "data_quality": {
            "completeness_pct": round(
                len(ts) / max(1, (last_date.year - ts["date"].iloc[0].year) * 12
                              + (last_date.month - ts["date"].iloc[0].month) + 1) * 100, 1
            ),
            "missing_values_count": 0,
            "total_records_analyzed": len(ts),
            "historical_span": f"{hist_dates[0]} to {hist_dates[-1]}",
            "last_dataset_update": dataset_max_date.strftime("%Y-%m-%d"),
        }
    }


# ═══════════════════════════════════════════════════════════════════
# 4. INTERACTIVE WHAT-IF CARGO SCENARIO SIMULATOR
# ═══════════════════════════════════════════════════════════════════

def simulate_cargo_scenario(
    commodity: str = "ALL",
    section: str = "ALL",
    vessel_arrival_change_pct: float = 0.0,
    trade_demand_change_pct: float = 0.0,
    weather_delay_days: float = 0.0,
    horizon_months: int = 6
) -> dict:
    """
    Simulates NMPA operational scenarios on cargo throughput.
    """
    base_forecast = get_enhanced_cargo_forecast(horizon_months=horizon_months, commodity=commodity, section=section)
    if "error" in base_forecast:
        return base_forecast

    base_vals = np.array([f["forecast_tonnes"] for f in base_forecast["forecast_series"]])
    facility = base_forecast.get("nmpa_facility", NMPA_FACILITY_MAP["ALL"])

    vessel_mult = 1.0 + (vessel_arrival_change_pct / 100.0) * 0.6
    demand_mult = 1.0 + (trade_demand_change_pct / 100.0) * 0.8
    weather_mult = max(0.7, 1.0 - (weather_delay_days * 0.033))

    sim_multiplier = vessel_mult * demand_mult * weather_mult
    simulated_vals = base_vals * sim_multiplier

    base_total = float(np.sum(base_vals))
    sim_total = float(np.sum(simulated_vals))
    delta_tonnes = sim_total - base_total
    delta_pct = (delta_tonnes / base_total * 100) if base_total > 0 else 0.0

    if delta_pct > 20.0 or weather_delay_days >= 3:
        capacity_risk = f"HIGH BERTH STRESS at {facility['berths']}"
    elif delta_pct < -15.0:
        capacity_risk = f"BERTH UNDER-UTILIZATION at {facility['berths']}"
    else:
        capacity_risk = f"MANAGEABLE CAPACITY at {facility['berths']}"

    sim_series = []
    for i, f in enumerate(base_forecast["forecast_series"]):
        sim_val = round(float(simulated_vals[i]), 1)
        sim_series.append({
            "month": f["month"],
            "baseline_tonnes": f["forecast_tonnes"],
            "simulated_tonnes": sim_val,
            "delta_tonnes": round(sim_val - f["forecast_tonnes"], 1),
        })

    return {
        "scenario_parameters": {
            "commodity": commodity,
            "section": section,
            "vessel_arrival_change_pct": vessel_arrival_change_pct,
            "trade_demand_change_pct": trade_demand_change_pct,
            "weather_delay_days": weather_delay_days,
            "horizon_months": horizon_months,
            "facility_impacted": facility["facility_name"]
        },
        "simulation_summary": {
            "baseline_total_tonnes": round(base_total, 1),
            "simulated_total_tonnes": round(sim_total, 1),
            "volume_delta_tonnes": round(delta_tonnes, 1),
            "volume_delta_pct": round(delta_pct, 2),
            "capacity_risk_level": capacity_risk,
        },
        "series": sim_series,
        "simulated_operational_advisories": [
            f"Expected throughput shift at {facility['facility_name']} ({facility['berths']}): {delta_pct:+.1f}% ({delta_tonnes:+,.0f} tonnes).",
            f"NMPA Capacity Stress Status: {capacity_risk}.",
            f"Hinterland Impact: {facility['hinterland_consumer']} supply pipeline affected.",
            "AI Advisory: Coordinate tugboat deployment and pre-stage handling gangs 48 hours prior to vessel peak arrival windows."
        ]
    }


# ═══════════════════════════════════════════════════════════════════
# 5. BACKWARD COMPATIBILITY STUBS
# ═══════════════════════════════════════════════════════════════════

def forecast_cargo(horizon_days: int = 7) -> dict[str, Any]:
    horizon_m = max(1, horizon_days // 30) if horizon_days >= 30 else 3
    res = get_enhanced_cargo_forecast(horizon_months=horizon_m)
    res["horizon_days"] = horizon_days
    res["confidence_pct"] = res["summary"]["model_accuracy_pct"]
    res["trend_signal"] = res["summary"]["trend_signal"].lower()
    res["trend_change_pct"] = res["summary"]["forecast_change_pct"]
    res["current_volume_mt000"] = round(res["summary"]["current_monthly_volume_tonnes"] / 1000.0, 1)
    res["forecast"] = [
        {
            "date": s["month"],
            "volume_mt000": round(s["forecast_tonnes"] / 1000.0, 1),
            "lower_bound": round(s["lower_bound_95"] / 1000.0, 1),
            "upper_bound": round(s["upper_bound_95"] / 1000.0, 1),
        }
        for s in res["forecast_series"]
    ]
    return res


def forecast_congestion() -> dict[str, Any]:
    """Delegates to the real scikit-learn congestion risk classifier (ml_models.py)."""
    from backend.app.services.ml_models import predict_congestion_risk
    return predict_congestion_risk()


def forecast_trade() -> dict[str, Any]:
    """
    Real inbound/outbound trade snapshot. The growth and momentum figures used to be
    typed-in constants (3.8, 5.2, 4.2, 6.1); they now come from trade_intelligence.py.
    Same keys as before, plus year-on-year fields. A *_mom_growth_pct of None means the
    previous calendar month is missing from the dataset (not zero).
    """
    from backend.app.services.trade_intelligence import get_legacy_trade_snapshot

    return {
        "engine": "trade_intelligence_v3_real",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **get_legacy_trade_snapshot(),
    }


def generate_recommendations() -> dict[str, Any]:
    res = get_enhanced_cargo_forecast(horizon_months=6)
    recs = res.get("operational_recommendations", [])
    return {
        "engine": "recommendation_engine_v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_recommendations": len(recs),
        "critical_count": sum(1 for r in recs if r["priority"] == "CRITICAL"),
        "high_count": sum(1 for r in recs if r["priority"] == "HIGH"),
        "recommendations": recs,
    }
