"""Tests for the honest 1-3 month forecast (real NMPA data, no network needed)."""
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import trade_forecast as tf
from backend.app.services import trade_intelligence as ti

client = TestClient(app)


def _series(values, start="2022-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


# ── methods ───────────────────────────────────────────────────────────────────
def test_mean12_is_average_of_last_12_months_with_data():
    s = _series(list(range(1, 25)))                       # 1..24
    assert tf.m_mean12(s, pd.Timestamp("2024-01-01")) == pytest.approx(np.mean(range(13, 25)))


def test_mean12_skips_missing_months_not_zero():
    s = _series([10.0] * 24)
    s.iloc[-1] = np.nan
    assert tf.m_mean12(s, pd.Timestamp("2024-01-01")) == pytest.approx(10.0)   # a zero would give < 10


def test_seasonal_blend_is_average_of_mean12_and_same_month_last_year():
    s = _series([100.0] * 12 + [200.0] + [100.0] * 11)    # Jan 2022 = 100, Jan 2023 = 200
    target = pd.Timestamp("2024-01-01")
    expected = (tf.m_mean12(s, target) + 200.0) / 2
    assert tf.m_seasonal_blend(s, target) == pytest.approx(expected)


def test_seasonal_blend_is_nan_without_last_year_value():
    s = _series([100.0] * 24).drop(pd.Timestamp("2023-01-01"))
    assert np.isnan(tf.m_seasonal_blend(s, pd.Timestamp("2024-01-01")))


# ── back-test ─────────────────────────────────────────────────────────────────
def test_backtest_never_uses_future_data():
    rng = np.random.default_rng(1)
    s = _series(rng.uniform(80, 120, 40))
    before = tf._backtest(s, 1)
    s2 = s.copy()
    s2.iloc[-1] = 9999.0                                   # change only the very last month
    after = tf._backtest(s2, 1)
    assert before.iloc[:-1][["mean12", "seasonal_blend"]].equals(after.iloc[:-1][["mean12", "seasonal_blend"]])


def test_wape_matches_hand_calculation():
    r = pd.DataFrame({"actual": [100.0, 200.0], "mean12": [90.0, 230.0], "seasonal_blend": [100.0, 200.0]})
    assert tf._wape(r, "mean12") == pytest.approx((10 + 30) / 300 * 100)


def test_baseline_error_matches_independent_loop_on_real_inbound():
    s = ti._prepared()["totals"]["inbound"]
    errs, acts = 0.0, 0.0
    ev = tf._backtest(s, 1).dropna()
    for i in range(tf.FIRST_ORIGIN, len(s)):
        t = s.index[i]
        if pd.isna(s.iloc[i]) or t not in set(ev["target"]):
            continue
        f = np.mean(s.iloc[:i].dropna().iloc[-12:])
        errs += abs(s.iloc[i] - f)
        acts += s.iloc[i]
    assert tf._wape(ev, "mean12") == pytest.approx(errs / acts * 100)


# ── honesty rules on the real output ─────────────────────────────────────────
@pytest.fixture(scope="module")
def result():
    return tf.get_trade_forecast()


def test_forecast_months_come_after_latest_data(result):
    last = pd.Timestamp(result["as_of"] + "-01")
    for x in result["results"]:
        for f in x["forecast"]:
            assert pd.Timestamp(f["month"] + "-01") > last


def test_challenger_used_only_when_it_wins_both_halves_by_margin(result):
    for x in result["results"]:
        for h, ev in x["by_horizon"].items():
            if ev["method_used"] == tf.CHALLENGER:
                assert ev["challenger_wins_both_halves"]
                assert ev["challenger_wape_pct"] <= ev["baseline_wape_pct"] * (1 - tf.MIN_RELATIVE_GAIN) + 0.05
            else:
                assert ev["used_wape_pct"] == ev["baseline_wape_pct"]


def test_not_forecastable_shows_no_number_and_high_error(result):
    for x in result["results"]:
        if x["confidence"] == "Not forecastable":
            assert x["forecast"] == []
            assert x["used_wape_pct"] >= tf.NOT_FORECASTABLE_WAPE_PCT


def test_range_contains_forecast_and_is_not_negative(result):
    for x in result["results"]:
        for f in x["forecast"]:
            assert 0 <= f["range_low_tonnes"] <= f["forecast_tonnes"] <= f["range_high_tonnes"]


def test_irregular_and_tiny_cargos_are_not_forecast(result):
    names = {(x["series"], x["direction"]) for x in result["results"] if x["kind"] == "cargo"}
    rows = ti._commodity_rows(ti._prepared())
    for r in rows:
        if (r["share_of_direction_pct"] or 0) < tf.MIN_SHARE_PCT or r["signal"] == "Irregular":
            assert not any(n == ti._prepared()["names"].get(ti._canon(r["commodity"]), r["commodity"]) and d == r["direction"] for n, d in names)


# ── API ───────────────────────────────────────────────────────────────────────
def test_endpoint_ok_json_and_no_nan():
    r = client.get("/trade/forecast")
    assert r.status_code == 200
    body = json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c} in JSON"))
    assert body["results"] and body["limits"]


def test_endpoint_horizon_limits():
    assert client.get("/trade/forecast?horizon=4").status_code == 422
    assert client.get("/trade/forecast?horizon=0").status_code == 422
    one = client.get("/trade/forecast?horizon=1").json()
    assert all(len(x["forecast"]) <= 1 for x in one["results"])
