# 04 — System Architecture & Technical Specifications

## 🏗️ High-Level System Architecture Diagram

```text
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   USER BROWSER CLIENT                                  │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                   HTTP / WS │ Port 8501
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                              STREAMLIT DASHBOARD SERVER                                │
 │  (`frontend/app.py`)                                                                   │
 │   - Header & Hero Objective Banner ("Predictive Cargo Analytics")                      │
 │   - 9-Tab Horizontal Navigation Pills                                                  │
 │   - Plotly Graphic Rendering Engines (Scatter, Bar, Donut, Radar, Histograms)          │
 │   - Interactive State Management & Scenario Sliders                                    │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                       JSON REST Requests    │ Port 8000 (Env: BACKEND_URL)
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                FASTAPI BACKEND SERVICE                                 │
 │  (`backend/app/main.py`)                                                               │
 │   - Router Dispatcher (`routes/cargo.py`, `vessels.py`, `trade.py`, `anomaly.py`, etc.) │
 │   - Custom Multipart File Upload Controller (`routes/upload.py`)                      │
 │   - CORS Middleware & JSON Serialization Layer                                         │
 └─────────────┬─────────────────────────────┬─────────────────────────────┬──────────────┘
               │                             │                             │
               ▼                             ▼                             ▼
 ┌───────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
 │   CARGO ML FORECASTING    │ │   SYNTHETIC & TWIN ENGINE │ │   AI COPILOT DISPATCHER   │
 │ (`services/forecasting.py`)│ │ (`services/synthetic_    │ │  (`services/copilot.py`)  │
 │  - Holt-Winters Smoothing │ │   data.py`, `nmpa_        │ │  - LangGraph Cognitive    │
 │  - Ridge Regression       │ │   vessels.py`)            │ │    3-Tier Dispatcher     │
 │  - WAPE Backtesting       │ │  - Monte Carlo Simulator  │ │  - 5 Specialized AI       │
 │  - Driver Explainability  │ │  - Anomaly Generators     │ │    Agent Roster           │
 └─────────────┬─────────────┘ └───────────────────────────┘ └───────────────────────────┘
               │
               ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                DATA PERSISTENCE LAYER                                  │
 │   - Actual NMPA Historical Monthly Traffic (`data/port_cargo_monthly.csv`)             │
 │   - Secondary Multi-Port Sample Data (`data/sample_cargo_data.csv`)                   │
 │   - Uploaded CSV Storage Directory (`uploads/`)                                        │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 💻 1. Frontend Architecture

* **Framework**: Streamlit 1.50.0 (Python-native web application server).
* **Entry Point File**: `frontend/app.py` (1,560+ lines of modular UI code).
* **Styling & Design Token System**:
  * Custom injected CSS stylesheet (`st.markdown("""<style>...</style>""")`).
  * Warm Amber / Cream Color Palette (`#FCFAF5` background, `#1C1917` dark neutral text, `#F59E0B` Gold primary accents, `#FEF3C7` highlight cards).
* **Navigation Architecture**:
  * 9-Tab Horizontal Navigation Pills:
    1. `Executive Dashboard`
    2. `Vessel Intelligence`
    3. `⭐ Cargo Forecasting` (Core Priority Feature)
    4. `Trade Intelligence` (`Commodity Demand by Trade Lane`)
    5. `Anomaly Detection` (`Cargo Anomaly & Risk Intelligence`)
    6. `Incentive Engine`
    7. `Digital Twin`
    8. `AI Maritime Copilot`
    9. `Data Pipeline`
* **Charting Engines**: Plotly 6.7.0 (Plotly Express `px` and Plotly Graph Objects `go` with customized theme `PLOTLY_THEME`).
* **API Communication Layer**: Custom synchronous HTTP helper functions `api_get()` and `api_post()` utilizing the `requests` library with configured timeout handling.

---

## ⚙️ 2. Backend Architecture

