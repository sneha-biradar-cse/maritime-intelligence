# 07 — Frontend Architecture & UI Component Guide

## 🎨 Overview of the Frontend Layer

The frontend of the Maritime Port Intelligence Platform is a single-page web dashboard built using **Streamlit 1.50.0** and **Plotly 6.7.0**. It is contained inside `frontend/app.py` (1,560+ lines of Python UI code).

### Simple Explanation to Tell Your Mentor:
> *"The frontend is responsible for presenting an intuitive, real-time decision-support console to port managers. It communicates asynchronously with our FastAPI backend REST endpoints, transforms raw JSON data into visual Plotly time-series charts, and allows operational staff to interactively filter commodities, evaluate forecast driver explainability, and run What-If cargo simulations."*

---

## 🛠️ Key Frontend Components & Helper Functions

### 1. Injected Custom CSS System (`app.py` lines 70–314)
* **Purpose**: Replaces standard default Streamlit styles with a custom Warm Amber / Cream design token system (`#FCFAF5` background, `#1C1917` dark neutral text, `#F59E0B` Gold primary accents).
* **Components Injected**: `.ys-header`, `.ys-live-badge`, `.alert-card`, `.rec-card`, `.opp-card`, `.pipeline-stage`, `.log-container`.

### 2. API Communication Helpers (`app.py` lines 43–60)
* **`api_get(path, params)`**: Issues HTTP GET requests to backend `http://127.0.0.1:8000{path}` with a 6-second timeout and JSON parsing.
* **`api_post(path, payload)`**: Issues HTTP POST requests to backend `http://127.0.0.1:8000{path}` with JSON payload and error handling.

---

## 📑 Complete Breakdown of All 9 Navigation Tabs

### Tab 1: Executive Dashboard (`tabs[0]`)
* **Purpose**: Provides a top-level port-wide command center for executive leadership.
* **APIs Called**:
  * `GET /executive/kpis` (Berth utilization, inbound vessels, daily throughput, revenue, congestion index).
  * `GET /vessels/` (Live AIS vessel positions for NMPA approach & anchorages scatter map).
  * `GET /executive/revenue-trend` (30-day revenue & throughput dual-axis trend line).
  * `GET /cargo/berths` (Berth occupancy bar chart).
  * `GET /executive/events` (Live port event feed).
* **Visuals Displayed**: 8 KPI metric cards, Plotly NMPA vessel approach map, 30-day revenue/throughput graph, berth occupancy bar chart, commodity donut pie chart, and recent event timeline.

---

### Tab 2: Vessel Intelligence (`tabs[1]`)
* **Purpose**: AIS vessel tracking, ETA predictions, delay probabilities, and route risk scoring.
* **APIs Called**:
  * `GET /vessels/` (Tracked vessels list).
  * `GET /vessels/congestion-alerts` (Congestion risk warnings).
* **Visuals Displayed**: 4 KPI metric cards, interactive vessel tracker dataframe with progress bars for delay probability and route risk, horizontal ETA arrival bar chart, congestion alert cards, and Route Risk vs Delay Probability scatter plot.

---

### ⭐ Tab 3: Cargo Forecasting — CORE FEATURE (`tabs[2]`)
* **Purpose**: Predictive Cargo Analytics, volume forecasting, commodity breakdown, driver explainability, backtesting model validation, and What-If scenario simulation.
* **APIs Called**:
  * `GET /cargo/commodities` (List of commodities for dropdown).
  * `GET /cargo/forecast` (Main forecast payload with 95% dynamic prediction interval and drivers).
  * `GET /cargo/accuracy` (Chronological backtesting matrix vs Seasonal Naive baseline).
  * `POST /cargo/scenario` (Interactive What-If cargo scenario simulator).
