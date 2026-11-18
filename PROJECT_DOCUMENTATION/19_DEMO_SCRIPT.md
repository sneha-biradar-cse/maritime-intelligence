# 19 — Step-by-Step Live Project Demonstration Script

This document provides a live demonstration script for presenting the Maritime Port Intelligence Platform (MPIP) to an audience or evaluation panel.

---

## 🎬 Pre-Demo Setup Verification Checklist

1. **Backend Server**: Ensure FastAPI backend is running on `http://127.0.0.1:8000`.
   ```bash
   python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```
2. **Frontend Server**: Ensure Streamlit frontend is running on `http://localhost:8501`.
   ```bash
   streamlit run frontend/app.py
   ```
3. **Browser Tab**: Open `http://localhost:8501` in full-screen browser view.

---

## 📺 Live Demo Step-by-Step Guide

### STEP 1 — Platform Overview & Core Objective Header
* **SHOW ON SCREEN**:
  * The top header card (`Maritime Intelligence Platform — AI-POWERED PREDICTIVE CARGO ANALYTICS & DECISION SUPPORT SYSTEM`).
  * The top hero positioning banner (`Predictive Cargo Analytics — See What's Coming. Plan Ahead.`).
* **WHAT TO SAY**:
  > *"Welcome everyone. As you can see on the screen, our platform's primary objective is **Predictive Cargo Analytics**. Rather than simply tracking ship coordinates, our platform connects historical cargo data, machine learning algorithms, commodity demand trends, and anomaly detection to support proactive port planning decisions."*

---

### STEP 2 — Core Feature: ⭐ Cargo Forecasting Tab
* **SHOW ON SCREEN**:
  * Click on the 3rd navigation tab: **`⭐ Cargo Forecasting`**.
  * Point out the 3 visual capability cards: `Cargo Volume Forecasting`, `Commodity & Trade Demand`, `Cargo Risk & Anomaly Detection`.
* **WHAT TO SAY**:
  > *"Here on the Cargo Forecasting Command Center, we immediately see our three core operational pillars. Let's select a specific commodity to analyze, such as **TOTAL COAL**."*

---

### STEP 3 — Commodity Selection & Metric Snapshot
* **SHOW ON SCREEN**:
  * Select `TOTAL COAL` from the commodity dropdown.
  * Point to the **Selected Commodity Analytics Banner** and **NMPA Facility Banner**.
* **WHAT TO SAY**:
  > *"When I select 'TOTAL COAL', the platform dynamically pulls multi-year historical records for New Mangalore Port Authority. We see our current monthly volume is 625,768 tonnes, with an expected 6-month average of 710,889 tonnes—a +13.6% growth trend. Notice the NMPA facility mapping below: thermal coal is automatically mapped to Mechanized Coal Handling Berths 15 & 16 (14.0m draft depth) supplying the UPCL Power Plant."*

---

### STEP 4 — Main Forecast Chart & 95% Confidence Interval
* **SHOW ON SCREEN**:
  * Hover over the Plotly main time-series forecast graph (`Cargo Volume Forecast — TOTAL COAL — 6 Month Horizon`).
  * Highlight the dark grey historical line, the dashed gold forecast line, and the shaded 95% dynamic prediction interval band.
* **WHAT TO SAY**:
  > *"On this chart, the dark grey line represents historical actual cargo tonnage. The dashed gold line displays our machine learning forecast for the next 6 months. The shaded amber band represents our 95% dynamic prediction interval, giving port operators mathematical confidence bounds for berth capacity planning."*

---

### STEP 5 — Explainable Forecast Drivers
* **SHOW ON SCREEN**:
  * Scroll down to `Explainable Forecast Drivers (WHY this prediction?)`.
* **WHAT TO SAY**:
  > *"Crucially, our platform is not a black box. Here we answer: **WHY is cargo volume expected to change?** The ML driver engine decomposes the forecast into weighted factors—showing that UPCL power plant demand contributes 45% to the forecast, while seasonal monsoon swell delays account for 25%."*

---

### STEP 6 — Model Validation & Chronological Backtesting
* **SHOW ON SCREEN**:
  * Scroll down to `Cargo Forecast Model Validation (Baseline vs Primary ML Model)`.
  * Highlight the WAPE metric (`17.15%`) and model accuracy (`82.8%`).
* **WHAT TO SAY**:
  > *"To prove the mathematical accuracy of our model, we run out-of-sample chronological backtesting against actual test data. We compare our Primary ML Model against a Seasonal Naive Baseline Model. Our model achieves an 82.8% accuracy score evaluated using Weighted Absolute Percentage Error (WAPE)."*

---

### STEP 7 — Interactive What-If Cargo Scenario Simulator
* **SHOW ON SCREEN**:
  * Move the **Vessel Arrival Change** slider to `+15%`.
  * Move the **Trade Demand Shift** slider to `+10%`.
  * Click **Run Cargo Scenario Simulation**.
  * Point to the updated metric: `Predicted Cargo Throughput: 4,836,894 Tonnes (+13.4% vs Base)`.
* **WHAT TO SAY**:
  > *"Now let's test a contingency scenario. Suppose vessel fleet arrivals surge by 15% and trade demand increases by 10%. When I click 'Run Cargo Scenario Simulation', the backend recalculates throughput in real time, projecting a net volume increase of 571,555 tonnes and issuing an operational advisory to deploy two additional bulk unloading cranes."*

---

### STEP 8 — Supporting Modules: Trade, Anomaly & Copilot
* **SHOW ON SCREEN**:
  * Briefly click **Trade Intelligence** (`Commodity Demand by Trade Lane`).
  * Briefly click **Anomaly Detection** (`Cargo Anomaly & Risk Intelligence`).
  * Briefly click **AI Maritime Copilot** and submit a sample query: *"Why is cargo forecast increasing?"*.
* **WHAT TO SAY**:
  > *"Supporting tabs reinforce our cargo focus. Trade Intelligence tracks commodity demand across major trade lanes. Anomaly Detection classifies cargo volume surges and decline risks with a 4-tier severity scale. Finally, our AI Maritime Copilot uses a 3-tier cognitive dispatcher to answer natural language query requests instantly."*

---

### STEP 9 — Concluding Remarks
* **WHAT TO SAY**:
  > *"In conclusion, our platform transforms fragmented maritime data into actionable, predictive decision support. Thank you, and I am now ready to take your questions."*
