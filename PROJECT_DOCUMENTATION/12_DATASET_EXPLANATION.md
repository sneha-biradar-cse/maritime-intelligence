# 12 — Dataset Specification & Data Engineering Analysis

## 📊 Overview of Project Datasets

The Maritime Port Intelligence Platform is powered by real-world, multi-year historical port traffic datasets stored in the `data/` directory.

```text
data/
├── port_cargo_monthly.csv       # Primary NMPA Monthly Cargo Dataset (1,354 records, 2021–2026)
└── sample_cargo_data.csv        # Multi-Port Weekly Benchmark Dataset (62 records, 2024)
```

---

## 🗃️ 1. Primary Dataset: `data/port_cargo_monthly.csv`

### General Metadata
* **File Location**: `data/port_cargo_monthly.csv` (83.6 KB).
* **Domain Grounding**: Actual traffic records mapped to **New Mangalore Port Authority (NMPA)**.
* **Total Record Count**: 1,354 historical monthly observation rows.
* **Temporal Coverage**: Spans years **2021, 2023, 2024, 2025, and 2026**.
  * `2021`: 72 unique commodity observations.
  * `2023`: 22 commodity observations.
  * `2024`: 16 commodity observations (Full multi-month coverage).
  * `2025`: 16 commodity observations (Full multi-month coverage).
  * `2026`: 22 commodity observations (Up to July 2026).

---

### Column Schema & Data Definitions

| Column Name | Data Type | Null Count | Description & Operational Meaning |
| :--- | :--- | :--- | :--- |
| `month` | Object (str) | 0 | Name of the calendar month (e.g., `January`, `February`, `December`). |
| `year` | Int64 | 0 | Calendar year (e.g., `2021`, `2024`, `2025`, `2026`). |
| `section` | Object (str) | 0 | Trade flow direction: `LOADED` (Export) or `UNLOADED` (Import). |
| `commodity` | Object (str) | 0 | Specific commodity category name (e.g., `TOTAL CRUDE`, `TOTAL COAL`, `CONTAINER (JSW)`). |
| `vessels_current` | Float64 | 0 | Number of ship calls recorded for this commodity in current month. |
| `vessels_prev_year` | Float64 | 0 | Number of ship calls for this commodity in the same month of previous year. |
| `traffic_tonnes_current`| Float64 | 0 | **Primary Metric**: Total cargo weight handled (Metric Tonnes). |
| `traffic_tonnes_prev_year`| Float64 | 0 | Total cargo weight handled in same month of previous year (Tonnes). |
| `pct_variation_yoy` | Float64 | 0 | Percentage variation in tonnage volume YoY ($((Current - Prev)/Prev) \times 100$). |

---

### Commodity Categories Represented in NMPA Data

1. **`TOTAL CRUDE`**: Crude oil imports for MRPL (Mangalore Refinery & Petrochemicals Ltd).
2. **`CRUDE - ISPRL`**: Strategic Crude Oil Reserves for Indian Strategic Petroleum Reserves Ltd.
3. **`TOTAL COAL`**: Thermal coal imports for UPCL (Udupi Power Corp Ltd / Adani Power Plant).
4. **`IRON ORE`**: Iron ore pellets and fines for KIOCL Bulk Terminal & Kudremukh Corridor.
5. **`CONTAINER (JSW)`**: Containerized cargo handled at dedicated Berth 14 (JSW Container Terminal).
6. **`FERTILIZER`**: Finished fertilizer imports for MCF (Mangalore Chemicals & Fertilizers Ltd).
7. **`F.R.M. (DRY)`**: Fertilizer Raw Materials (Rock Phosphate, Sulphur).
8. **`TOTAL LPG`**: Liquefied Petroleum Gas imports for HPCL / BPCL / IOCL bottling plants.
9. **`POL PRODUCTS`**: Petroleum, Oil & Lubricants (Clean products like Diesel, Petrol, Naphtha).
10. **`OTH. LIQ. CARGOES`**: Chemicals, Acids, Molasses, Bio-fuels.
11. **`EDIBLE OIL`**: Palm oil and crude sunflower oil imports.
12. **`TOTAL CEMENT`**: Bulk cement and clinker shipments.
13. **`FOOD GRAINS`**: Wheat, Rice, and Agricultural exports.
14. **`PETROCHEMICALS`**: Polypropylene, Paraxylene, Aromatic compounds.
15. **`OTHER CARGO`**: General dry bulk and break-bulk items.

---

## 📅 Multi-Year Combination & Comparison Methodology

How does the system combine and compare **2024, 2025, and 2026** commodity datasets?

1. **Continuous Time-Series Construction** (`forecasting.py:_load_and_prep_cargo_data()`):
   * Converts `year` and `month` into standard datetime objects:
     `ds = pd.to_datetime(df['year'].astype(str) + '-' + df['month'] + '-01')`
   * Sorts all 1,354 records chronologically from `2021-01-01` through `2026-07-01`.

2. **Handling Missing Month-Commodity Gaps**:
   * If a specific commodity (e.g., `FOOD GRAINS`) had zero shipments in a given month, the preprocessing pipeline performs a reindex grid search and fills missing volume values with `0.0` tonnes rather than dropping rows.

3. **Year-over-Year (YoY) Growth Calculations**:
   * Compares 2024 vs 2025 and 2025 vs 2026 tonnage by aligning identical calendar months:
     $$\text{Growth \%} = \frac{\text{Volume}_{2026,\text{Month}} - \text{Volume}_{2025,\text{Month}}}{\text{Volume}_{2025,\text{Month}}} \times 100$$

4. **Multi-Year Feature Engineering for ML**:
   * **Lag 1 Feature ($y_{t-1}$)**: Volume in the immediately preceding month.
   * **Lag 12 Feature ($y_{t-12}$)**: Volume in the exact same month of the prior calendar year (captures annual seasonal cycles such as monsoon delays during June–August).

---

## 🗃️ 2. Secondary Benchmark Dataset: `data/sample_cargo_data.csv`

* **File Location**: `data/sample_cargo_data.csv` (2.6 KB).
* **Total Record Count**: 62 weekly records.
* **Fields**: `date`, `port` (Mumbai, Chennai, JNPT, Kandla, Vizag, Kochi), `cargo_volume_mt`, `vessel_arrivals`, `congestion_score`, `import_volume`, `export_volume`.
* **Usage**: Provides national benchmark metrics for comparing NMPA port performance against major Indian ports.
