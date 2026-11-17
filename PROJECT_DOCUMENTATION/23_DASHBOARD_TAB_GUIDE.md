 # 23 — Dashboard Tab-by-Tab Guide (What Every Screen Shows and How It Works)

## Purpose

A presenter's guide to every tab of the platform: what the tab is for, what each
card / chart / table on it means, how each number is calculated, where the data
comes from, and how honest it is (real vs. simulated). Written from the current
code on 2026-09-29, including the new **Port Cost & Tariff** features.

There are **two dashboards** with almost the same tabs:

| Dashboard | URL | How it runs |
| :--- | :--- | :--- |
| **Web dashboard** (HTML/JS) | http://127.0.0.1:8000 | Served by the FastAPI backend (`frontend/index.html`, `frontend/app.js`) |
| **Streamlit dashboard** | http://localhost:8501 | `streamlit run frontend/app.py` — richer version of the same tabs |

Both call the **same backend API**, so the same number means the same thing in both.
Differences are noted per tab.

## Data-honesty legend (use this when someone asks "is this real?")

| Tag | Meaning |
| :--- | :--- |
| 🟢 **REAL (ML)** | A trained machine-learning model on real NMPA data, with measured accuracy |
| 🟢 **REAL (derived)** | Direct calculation from real NMPA data or official NMPA documents — no model, no invented numbers |
| 🟡 **SCRIPTED** | Fixed, hand-written values or formulas (same every time, but not from a live source) |
| 🔴 **SIMULATED** | Random/demo numbers generated on each request — for illustration only |

## The real data behind the platform

| Dataset | What it is | Size |
| :--- | :--- | :--- |
| `data/port_cargo_monthly.csv` | NMPA monthly cargo traffic: commodity, loaded/unloaded, vessels, tonnes, same month last year | 1,354 rows · 54 months (Jan 2021 – Jul 2026, 2022 missing) · 65 commodity labels |
| `data/berths.csv`, `data/berth_capacity.csv` | Official specifications of NMPA's 17 berths: type, cargo, max draught, quay length, max DWT, capacity | 17 berths |
| `data/daily_vessel_position/` → `_parsed/` | NMPA Daily Vessel Position reports (PDF), parsed | 288 daily reports (Sep 2025 – Sep 2026) |
| `data/vessel_stays.json` | Vessel berth stays linked from the daily reports (berthing → sailing) | 1,688 stays |
| `nmpa_public_data/tariff/Indexed SOR wef 01.05.2026` | NMPA Schedule of Rates 2026-27 (official tariff) | 116 wharfage lines + vessel/storage charges |

**One-line summary for the audience:** *Forecasting, anomaly detection, congestion
risk, vessel-call forecasting, berth routing and port-cost calculation run on real
NMPA data. Live ship tracking, revenue, trade lanes, digital-twin outcomes, the
copilot and the pipeline metrics are demonstration screens, and they are labelled
as such.*

---

## Tab 1 — Executive Dashboard ("Executive Command Center")

**Purpose:** A one-screen overview of the port for management.
**Overall status:** Mostly 🔴 SIMULATED — the tab itself shows a warning saying so.

| Element | What it means | How it is calculated | Status |
| :--- | :--- | :--- | :--- |
| **Berth Utilization %** | How busy the berths are | Demo KPI generator (`/executive/kpis`) | 🔴 |
| **Vessels Inbound** | Ships heading to port | Demo KPI generator | 🔴 |
| **Daily Throughput (MT)** | Cargo handled per day | Demo KPI generator | 🔴 |
| **Revenue Index (₹ Cr)** | Port revenue | Demo — the project has no financial data | 🔴 |
| **Avg Turnaround / Vessels at Anchor** *(Streamlit only)* | Time in port, ships waiting | Demo KPI generator | 🔴 |
| **Forecast Accuracy (ML)** *(Streamlit only)* | How accurate the cargo forecast is | Real: 100 − WAPE of the cargo ML model (see Tab 3) | 🟢 REAL (ML) |
| **Congestion Index (ML)** *(Streamlit only)* | Congestion risk, 0–1 | Real: congestion classifier score ÷ 10 (see Tab 5) | 🟢 REAL (ML) |
| Green/red **deltas** under each KPI | Change vs. previous period | Demo | 🔴 |
| **Vessel Approach Map** | Ships around Mangalore | Fixed list of 25 demo ships placed near NMPA terminals | 🟡 |
| **30-Day Revenue & Throughput Trend** | Revenue over time | Demo series | 🔴 |
| **Berth Occupancy bar chart** *(Streamlit)* | Utilization of each of the 17 berths | Real: each berth's matched commodity's latest monthly tonnage, annualised, ÷ berth capacity | 🟢 REAL (derived) |
| **Active Vessels by Commodity donut** *(Streamlit)* | Mix of ships by cargo | Counts from the demo fleet | 🟡 |
| **Recent Port Events** *(Streamlit)* | Event feed | Demo events | 🔴 |

