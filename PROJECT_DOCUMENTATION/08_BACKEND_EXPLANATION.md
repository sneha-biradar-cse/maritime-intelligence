# 08 — Backend Architecture & Service Layer Reference

## ⚙️ Backend Structure & Module Overview

The backend of the Maritime Port Intelligence Platform is built on **FastAPI** (`0.128.8`) and running asynchronously on **Uvicorn** (`0.39.0`).

```text
backend/
├── app/
│   ├── main.py                   # FastAPI Application Entry Point & Router Assembly
│   ├── routes/                   # HTTP Controller Router Layer
│   │   ├── cargo.py              # Cargo Forecasting & Scenario Simulation Routes
│   │   ├── vessels.py            # AIS Vessel Tracking & Congestion Routes
│   │   ├── trade.py              # Trade Lanes & Commodity Prices Routes
│   │   ├── anomaly.py            # Anomaly Detection Event Routes
│   │   ├── incentive.py          # Trade Incentive & Monte Carlo Simulation Routes
│   │   ├── twin.py               # Digital Twin Scenario Routes
│   │   ├── copilot.py            # AI Copilot Query & Dispatcher Routes
│   │   ├── pipeline.py           # Ingestion Pipeline & Log Routes
│   │   ├── executive.py          # Executive KPI & Revenue Trend Routes
│   │   ├── security.py           # SOC Threats, DPDP Compliance & Audit Logs Routes
│   │   ├── upload.py             # Custom CSV File Upload Controller
│   │   ├── forecast.py           # Intelligence Forecasting Router
│   │   └── health.py             # Health Check Route
│   └── services/                 # Analytical Business Logic & Analytical Engines
│       ├── forecasting.py        # Holt-Winters + Ridge Regression ML Cargo Engine
│       ├── synthetic_data.py     # Port Metric Generators & Monte Carlo Engine
│       ├── copilot.py            # LangGraph Cognitive 3-Tier Query Dispatcher
│       ├── nmpa_vessels.py       # AIS Tracking & Vessel Route Risk Engine
│       └── security.py           # MITRE ATT&CK & Cryptographic Audit Logger
```

---

## 🔍 Detailed Breakdown of Every Backend File

### File: `backend/app/main.py`
* **Purpose**: Application entry point. Instantiates `FastAPI(title="YellowSense Maritime Intelligence API")`, configures CORS middleware, mounts all 12 feature routers, and defines root status endpoint.
* **Input**: Server startup invocation (`uvicorn backend.app.main:app`).
* **Processing**: Registers router prefixes (`/cargo`, `/vessels`, `/trade`, `/anomaly`, etc.).
* **Output**: Running HTTP ASGI server instance on port 8000.
* **Used by**: Uvicorn server launcher & Streamlit HTTP frontend.

---

### File: `backend/app/routes/cargo.py`
* **Purpose**: Exposes REST endpoints for cargo volume forecasting, commodity metadata, backtesting model evaluation, forecast explainability drivers, and What-If scenario simulations.
* **Input**: HTTP GET/POST queries (`horizon`, `commodity`, `section`, scenario JSON payloads).
* **Processing**: Validates input parameters via FastAPI `Query` and `Body` helpers and delegates computations to `services/forecasting.py`.
* **Output**: JSON REST responses containing forecast values, prediction intervals, WAPE metrics, and simulation results.
* **Used by**: Streamlit Tab 3 (`⭐ Cargo Forecasting`).

---

### File: `backend/app/routes/vessels.py`
* **Purpose**: Serves live AIS vessel tracking data, ETA countdowns, and berth congestion alert logs.
* **Input**: HTTP GET request.
* **Processing**: Calls `services/nmpa_vessels.py:get_nmpa_vessels()`.
* **Output**: JSON list of 25 active vessels with coordinate locations (`lat`, `lon`), delay probabilities, and route risk scores.
* **Used by**: Streamlit Tab 1 & Tab 2 (`Executive Dashboard` & `Vessel Intelligence`).

---

### File: `backend/app/routes/trade.py`
* **Purpose**: Exposes endpoints for commodity trade lane growth, Bloomberg commodity price indices, and AI-ranked market opportunities.
* **Input**: HTTP GET request.
* **Processing**: Delegates data extraction to `services/synthetic_data.py`.
* **Output**: JSON payload of trade routes, growth YoY %, price trends, and revenue potentials.
* **Used by**: Streamlit Tab 4 (`Commodity Demand by Trade Lane`).

---

### File: `backend/app/routes/anomaly.py`
* **Purpose**: Serves active anomaly detection logs and historical severity frequency distributions.
* **Input**: HTTP GET request.
* **Processing**: Calls `services/synthetic_data.py:generate_anomaly_events()`.
* **Output**: JSON list of classified anomaly events (Surge, Decline, Congestion, Weather) with severity ratings (`Normal → Critical`).
* **Used by**: Streamlit Tab 5 (`Cargo Anomaly & Risk Intelligence`).

---