* **Visuals Displayed**:
  * **Top Hero Objective Banner**: `Predictive Cargo Analytics — See What's Coming. Plan Ahead.`
  * **3 Visual Capability Cards**: `Cargo Volume Forecasting`, `Commodity & Trade Demand`, `Cargo Risk & Anomaly Detection`.
  * **Selected Commodity Analytics Banner**: Current volume, forecast average, expected growth %, predictability level, and accuracy.
  * **NMPA Facility Banner**: Berths, hinterland consumer, draft depth.
  * **Plotly Main Forecast Graph**: `Cargo Volume Forecast — [Commodity] — [Horizon] Month Horizon` with Y-axis `Cargo Volume (Tonnes)` and X-axis `Month`.
  * **Explainable Forecast Drivers**: Card list detailing WHY cargo is changing.
  * **Cargo Forecast Model Validation Table & Plot**: WAPE, MAPE, MAE, RMSE performance comparison.
  * **What-If Cargo Scenario Simulator**: Sliders for vessel shift %, trade demand %, weather delay days, metrics for `Predicted Cargo Throughput`, and scenario comparison chart.

---

### Tab 4: Trade Intelligence (`tabs[3]`)
* **Purpose**: Analyzes commodity demand by trade lane, commodity price indices, and market opportunities.
* **APIs Called**:
  * `GET /trade/lanes` (Trade lane growth/decline YoY %).
  * `GET /trade/commodity-prices` (30-day commodity price trends in USD).
  * `GET /trade/opportunities` (AI-ranked trade opportunities).
* **Visuals Displayed**: Section header `Commodity Demand by Trade Lane`, horizontal bar chart of growing/declining trade routes, commodity price ticker cards, 30-day price trend line chart, and AI-ranked market opportunity cards.

---

### Tab 5: Anomaly Detection (`tabs[4]`)
* **Purpose**: Detects cargo volume surges, volume decline anomalies, commodity movement deviations, and operational bottlenecks.
* **APIs Called**:
  * `GET /anomaly/events` (Active anomaly event logs).
  * `GET /anomaly/history` (30-day anomaly frequency histogram).
* **Visuals Displayed**: Section header `Cargo Anomaly & Risk Intelligence`, Severity Progression Bar (`Normal → Low/Medium Risk → High Risk Warning → Critical Anomaly`), active anomaly cards, stacked bar chart of anomaly frequency, and algorithm explanatory panel (Isolation Forest, LSTM, Autoencoder, Transformer).

---

### Tab 6: Incentive Engine (`tabs[5]`)
* **Purpose**: RL-based trade policy optimization and Monte Carlo revenue maximization.
* **APIs Called**:
  * `GET /incentive/recommendations` (Priority-ranked policy recommendations).
  * `POST /incentive/monte-carlo` (1,000-iteration Monte Carlo simulation).
* **Visuals Displayed**: AI policy recommendation cards, Monte Carlo interactive sliders (handling charges, incentive rates), revenue histogram distribution with P10/P50/P90 markers.

---

### Tab 7: Digital Twin (`tabs[6]`)
* **Purpose**: Virtual port simulation for stress-testing cargo, vessel, weather, and policy disruptions.
* **APIs Called**:
  * `GET /twin/scenario/{key}` (Scenario simulation parameters).
  * `GET /twin/berths` (Simulated berth utilization).
* **Visuals Displayed**: Scenario selector dropdown, risk level badge, KPI deltas, radar chart comparing scenario vs baseline, workforce/crane delta metrics, and berth utilization grouped bar chart.

---

### Tab 8: AI Maritime Copilot (`tabs[7]`)
* **Purpose**: Natural language query interface powered by a 3-tier cognitive dispatcher.
* **APIs Called**:
  * `GET /copilot/suggested-queries` (Suggested question chips).
  * `POST /copilot/query` (Dispatches natural language query).
* **Visuals Displayed**: Agent roster cards (Forecast, Trade, Policy, Simulation, Reporting agents), suggested query chips, text query input area, 3-tier dispatch trace step log, and structured markdown response box.

---

### Tab 9: Data Pipeline (`tabs[8]`)
* **Purpose**: Displays system architecture, Kafka/Spark ingestion metrics, data pool statistics, and system architecture diagrams.
* **APIs Called**:
  * `GET /pipeline/status` (Kafka, Spark, Airflow, and database metrics).
  * `GET /pipeline/log` (Live ingestion event log).
* **Visuals Displayed**: 4 pipeline stage cards, live system metrics (msg/sec, consumer lag, uptime), live event log container, data pool storage cards, and 4 system architecture diagrams.