* **Framework**: FastAPI 0.128.8 running on Uvicorn ASGI Server (`uvicorn==0.39.0`).
* **Entry Point File**: `backend/app/main.py`.
* **Middlewares**: `CORSMiddleware` (permits cross-origin requests from Streamlit frontend).
* **Router Modular Structure** (`backend/app/routes/`):
  * `cargo.py`: Serves `/cargo/forecast`, `/cargo/commodities`, `/cargo/accuracy`, `/cargo/explainability`, `/cargo/data-quality`, `/cargo/scenario`, `/cargo/berths`.
  * `vessels.py`: Serves `/vessels/`, `/vessels/live`, `/vessels/congestion-alerts`.
  * `trade.py`: Serves `/trade/lanes`, `/trade/commodity-prices`, `/trade/opportunities`.
  * `anomaly.py`: Serves `/anomaly/events`, `/anomaly/history`.
  * `incentive.py`: Serves `/incentive/recommendations`, `/incentive/monte-carlo`.
  * `twin.py`: Serves `/twin/scenario/{key}`, `/twin/berths`.
  * `copilot.py`: Serves `/copilot/suggested-queries`, `/copilot/query`.
  * `pipeline.py`: Serves `/pipeline/status`, `/pipeline/log`.
  * `executive.py`: Serves `/executive/kpis`, `/executive/revenue-trend`, `/executive/events`, `/executive/status`.
  * `security.py`: Serves `/security/threat-alerts`, `/security/classifications`, `/security/audit-logs`, `/security/collaboration-status`.
  * `upload.py`: Serves `POST /upload/` for custom CSV report uploads.
  * `health.py`: Serves `GET /health` liveness checks.

---

## 🗄️ 3. Database & Data Storage Layer

* **Storage Strategy**: In-Memory Pandas DataFrame Data Pool backed by persistent CSV files.
* **Primary Dataset**: `data/port_cargo_monthly.csv` (1,354 records across 2021–2026 NMPA monthly cargo operations).
* **Secondary Datasets**: `data/sample_cargo_data.csv` (multi-port benchmark data) and `uploads/` directory for dynamic user uploads.
* **Data Schemas**:
  * `month` (str), `year` (int), `section` (str: LOADED/UNLOADED), `commodity` (str: Crude, Coal, Containers, etc.), `vessels_current` (float), `vessels_prev_year` (float), `traffic_tonnes_current` (float), `traffic_tonnes_prev_year` (float), `pct_variation_yoy` (float).

---

## 🤖 4. AI & Machine Learning Architecture

* **Primary Time-Series Forecasting Model**:
  * **Combination Model**: Holt-Winters Exponential Smoothing + Multi-Feature Ridge Regression with L2 regularization (`backend/app/services/forecasting.py`).
  * **Features**: Lagged monthly volumes (t-1, t-12), rolling 3-month stats, vessel arrival counts, seasonal indicator dummies.
  * **Prediction Bounds**: 95% dynamic confidence intervals scaled via residual standard error.
* **Model Backtesting & Metrics Engine**:
  * **Baseline Model**: Seasonal Naive / 12-month rolling historical average.
  * **Evaluation Metrics**: Weighted Absolute Percentage Error (WAPE), Mean Absolute Percentage Error (MAPE), Mean Absolute Error (MAE), Root Mean Squared Error (RMSE).
* **Explainability Module**:
  * Multi-factor regression weight decomposition calculating percentage contribution of monsoon swells, hinterland demand, and trade momentum.
* **Simulation & Anomaly Algorithms**:
  * Isolation Forest, LSTM, Autoencoder, and Transformer simulation models for anomaly detection (`backend/app/services/synthetic_data.py`).
  * Monte Carlo 1,000-iteration probability distribution generator for trade incentive revenue modeling.

---

## 🔌 5. External Services & APIs

* **Current Implementation**: The application is fully self-contained with simulated live feeds for external data providers (GDELT trade intelligence feeds, Bloomberg commodity price indices, MITRE ATT&CK security threat framework, and NMPA AIS vessel coordinate feeds).
