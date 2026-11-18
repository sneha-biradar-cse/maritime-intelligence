# Data sources: what every figure is built from

This file lists every source used by Trade Intelligence and the Incentive Engine, where the original is kept,
and what is still missing or assumed. Keep it up to date when data is added.

## 1. Original files held in this project

| Source | Original file(s) | Read into |
|---|---|---|
| NMPA monthly commodity-wise traffic statements (Jan 2023 - Sep 2026; 2022 from prior-year columns) | `nmpa_public_data/Commodity wise traffic statement *.pdf` | `data/port_cargo_monthly.csv` |
| NMPA container statements (Statement II) | `nmpa_public_data/container traffic*.pdf` | `data/nmpa_container_commodities.csv` |
| NMPA Traffic & Performance reports (Apr 2025 - Sep 2026) | `nmpa_public_data/*performance*.pdf` | `data/nmpa_performance_monthly.csv`, `data/port_targets.csv` |
| Ministry of Ports "Cargo handled at Major Ports" monthly reports (Mar 2025 - Sep 2026) | `nmpa_public_data/*Major*Port*.pdf` | `data/major_ports_monthly.csv`, `data/major_ports_commodity_monthly.csv` |
| NMPA Scale of Rates, indexed 01-05-2026 to 30-04-2027 | `nmpa_public_data/Microsoft Word - NMPA SOR indexation 0.65.doc.pdf` | rates in `backend/app/services/cost_engine.py`, pages in `data/sor_reference.json` |
| NMPA daily vessel position reports (97 days with PDF) | `data/daily_vessel_position/*.pdf` | `data/daily_vessel_position_parsed/*.json` |

## 2. Read from websites; the original file is NOT yet in this project

| Source | Web address | Used for | Read into |
|---|---|---|---|
| NMPA Revised Estimate 2023-24 & Budget Estimate 2024-25, operating income detail | https://newmangaloreport.gov.in/sites/default/files/2024-08/7-36.pdf | Check against NMPA's own accounts; PPP royalty income | `data/nmpa_budget_income.csv` (transcribed) |
| NMPA PPP disclosure 3.1.3 (Berth 14 container terminal, Berth 16 coal terminal) | https://newmangaloreport.gov.in/sites/default/files/2025-09/3.1.3.pdf | Concession date (27 Jan 2020, 30 years), Berth 16 royalty 31% of gross revenue | text in `backend/app/services/incentive_engine.py` |
| Ministry of Ports non-major ports report, July 2026 | (Ministry website) | Nearby state-port comparison | `data/non_major_ports_2026-07.csv` |

## 3. Facts taken from news reports only (an official document is still needed)

| Fact | Where it came from | Official document needed |
|---|---|---|
| Container royalty Rs 951 per TEU at award (2019) | BusinessLine, via Maritime Gateway | Concession agreement summary or NMPA document stating the royalty and its indexation |
| NMPA waived cargo charges for LPG and crude tankers from March 2026 | India Shipping News, March 2026 | NMPA notice / circular with dates and terms |
| Mangalore Chemicals & Fertilizers merged into Paradeep Phosphates (Oct 2025) | Company news | Company or NMPA confirmation (used to merge customer names) |
| Adani Wilmar renamed AWL Agri Business | Company news | Company or NMPA confirmation (used to merge customer names) |

## 4. Original PDFs missing for data already held

- 226 NMPA daily vessel position reports, Sep 2025 - Sep 2026 (the read data is in `data/daily_vessel_position_parsed/`,
  the PDFs are not). 62 days were re-checked against their PDFs and matched exactly.

## 5. Choices made in the calculations (to be confirmed by NMPA)

- Customer name merges in `data/customer_aliases.csv` (e.g. APL = UPCL, ADANI = AWL Agri) - from spellings, not confirmed.
- Crude priced by where it was discharged (SPM or berths 10/11), using the berth recorded in the daily reports.
- KIOCL iron ore and UPCL coal removed from wharfage estimates using their share of the cargo in the daily reports.
- Container royalty per laden TEU taken from NMPA's 2023-24 royalty income / laden TEU.
- Alert thresholds are judgement calls, not published figures: cargo change 20% with at least 1% share; customer
  change 30%, or 5% and 100,000 t; market share gaining/losing at 5 points against the other 11 major ports.
- Wharfage estimates use today's tariff for all periods; waivers and special discounts are not deducted.

## 6. Data that would improve the tool (not yet received)

- Cochin and Mormugao (and other competing ports') Scale of Rates - tariff comparison.
- NMPA incentive, rebate and waiver notices.
- Ministry "Update on Indian Port Sector" 2024-25 / 2025-26, or IPA commodity-wise traffic by port - fills March gaps.
- NMPA Revised Estimate 2024-25 / Budget Estimate 2025-26 - a more recent accounts check.
- From NMPA: actual billed wharfage, current container royalty and total TEU (incl. empties), cost per tonne,
  ship call records, customer name confirmations, approval hierarchy.