### File: `backend/app/routes/incentive.py`
* **Purpose**: Serves RL trade incentive recommendations and accepts POST requests for 1,000-iteration Monte Carlo revenue simulations.
* **Input**: HTTP GET and POST JSON payloads (`scenario`, `charge_delta`, `incentive_pct`).
* **Processing**: Calls Monte Carlo probabilistic engine in `services/synthetic_data.py`.
* **Output**: P10, P50, P90 revenue quantiles and sample arrays for Plotly histogram.
* **Used by**: Streamlit Tab 6 (`Incentive Engine`).

---

### File: `backend/app/routes/twin.py`
* **Purpose**: Serves virtual port digital twin scenario stress-test results.
* **Input**: HTTP GET scenario key (`cargo_surge`, `vessel_delay`, `weather_disruption`, `incentive_change`).
* **Processing**: Computes congestion index, berth/storage utilization, workforce deltas, and radar comparison points.
* **Output**: JSON dictionary of baseline vs scenario metrics.
* **Used by**: Streamlit Tab 7 (`Digital Twin`).

---

### File: `backend/app/routes/copilot.py`
* **Purpose**: Handles conversational queries directed to the AI Maritime Copilot.
* **Input**: HTTP POST query payload (`{"query": "Why is cargo forecast decreasing?"}`).
* **Processing**: Dispatches query through `services/copilot.py:dispatch_copilot_query()`.
* **Output**: JSON payload containing 3-tier dispatch trace, confidence score, and answer text.
* **Used by**: Streamlit Tab 8 (`AI Maritime Copilot`).

---

### File: `backend/app/routes/upload.py`
* **Purpose**: Accepts multipart form uploads for custom CSV reports.
* **Input**: Multipart file binary stream (`file: UploadFile`).
* **Processing**: Validates `.csv` extension, checks size limit (max 20MB), saves file to `uploads/` directory, and validates CSV structure using Pandas.
* **Output**: Success status JSON with file path, row count, and parsed column headers.
* **Used by**: External API clients & data integration tools.

---

### File: `backend/app/services/forecasting.py` (666 lines)
* **Purpose**: Core analytical ML engine of the platform. Loads `data/port_cargo_monthly.csv`, performs time-series feature engineering, fits Holt-Winters Exponential Smoothing + Ridge Regression models, computes 95% dynamic prediction interval bounds, evaluates WAPE/MAPE/MAE/RMSE out-of-sample backtesting metrics, maps NMPA berths, and executes scenario simulations.
* **Input**: Filter parameters (`horizon`, `commodity`, `section`) or scenario vectors.
* **Processing**: Advanced Pandas time-series resampling, NumPy matrix operations, Scipy/Holt-Winters math.
* **Output**: Structured Python dictionary consumed directly by `routes/cargo.py`.
* **Used by**: `routes/cargo.py` & `routes/forecast.py`.

---

### File: `backend/app/services/synthetic_data.py` (720 lines)
* **Purpose**: Generates realistic simulation data for berth statuses, trade lane momentum, commodity price indices, anomaly events, Monte Carlo revenue distributions, executive KPIs, and digital twin scenarios.
* **Input**: Function parameters and random seeds.
* **Processing**: NumPy statistical sampling, Gaussian noise distributions, deterministic pseudo-random seed controls.
* **Output**: Python dictionaries for trade, anomaly, executive, twin, and incentive endpoints.
* **Used by**: `routes/trade.py`, `routes/anomaly.py`, `routes/incentive.py`, `routes/twin.py`, `routes/executive.py`.

---

### File: `backend/app/services/copilot.py` (600 lines)
* **Purpose**: Implements the LangGraph 3-tier cognitive query dispatcher.
  * **Tier 1 (Heavy Synthesis LLM)**: Complex multi-variable queries.
  * **Tier 2 (Fast Reasoning SLM)**: Domain specific cargo queries.
  * **Tier 3 (Deterministic Zero-LLM)**: Fallback rule engine for instant responses.
* **Input**: User string query.
* **Processing**: Pattern matching, intent classification, simulated step-by-step dispatch trace generation, agent assignment.
* **Output**: Answer text, confidence score, data references, and trace steps.
* **Used by**: `routes/copilot.py`.

---

## 🔁 Request-Response Lifecycle

```text
1. Client Sends Request  ──► HTTP GET /cargo/forecast?horizon=6&commodity=TOTAL%20COAL
2. FastAPI Middleware    ──► CORS validation & URL path matching
3. Router Dispatcher     ──► Calls `routes/cargo.py:get_forecast()`
4. Business Service      ──► Invokes `forecasting.py:get_enhanced_cargo_forecast()`
5. Data Extraction       ──► Reads `data/port_cargo_monthly.csv` & filters `TOTAL COAL`
6. ML Execution          ──► Fits Holt-Winters + Ridge model, calculates 95% bounds & WAPE
7. Response Structuring  ──► Pydantic/FastAPI serializes dictionary to JSON
8. HTTP Response Sent    ──► Returns HTTP 200 OK + JSON payload to Client
```
