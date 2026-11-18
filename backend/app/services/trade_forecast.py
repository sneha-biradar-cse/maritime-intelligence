"""
Trade Intelligence - honest short-term forecast (next 1-3 months).

Design rules (kept deliberately simple, so a port analyst can follow every step):

1. Every method uses ONLY past tonnes from data/port_cargo_monthly.csv (through
   trade_intelligence._prepared()). No made-up inputs.
2. The baseline is "next month = average of the last 12 months with data". A fancier
   method replaces it ONLY if it beats the baseline in BOTH halves of the back-test
   and by at least MIN_RELATIVE_GAIN overall. Otherwise the baseline is kept.
3. Accuracy is measured by a rolling-origin back-test ("go back in time, forecast, compare
   with what really happened", month after month) - never on data the method has seen.
4. The shown range ("typical range") is the 80th percentile of past forecast errors of the method
   that is used, at the same horizon - not a statistical model assumption.
5. If the back-test error is above NOT_FORECASTABLE_WAPE_PCT, no number is shown at all.

Missing months (for example June 2026) are skipped, never treated as zero.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from backend.app.services import trade_intelligence as ti

# ─── Settings (all can be changed) ──────────────────────────────────────────
MAX_HORIZON = 3
FIRST_ORIGIN = 24                 # back-test starts once 24 months of history exist (2 full years)
MIN_TESTED_MONTHS = 18            # fewer back-test points than this -> not enough evidence
MIN_RELATIVE_GAIN = 0.03          # challenger must be >=3% better (relative) than the baseline
RANGE_QUANTILE = 0.80             # share of past months that fall inside the shown range
MIN_SHARE_PCT = 3.0               # single cargos below this share of their direction are not forecast
CONFIDENCE_BANDS = [(10.0, "High"), (20.0, "Medium"), (35.0, "Low")]
NOT_FORECASTABLE_WAPE_PCT = 35.0
BASELINE = "mean12"
CHALLENGER = "seasonal_blend"


# ─── Forecast methods: f(history, target_month) -> tonnes (NaN if it cannot be made) ─
def _last_obs(s: pd.Series, n: int) -> pd.Series:
    return s.dropna().iloc[-n:]


def m_mean12(s: pd.Series, target: pd.Timestamp) -> float:
    """Baseline: average of the last 12 months that have data."""
    return float(_last_obs(s, 12).mean())


def m_same_month_last_year(s: pd.Series, target: pd.Timestamp) -> float:
    v = s.get(target - pd.DateOffset(years=1), np.nan)
    return float(v) if pd.notna(v) else np.nan


def m_seasonal_blend(s: pd.Series, target: pd.Timestamp) -> float:
    """Challenger: average of (12-month average) and (same month last year)."""
    a, b = m_mean12(s, target), m_same_month_last_year(s, target)
    return float((a + b) / 2) if pd.notna(b) else np.nan


METHODS: dict[str, Callable[[pd.Series, pd.Timestamp], float]] = {
    "mean12": m_mean12,
    "seasonal_blend": m_seasonal_blend,
}
METHOD_TEXT = {
    "mean12": "average of the last 12 months",
    "seasonal_blend": "average of the 12-month average and the same month last year",
}


# ─── Back-test ──────────────────────────────────────────────────────────────
def _backtest(s: pd.Series, horizon: int) -> pd.DataFrame:
    """One row per (origin, target) with the actual tonnes and each method's forecast."""
    rows = []
    idx = s.index
    for i in range(FIRST_ORIGIN, len(idx) - horizon + 1):
        origin, target = idx[i - 1], idx[i - 1 + horizon]
        actual = s.loc[target]
        if pd.isna(actual) or actual <= 0:
            continue
        hist = s.loc[:origin]
        row = {"target": target, "actual": float(actual)}
        for name, fn in METHODS.items():
            row[name] = fn(hist, target)
        rows.append(row)
    return pd.DataFrame(rows)


def _wape(r: pd.DataFrame, method: str) -> float:
    """Weighted absolute percentage error: total absolute miss / total actual tonnes."""
    return float((r["actual"] - r[method]).abs().sum() / r["actual"].sum() * 100)


def _evaluate_horizon(s: pd.Series, horizon: int) -> dict[str, Any] | None:
    r = _backtest(s, horizon).dropna()          # only months where BOTH methods could forecast
    if len(r) < MIN_TESTED_MONTHS:
        return None
    half = len(r) // 2
    first, second = r.iloc[:half], r.iloc[half:]
    base, chal = _wape(r, BASELINE), _wape(r, CHALLENGER)
    wins_both_halves = _wape(first, CHALLENGER) < _wape(first, BASELINE) and _wape(second, CHALLENGER) < _wape(second, BASELINE)
    adopt = bool(wins_both_halves and chal <= base * (1 - MIN_RELATIVE_GAIN))
    used = CHALLENGER if adopt else BASELINE
    rel_err = ((r["actual"] - r[used]).abs() / r[used]).to_numpy()
    return {
        "tested_months": int(len(r)),
        "baseline_wape_pct": round(base, 1),
        "challenger_wape_pct": round(chal, 1),
        "challenger_wins_both_halves": bool(wins_both_halves),
        "method_used": used,
        "used_wape_pct": round(chal if adopt else base, 1),
        "range_pct": float(np.quantile(rel_err, RANGE_QUANTILE)),
    }


