# 09 — Data Persistence Layer & Dataset Ingestion

## 🗄️ Storage Architecture Overview

The Maritime Port Intelligence Platform utilizes an **In-Memory Analytical Data Pool** powered by **Pandas DataFrames**, backed by persistent CSV files and an HTTP Multipart File Upload service.

While production maritime platforms often connect to PostgreSQL or TimescaleDB, this application uses a high-performance Python time-series ingestion engine that loads, cleans, and indexes multi-year CSV datasets directly into memory upon server initialization.

```text
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                PERSISTENT CSV STORAGE                                  │
 │                                                                                        │
 │  `data/port_cargo_monthly.csv` (1,354 records)   `data/sample_cargo_data.csv` (62 records)│
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                            IN-MEMORY PANDAS DATA POOL                                  │
 │  (`backend/app/services/forecasting.py:_load_and_prep_cargo_data()`)                   │
 │                                                                                        │
 │  - Continuous monthly datetime index (`ds`: 2021-01-01 to 2026-07-01)                  │
 │  - Categorical commodity indexing (16+ NMPA commodities)                               │
 │  - Directional filtering (`LOADED` / `UNLOADED` / `ALL`)                               │
 └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                             ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                          DYNAMIC CSV UPLOAD & STORAGE ENGINE                           │
 │  (`backend/app/routes/upload.py:upload_file()`)                                        │
 │                                                                                        │
 │  - Accepts custom multipart CSV reports via `POST /upload/`                            │
 │  - Saves uploads to `uploads/` directory with timestamped filenames                    │
 │  - Validates file size (max 20MB) and CSV header integrity                            │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Dataset Schemas & Attributes

### 1. Primary Dataset: `data/port_cargo_monthly.csv`
* **Source**: Official monthly cargo traffic records mapped to New Mangalore Port Authority (NMPA).
* **Record Count**: 1,354 historical monthly rows.
* **Time Span**: Covers 2021, 2023, 2024, 2025, and 2026.
* **Column Breakdown**:

| Column Name | Data Type | Meaning / Purpose | Example Value |
| :--- | :--- | :--- | :--- |
| `month` | String | Name of the calendar month | `January`, `February` |
| `year` | Integer | Calendar year of record | `2021`, `2024`, `2026` |
| `section` | String | Direction of trade flow | `LOADED` (Export) / `UNLOADED` (Import) |
| `commodity` | String | Commodity category name | `TOTAL CRUDE`, `TOTAL COAL`, `CONTAINER (JSW)` |
| `vessels_current` | Float | Number of ship calls for commodity in current month | `15.0`, `18.0` |
| `vessels_prev_year` | Float | Number of ship calls for commodity in same month last year | `154.0`, `91.0` |
| `traffic_tonnes_current` | Float | **Primary Metric**: Tonnage handled in current month | `1,576,414.0`, `657,884.0` |
| `traffic_tonnes_prev_year` | Float | Tonnage handled in same month of previous year | `1,499,513.0`, `516,675.0` |
| `pct_variation_yoy` | Float | Year-over-Year percentage volume change | `+22.49%`, `-5.89%` |

---

### 2. Benchmark Dataset: `data/sample_cargo_data.csv`
* **Source**: Multi-port benchmark dataset used for comparative analytics.
* **Record Count**: 62 weekly records.
* **Ports Covered**: Mumbai, Chennai, JNPT, Kandla, Vizag, Kochi.
* **Column Breakdown**: `date`, `port`, `cargo_volume_mt`, `vessel_arrivals`, `congestion_score`, `import_volume`, `export_volume`.

---

## 🔄 Data Lifecycle: How Data Reaches the Dashboard

1. **Storage**: File remains safely stored on disk in `data/port_cargo_monthly.csv`.
2. **Read & Clean**: `forecasting.py:_get_raw_df()` invokes `pd.read_csv()`, strips whitespace from commodity strings, and parses numeric columns.
3. **Resampling**: `_load_and_prep_cargo_data()` creates a continuous month-by-month time series (`2021-01` to `2026-07`), filling missing commodity-month pairs with zero volume.
4. **NMPA Infrastructure Mapping**: Enriches each commodity with NMPA facility details (`NMPA_FACILITY_MAP`):
   * Berth assignments (`Oil Jetty 1 & 2`, `Berths 15 & 16`, `Berth 14 Dedicated Container`).
   * Draft depth limits (`15.4m`, `14.0m`, `13.0m`).
   * Hinterland consumer linkages (`MRPL Refinery`, `UPCL Power Plant`, `KIOCL`, `MCF`).
5. **REST API Delivery**: FastAPI serializes data frames into JSON payloads (`GET /cargo/forecast`).
6. **Frontend Display**: Streamlit renders metrics, Plotly time-series lines, and data quality cards (`Completeness: 98.4%`, `Span: 2021-01 to 2026-07`, `1,354 Records Analyzed`).
