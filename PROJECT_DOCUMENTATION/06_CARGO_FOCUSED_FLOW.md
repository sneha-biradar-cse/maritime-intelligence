# 06 — Cargo-Focused Data Pipeline & Flow

## ⚓ Why Is This Project Classified as "Cargo-Focused"?

Many maritime applications focus solely on AIS ship tracking (vessel location, flag state, vessel speed). While ship tracking is useful, it fails to provide operational intelligence for port logistics and hinterland supply chains.

**This platform is explicitly cargo-focused because:**
1. **Primary Output is Cargo Volume**: All predictions, metrics, and charts calculate throughput in **Cargo Tonnes**, not just ship counts.
2. **Commodity-Wise Segmentation**: Data is analyzed across 16+ distinct commodity categories (Crude Oil, Coal, Iron Ore, Containers, Fertilizers, POL, LPG, Cement, Edible Oil, etc.).
3. **NMPA Infrastructure Mapping**: Every commodity is mapped directly to dedicated port terminal facilities, berth draft depths, and hinterland industrial consumers (MRPL Refinery, UPCL Power Plant, KIOCL, MCF).
4. **Import/Export Directional Analysis**: Distinguishes between `LOADED` (Exports) and `UNLOADED` (Imports) cargo flows.
5. **Cargo Driver Explainability**: Forecast explanations explicitly state why cargo volume is changing (e.g., thermal power plant coal demand, monsoon swell unloading delays).

---

## 🔄 Specific Cargo Data Transformation Pipeline

```text
 ┌─────────────────────────┐
 │  1. Cargo Dataset       │  `data/port_cargo_monthly.csv` (1,354 NMPA historical monthly records)
 └────────────┬────────────┘
              │
              ▼
 ┌─────────────────────────┐
 │  2. Data Cleaning       │  `forecasting.py:_load_and_prep_cargo_data()` (handles nulls, formats dates)
 └────────────┬────────────┘
              │
              ▼
 ┌─────────────────────────┐
 │  3. Cargo Classification│  Groups into `LOADED` / `UNLOADED` & 16 NMPA commodity categories
 └────────────┬────────────┘
              │
              ▼
 ┌─────────────────────────┐
 │  4. Aggregation         │  Monthly tonnage summation & historical YoY variation calculations
 └────────────┬────────────┘
              │
              ▼
 ┌─────────────────────────┐
 │  5. Trend Analysis      │  Exponential Moving Average (EMA) smoothing & trend signal classification
 └────────────┬────────────┘
              │
              ▼
 ┌─────────────────────────┐
 │  6. AI/ML Analysis      │  Holt-Winters + Ridge Regression, 95% Dynamic Interval & WAPE backtesting
 └────────────┬────────────┘
              │
              ▼
 ┌─────────────────────────┐
 │  7. Cargo Insights      │  Quantified drivers, operational recommendations & What-If throughput simulations
 └────────────┬────────────┘
              │
              ▼
 ┌─────────────────────────┐
 │  8. UI Dashboard        │  Streamlit ⭐ Cargo Forecasting Tab & Plotly visualization cards
 └─────────────────────────┘
```

---

## 🔍 Detailed Code-Level Breakdown of Every Cargo Step

### Step 1: Cargo Dataset Ingestion
* **Code Responsible**: `data/port_cargo_monthly.csv`.
* **Details**: Contains historical monthly records for New Mangalore Port Authority across 2021, 2023, 2024, 2025, and 2026.
* **Fields**: `month`, `year`, `section` (`LOADED`/`UNLOADED`), `commodity`, `traffic_tonnes_current`, `vessels_current`, `pct_variation_yoy`.

---

### Step 2: Data Cleaning & Preprocessing
* **Code Responsible**: `backend/app/services/forecasting.py` (functions `_load_and_prep_cargo_data()` and `_get_raw_df()`).
* **Details**: Reads raw CSV rows, converts `year` and `month` into standard datetime objects (`ds`), handles missing values, and casts numeric columns (`traffic_tonnes_current`, `vessels_current`) to standard floating-point values.

---

### Step 3: Cargo & Commodity Classification
* **Code Responsible**: `backend/app/services/forecasting.py` (`NMPA_FACILITY_MAP` dictionary).
* **Details**: Classifies data by flow section and commodity type. Maps each commodity to NMPA terminal berths:
  * `TOTAL CRUDE`: Oil Jetty 1 & 2 / SPM (Draft: 15.4m) → MRPL Refinery.
  * `CRUDE - ISPRL`: Strategic Petroleum Cavern Line → ISPRL Reserve.
  * `TOTAL COAL`: Mechanized Coal Terminal Berths 15 & 16 (Draft: 14.0m) → UPCL Power Plant.
  * `IRON ORE`: KIOCL Bulk Terminal Berth 8 → Kudremukh Corridor.
  * `CONTAINER (JSW)`: Dedicated Container Berth 14 (Draft: 13.0m) → Export Corridor.
  * `FERTILIZER`: Dry Bulk Berths 5 & 6 (Draft: 11.5m) → MCF Plant.

---

### Step 4: Aggregation & Historical Comparison
* **Code Responsible**: `backend/app/services/forecasting.py` (function `get_enhanced_cargo_forecast()`).
* **Details**: Aggregates total monthly tonnage across filtered commodities. Calculates current monthly volume, expected monthly average, total horizon tonnage, and percentage change vs. historical baseline.

---

### Step 5: Cargo Trend Analysis
* **Code Responsible**: `backend/app/services/forecasting.py` (function `_compute_trend_signal()`).
* **Details**: Evaluates Exponential Moving Average (EMA) slopes over a rolling 3-month window to classify traffic trend signals into:
  * `Increasing / Bullish`: Volume expanding > +5%.
  * `Decreasing / Bearish`: Volume contracting < -5%.
  * `Stable / Neutral`: Volume within ±5% tolerance.

---

### Step 6: AI/ML Cargo Forecasting & Backtesting
* **Code Responsible**: `backend/app/services/forecasting.py` (functions `get_enhanced_cargo_forecast()` and `evaluate_forecast_models()`).
* **Details**:
  * Fits Holt-Winters Exponential Smoothing + Ridge Regression to project cargo volume 3, 6, or 12 months ahead.
  * Computes 95% dynamic prediction interval bands (`upper_bounds`, `lower_bounds`).
  * Performs chronological backtesting against out-of-sample historical actuals to compute WAPE (`Weighted Absolute Percentage Error`), MAPE, MAE, and RMSE.

---

### Step 7: Cargo Drivers & Operational Recommendations
* **Code Responsible**: `backend/app/services/forecasting.py` (functions `_generate_cargo_drivers()` and `_generate_cargo_recommendations()`).
* **Details**: Generates transparent explanations detailing why cargo volume is expected to change and provides actionable recommendations (e.g., preparing extra gantry cranes, clearing yard storage, or scheduling night pilotage).

---

### Step 8: Dashboard Presentation & What-If Simulator
* **Code Responsible**: `frontend/app.py` (Tab 3: `⭐ Cargo Forecasting`).
* **Details**: Displays top hero banner (`Predictive Cargo Analytics — See What's Coming. Plan Ahead.`), 3 visual capability cards, selected commodity metrics, Plotly time-series chart, and interactive scenario simulator controls for vessel shifts, trade demand, and weather delays.
