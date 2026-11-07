# 18 — Mentor Q&A Bank (30+ Predicted Questions & Technical Answers)

This document provides answers to 30+ technical and operational questions that a project mentor or evaluation panel may ask during an oral examination.

---

## 📌 Section 1: Basic & Overview Questions

### Q1: What is the main objective of your project?
* **Simple Answer**: To help maritime ports predict upcoming cargo volume and manage port logistics using machine learning.
* **Technical Answer**: The primary objective is to build a data-grounded decision support platform that ingests multi-year historical port traffic datasets, fits Holt-Winters + Ridge time-series ML models, and outputs commodity-wise volume forecasts with 95% dynamic prediction bounds.
* **If mentor asks deeper →**: Point them to `backend/app/services/forecasting.py:get_enhanced_cargo_forecast()` and explain how `traffic_tonnes_current` is aggregated across 16+ commodities.

---

### Q2: Who are the target end-users of this platform?
* **Simple Answer**: Port managers, harbor masters, customs officers, and terminal logistics operators.
* **Technical Answer**: The system serves operations executives requiring berth utilization metrics (`GET /executive/kpis`), harbor masters tracking AIS vessel delay probabilities (`GET /vessels/`), and logistics managers running What-If scenario simulations (`POST /cargo/scenario`).
* **If mentor asks deeper →**: Explain how different tabs tailor data for different roles (Tab 1 for C-suite executives, Tab 3 for logistics planners, Tab 5 for risk managers).

---

### Q3: Why did you focus on Cargo rather than just Vessel tracking?
* **Simple Answer**: Because ports generate revenue and manage logistics based on cargo weight, not just ship counts.
* **Technical Answer**: Vessel counts alone do not indicate resource requirements. A 300-meter crude tanker requires oil jetties and pipelines, while a container vessel requires gantry cranes and yard stacking. Focusing on cargo tonnage enables precise terminal infrastructure and draft depth mapping.
* **If mentor asks deeper →**: Show how `NMPA_FACILITY_MAP` in `forecasting.py` maps commodities to specific draft depths and hinterland consumers.

---

## 🏗️ Section 2: Architecture & Technical Stack Questions

### Q4: Why did you choose FastAPI over Flask or Django for the backend?
* **Simple Answer**: FastAPI is faster, handles modern asynchronous requests, and generates interactive API documentation automatically.
* **Technical Answer**: FastAPI is built on Starlette and Pydantic, executing asynchronous ASGI handlers with low overhead. It performs automatic request validation and generates interactive OpenAPI Swagger UI at `/docs`.
* **If mentor asks deeper →**: Show `backend/app/main.py` where routers are mounted with clean dependency injection.

---

### Q5: Why did you select Streamlit for the frontend?
* **Simple Answer**: Streamlit allows us to build an interactive data science web UI directly in Python without complex JavaScript frameworks.
* **Technical Answer**: Streamlit provides rapid UI state binding, native dataframe widgets, and seamless integration with Plotly charts, letting us focus on analytical pipeline logic.
* **If mentor asks deeper →**: Explain how custom CSS injections in `frontend/app.py` transform default Streamlit styles into a custom design system.

---

### Q6: How do the frontend and backend communicate?
* **Simple Answer**: The frontend sends HTTP requests to backend REST API endpoints on port 8000 and receives JSON data.
* **Technical Answer**: `frontend/app.py` uses helper functions `api_get()` and `api_post()` powered by Python's `requests` library to issue REST queries to `http://127.0.0.1:8000`. Responses are parsed from JSON into Streamlit session state and Plotly render objects.
* **If mentor asks deeper →**: Trace `api_get("/cargo/forecast", params)` from `app.py:639` to `routes/cargo.py:8`.

---

## ⚙️ Section 3: Backend & Data Questions

