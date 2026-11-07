"""
Run a forecast for one specific target month from the terminal.

Usage:
  python scratch_aug2026_test/forecast_month.py --target 2026-08
  python scratch_aug2026_test/forecast_month.py --target 2026-09 --commodity "TOTAL CRUDE" --section UNLOADED
  python scratch_aug2026_test/forecast_month.py --target 2026-12 --commodity ALL --section ALL
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from backend.app.services.forecasting import load_cargo_dataset, _prepare_time_series, get_enhanced_cargo_forecast


def months_between(d1: pd.Timestamp, d2: pd.Timestamp) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True, help="Target month, e.g. 2026-08")
    p.add_argument("--commodity", default="ALL")
    p.add_argument("--section", default="ALL")
    args = p.parse_args()

    df = load_cargo_dataset()
    ts = _prepare_time_series(df, commodity=args.commodity, section=args.section)
    if len(ts) == 0:
        print(f"No history for commodity={args.commodity!r} section={args.section!r}")
        return

    last_date = ts["date"].iloc[-1]
    target_date = pd.Timestamp(args.target + "-01")
    horizon = months_between(last_date, target_date)

    if horizon <= 0:
        print(f"Target {args.target} is at/before the last recorded month ({last_date:%Y-%m}) — nothing to forecast.")
        return

    result = get_enhanced_cargo_forecast(horizon_months=horizon, commodity=args.commodity, section=args.section)
    if "error" in result:
        print(result["error"])
        return

    entry = next((s for s in result["forecast_series"] if s["month"] == args.target), None)
    print(f"Commodity: {args.commodity} | Section: {args.section}")
    print(f"Last real data point: {last_date:%Y-%m} -> forecasting {horizon} month(s) ahead to reach {args.target}")
    if entry:
        print(f"Forecast for {args.target}: {entry['forecast_tonnes']:,.0f} t "
              f"(95% CI: {entry['lower_bound_95']:,.0f}–{entry['upper_bound_95']:,.0f})")
    print(f"Predictability: {result['summary']['predictability_level']} — {result['summary']['predictability_desc']}")


if __name__ == "__main__":
    main()
