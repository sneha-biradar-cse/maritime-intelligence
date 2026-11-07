# 11 — API Documentation & Endpoint Reference

## 📡 REST API Architecture Overview

The backend service hosts fully documented REST API endpoints running on `http://127.0.0.1:8000`. Interactive Swagger UI documentation is available at `http://127.0.0.1:8000/docs`.

---

## 📋 Complete REST Endpoint Reference Table

| Method | Endpoint | Purpose / Function | Input Parameters | Output Payload | Frontend Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | Root status check | None | `{"message": "...", "modules": 8}` | Server verification |
| `GET` | `/health` | Liveness check | None | `{"status": "healthy"}` | Container health |
| `GET` | `/cargo/commodities` | List available commodities | None | `{"commodities": [...], "sections": [...]}` | Tab 3 Dropdown |
| `GET` | `/cargo/forecast` | Data-grounded ML cargo forecast | `horizon`, `commodity`, `section` | Forecast series, 95% bounds, drivers, NMPA meta | ⭐ Tab 3 Main Chart |
| `GET` | `/cargo/accuracy` | Backtesting WAPE comparison | `commodity`, `section` | Test actuals, baseline vs ML model, metrics table | Tab 3 Backtesting |
| `GET` | `/cargo/explainability` | Driver weights & explanations | `commodity`, `section` | Drivers list with weights and directions | Tab 3 Drivers |
| `GET` | `/cargo/data-quality` | Lineage & completeness stats | None | Completeness %, record count, date span | Tab 3 Lineage Card |
| `POST`| `/cargo/scenario` | What-If cargo scenario simulator | `vessel_arrival_change_pct`, `demand`, `weather` | Simulated throughput, delta tonnes, stress level | Tab 3 Simulator |
| `GET` | `/cargo/berths` | Berth occupancy status | None | List of 12 berths with commodity assignments | Tab 1 Berth Bar Chart |
| `GET` | `/vessels/` | Active AIS vessel logs | None | List of 25 vessels with coords, ETA, delay prob | Tab 1 & Tab 2 Map/Table|
| `GET` | `/vessels/congestion-alerts`| Congestion risk warnings | None | List of alert objects with risk scores | Tab 2 Alert Cards |
| `GET` | `/trade/summary` | Real inbound/outbound cargo summary | None | Latest month, last-12-month totals, YoY, data-quality notes | Tab 4 KPIs |
| `GET` | `/trade/flows?months=36` | Real monthly inbound/outbound series with 3-month EMA | None | `series[]` (null = missing month) | Tab 4 flow chart |
| `GET` | `/trade/commodities?direction=all` | Per-cargo YoY, share, momentum signal | None | `commodities[]` | Tab 4 momentum chart/table |
| `GET` | `/trade/commodity?name=` | One cargo's monthly series (404 if unknown) | None | `series[]` | Tab 4 drill-down |
| `GET` | `/trade/forecast?horizon=3` | Real 1-3 month forecast from past tonnes, back-tested against the 12-month average; shows a typical range and a reliability label; no number for cargos that cannot be forecast | `horizon` 1-3 | `results[]` with `forecast[]`, `by_horizon`, `confidence`, `how_it_works`, `limits` | Tab 4 forecast section |
| `GET` | `/trade/cargo-split` | ESTIMATE of foreign vs coastal ships per cargo (and main customers) from NMPA daily vessel reports, checked against the Ministry's whole-port coastal share | None | `families[]`, `validation_against_ministry`, `limits` | Tab 4 foreign vs coastal section |
| `GET` | `/trade/lanes` | Trade lane volume & growth % | None | List of trade routes with growth rates | Tab 4 Trade Lanes |
| `GET` | `/trade/commodity-prices` | 30-day commodity price trends | None | Price USD series, 30d delta | Tab 4 Price Ticker |
| `GET` | `/trade/opportunities` | AI-ranked trade opportunities | None | Ranked list with revenue potential in ₹ Cr | Tab 4 Opportunities |
| `GET` | `/anomaly/events` | Active anomaly event logs | None | Anomalies classified by severity (Surge, Decline) | Tab 5 Anomaly Cards |
| `GET` | `/anomaly/history` | 30-day anomaly histogram data | None | Historical count by severity tier | Tab 5 Histogram |
| `GET` | `/incentive/recommendations`| Trade incentive policy recs | None | Priority-ranked policy recommendations | Tab 6 Incentives |
| `POST`| `/incentive/monte-carlo` | Monte Carlo revenue simulator | `scenario`, `charge_delta`, `incentive_pct` | P10/P50/P90 quantiles & 1,000 sample points | Tab 6 Histogram |
| `GET` | `/twin/scenario/{key}` | Digital twin scenario result | `key` (`cargo_surge`, `vessel_delay`, etc.) | Congestion index, utilization, radar metrics | Tab 7 Digital Twin |
| `GET` | `/twin/berths` | Simulated berth utilization | None | Baseline vs simulated berth utilization | Tab 7 Berth Chart |
| `GET` | `/copilot/suggested-queries`| Suggested AI questions | None | List of sample question strings | Tab 8 Copilot Chips |
| `POST`| `/copilot/query` | Natural language copilot query | `{"query": "..."}` | 3-tier dispatch trace, confidence, answer | Tab 8 AI Response |
| `GET` | `/pipeline/status` | Ingestion pipeline health | None | Kafka msg/sec, Spark rows/sec, storage GB | Tab 9 System Metrics |
| `GET` | `/pipeline/log` | Live ingestion event log | None | List of timestamped ingestion log rows | Tab 9 Event Log |
| `GET` | `/executive/kpis` | Executive KPI summary | None | Berth util, throughput, revenue, congestion | Tab 1 Top Metrics |
| `GET` | `/executive/revenue-trend` | 30-day revenue & throughput | None | Dates, revenue ₹ Cr, throughput MT arrays | Tab 1 Trend Line |
| `GET` | `/executive/events` | Port event stream | None | Recent arrival/departure/forecast events | Tab 1 Event Log |
| `POST`| `/upload/` | Multipart CSV file upload | `file` (Multipart Form) | File path, row count, column headers | Data Integration |