### Q7: Where is the dataset stored, and how is it loaded?
* **Simple Answer**: The data is stored in `data/port_cargo_monthly.csv` and loaded into memory using Pandas.
* **Technical Answer**: The system reads `data/port_cargo_monthly.csv` (1,354 records) on demand using `pd.read_csv()`. Function `_load_and_prep_cargo_data()` processes the dataset into an in-memory time-series DataFrame.
* **If mentor asks deeper →**: Point to `backend/app/routes/upload.py` to show how the backend also supports dynamic multipart CSV file uploads (`POST /upload/`).

---

### Q8: How does the backend handle missing data or missing months in the dataset?
* **Simple Answer**: It fills missing commodity-month pairs with zero volume so time series remain continuous.
* **Technical Answer**: `forecasting.py` constructs a complete month-by-month grid from `2021-01` to `2026-07` using Pandas `pd.date_range()`. Missing commodity observations are zero-filled (`fillna(0.0)`) to maintain equal step intervals required for lag calculations.
* **If mentor asks deeper →**: Explain why zero-filling is mathematically safer than dropping rows when calculating lag 12 ($y_{t-12}$) seasonal features.

---

### Q9: Does the system use a SQL database?
* **Simple Answer**: Not in the PoC build; it uses an in-memory Pandas data pool backed by CSV persistence.
* **Technical Answer**: To ensure high-speed analytical calculations without external database overhead, data is maintained in Pandas DataFrames. However, the system exposes dynamic CSV upload endpoints (`POST /upload/`) and can easily swap the Pandas reader for SQLAlchemy/PostgreSQL.
* **If mentor asks deeper →**: Reference Tab 9 (`Data Pipeline`), which shows simulated architecture statistics for PostgreSQL and TimescaleDB pools.

---

## 🤖 Section 4: AI & ML Questions

### Q10: What machine learning algorithms are used for cargo forecasting?
* **Simple Answer**: We use Holt-Winters Exponential Smoothing combined with Ridge Regression.
* **Technical Answer**: The primary model applies Holt-Winters Exponential Smoothing to decompose level and seasonal trends, combined with Multi-Feature Ridge Regression with L2 regularization to evaluate lagged features ($t-1, t-12$) and vessel arrival counts.
* **If mentor asks deeper →**: Show `forecasting.py:get_enhanced_cargo_forecast()` where model predictions and residual error scaling generate the 95% dynamic prediction interval.

---

### Q11: Why didn't you use deep learning models like LSTM or Transformer for forecasting?
* **Simple Answer**: Deep learning requires millions of data points and tends to overfit small monthly tabular datasets.
* **Technical Answer**: Monthly port datasets (1,354 records) are structured time-series data. LSTMs contain millions of parameters and overfit on small sample sizes. Ridge Regression with L2 regularization guarantees stable, explainable weights with zero overfitting.
* **If mentor asks deeper →**: Explain that deep learning models (LSTM/Autoencoder) are used in `synthetic_data.py` for anomaly detection where sequence pattern matching is required.

---

### Q12: How do you evaluate the accuracy of your forecasting model?
* **Simple Answer**: We compare our model against a Seasonal Naive baseline using WAPE, MAPE, MAE, and RMSE metrics.
* **Technical Answer**: `forecasting.py:evaluate_forecast_models()` performs chronological out-of-sample backtesting against actual test data, calculating Weighted Absolute Percentage Error (WAPE), MAPE, MAE, and RMSE.
* **If mentor asks deeper →**: Write out the WAPE formula: $\text{WAPE} = \frac{\sum |y - \hat{y}|}{\sum y} \times 100$ and explain why it avoids division-by-zero artifacts.

---

### Q13: What are "Explainable Forecast Drivers"?
* **Simple Answer**: It shows the exact percentage contribution of real-world factors causing cargo volume to rise or fall.
* **Technical Answer**: It is a regression weight decomposition algorithm that calculates relative feature importance for factors like hinterland industrial demand (MRPL/UPCL), monsoon swells, and trade lane velocity.
* **If mentor asks deeper →**: Point to `forecasting.py:_generate_cargo_drivers()` and show how driver weights sum to 100%.

