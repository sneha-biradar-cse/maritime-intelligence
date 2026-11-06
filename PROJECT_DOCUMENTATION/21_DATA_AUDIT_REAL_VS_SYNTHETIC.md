# 21 â€” Data Audit: What's Real vs. Scripted vs. Synthetic

## Purpose

Every API endpoint traced to its backing function in the codebase (not the docs)
to establish, endpoint by endpoint, what is actually grounded in real data versus
generated at request time. Compiled 2026-09-03 against the current `backend/app/`
tree, including the routing module merged in from `heera-art/maritime_port_enhanced`.

## Legend

| Tag | Meaning |
| :--- | :--- |
| ðŸŸ¢ **REAL (ML)** | Trained/backtested model over `data/*.csv`, reports a measured accuracy metric |
| ðŸŸ¢ **REAL (derived)** | Direct computation over real CSV data â€” no model, but no fabrication either |
| ðŸŸ¡ **SCRIPTED** | Deterministic, fixed-list logic (e.g. a hardcoded fleet) â€” not random, but not live/real either |
| ðŸ”´ **SYNTHETIC** | `synthetic_data.py` random generator â€” different numbers on every call, no data backing |

---

## Endpoint-by-endpoint

| Endpoint | Backing function | Tag | Notes |
| :--- | :--- | :--- | :--- |
| `GET /cargo/forecast` | `forecasting.get_enhanced_cargo_forecast()` â†’ `ml_models.fit_cargo_forecast_model()` | ðŸŸ¢ REAL (ML) | RandomForestRegressor, walk-forward backtested, `data/port_cargo_monthly.csv` |
| `GET /cargo/accuracy` | `forecasting.evaluate_forecast_models()` | ðŸŸ¢ REAL (ML) | WAPE/MAPE/MAE/RMSE vs. seasonal-naive baseline |
| `GET /cargo/explainability` | `forecasting._generate_cargo_drivers()` | ðŸŸ¡ SCRIPTED | Percentage driver weights (monsoon/hinterland/market) are **fixed constants**, not fit to data |
| `GET /cargo/data-quality` | `forecasting` (CSV completeness scan) | ðŸŸ¢ REAL (derived) | |
| `POST /cargo/scenario` | `forecasting.simulate_cargo_scenario()` | ðŸŸ¡ SCRIPTED | Elasticity constants for the what-if simulator are documented assumptions, not learned |
| `GET /cargo/berths` | `routing.get_live_berth_status()` | ðŸŸ¢ REAL (derived) | **Fixed 2026-09-03** â€” now uses real `data/berths.csv`/`berth_capacity.csv` capacity + the latest real per-commodity monthly tonnage from `port_cargo_monthly.csv`, annualised the same way `recommend_cargo_route()` does. No live AIS feed exists, so "occupied" means *real cargo moved through that berth's matched commodity last month*, not *a ship is there right now* â€” see the function's docstring and `utilization_basis` field in the response. |
| `GET /forecast/cargo` \| `/forecast/congestion` \| `/forecast/trade` \| `/forecast/recommendations` | delegate to `forecasting`/`ml_models` (see above) | ðŸŸ¢ REAL (ML/derived) | These wrap the same real engine as `/cargo/*` |
| `GET /vessels/` | `nmpa_vessels.get_nmpa_vessels()` | ðŸŸ¡ SCRIPTED | Fixed 25-ship `VESSEL_FLEET` list; positions computed from list index, not live AIS |
| `GET /vessels/eta` | same, self-labeled | ðŸŸ¡ SCRIPTED | Route summary already says *"not a real prediction"* |
| `GET /vessels/congestion-alerts` | `nmpa_vessels.get_nmpa_congestion_alerts()` | ðŸŸ¡ SCRIPTED | Derived from the same fixed fleet |
| `GET /vessels/forecast` | `ml_models.forecast_vessel_calls()` | ðŸŸ¢ REAL (ML) | RandomForestRegressor on monthly vessel-call counts per commodity |
| `GET /anomaly/events` \| `/anomaly/history` | `ml_models` (IsolationForest) | ðŸŸ¢ REAL (ML) | Unsupervised â€” flags outlier months, no labeled ground truth to validate against |
| `GET /incentive/recommendations` | `ml_models.generate_incentive_recommendations()` | ðŸŸ¢ REAL (derived) | Real YoY decline detection; incentive-elasticity **constants are assumed**, not fit |
| `POST /incentive/monte-carlo` | `ml_models.run_incentive_monte_carlo()` | ðŸŸ¢ REAL (derived) | Samples from the commodity's real historical mean/std; no â‚¹ revenue (no price column exists) |
| `GET /twin/scenarios` \| `/scenario/{key}` \| `/berths` | `synthetic_data.*` | ðŸ”´ SYNTHETIC | Every digital-twin stress-test number is generated fresh, no calibration data |
| `GET /trade/summary` \| `/flows` \| `/commodities` \| `/commodity` | `trade_intelligence` (reads `port_cargo_monthly.csv`) | ðŸŸ¢ REAL (derived) | Inbound = UNLOADED, outbound = LOADED. 2022 rebuilt from prior-year columns (flagged); missing months stay missing. `pct_variation_yoy` in the CSV is financial-year-to-date, so YoY is recomputed from tonnes. |
| `GET /trade/alerts` \| `/trade/overseas-coastal` | `trade_intelligence` (`port_cargo_monthly.csv`; `port_overseas_coastal_monthly.csv` from the Ministry of Ports monthly reports) | ðŸŸ¢ REAL (derived) | Overseas/coastal is whole-port only. Months Mar-May and Aug 2026 were checked against NMPA's own commodity statements; see `scripts/verify_trade_against_nmpa.py`. |
| `GET /trade/lanes` \| `/commodity-prices` \| `/opportunities` | `synthetic_data.*` | ðŸ”´ SYNTHETIC | No real trade-lane or pricing dataset exists in the project |
| `GET /copilot/*` | `synthetic_data.generate_copilot_response()` | ðŸ”´ SYNTHETIC | Templated responses; not backed by an LLM or the real dataset |
| `GET /executive/kpis` \| `/events` \| `/revenue-trend` | `synthetic_data.*` | ðŸ”´ SYNTHETIC | Including the â‚¹ revenue figures â€” no financial data exists |
| `GET /pipeline/status` \| `/log` | `synthetic_data.*` | ðŸ”´ SYNTHETIC | Includes a fabricated `"postgresql_records": 847203` â€” there is no database |
| `GET /security/*` | `security.py` service | ðŸ”´ SYNTHETIC (self-labeled) | Routes already say *"Simulated cybersecurity threat detections"* â€” MITRE/DPDP mapping is illustrative |
| `GET /routing/facilities` | `routing.get_all_facilities_list()` | ðŸŸ¢ REAL (derived) | Official NMPA `data/berths.csv` + `data/berth_capacity.csv` (merged in from heera-art repo) |
| `POST /routing/recommend` | `routing.recommend_cargo_route()` | ðŸŸ¢ REAL (derived) | Rule-based, but rules run against the real berth spec sheet, not fabricated |
| `GET /routing/integrated-pipeline` | `routing.get_integrated_forecast_routing()` | ðŸŸ¢ REAL (ML + derived) | Chains the real ML cargo forecast into the real berth-matching engine |
| `POST /upload/` | `upload.py` | â€” | Accepts a CSV but nothing downstream re-ingests it into the working dataset (see Recommendations) |

