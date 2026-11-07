# 05 — Complete Project Execution Flow

This document details the exact sequence of events that occurs from the moment a user launches the browser application to when machine learning predictions and interactive charts update on screen.

---

## 🔄 End-to-End User Interaction Flow Diagram

```text
 User Opens Browser (http://localhost:8501)
                    │
                    ▼
 Streamlit App Execution (`frontend/app.py`)
                    │
                    ▼
 Renders Header & Top Hero Objective Banner
                    │
                    ▼
 Tab 3 Activated ("⭐ Cargo Forecasting")
                    │
                    ▼
 API Call: `api_get("/cargo/commodities")`
                    │
                    ▼
 FastAPI Router (`backend/app/routes/cargo.py:get_commodities()`)
                    │
                    ▼
 Service Call (`backend/app/services/forecasting.py:get_available_commodities()`)
                    │
                    ▼
 Returns List of 16+ Commodities to Frontend Dropdown
                    │
                    ▼
 User Selects Commodity: "TOTAL COAL", Horizon: "6 Months"
                    │
                    ▼
 API Call: `api_get("/cargo/forecast", {"horizon": 6, "commodity": "TOTAL COAL", "section": "ALL"})`
                    │
                    ▼
 FastAPI Router (`backend/app/routes/cargo.py:get_forecast()`)
                    │
                    ▼
 Service Call (`backend/app/services/forecasting.py:get_enhanced_cargo_forecast()`)
                    │
                    ▼
 Data Ingestion & Preprocessing (`_load_and_prep_cargo_data()`)
                    │
                    ▼
 Holt-Winters & Ridge ML Regression Execution
                    │
                    ▼
 Computes 95% Prediction Interval Bands & WAPE Metrics
                    │
                    ▼
 Calculates Driver Weights (Monsoon, Hinterland demand, UPCL Power)
                    │
                    ▼
 API Returns JSON Response Payload (HTTP 200 OK)
                    │
                    ▼
 Frontend Receives Response (`frontend/app.py`)
                    │
                    ▼
 UI Updates Dynamically:
   • Selected Commodity Metrics Banner
   • NMPA Facility Mapping (Berths 15 & 16 UPCL)
   • Plotly Line Chart (Historical Cargo vs Predicted Cargo vs 95% Band)
   • Explainable Forecast Drivers Cards
   • Model Validation Backtesting Table (WAPE vs Baseline)
```

---

## 🛠️ Step-by-Step Code Execution Trace

### Step 1: User Launches Application
* **Action**: User opens browser to `http://localhost:8501`.
* **Code Execution**: Streamlit executes `frontend/app.py` top-to-bottom.
* **UI Action**:
  * Configures wide layout (`st.set_page_config`).
  * Injects CSS design system (`st.markdown("""<style>...</style>""")`).
  * Renders logo, timestamp, and header card (`ys-header`).
  * Renders top hero positioning banner (`Predictive Cargo Analytics — See What's Coming. Plan Ahead.`).

---

### Step 2: Tab Navigation & Filter Initialization
* **Action**: User views the horizontal tab bar. `tabs[2]` (`⭐ Cargo Forecasting`) is selected.
* **Code Execution**:
  * `app.py` line 610 triggers `with tabs[2]:`.
  * Calls `api_get("/cargo/commodities")`.
* **Backend Execution**:
  * FastAPI route `backend/app/routes/cargo.py:get_commodities()` receives GET request.
  * Calls `forecasting.py:get_available_commodities()`.
  * Ingests `data/port_cargo_monthly.csv` and returns JSON array of commodities (`TOTAL COAL`, `TOTAL CRUDE`, `CONTAINER (JSW)`, `IRON ORE`, `FERTILIZER`, etc.).
* **UI Action**: Populates the commodity selectbox dropdown (`col_c1.selectbox("Select Commodity for Cargo Analytics")`).

---

### Step 3: Predictive Cargo Analysis Execution
* **Action**: User selects `TOTAL COAL` and `6 Months` horizon.
* **Code Execution**:
  * `app.py` invokes `api_get("/cargo/forecast", {"horizon": 6, "commodity": "TOTAL COAL", "section": "ALL"})`.
* **Backend Execution**:
  1. `backend/app/routes/cargo.py:get_forecast()` triggers `forecasting.py:get_enhanced_cargo_forecast()`.
  2. Filters `port_cargo_monthly.csv` DataFrame for `TOTAL COAL`.
  3. Resamples time-series data to continuous monthly intervals (`2021-01` to `2026-07`).
  4. Runs Holt-Winters Exponential Smoothing to extract seasonal components and trend vectors.
  5. Fits Ridge Regression on time-lagged features (`t-1`, `t-12`) to generate 6-month predictions.
  6. Calculates residual standard error to construct upper and lower 95% dynamic prediction interval arrays.
  7. Maps facility metadata: `Mechanized Coal Handling Terminal (Berths 15 & 16)`, `Hinterland: UPCL (Udupi Power Corp Ltd)`.
  8. Computes WAPE score (`17.15%`) and accuracy (`82.8%`).
  9. Calculates driver weights: `UPCL Thermal Power Plant Demand (45%)`, `Monsoon Vessel Delay (25%)`, `Hinterland Freight Capacity (20%)`.
  10. Returns full JSON dictionary to frontend.

---

### Step 4: UI Rendering & Visualization
* **Action**: Frontend receives JSON payload.
* **Code Execution**:
  * Renders **Selected Commodity Analytics Banner** displaying volume, expected growth (`+13.6%`), predictability score (`MEDIUM`), and accuracy.
  * Renders **NMPA Facility Banner** displaying berths and draft depth (`14.0 Meters`).
  * Renders **Plotly Main Forecast Chart**:
    * Trace 1: `Historical Cargo (Tonnes)` (Dark grey line).
    * Trace 2: `95% Dynamic Prediction Interval` (Shaded amber band).
    * Trace 3: `Predicted Cargo` (Dashed gold line).
  * Renders **Explainable Forecast Drivers** cards detailing factor impacts and weights.

---

### Step 5: Model Validation & Backtesting Trace
* **Action**: User scrolls down to inspect model validation.
* **Code Execution**:
  * `app.py` calls `api_get("/cargo/accuracy", {"commodity": "TOTAL COAL", "section": "ALL"})`.
  * Backend `forecasting.py:evaluate_forecast_models()` performs chronological out-of-sample backtesting against actual test data.
  * Compares **Baseline Model (Seasonal Naive)** vs **Primary ML Model (Ridge Exponential)**.
  * Renders comparison line chart and WAPE/MAPE/MAE/RMSE comparison table.

---

### Step 6: Interactive What-If Scenario Simulation Trace
* **Action**: User adjusts sliders (`Vessel Arrival Change: +15%`, `Trade Demand Shift: +10%`, `Weather Delay: 1 Day`) and clicks **Run Cargo Scenario Simulation**.
* **Code Execution**:
  * `app.py` sends POST request `api_post("/cargo/scenario", payload)` to `backend/app/routes/cargo.py:run_scenario()`.
  * Calls `forecasting.py:simulate_cargo_scenario()`.
  * Calculates simulated throughput delta (`+13.4%`), net volume delta (`+571,555 Tonnes`), and capacity stress level (`MODERATE_STRESS`).
  * Returns scenario series arrays and operational advisories.
  * Renders **Baseline vs Simulated Scenario Forecast Chart** and warning boxes.