def _confidence(wape_pct: float) -> str:
    for limit, label in CONFIDENCE_BANDS:
        if wape_pct < limit:
            return label
    return "Not forecastable"


def _forecast_series(label: str, direction: str, kind: str, s: pd.Series, horizon: int) -> dict[str, Any]:
    last = s.dropna().index.max()
    out: dict[str, Any] = {"series": label, "direction": direction, "kind": kind, "forecast": [], "by_horizon": {}}
    for h in range(1, horizon + 1):
        ev = _evaluate_horizon(s, h)
        if ev is None:
            continue
        out["by_horizon"][h] = ev
    if 1 not in out["by_horizon"]:
        out.update(confidence="Not enough history", verdict="Not enough past months to test a forecast fairly.")
        return out
    ev1 = out["by_horizon"][1]
    conf = _confidence(ev1["used_wape_pct"])
    out["confidence"] = conf
    out["method_used"] = ev1["method_used"]
    out["method_text"] = METHOD_TEXT[ev1["method_used"]]
    out["baseline_wape_pct"] = ev1["baseline_wape_pct"]
    out["used_wape_pct"] = ev1["used_wape_pct"]
    out["tested_months"] = ev1["tested_months"]
    if conf == "Not forecastable":
        out["verdict"] = (f"Past forecasts missed by about {ev1['used_wape_pct']:.0f}% of the tonnes, so no forecast number "
                          "is shown. This cargo moves in large, irregular shipments.")
        return out
    for h in range(1, horizon + 1):
        ev = out["by_horizon"].get(h)
        if ev is None:
            continue
        target = last + pd.DateOffset(months=h)
        value = METHODS[ev["method_used"]](s, target)
        if pd.isna(value):                      # e.g. seasonal data missing -> fall back to the baseline
            value = METHODS[BASELINE](s, target)
        q = ev["range_pct"]
        out["forecast"].append({
            "month": target.strftime("%Y-%m"),
            "horizon_months": h,
            "forecast_tonnes": round(float(value)),
            "range_low_tonnes": round(max(0.0, float(value) * (1 - q))),
            "range_high_tonnes": round(float(value) * (1 + q)),
            "typical_range_pct": round(q * 100, 1),
            "method_used": ev["method_used"],
            "backtest_wape_pct": ev["used_wape_pct"],
        })
    if ev1["method_used"] == CHALLENGER:
        out["verdict"] = (f"Seasonal blend beat the 12-month average in both halves of the test "
                          f"({ev1['challenger_wape_pct']}% vs {ev1['baseline_wape_pct']}% error), so it is used.")
    else:
        out["verdict"] = (f"No method clearly beat the plain 12-month average (error {ev1['baseline_wape_pct']}%), "
                          "so the plain average is used.")
    return out


def _series_catalogue(p: dict) -> list[tuple[str, str, str, pd.Series]]:
    tot, wide = p["totals"], p["wide"]
    items: list[tuple[str, str, str, pd.Series]] = [
        ("All inbound cargo", "inbound", "direction", tot["inbound"]),
        ("All outbound cargo", "outbound", "direction", tot["outbound"]),
        ("All cargo (in + out)", "total", "direction", tot["total"]),
    ]
    for r in ti._commodity_rows(p):
        if (r["share_of_direction_pct"] or 0) < MIN_SHARE_PCT or r["signal"] == "Irregular":
            continue
        section = ti.SECTION[r["direction"]]
        key = ti._canon(r["commodity"])
        cols = [c for c in wide[section].columns if ti._canon(c) == key]
        if cols:
            items.append((p["names"].get(key, r["commodity"]), r["direction"], "cargo", wide[(section, cols[0])]))
    return items


def get_trade_forecast(horizon: int = MAX_HORIZON) -> dict[str, Any]:
    horizon = max(1, min(int(horizon), MAX_HORIZON))
    p = ti._prepared()
    results = [_forecast_series(lbl, d, k, s, horizon) for lbl, d, k, s in _series_catalogue(p)]
    return {
        "as_of": p["data_quality"]["latest_month"],
        "horizon_months": horizon,
        "data_source": "data/port_cargo_monthly.csv (NMPA monthly commodity-wise traffic statements)",
        "how_it_works": [
            "Baseline = average of the last 12 months with data. A fancier method replaces it only if it wins in both "
            "halves of the back-test and by at least 3%.",
            "Back-test = go back in time month by month, forecast, and compare with what really happened.",
            "Typical range = the size of miss that 80% of past forecasts stayed within.",
            "If past forecasts missed by more than 35% of the tonnes, no number is shown.",
        ],
        "limits": [
            "Uses only past tonnes. It does not know about ship schedules, contracts, prices or port closures.",
            "Single big shipments cannot be predicted from past tonnes, so cargo-level forecasts are rougher than totals.",
            "June 2026 is missing in the source and is skipped, not treated as zero.",
            "A forecast here is a planning guide, not a promise.",
        ],
        "results": results,
    }
