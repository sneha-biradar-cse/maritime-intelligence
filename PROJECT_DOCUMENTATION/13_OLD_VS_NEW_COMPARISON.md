# 13 — Structural Comparison: Previous vs. Current Project Version

## 🔄 Overview of Platform Evolution

This document provides a comparative analysis of the transformation from the **Previous Project Architecture** (generic maritime vessel tracker dashboard) to the **Current Project Architecture** (**Predictive Cargo Analytics & Decision Support System**).

---

## 📋 Comprehensive Structural Comparison Table

| Functional Area | Previous Project Version | Current Enhanced Project Version | Why Changed | Major Benefit / Business Value |
| :--- | :--- | :--- | :--- | :--- |
| **Primary System Focus** | Generic vessel tracking & ship ETA counting | ⭐ **Predictive Cargo Analytics & Volume Forecasting** | Vessels are inputs; ports care about cargo throughput & terminal capacity | Direct decision support for terminal operators & hinterland industries |
| **Data Foundation** | Mock vessel AIS location coordinates | Actual NMPA monthly cargo records (1,354 rows, 2021–2026) | Synthetic vessel dots lack real-world grounding | Mathematically grounded in real Indian port operations |
| **ML Algorithms** | Simple linear trendline extrapolation | Holt-Winters Exponential Smoothing + Multi-Feature Ridge Regression | Linear models fail to capture monsoon seasonality | Accurate 3, 6, and 12-month forecasts with 95% dynamic prediction bounds |
| **Model Validation** | No backtesting or accuracy measurement | Chronological out-of-sample backtesting (WAPE, MAPE, MAE, RMSE vs Naive) | Mentors & operators demand proof of ML model reliability | Verified performance metrics (WAPE 17.1%, accuracy 82.8%) |
| **Explainability** | Black-box numerical outputs | Quantified driver weight decomposition (MRPL Crude, UPCL Coal, Monsoon) | Operators must know WHY a forecast is rising/falling | Justified allocation of crane crews, tugboats, and berth depths |
| **Scenario Testing** | Static UI with fixed controls | Interactive What-If Cargo Scenario Simulator | Real ports face sudden delays and traffic spikes | Instant stress-testing of throughput & capacity risk levels |
| **Trade Intelligence** | Generic trade route listing | `Commodity Demand by Trade Lane` with YoY growth tracking | Connects global trade lanes directly to port commodity demand | Identifies high-margin trade lanes & revenue growth corridors |
| **Anomaly Engine** | Basic threshold alerts | `Cargo Anomaly & Risk Intelligence` with severity progression scale | Surges and declines require tiered response protocols | Visual classification (`Normal → Warning → Critical`) |
| **AI Capabilities** | None / Generic static text | LangGraph 3-Tier Cognitive Dispatcher & AI Maritime Copilot | Natural language query dispatch across specialized agents | Instant answer synthesis for operational staff |
| **UI Aesthetics** | Default Streamlit layout with basic tables | Premium Warm Amber / Cream design system with Plotly theme | Professional visual presentation for executive demos | High-impact dashboard experience |
| **Backend Architecture**| Monolithic single script | Modular FastAPI microservice framework with 12 API routers | Monoliths are hard to maintain and scale | Clean separation of routing, analytics, and data pipeline layers |
| **Data Ingestion** | Fixed dataset file reading | Centralized Pandas pipeline + Multipart CSV Upload Endpoint (`/upload/`) | Ports need ability to ingest new monthly reports | Flexible ingestion for dynamic port data updates |
| **NMPA Infrastructure** | Generic terminal labels | Specific berth assignments, draft depths (meters), & hinterland consumers | Ports operate around physical draft and berth constraints | Realistic operational mapping (Oil Jetties, JSW Terminal, UPCL) |
