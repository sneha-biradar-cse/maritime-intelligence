> **Trade Intelligence and Incentive Engine:** the authoritative record of their data sources, verification status, assumptions and open questions is `../DATA_SOURCES_AND_ASSUMPTIONS.md` (with `../data/data_status.csv`, `../data/daily_reports_manifest.csv`, `../data/daily_reports_missing_pdfs.csv` and `../data/customer_identity_proposals.csv`). Where an older document in this folder differs, that file takes precedence.

# Project Documentation Directory â€” Maritime Port Intelligence Platform (MPIP)

Welcome to the official documentation folder for the **Maritime Port Intelligence Platform (MPIP)** / **Maritime Port Enhanced**.

This repository documentation is designed to give students, developers, and academic/industry mentors a complete, 360-degree understanding of the project's architecture, data engineering pipelines, machine learning forecasting algorithms, frontend user interface, and operational workflows.

---

## ðŸ“Œ Project Overview at a Glance

* **Project Name**: Maritime Port Intelligence Platform (MPIP) / Maritime Port Enhanced
* **One-Line Explanation**: An AI-powered, data-grounded maritime decision-support platform designed to deliver predictive cargo volume forecasting, trade lane momentum analytics, risk/anomaly detection, and interactive port scenario simulation.
* **Main Objective**: Bridge fragmented maritime datasets and convert historical port operations into actionable, forward-looking decisions for port authorities, customs agencies, and shipping line operators.
* **Primary Focus**: **Predictive Cargo Analytics & Intelligence** (specifically grounded on actual multi-year monthly port traffic records mapped to New Mangalore Port Authority â€” NMPA).
* **Technologies**: Python 3.12, FastAPI, Streamlit, Pandas, NumPy, Holt-Winters Exponential Smoothing, Multi-Feature Ridge Regression, Plotly, Docker, REST APIs.
* **Main Features**:
  1. â­ **Predictive Cargo Analytics & Volume Forecasting** (Holt-Winters + Ridge Regression with 95% dynamic confidence bounds)
  2. **Commodity & Trade Demand Intelligence** (Trade lane momentum, YoY growth tracking, commodity price indices)
  3. **Cargo Anomaly & Risk Intelligence** (Isolation Forest, LSTM, Autoencoder & Transformer simulation with severity progression)
  4. **Explainable Forecast Drivers** (Quantified weights for hinterland consumer demand, monsoon swells, and market inputs)
  5. **Model Validation & Out-of-Sample Backtesting** (WAPE, MAPE, MAE, RMSE performance comparison vs Seasonal Naive baseline)
  6. **Interactive What-If Cargo Scenario Simulator** (Stress-testing port throughput against vessel arrival spikes, trade demand shifts, and weather delays)
  7. **Executive Command Center & Digital Twin** (Real-time KPIs, berth utilization, live vessel positions, revenue trends, and operational stress-testing)
  8. **AI Maritime Copilot** (LangGraph 3-tier cognitive dispatcher with specialized agent roster)

---

## ðŸ“š Recommended Documentation Reading Order

For maximum clarity when reviewing this project or preparing for a mentor presentation, follow this sequence:

| Step | File Name | Purpose / What You Will Learn |
| :--- | :--- | :--- |
| 1 | [01_PROJECT_OVERVIEW.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/01_PROJECT_OVERVIEW.md) | High-level summary, 30s / 1min / 3min mentor elevators pitches. |
| 2 | [02_PROBLEM_STATEMENT.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/02_PROBLEM_STATEMENT.md) | Real-world port management challenges & cargo data fragmentation. |
| 3 | [03_SOLUTION_EXPLANATION.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/03_SOLUTION_EXPLANATION.md) | End-to-end processing pipeline from CSV data source to UI insight. |
| 4 | [04_SYSTEM_ARCHITECTURE.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/04_SYSTEM_ARCHITECTURE.md) | Full technical breakdown, ASCII architecture diagrams, module layers. |
| 5 | [05_COMPLETE_PROJECT_FLOW.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/05_COMPLETE_PROJECT_FLOW.md) | Step-by-step user interaction lifecycle and request execution flow. |
| 6 | [06_CARGO_FOCUSED_FLOW.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/06_CARGO_FOCUSED_FLOW.md) | Detailed explanation of why and how **Cargo** is the central axis. |
| 7 | [07_FRONTEND_EXPLANATION.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/07_FRONTEND_EXPLANATION.md) | Streamlit dashboard design, UI components, state management & Plotly charts. |
| 8 | [08_BACKEND_EXPLANATION.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/08_BACKEND_EXPLANATION.md) | FastAPI route handlers, service layer logic, response schemas. |
| 9 | [09_DATABASE_AND_DATA.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/09_DATABASE_AND_DATA.md) | In-memory data store, CSV persistence, data ingestion & upload handler. |
| 10 | [10_AI_ML_EXPLANATION.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/10_AI_ML_EXPLANATION.md) | Time-series ML algorithms (Holt-Winters, Ridge, Naive baseline, WAPE metrics). |
| 11 | [11_API_DOCUMENTATION.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/11_API_DOCUMENTATION.md) | Complete REST API endpoint reference table and example JSON payloads. |
| 12 | [12_DATASET_EXPLANATION.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/12_DATASET_EXPLANATION.md) | In-depth breakdown of `port_cargo_monthly.csv` (2021-2026 NMPA cargo traffic). |
| 13 | [13_OLD_VS_NEW_COMPARISON.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/13_OLD_VS_NEW_COMPARISON.md) | Structural comparison between generic maritime dashboard vs cargo-core version. |
| 14 | [14_CHANGES_MADE.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/14_CHANGES_MADE.md) | Comprehensive log of major/minor enhancements, refactorings, and UI fixes. |
| 15 | [15_FEATURES_IMPLEMENTED.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/15_FEATURES_IMPLEMENTED.md) | Feature checklist categorizing Implemented vs Partially Implemented items. |
| 16 | [16_TECH_STACK.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/16_TECH_STACK.md) | Technology choice justification, library dependencies, deployment containers. |
| 17 | [17_MENTOR_EXPLANATION.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/17_MENTOR_EXPLANATION.md) | Ready-to-speak mentor script with structured sections for oral evaluation. |
| 18 | [18_MENTOR_QA.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/18_MENTOR_QA.md) | 30+ predicted mentor questions with basic, technical, and deep-dive answers. |
| 19 | [19_DEMO_SCRIPT.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/19_DEMO_SCRIPT.md) | Step-by-step live demo walkthrough script (What to Show vs What to Say). |
| 20 | [20_LIMITATIONS_AND_FUTURE_SCOPE.md](file:///c:/Users/hirab/Downloads/maritime_port_enhanced/PROJECT_DOCUMENTATION/20_LIMITATIONS_AND_FUTURE_SCOPE.md) | Current architectural limits, data constraints, and realistic roadmap. |

---

> [!NOTE]
> All code references, filenames, function names, and dataset metrics referenced in these documentation files correspond to the active codebase in `c:\Users\hirab\Downloads\maritime_port_enhanced`.