**How to explain it:** "This is the management view. The layout shows what a live
control room would look like; the headline KPIs are placeholders because we don't
have NMPA's financial or live AIS feeds. The two items marked (ML) and the berth
occupancy chart are computed from real NMPA data."

**Careful:** "Berth occupancy" does **not** mean a ship is at the berth right now. It
means the cargo that berth handles actually moved last month. There is no live feed.

---

## Tab 2 — Vessel Intelligence

**Purpose:** Ship-level view (tracking, ETAs, risk) plus a real forecast of how many
ships will call.

| Element | What it means | How it is calculated | Status |
| :--- | :--- | :--- | :--- |
| **Vessel Tracker table** (name, commodity, capacity, speed, ETA, delay probability, route risk) | Ships approaching NMPA | A fixed 25-ship demo fleet; positions/ETAs computed from list order, not AIS | 🟡 SCRIPTED |
| **Route risk badge** (green / amber / red) | Risk on the ship's route | Colour rule: > 0.6 red, > 0.3 amber | 🟡 |
| **Next 15 Arrivals chart** *(Streamlit)* | Hours until each ship arrives | From the demo fleet | 🟡 |
| **Congestion Alerts** *(Streamlit)* | Warnings about queues | Derived from the demo fleet | 🟡 |
| **Route Risk vs Delay Probability scatter** *(Streamlit)* | Which ships are both risky and late | Demo fleet; dashed lines = risk 0.7, delay 0.35 thresholds | 🟡 |
| **Vessel Call Forecast (ML)** *(Streamlit)* | How many vessels will call per month for a commodity | Random Forest on real monthly vessel counts (lags, seasonality, trend), backtested | 🟢 REAL (ML) |
| **Real call spacing** *(Streamlit)* | Average days between ships at that commodity's berth | Measured from the 288 real Daily Vessel Position reports | 🟢 REAL (derived) |
| **Real stay duration** *(Streamlit)* | How long ships actually occupy the berth | Measured from 1,688 real linked berth stays, each with a confidence label | 🟢 REAL (derived) |

**How to explain it:** "Per-ship tracking needs an AIS feed, which we don't have, so
the tracker is a demo. What we can do with NMPA's own data is forecast **how many**
ships will call each month — that model is real and backtested — and measure real
berth spacing and stay times from a year of NMPA daily vessel position reports."

**Careful:** The vessel-call forecast is **not** "Ship X arrives Tuesday". It is a
monthly count.

---

## Tab 3 — Cargo Forecasting ⭐ (core module)

**Purpose:** Forecast future cargo volume per commodity and show how reliable that
forecast is. This is the heart of the project.
**Overall status:** 🟢 REAL (ML), except where noted.

### Controls
| Control | Meaning |
| :--- | :--- |
| **Commodity** | Which cargo (e.g. TOTAL COAL, IRON ORE, or ALL) — list comes from the real dataset |
| **Flow Section** | ALL, LOADED (exports) or UNLOADED (imports) |
| **Forecast Horizon** | 3, 6 or 12 months ahead |

### Snapshot / KPI cards
| Element | Meaning | How calculated |
| :--- | :--- | :--- |
| **NMPA Berth / Draft / Hinterland** | Which NMPA facility and customer this cargo goes through | Fixed commodity → facility map (e.g. Coal → Berth 15 & 16 → UPCL) |
| **Current Monthly Volume** | Last real month's tonnage | From the CSV |
| **Expected Monthly Avg** | Average of the forecast months | Mean of the model's predictions |
| **Forecast Growth %** | Expected change vs. current | (Expected avg − current) ÷ current. Shows "N/A (resuming from zero)" if last month was 0 |
| **Model Accuracy** | How accurate the model was on past data | **100 − WAPE** from the backtest (below) |