---

## Summary

- **Genuinely real/data-grounded:** cargo forecasting, vessel-call forecasting, anomaly detection, incentive recommendations, Monte Carlo simulation, and (as of the routing merge) berth/facility matching â€” all traceable to `data/port_cargo_monthly.csv`, `data/berths.csv`, or `data/berth_capacity.csv`.
- **Scripted but not random** (same shape every call, no live source): vessel positions/ETAs, cargo-driver explainability weights, what-if elasticity constants.
- **Fully synthetic** (different fabricated numbers on every request, no data backing at all): digital twin, trade lanes/prices/opportunities, AI copilot, executive KPIs/revenue, pipeline status, and the SOC/security module.

Roughly half the platform's surface area (by endpoint count) is ðŸ”´ SYNTHETIC. That's the gap to close before any of these numbers can be shown to a real port operator as decision-support rather than demo dressing.

## Recommendations, in order of effort-to-impact

1. **`/security/*` and `/executive/*`** are the highest-visibility screens in the dashboard and are 100% synthetic â€” either get real data behind them or make the "simulated" labeling as visible in the UI as it already is in the route docstrings.
2. **`POST /upload/`** accepts a file and does nothing with it â€” either wire uploaded CSVs into the forecasting/routing pipeline, or remove the endpoint's implication that it does.
3. **`/twin/*` and `/trade/*`** need either real data or a documented methodology (right now the numbers are arbitrary).
4. ~~**`/cargo/berths`** should be redirected to the real `/routing/facilities` data~~ â€” **Done.** Now backed by `routing.get_live_berth_status()`.

## Addendum â€” a real bug this fix surfaced (2026-09-03)

Wiring `/cargo/berths` to real data exposed a substring-matching bug inherited from the
original `heera-art/maritime_port_enhanced` source: `routing.py` matched a berth to a
commodity with `berth_id.lower() in default_berth_label.lower()`. Since `"berth 1"` is a
substring of `"berth 10"`, `"berth 11"`, ... `"berth 17"`, **Berth 1** (a shallow, 4,000-DWT
general-cargo berth) was being matched to crude oil, LPG, coal, and containers â€” everything
whose default berth number started with `1`. This silently corrupted three things: the
`suitable_commodities` field on `/routing/facilities`, the `is_preferred` scoring in
`/routing/recommend`, and (had it shipped as originally written) the new berth-status
utilization numbers.

Fixed by comparing berth numbers as integers (`_berth_matches()` in `routing.py`) instead of
raw substrings, with a fallback to exact-token matching for non-numeric ids like `"SPM"`.
Verified: crude-oil routing requests now correctly resolve to SPM/Berth 10/Berth 11 instead
of being polluted by Berth 1.
