# 01 — Project Overview

## 🚢 What is the Maritime Port Intelligence Platform (MPIP)?

The **Maritime Port Intelligence Platform (MPIP)** is an AI-powered, data-grounded decision support system designed specifically for maritime ports. It ingests historical monthly port traffic datasets, analyzes commodity-wise trade flows, applies machine learning algorithms (Holt-Winters Exponential Smoothing + Multi-Feature Ridge Regression), and provides predictive insights to optimize port operations.

The platform transforms raw historical records into actionable forecasts—predicting cargo volume arrival, identifying commodity trade trends, detecting operational anomalies, and stress-testing port infrastructure via scenario simulations.

---

## 🎯 What Problem Does It Solve?

Port operators and maritime authorities traditionally rely on fragmented spreadsheets, delayed reports, and manual intuition to guess upcoming cargo traffic. This leads to severe operational bottlenecks:
1. **Berth Congestion & Queue Delays**: Ports do not know when bulk or container surges will arrive, leading to vessel queueing.
2. **Commodity Misallocation**: Failure to anticipate demand for key industrial commodities (Crude, Coal, Iron Ore, Containers, Fertilizers) causes hinterland supply chain breakdowns.
3. **Data Fragmentation**: Port authorities, customs agencies, and logistics operators store data in isolated silos.
4. **Lack of Predictive Foresight**: Traditional systems show *what happened in the past*, but fail to answer *what will happen next month* or *how operational disruptions will affect throughput*.

---

## 👥 Who Would Use It?

1. **Port Operations Managers**: To schedule berth allocations, draft depths, tugboats, and crane crews based on projected cargo volume.
2. **Maritime Authorities & Harbor Masters**: To monitor vessel arrival risk, port congestion scores, and regional trade flows.
3. **Logistics & Terminal Operators**: To manage yard storage capacity and hinterland transport (rail & road freight corridor planning).
4. **Customs & Trade Analysts**: To analyze commodity import/export velocity, tariff incentives, and revenue leakages.

---

## 💡 Why Is It Useful for a Maritime Port?

For a smart port like **New Mangalore Port Authority (NMPA)**, proactive planning saves millions of dollars in demurrage fees, reduces vessel turnaround times, and guarantees continuous raw material feed to major hinterland industries (e.g., MRPL refinery crude requirements, UPCL power plant coal supply, and JSW container traffic).

---

## 📊 What Data Does It Process?

The system processes real-world data grounded in the **New Mangalore Port Authority (NMPA) Cargo Dataset** (`data/port_cargo_monthly.csv`), covering 1,350+ monthly records across 2021, 2023, 2024, 2025, and 2026. Data attributes include:
* **Time Dimensions**: Year, Month, Historical Spans.
* **Flow Section**: `LOADED` (Exports), `UNLOADED` (Imports), `ALL`.
* **Commodity Breakdown**: Crude Oil, Coal, Iron Ore, Containers, Fertilizers, POL Products, LPG, Edible Oil, Cement, Food Grains.
* **Traffic Metrics**: Monthly tonnage (`traffic_tonnes_current`, `traffic_tonnes_prev_year`), vessel arrival counts (`vessels_current`, `vessels_prev_year`), and YoY percentage variations (`pct_variation_yoy`).
* **Facility & Hinterland Mapping**: Specific berth assignments, max draft depths (meters), and hinterland industrial consumers (e.g., MRPL, UPCL, KIOCL, MCF).

---

## 📦 What Does the System Produce?

1. **Predictive Cargo Volume Forecasts**: 3-month, 6-month, and 12-month forward-looking tonnage estimates with 95% dynamic prediction interval bands.
2. **Commodity & Trade Demand Analytics**: Commodity-wise momentum, trade lane velocity (YoY growth), and revenue impact gauges.
3. **Model Accuracy & Backtesting Metrics**: Weighted Absolute Percentage Error (WAPE), MAPE, MAE, and RMSE evaluated against a Seasonal Naive baseline model.
4. **Explainable Forecast Drivers**: Quantified weights showing *why* cargo volume is expected to rise or fall (e.g., hinterland industrial demand, monsoon swells, trade demand).
5. **Interactive What-If Scenario Simulations**: Real-time stress-test outputs measuring capacity risk level and predicted throughput when vessel arrivals, trade demand, or weather delays shift.
6. **Cargo Anomaly & Risk Alerts**: Categorized anomaly logs (surges, declines, disruptions) with severity levels (`Normal → Warning → Critical`).

