"""
One-off test-case script (NOT part of the app): compares the existing
forecasting engine's August-2026 predictions against the real August-2026
actuals from the NMPA PDF. Does NOT modify data/port_cargo_monthly.csv.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from backend.app.services.forecasting import (
    load_cargo_dataset, _prepare_time_series, get_enhanced_cargo_forecast,
    _fit_primary_ml_model, MONTH_MAP, DATA_PATH,
)

TARGET = "2026-08"

# Actual figures transcribed from "Commodity wise Container Statement - August 2026.xlsx.pdf"
# ("Traffic handled during August 2026" column, in tonnes)
ACTUALS = [
    # (section, commodity, actual_tonnes)
    ("UNLOADED", "TOTAL CRUDE", 1_391_896),
    ("UNLOADED", "TOTAL LPG", 199_261),
    ("UNLOADED", "POL PRODUCTS", 96_145),
    ("UNLOADED", "EDIBLE OIL", 97_519),
    ("UNLOADED", "OTH. LIQ. CARGOES", 5_228),
    ("UNLOADED", "FERTILIZER", 52_070),
    ("UNLOADED", "F.R.M. (DRY)", 5_720),
    ("UNLOADED", "TOTAL CEMENT", 45_428),
    ("UNLOADED", "TOTAL COAL", 633_638),
    ("UNLOADED", "IRON ORE", 390_935),
    ("UNLOADED", "OTHER CARGO", 14_144),
    ("UNLOADED", "CONTAINER (JSW)", 123_802),
    ("LOADED", "IRON ORE", 278_974),
    ("LOADED", "TOTAL COAL", 0),
    ("LOADED", "CRUDE - ISPRL", 0),
    ("LOADED", "POL PRODUCTS", 268_430),
    ("LOADED", "PETROCHEMICALS", 100_825),
    ("LOADED", "OTH.LIQ.CARGOES", 5_706),
    ("LOADED", "FOOD GRAINS", 0),
    ("LOADED", "OTHER CARGO", 42_023),
    ("LOADED", "CONTAINER (JSW)", 87_692),
    ("CATEGORY_TOTAL", "GRAND TOTAL (A+B+C+D)", 3_885_913),
    ("CATEGORY_TOTAL", "a) Dry Bulk (Total)", 1_438_265),
    ("CATEGORY_TOTAL", "b) Break Bulk", 50_629),
    ("CATEGORY_TOTAL", "c) Liquid Bulk", 2_185_525),
    ("CATEGORY_TOTAL", "d) Containers (In Tons)", 211_494),
]


def months_between(d1: pd.Timestamp, d2: pd.Timestamp) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def load_dataset_including_category_totals() -> pd.DataFrame:
    """Same cleaning pipeline as load_cargo_dataset(), but keeps CATEGORY_TOTAL
    rows (grand total / dry bulk / break bulk / liquid bulk / containers),
    which the app's forecast API deliberately excludes. Used here only to
    extend the comparison to those aggregate lines with the same model."""
    df = pd.read_csv(DATA_PATH)
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
    return df.sort_values("date").reset_index(drop=True)


def forecast_one_series(df: pd.DataFrame, section: str, commodity: str, target_date: pd.Timestamp):
    ts = _prepare_time_series(df, commodity=commodity, section=section)
    if len(ts) == 0:
        return None, "no history"
    last_date = ts["date"].iloc[-1]
    horizon = months_between(last_date, target_date)
    if horizon <= 0:
        return None, f"last record {last_date:%Y-%m} is at/after target"
    _, forecast_vals, residual_std = _fit_primary_ml_model(ts, forecast_horizon_months=horizon)
    predicted = float(forecast_vals[-1])
    margin = 1.96 * residual_std * np.sqrt(1 + horizon / 12.0)
    lower, upper = max(0.0, predicted - margin), predicted + margin
    return dict(predicted=round(predicted, 1), lower_95=round(lower, 1), upper_95=round(upper, 1),
                last_history_month=f"{last_date:%Y-%m}", horizon_used=horizon), None


def main():
    df = load_cargo_dataset()
    df_cat = load_dataset_including_category_totals()
    target_date = pd.Timestamp(TARGET + "-01")

    rows = []
    for section, commodity, actual in ACTUALS:
        if section == "CATEGORY_TOTAL":
            res, note = forecast_one_series(df_cat, section, commodity, target_date)
            if res is None:
                rows.append(dict(section=section, commodity=commodity, actual=actual,
                                  predicted=None, note=note))
                continue
            predicted = res["predicted"]
            lower, upper = res["lower_95"], res["upper_95"]
            err = predicted - actual
            pct_err = (err / actual * 100) if actual != 0 else None
            rows.append(dict(
                section=section, commodity=commodity, actual=actual, predicted=predicted,
                lower_95=lower, upper_95=upper, error=round(err, 1),
                pct_error=round(pct_err, 1) if pct_err is not None else pct_err,
                within_95ci=lower <= actual <= upper,
                predictability="N/A (not exposed by app API)", model_accuracy_pct=None,
                last_history_month=res["last_history_month"], horizon_used=res["horizon_used"],
                note="computed via same RandomForest pipeline; app's /forecast endpoint excludes CATEGORY_TOTAL rows",
            ))
            continue

        ts = _prepare_time_series(df, commodity=commodity, section=section)
        if len(ts) == 0:
            rows.append(dict(section=section, commodity=commodity, actual=actual,
                              predicted=None, note="no history"))
            continue

        last_date = ts["date"].iloc[-1]
        horizon = months_between(last_date, target_date)
        if horizon <= 0:
            rows.append(dict(section=section, commodity=commodity, actual=actual,
                              predicted=None, note=f"last record {last_date:%Y-%m} is at/after target"))
            continue

        result = get_enhanced_cargo_forecast(horizon_months=horizon, commodity=commodity, section=section)
        if "error" in result:
            rows.append(dict(section=section, commodity=commodity, actual=actual,
                              predicted=None, note=result["error"]))
            continue

        series = {s["month"]: s for s in result["forecast_series"]}
        entry = series.get(TARGET)
        if entry is None:
            rows.append(dict(section=section, commodity=commodity, actual=actual,
                              predicted=None, note=f"target month not in forecast series (horizon={horizon})"))
            continue

        predicted = entry["forecast_tonnes"]
        lower = entry["lower_bound_95"]
        upper = entry["upper_bound_95"]
        err = predicted - actual
        pct_err = (err / actual * 100) if actual != 0 else (None if predicted == 0 else float("inf"))
        within_ci = lower <= actual <= upper

        rows.append(dict(
            section=section, commodity=commodity,
            actual=actual, predicted=predicted,
            lower_95=lower, upper_95=upper,
            error=round(err, 1),
            pct_error=round(pct_err, 1) if pct_err is not None and pct_err != float("inf") else pct_err,
            within_95ci=within_ci,
            predictability=result["summary"]["predictability_level"],
            model_accuracy_pct=result["summary"]["model_accuracy_pct"],
            last_history_month=f"{last_date:%Y-%m}",
            horizon_used=horizon,
        ))

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(out.to_string(index=False))

    out.to_csv(Path(__file__).parent / "aug2026_comparison_results.csv", index=False)
    print(f"\nSaved -> {Path(__file__).parent / 'aug2026_comparison_results.csv'}")


if __name__ == "__main__":
    main()
