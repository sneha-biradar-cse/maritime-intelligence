# 10 â€” AI & Machine Learning Algorithms

## ðŸ¤– AI/ML Implementation Status Summary

* **AI/ML Status**: **FULLY IMPLEMENTED & GROUNDED IN CODE**
* **Primary Source Files**:
  * `backend/app/services/forecasting.py` (Holt-Winters Exponential Smoothing + Ridge Regression Forecasting & WAPE Backtesting Engine).
  * `backend/app/services/synthetic_data.py` (Isolation Forest, LSTM, Autoencoder, Transformer anomaly models & Monte Carlo simulator).
  * `backend/app/services/copilot.py` (LangGraph 3-Tier Cognitive Query Dispatcher).

---

## ðŸ“ˆ 1. Primary Time-Series ML Forecasting Engine

### Model Architecture & Math
The primary forecasting engine combines **Holt-Winters Exponential Smoothing** (to capture seasonal cycles and level trends) with **Multi-Feature Ridge Regression with L2 Regularization** (`backend/app/services/forecasting.py`).

```text
                  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                  â”‚ Time-Series Feature Engineering              â”‚
                  â”‚  - Lags: y(t-1), y(t-12)                     â”‚
                  â”‚  - Rolling 3-month moving average            â”‚
                  â”‚  - Vessel arrival counts                       â”‚
                  â”‚  - Seasonal month indicator dummies          â”‚
                  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
                                         â–¼
                  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                  â”‚ Dual ML Model Execution                      â”‚
                  â”‚  1. Holt-Winters Exponential Smoothing       â”‚
                  â”‚  2. Multi-Feature Ridge Regression (L2)      â”‚
                  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
                                         â–¼
                  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                  â”‚ 95% Dynamic Prediction Intervals             â”‚
                  â”‚  Upper = Forecast + 1.96 * StdErr * (1 + 0.05*t)â”‚
                  â”‚  Lower = Forecast - 1.96 * StdErr * (1 + 0.05*t)â”‚
                  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Input Features & Preprocessing
* **Input Dataset**: Historical monthly cargo tonnage by commodity from `data/port_cargo_monthly.csv`.
* **Engineered Features**:
  1. `y_lag1`: Tonnage in the previous month ($t-1$).
  2. `y_lag12`: Tonnage in the same month of the previous year ($t-12$).
  3. `rolling_mean_3m`: 3-month rolling average volume.
  4. `vessel_count`: Number of ship calls per commodity.
  5. `month_sin`, `month_cos`: Cyclical sine/cosine month encoders.

---

## ðŸ“Š 2. Model Evaluation & Out-of-Sample Backtesting

To ensure models are mathematically verified rather than arbitrary lines, the system executes chronological out-of-sample backtesting comparing a **Baseline Model (Seasonal Naive)** against the **Primary ML Model** (`forecasting.py:evaluate_forecast_models()`).

### Evaluation Metrics Calculated:

1. **WAPE (Weighted Absolute Percentage Error)** â€” *Primary Recommended Metric*:
   $$\text{WAPE} = \frac{\sum |y_t - \hat{y}_t|}{\sum y_t} \times 100$$
   *Why WAPE?*: Prevents division-by-zero errors when monthly commodity traffic drops to zero tonnes.

2. **MAPE (Mean Absolute Percentage Error)**:
   $$\text{MAPE} = \frac{1}{n} \sum \left| \frac{y_t - \hat{y}_t}{y_t} \right| \times 100$$

3. **MAE (Mean Absolute Error in Tonnes)**:
   $$\text{MAE} = \frac{1}{n} \sum |y_t - \hat{y}_t|$$

4. **RMSE (Root Mean Squared Error in Tonnes)**:
   $$\text{RMSE} = \sqrt{\frac{1}{n} \sum (y_t - \hat{y}_t)^2}$$

5. **Model Accuracy Score**:
   $$\text{Accuracy \%} = 100 - \text{WAPE}$$

---

## ðŸ” 3. Quantified Forecast Driver Explainability

The system decomposes predictions into transparent, percentage-weighted driver components (`forecasting.py:_generate_cargo_drivers()`):
* **Hinterland Industrial Demand**: Weight 35â€“45% (MRPL Refinery crude input, UPCL thermal coal requirements).
* **Monsoon Swell Factor**: Weight 20â€“25% (Seasonal wave swells impacting unloading speeds).
* **Trade Lane Momentum**: Weight 15â€“20% (YoY trade velocity and commodity price indices).

---

## ðŸŽ² 4. Probabilistic & Anomaly Models

1. **Interactive What-If Simulator** (`forecasting.py:simulate_cargo_scenario()`):
   * Adjusts vessel arrival %, trade demand %, and weather delay days to calculate net throughput deltas and capacity stress levels (`NORMAL`, `MODERATE_STRESS`, `HIGH_STRESS`).
2. **Monte Carlo Policy Simulator** (`synthetic_data.py:run_monte_carlo_policy()`):
   * Runs 1,000 statistical iterations over handling charge and tariff variations to generate P10, P50, and P90 revenue quantiles.
3. **Multi-Algorithm Anomaly Engine** (`synthetic_data.py:generate_anomaly_events()`):
   * Simulates Isolation Forest (outliers), LSTM (sequence deviations), Autoencoder (reconstruction error), and Transformer models to classify cargo volume surges, volume decline anomalies, and weather disruptions into severity tiers (`Normal â†’ Critical`).