---

## ⚓ What is the Role of Cargo?

**Cargo is the central axis of the entire platform.** While vessel movements, berth draft depths, and weather delays are tracked, they are treated as *input drivers* to answer the primary operational question:
> **"How much cargo volume of which commodity will pass through our port, when will it arrive, and how do we prepare our berths and hinterland corridors to handle it?"**

---

## 🚀 What Makes This Project Different From a Normal Dashboard?

| Standard Maritime Dashboard | Maritime Port Intelligence Platform (MPIP) |
| :--- | :--- |
| Displays past historical statistics only | Predicts future cargo throughput using machine learning |
| Generic vessel ETA counting | Commodity-specific volume & arrival forecasting mapped to NMPA berths |
| Static charts with no user interaction | Interactive What-If cargo scenario simulator |
| Black-box metrics with no explanation | Quantified explainable forecast drivers (WHY cargo changes) |
| Basic percentage error metrics | Out-of-sample chronological backtesting (WAPE vs Baseline) |

---

## 🎤 Ready-to-Speak Explanations for Your Mentor

### ⏱️ 30-Second Explanation
> *"Our project is an AI-Powered Predictive Cargo Analytics platform for maritime ports, grounded in real multi-year monthly port traffic datasets from New Mangalore Port Authority. Rather than just displaying historical vessel counts, our system uses time-series machine learning—specifically Holt-Winters Exponential Smoothing and Ridge Regression—to forecast future cargo tonnage by commodity, quantify model accuracy using WAPE backtesting, and allow port managers to run interactive What-If scenario simulations for proactive berth and logistics planning."*

---

### ⏱️ 1-Minute Explanation
> *"In real-world port management, the biggest challenge is predicting cargo volume arrivals and commodity trends. Traditional ports rely on static spreadsheets and react only after congestion occurs.
> 
> To solve this, we built the Maritime Port Intelligence Platform. Our system ingests 1,350+ monthly cargo records spanning 2021 to 2026 across major commodities like Crude, Coal, Containers, and Fertilizers. We engineered a dual-model ML forecasting pipeline that predicts future cargo throughput up to 12 months in advance with 95% dynamic confidence intervals. 
> 
> Crucially, our dashboard explains WHY a forecast is changing using quantified driver weights, measures model accuracy against a baseline using WAPE backtesting, and features an interactive What-If simulator so port authorities can test how vessel delays or demand shifts impact total cargo capacity."*

---

### ⏱️ 3-Minute Explanation
> *"Good morning/afternoon Mentor. Today I am presenting the Maritime Port Intelligence Platform, an end-to-end decision support system focused on Predictive Cargo Analytics.
> 
> **The Problem**: Maritime port operations suffer from severe data fragmentation. Port managers know which ships are at anchor today, but they lack data-driven visibility into cargo tonnage arriving next month. This causes berth congestion, crane bottlenecks, and supply chain delays for hinterland industries that rely on port raw materials.
> 
> **Our Solution**: We built a full-stack platform using FastAPI on the backend and Streamlit on the frontend, grounded on actual historical monthly cargo traffic data from New Mangalore Port Authority (NMPA).
> 
> **How It Works**:
> 1. **Data Pipeline**: The system cleans and classifies monthly traffic records across 16+ commodities, mapping each commodity to dedicated port berths (like Oil Jetties, JSW Container Terminal, and UPCL Coal Berths) and hinterland consumers (like MRPL Refinery or UPCL Power Plant).
> 2. **ML Forecasting Engine**: We implemented a Holt-Winters Exponential Smoothing and Multi-Feature Ridge Regression pipeline. It outputs 3, 6, and 12-month cargo volume predictions, surrounded by 95% dynamic prediction interval bands.
> 3. **Model Validation**: We don't just display predictions; we prove their reliability using chronological out-of-sample backtesting, evaluating Weighted Absolute Percentage Error (WAPE), MAE, and RMSE against a Seasonal Naive baseline.
> 4. **Explainability & What-If Simulation**: The dashboard provides transparent explainability, showing driver weights for monsoon swells, hinterland demand, and trade velocity. Furthermore, users can adjust sliders for vessel arrival changes, trade shifts, and weather delays to immediately simulate the impact on predicted cargo throughput.
> 
> **In Summary**: Our project elevates port management from reactive crisis response to proactive predictive cargo planning."*