### Main forecast chart
- **Grey line** — real historical monthly cargo (tonnes).
- **Gold dashed line** — the prediction.
- **Shaded band** — 95% prediction interval: ±1.96 × the model's error spread,
  widening the further ahead it goes. Wider band = less certain.

### How the model works (say this simply)
1. Takes the monthly tonnage history for the chosen commodity/flow.
2. Builds features: last month (lag-1), 3 months ago (lag-3), same month last year
   (lag-12), 3-month rolling average, month-of-year (seasonality), trend, vessel arrivals.
3. Trains a **Random Forest** (scikit-learn) on those features.
4. Forecasts one month at a time, feeding each prediction back in to forecast the next.

### Predictability Score (Streamlit)
**HIGH** if error (WAPE) < 15% and history is stable; **MEDIUM** if WAPE < 28% or
volatility moderate; **LOW** otherwise, or when there's under 12 months of data, or
the commodity label has gone stale/discontinued.

### Data Lineage & Quality (Streamlit)
Shows the dataset used, number of records analysed, and completeness — so viewers
can see the forecast is traceable to real records.

### Explainable Forecast Drivers ("WHY this prediction?")
Lists factors such as hinterland demand, monsoon impact and market conditions with
percentage weights. **🟡 SCRIPTED** — the weights are fixed explanatory values, not
learned from the model. Present them as "the factors that typically drive this
cargo", not as measured model output.