---

### Q14: How does the What-If Cargo Scenario Simulator work?
* **Simple Answer**: It allows users to move sliders for vessel arrivals, demand, and weather to see the net impact on future cargo volume.
* **Technical Answer**: `forecasting.py:simulate_cargo_scenario()` accepts parameter offsets (`vessel_arrival_change_pct`, `trade_demand_change_pct`, `weather_delay_days`), recalculates the time-series vector, computes simulated throughput, and categorizes capacity risk levels.
* **If mentor asks deeper →**: Show `routes/cargo.py:run_scenario()` handling POST requests from Streamlit Tab 3.

---

## ⚓ Section 5: Cargo & Domain Specific Questions

### Q15: Which port's data is used in this project?
* **Simple Answer**: New Mangalore Port Authority (NMPA) in Karnataka, India.
* **Technical Answer**: The primary dataset `data/port_cargo_monthly.csv` contains actual traffic records for NMPA, covering major terminals like Oil Jetties, JSW Container Terminal, UPCL Coal Berths, and KIOCL Iron Ore Jetty.
* **If mentor asks deeper →**: Point to `NMPA_FACILITY_MAP` in `forecasting.py` line 35.

---

### Q16: How does the platform distinguish between Imports and Exports?
* **Simple Answer**: By filtering the `section` column into `LOADED` (Exports) and `UNLOADED` (Imports).
* **Technical Answer**: The dataset contains explicit `section` tags. `LOADED` represents outward export shipments (e.g., POL products, iron ore pellets), while `UNLOADED` represents inward imports (e.g., crude oil, thermal coal, fertilizers).
* **If mentor asks deeper →**: Show the `Flow Section` dropdown in Streamlit Tab 3.

---

### Q17: What commodities are analyzed in the system?
* **Simple Answer**: 16 major commodities including Crude Oil, Thermal Coal, Containers, Iron Ore, Fertilizers, LPG, POL Products, Edible Oil, and Cement.
* **Technical Answer**: The system categorizes cargo into 16 NMPA commodity strings extracted dynamically via `get_available_commodities()`.
* **If mentor asks deeper →**: Explain how `COMMODITY_COLORS` in `app.py:33` assigns distinct color tokens to each commodity for consistent UI visualization.

---

## 🔄 Section 6: Old vs. New & Scalability Questions

### Q18: What is the single biggest improvement in the current version over the previous version?
* **Simple Answer**: Shifting the core focus from basic ship counting to **Predictive Cargo Analytics** backed by backtested ML models.
* **Technical Answer**: The previous version was a passive vessel tracker displaying static ship locations. The new version introduces a time-series ML forecasting engine, chronological WAPE backtesting, explainable drivers, and interactive scenario simulators.
* **If mentor asks deeper →**: Point to `PROJECT_DOCUMENTATION/13_OLD_VS_NEW_COMPARISON.md`.

---

### Q19: Is the system scalable to handle other major ports like JNPT or Mundra?
* **Simple Answer**: Yes, because the data pipeline and ML models are commodity-agnostic.
* **Technical Answer**: The architecture separates data ingestion from model execution. Adding JNPT or Mundra simply requires passing a new CSV file to `_load_and_prep_cargo_data()` or uploading it via `POST /upload/`.
* **If mentor asks deeper →**: Reference `data/sample_cargo_data.csv`, which already contains benchmark data for JNPT, Mumbai, Chennai, Kandla, Vizag, and Kochi.

---

### Q20: How does the AI Maritime Copilot work?
* **Simple Answer**: It parses natural language questions using a 3-tier fallback execution model.
* **Technical Answer**: `services/copilot.py` implements a LangGraph cognitive dispatcher. Tier 1 handles complex multi-variable queries via LLM synthesis, Tier 2 uses SLM fast reasoning, and Tier 3 executes deterministic zero-LLM rule matching.
* **If mentor asks deeper →**: Show the step-by-step dispatch trace rendered on Streamlit Tab 8.