---

## 💡 Detailed Explanation of Primary Core Endpoints

### 1. `GET /cargo/forecast`
* **Query Parameters**:
  * `horizon`: Integer (3, 6, 12 months, default: 6).
  * `commodity`: String (`ALL`, `TOTAL COAL`, `TOTAL CRUDE`, `CONTAINER (JSW)`, etc.).
  * `section`: String (`ALL`, `LOADED`, `UNLOADED`).
* **Example JSON Response**:
```json
{
  "summary": {
    "current_monthly_volume_tonnes": 625768.0,
    "expected_monthly_avg_tonnes": 710889.9,
    "total_expected_horizon_tonnes": 4265339.5,
    "forecast_change_pct": 13.6,
    "trend_signal": "Increasing / Bullish",
    "predictability_level": "MEDIUM",
    "model_wape_pct": 17.15,
    "model_accuracy_pct": 82.8
  },
  "chart": {
    "history_months": ["2024-01", "2024-02", "2024-03"],
    "history_values": [657884.0, 612400.0, 640100.0],
    "forecast_months": ["2026-08", "2026-09", "2026-10"],
    "forecast_values": [690000.0, 715000.0, 730000.0],
    "lower_bounds": [610000.0, 625000.0, 635000.0],
    "upper_bounds": [770000.0, 805000.0, 825000.0]
  },
  "nmpa_facility": {
    "facility_name": "Mechanized Coal Handling Terminal",
    "berths": "Berth 15 & 16",
    "hinterland_consumer": "UPCL (Udupi Power Corp Ltd / Adani Power)",
    "max_draft_m": 14.0
  }
}
```

---

### 2. `POST /cargo/scenario`
* **Example Request Body**:
```json
{
  "commodity": "TOTAL COAL",
  "section": "ALL",
  "vessel_arrival_change_pct": 15.0,
  "trade_demand_change_pct": 10.0,
  "weather_delay_days": 1.0,
  "horizon_months": 6
}
```
* **Example JSON Response**:
```json
{
  "simulation_summary": {
    "baseline_total_tonnes": 4265339.5,
    "simulated_total_tonnes": 4836894.5,
    "volume_delta_tonnes": 571555.0,
    "volume_delta_pct": 13.4,
    "capacity_risk_level": "MODERATE_STRESS"
  },
  "simulated_operational_advisories": [
    "Vessel arrival increase of 15.0% requires preparing 2 additional bulk unloading cranes."
  ]
}
```
- /trade/waiting (GET): ship waiting analysis from NMPA daily vessel reports (reasons, cargo, customers, months).