### AI Operational Recommendations (Streamlit)
Rule-based advice from the forecast (e.g. "prepare Berth 15 & 16 for a +12% surge —
pre-allocate yard storage"). 🟢 derived from the real forecast; the wording is a
template.

### Model Validation (backtest) — the proof of accuracy
- The last 4–8 real months are **hidden** from the model; the model predicts them;
  predictions are compared with what really happened.
- Compared against a **Seasonal Naive baseline** ("same as the same month last year").
- **WAPE** = total absolute error ÷ total actual volume. Lower is better. Used instead
  of MAPE because months with near-zero cargo distort MAPE.
- **WAPE Improvement** = how much lower the ML error is than the baseline's.
- **Status:** PASSED, or **LOW RELIABILITY** when the commodity ships only
  occasionally (fewer than 40% of test months have cargo).
- Table: month, actual, ML prediction, baseline, ML error %.

### NMPA Port Cost Estimator (Streamlit — bottom of this tab)
Same engine as the **Port Cost & Tariff** tab — see that section below.

### What-If Cargo Scenario Simulator
Sliders: vessel arrival change %, trade demand shift %, weather delay days.
**How:** takes the real forecast and multiplies it:
`(1 + vessel% × 0.6) × (1 + demand% × 0.8) × (1 − 0.033 × weather days, min 0.7)`.
Output: simulated total tonnes, change vs. baseline, and a stress label (HIGH BERTH
STRESS if > +20% or ≥ 3 weather days; UNDER-UTILIZATION if < −15%).
**🟡 SCRIPTED** — the 0.6 / 0.8 / 0.033 factors are documented assumptions, not
learned. The baseline it starts from is the real forecast.

**How to explain the tab:** "We forecast every commodity's monthly cargo from five
years of NMPA traffic data using a Random Forest model, show a 95% uncertainty band,
and prove accuracy by hiding the last months and checking the model against a simple
baseline. Where history is too thin, the screen says so instead of showing a fake
accuracy."

**Careful (web dashboard only):** its subtitle says "Holt-Winters + Ridge ML models";
the model actually running is a **Random Forest**. If the accuracy API fails, the
card falls back to a placeholder 82.8%.

---

## Tab 4 — Cargo Routing (web dashboard only)

**Purpose:** Recommend which NMPA berth should handle a cargo, and check capacity.
**Status:** 🟢 REAL (derived) — rules applied to NMPA's official berth specifications.

| Element | Meaning | How calculated |
| :--- | :--- | :--- |
| **Inputs:** commodity, monthly volume, vessel DWT, required draught | The cargo and ship to be handled | User input |
| **Recommended NMPA Handling Facility** | Best berth | Keeps only berths whose max draught ≥ required draught and max DWT ≥ vessel DWT; ranks the commodity's designated berths first (score 95) above other eligible berths (75) |
| **Max Draught / Max DWT badges** | Limits of the recommended berth | From `berths.csv` |
| **Utilization % (status)** | How full the berth would be | (monthly volume × 12) ÷ berth annual capacity. OPTIMAL ≤ 70%, MODERATE 70–85%, HIGH_CONGESTION_RISK > 85% |
| **Stage 1–4 cards** | Sea approach → berth → storage → hinterland exit | Commodity routing map (e.g. coal → conveyor → rail to UPCL) |
| **Official NMPA Berth Facilities table** | All 17 berths with type, draught, DWT, capacity, ownership | Straight from `berths.csv` + `berth_capacity.csv` |

**How to explain it:** "Given a commodity and a ship, the engine filters NMPA's 17
berths by draught and DWT, prefers the berth designated for that cargo, and checks
whether the annual volume fits the berth's capacity."

---

## Tab 4b — Port Cost & Tariff (web dashboard; Streamlit has it inside Cargo Forecasting)

**Purpose:** Estimate the port charges for a cargo shipment using NMPA's official
**Schedule of Rates (SOR) 2026-27** (effective 01-05-2026 to 30-04-2027).
**Status:** 🟢 REAL (derived) — every rate is from the official SOR. The inputs are
what-if values you type in, so the result is an estimate, not an invoice.

### Inputs
| Input | Meaning |
| :--- | :--- |
| **Commodity** | Type any name ("Urea", "TOTAL COAL") or an SOR code ("B.III.j") |
| **Quantity** | In the SOR unit of that commodity — MT for most, CBM for timber/yarn, units for vehicles |
| **Cargo Flow** | Import, Export, Coastal, Transhipment — decides foreign/coastal rate and free days |
| **Vessel Type / GRT / Berth Hours** | For berth hire |
| **Storage Days / Storage Category** | For transit storage (bulk, break bulk, salvaged, export not shipped) |
| **Annual Volume** | Only used for cement, whose rate depends on yearly volume |
| **USD → INR rate** | RBI reference rate on the vessel's entry day — needed because the SOR sets foreign-vessel charges in US$ |

### Commodity matching (shown under the Commodity box)
The name is matched to one of the **116 SOR wharfage lines** in this order:
exact name/code → known alias inside the name → spelling-tolerant word match →
otherwise "Unremunerated goods" (as the SOR itself directs). Low-confidence matches
show a ⚠ so the user can confirm. Containers and total/summary rows are refused
because they are not charged wharfage per tonne.

### Results
| Element | How calculated | SOR reference |
| :--- | :--- | :--- |
| **Wharfage** | Chargeable units × SOR rate (coastal or foreign). Rounding: fraction < 0.5 → 0.5 unit, ≥ 0.5 → 1 unit; minimum 1 unit | 3.1.1 |
| **Berth Hire** | Vessel GRT × rate × hours, subject to an hourly minimum. **Foreign vessels are charged in US$**, converted with the rate you enter; without a rate it shows US$ only and is kept out of the ₹ total | 2.3.1 |
| **Transit Storage** | After free days: imports ₹5.083 → ₹8.884 → ₹12.696 per unit per day (1st week / 2nd week / after); exports flat ₹5.083 | 3.2.1(a)/(b) |
| **Free days** | Foreign import 7 · coastal 15 · export 21 · transhipment 28 · salvaged export 3 · export not shipped 7 | 3.2.1 |
| **Total Known Cost (₹)** | Sum of the calculated ₹ components only | — |
| **Cost Breakdown table** | Each component with its SOR reference, status, SOR currency, US$ and ₹ amounts | — |
| **🚧 Coming soon** | Charges the SOR lists but prints as "*" (as and when applicable): demurrage, hazardous +50%, storage licence fee (Estate SOR), wharf-evacuation penalty, shut-out surcharge, volume discount, labour | 3.1.2, 3.1.4, 3.2.2, 3.3, 3.4 |
| **SOR 3.1.1 Wharfage Schedule** *(web)* | All 116 lines with coastal/foreign ₹ rates, filterable | 3.1.1 |

**Worked example:** 10,000 MT crude oil, foreign → wharfage = 10,000 × ₹96.60 =
₹9,66,000. A 30,000 GRT dry-bulk ship for 24 h → 30,000 × US$0.002824 × 24 =
**US$ 2,033.28** berth hire (converted to ₹ at the RBI rate you enter).

**How to explain it:** "This turns NMPA's 87-page tariff PDF into a calculator: pick
a cargo, and it finds the right tariff line, applies the SOR's own rounding,
free-day and currency rules, and clearly marks charges the SOR hasn't priced yet."

**Careful:** not included — port dues, pilotage (calculable in the engine, not yet on
the form), GST, and the "coming soon" items. It is an estimate of known components.

---

## Tab 5 — Trade Intelligence

**Purpose:** Show trade lanes, commodity prices and trade opportunities.
**Status:** 🔴 SIMULATED — the tab carries a warning. The project has no trade-lane,
shipping-route or commodity-price dataset.

| Element | Meaning | Status |
| :--- | :--- | :--- |
| **Trade Lane YoY Growth bar chart** | Growth per route (green up, red down) | 🔴 |
| **Commodity Demand & Route Flow Details** *(Streamlit)* | Route-level demand table | 🔴 |
| **Commodity Price Indices** *(Streamlit)* | Price trend lines | 🔴 |
| **Commodity Trade Opportunities** *(Streamlit)* | Ranked opportunities | 🔴 |

**How to explain it:** "This shows the intended trade-intelligence view. Once trade
or price data is connected it would feed these charts; for real commodity demand,
use the Cargo Forecasting tab."

---

## Tab 6 — Anomaly Detection ("Cargo Anomaly & Risk Intelligence")

**Purpose:** Automatically flag unusual months in cargo traffic.
**Status:** 🟢 REAL (ML), unsupervised.

| Element | Meaning | How calculated |
| :--- | :--- | :--- |
| **Anomaly cards** | One unusual month per card | **Isolation Forest** (scikit-learn, 200 trees) on each commodity's monthly series using: tonnage, month-on-month change, and vessel count (standardised). About 15% of months are flagged |
| **Type** | Cargo Surge / Cargo Decline / Vessel Congestion Spike / Volume Pattern Anomaly | Surge if MoM > +25% or resuming from zero; decline if < −25%; congestion spike if vessel count > 2 standard deviations; otherwise pattern anomaly |
| **Severity** | Critical / High / Medium / Low | Rank of the anomaly score among the flagged months (quartiles) — relative, not absolute |
| **Confidence** | How strongly the month stands out | Scaled anomaly score, 55–99% |
| **Recommended action** | What operations should do | Fixed action per type (e.g. surge → pre-allocate yard storage) |
| **Anomaly history chart** *(Streamlit)* | Anomaly counts over time | Real monthly detection counts, drawn on a daily axis |
| **Detection Algorithms** *(Streamlit)* | Which methods are used | Descriptive panel |
| **Port Congestion Risk Classifier (ML)** *(Streamlit)* | LOW / MODERATE / HIGH congestion risk, now and next 3 months | **Random Forest classifier**. Months are labelled by vessel-count percentile; features = tonnage, lag, rolling average, MoM, seasonality, trend. Accuracy measured on 25% held-out months. Future months use the cargo forecast's predicted tonnage. Score 0–10 |

**How to explain it:** "No one has to scan 54 months of traffic tables: the model
learns what a normal month looks like for each commodity and flags months that
don't fit, then says whether it's a surge, a decline or a vessel spike."

**Careful:** there is no labelled list of "true" anomalies, so accuracy can't be
scored; severity is relative to other flagged months.

---

## Tab 7 — Incentive Engine ("Trade Incentive Recommendation Engine")

**Purpose:** Suggest tariff incentives to win back declining cargo or premiums where
demand is strong.
**Status:** 🟢 REAL (derived) trends + 🟡 assumed elasticity.

| Element | Meaning | How calculated |
| :--- | :--- | :--- |
| **Recommendation cards** (action, priority, rationale) | E.g. "Offer a 6.5% handling-charge rebate on Iron Ore" | Real year-on-year change for each commodity's latest month. **Decline > 5%** → rebate = min(10%, decline × capture factor). **Growth > 15%** → priority-berth premium |
| **Priority** | High / Medium | High if decline > 20% or growth > 40% |
| **Predicted traffic impact** | Expected recovery | Rebate × pass-through factor (assumed) |
| **Revenue impact** | Shows "N/A" | The cargo dataset has no price column, so no ₹ figure is invented |
| **Confidence** | 40–75% | Grows with the size of the real trend |
| **Monte Carlo simulation** *(Streamlit)* | Range of possible volumes under a charge change / incentive | 1,000 random draws from the commodity's **real** historical mean and spread, shifted by the incentive assumption. Shows P10–P90 in tonnes |

**How to explain it:** "The trigger is real — actual YoY decline or growth from NMPA
traffic. The size of the suggested rebate uses a stated assumption, because NMPA has
no history of past incentive campaigns to learn from."

**Note:** revenue can now be estimated for a specific shipment using the Port Cost
& Tariff tab (SOR rates); the incentive engine itself is still tonnage-based.

---

## Tab 8 — Digital Twin ("Digital Twin Port Simulator")

**Purpose:** Stress-test the port under scenarios.
**Status:** 🔴 SIMULATED outcomes on a 🟢 real berth baseline.

| Element | Meaning | Status |
| :--- | :--- | :--- |
| **Scenario selector** *(Streamlit)* | Cargo Surge +20%, Vessel Delay Increase, Trade Incentive Policy, Weather Disruption (Cyclone) | — |
| **Radar chart** | Congestion, berth utilisation, storage utilisation, revenue under the scenario | 🔴 (web version: revenue axis is a fixed 90) |
| **Operational Impact Assessment** *(Streamlit)* | Text impact summary | 🔴 |
| **Berth comparison chart** *(Streamlit)* | Berth utilisation before vs. after the scenario | Baseline 🟢 real (same as berth occupancy); scenario change 🔴 simulated |

**How to explain it:** "This demonstrates the digital-twin concept. The berth
baseline is real; the scenario effects are illustrative until calibrated with real
incident data."

---

## Tab 9 — AI Maritime Copilot

**Purpose:** Ask questions in plain English ("Why is coal forecast increasing?").
**Status:** 🔴 SIMULATED — answers are templates, not a real AI/LLM call. The tab says
so.

| Element | Meaning |
| :--- | :--- |
| **Question box + Submit** | Sends the question to `/copilot/query` |
| **Suggested queries** *(Streamlit)* | Example questions, clickable |
| **Copilot response** | Templated answer |
| **LangGraph Dispatch Trace** *(Streamlit)* | Illustrates a multi-agent design; LangGraph is not actually installed |

**How to explain it:** "This shows the planned conversational interface. In the next
phase it would be connected to a real language model grounded in our forecast and
tariff data."

---

## Tab 10 — Data Pipeline ("Data Pipeline & System Architecture")

**Purpose:** Show the intended data architecture.
**Status:** 🔴 SIMULATED — no Kafka, Spark, Airflow or database runs behind the project;
the tab says so.

| Element | Meaning | Status |
| :--- | :--- | :--- |
| **Kafka msg/sec, Spark rows/sec, Storage GB, Airflow DAGs** | Pipeline throughput | 🔴 fixed demo values |
| **Live Ingestion Event Log** *(Streamlit)* | Log lines | 🔴 |
| **Data Pool Statistics** *(Streamlit)* | Storage per pool | 🔴 |
| **System Architecture Diagrams** *(Streamlit)* | How the production system would be built | Design illustration |

**How to explain it:** "Today the platform reads NMPA's CSV/PDF data directly. This
tab shows the target production architecture for streaming data at scale."

---

## Quick answers to common questions

| Question | Answer |
| :--- | :--- |
| Is the forecast real? | Yes — Random Forest on 54 months of real NMPA traffic, with backtested accuracy shown next to it. |
| How accurate is it? | Shown per commodity as 100 − WAPE, compared with a seasonal baseline. Commodities that ship irregularly are marked LOW RELIABILITY. |
| Is the ship map live? | No. There is no AIS feed; the map and tracker use a demo fleet. |
| Is the revenue real? | No. The executive revenue figure is simulated. Shipment-level charges can be estimated from the official SOR in the Port Cost & Tariff tab. |
| Are the tariff rates official? | Yes — NMPA SOR 2026-27 (effective 01-05-2026). Rates printed as "*" are shown as "Coming soon", not guessed. |
| Why US$ for berth hire? | The SOR sets foreign-going vessel charges in US$, billed in ₹ at the RBI reference rate on the vessel's entry day. |
| What data would make more tabs real? | Live AIS feed, financial/revenue data, trade-lane and price data, historical incentive campaigns, and incident logs for the digital twin. |

## Suggested presentation order

1. **Cargo Forecasting** — core, real ML, show the backtest.
2. **Port Cost & Tariff** — official SOR, worked example.
3. **Cargo Routing** — official berth data.
4. **Anomaly Detection** — real ML flags + congestion classifier.
5. **Vessel Intelligence** — explain demo tracker vs. real vessel-call forecast.
6. **Incentive Engine** — real trends, stated assumptions.
7. **Executive, Digital Twin, Trade, Copilot, Pipeline** — present as the target
   product vision, clearly labelled as demo.
