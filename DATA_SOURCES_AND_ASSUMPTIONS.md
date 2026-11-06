# Data sources and assumptions: Trade Intelligence and Incentive Engine

**What can be claimed:** verified against the available sources, with unresolved fields marked and excluded from official
figures. Not 100% accuracy. A record that matches its PDF proves the reading, not that the publisher's figure is final or that
two reports use the same definitions.

**Statuses used** (per dataset in `data/data_status.csv`, per daily report in `data/daily_reports_manifest.csv`, shown on the
Data & checks tab): Original obtained · Extraction checked · Reconciled · NMPA-confirmed · Estimated · Unresolved.

This file lists every data source the two modules use, which original documents are in this project and which are not,
and every assumption made where the data did not give the answer directly. Anyone checking or extending the work should
start here. Items marked **TO CONFIRM** need an answer from NMPA or an original document.

## 1. Original documents held in this project

| Folder / file | What it is | Coverage held | Checked |
|---|---|---|---|
| `nmpa_public_data/` commodity-wise traffic statements | NMPA monthly statements (tonnes by cargo) | Jan 2023 to Sep 2026 (all 45 months held) | Every line against the data; the 2023 statements also confirm the 2022 figures printed beside them (252 of 252 lines match) |
| `nmpa_public_data/` container traffic statements | NMPA Statement II, containers by commodity (TEU) | Jan 2025 to Sep 2026 | Commodities add up to printed totals |
| `nmpa_public_data/` operational performance | NMPA Traffic & Performance reports (totals, target, vessels) | Apr 2025 to Sep 2026 | |
| `nmpa_public_data/` Cargo handled at Major Ports | Ministry of Ports monthly reports (all 12 major ports) | Feb 2025 to Sep 2026 (17 reports; other months come from their "last year" and "April-to-date" columns) | Ports and commodities add up to printed totals |
| `nmpa_public_data/Microsoft Word - NMPA SOR indexation 0.65.doc.pdf` | NMPA Scale of Rates, indexed rates from 1 May 2026 to 30 April 2027 | | Every rate used is tested against the PDF |
| `nmpa_public_data/finance_and_policy/NMPA Budget RE 2023-24 BE 2024-25 (7-36).pdf` | NMPA income by cargo line, Actual 2022-23, RE 2023-24, BE 2024-25 | | All 17 lines in `data/nmpa_budget_income.csv` match the PDF |
| `nmpa_public_data/finance_and_policy/NMPA PPP details (3.1.3).pdf` | PPP terminals: Berth 14 (JSW containers), Berth 15 (UPCL / Adani Power captive jetty), Berth 16 (Mangalore Coal Terminal, 31% royalty) | | Read; facts used in the Incentive Engine |
| `nmpa_public_data/finance_and_policy/NMPA Trade Circular 2025-26 Gen.2 ... 14.03.2026.pdf` | Waiver of cargo-related charges for crude oil and LPG, vessels declared after 14 Mar and berthed up to 31 Mar 2026 | | Scanned image; read and transcribed into the Incentive Engine |
| `nmpa_public_data/finance_and_policy/Ministry Non-Major Cargo Report July 2026.pdf` | Ministry report, non-major ports by state board | Apr to Jul 2026 | All 11 states in `data/non_major_ports_2026-07.csv` match |
| `nmpa_public_data/finance_and_policy/Ministry Update on Indian Ports Sector upto 31.03.2025.pdf` | Ministry annual report; Annexure-I = tonnes by cargo for each major port, 2021-22 to 2024-25 (read into `data/major_ports_annual_port_commodity.csv`) | FY 2021-22 to 2024-25 | Every column adds up across the 13 ports; the 2024-25 all-ports total equals the monthly reports' April-March figure |
| `nmpa_public_data/company_notices/` | Adani Wilmar renamed AWL Agri Business (17 Mar 2025, stock-exchange filing); Paradeep Phosphates merger with Mangalore Chemicals & Fertilizers effective 16 Oct 2025 (stock-exchange filing); JSW Mangalore Container Terminal credit rating (5 Sep 2025: royalty Rs 951 per TEU, TEU handled FY24 and FY25) | | Read; used for customer names and container royalty |
| `nmpa_public_data/finance_and_policy/NMPA SOR 01-05-2026 to 06-05-2026 (old format).pdf` | NMPA Scale of Rates for 1-6 May 2026 | | All 8 wharfage lines used match the later version |
| `nmpa_public_data/finance_and_policy/NMPA Administration Report 2024-25.pdf` | Table F-I, actual income by activity 2023-24 and 2024-25 (in `data/nmpa_actual_income_2023_25.csv`) | | Scanned and structurally damaged (opens after repair, e.g. qpdf); read from page images; internal totals reconcile |
| `nmpa_public_data/finance_and_policy/NMPA Berth Capacity as on 31-3-2025.pdf` | Rated and usable capacity per berth (in `data/berth_capacity.csv`) | 31 Mar 2025 | All 17 berths match |
| `nmpa_public_data/cochin/` | Cochin Scale of Rates w.e.f. 01-05-2026, corrigendum (22.04.2026), trade notices 06/2026, 11/2026, 13/2026, 04/2025 (in `data/port_tariff_comparison.csv`, `data/cochin_schemes.csv`) | | Rates located with page numbers; notices scanned, numbers and dates checked inside |
| `data/daily_vessel_position/` | NMPA daily vessel position reports (PDF) | All 323 report days | 62 re-read days match the JSON exactly |
| `data/daily_vessel_position_parsed/` | The same reports, read into JSON | 323 days, 1 Sep 2025 to 26 Oct 2026 | |

## 2. Data used whose original document is still NOT in this project

| Data | Where it is used | Source used | Original wanted |
|---|---|---|---|
| Whether the names written in NMPA's daily reports ("ADANI", "MCF", "PPL", ...) refer to these companies | Customer name merges | The company renames and the merger are now confirmed by the companies' own filings; that NMPA's entries refer to them is inferred | NMPA's confirmation of customer names |

Ministry monthly reports for months not held (e.g. Jan, Feb, Sep 2025; Apr, Aug 2026) are not needed: their figures come from
the "last year" or "April-to-date" columns of later reports.

Every original document (publisher, period, pages/tables used, units, revision status, check status, MD5) is listed in
`data/source_register.csv` (rebuild with `python scripts/build_source_register.py`).

Every daily report day, with whether its original PDF is held and the PDF's MD5 checksum, is listed in
`data/daily_reports_manifest.csv`. To add originals: put the PDFs in `incoming/` (names starting with the date, e.g.
`01-09-2025.pdf`, `01-09-2025 (1).pdf`, `01-09-2025_0.pdf` or `01.09.2025.pdf`) and run `python scripts/update_trade_data.py`.
For a day already held as JSON, the script compares the PDF with it and reports "matches" or "DIFFERS" (keeping the old copy),
then uses the PDF.

## 3. Assumptions and rules (where the data does not give the answer directly)

### Trade Intelligence

| # | Assumption / rule | Why | Status |
|---|---|---|---|
| T1 | 2022 monthly tonnes are taken from the "same month last year" column of the 2023 statements | 2022 statements not held | Shaded on the chart |
| T2 | Months missing from a source are left empty, never treated as zero | Avoids false drops | Rule |
| T3 | Ministry months without their own report are derived from cumulative columns: (April to X) minus (April to X-1) | Fills months without a report | Checked: every month adds up to the printed total |
| T4 | Ministry April reports: cumulative columns are the two previous **full** financial years | That is how those reports are laid out | Rule; tested |
| T5 | Market share: NMPA cargo names are matched to Ministry groups (e.g. NMPA "Other cargo" against several Ministry lines) | The two sources group cargo differently | Approximate for mixed groups |
| T6 | NMPA statements exclude shore handling; Ministry totals include it | Source definitions | Shares very slightly understated |
| T7 | Gaining / losing share = NMPA grows at least 5 points faster / slower than the **other 11** major ports | Judgement threshold | TO CONFIRM with NMPA |
| T8 | Cargo alert = down or up at least 20% on the same 3 months last year and at least 1% of its direction | Judgement threshold | TO CONFIRM |
| T9 | Cargo momentum: rising/falling at +/- 5% (3-month vs 12-month weighted average); irregular if moved in fewer than 6 of 12 months | Judgement threshold | TO CONFIRM |
| T10 | Customer tonnes = each ship's cargo in the daily report (handled + balance); about 85% of official tonnes are traced to a customer | Daily reports miss ships whose stay fell between reports | Shown on the Data & checks tab |
| T11 | A ship call = one ship's stay for one cargo; a gap of more than 30 days starts a new call (20 days for container ships) | Daily reports list ships each day | Rule |
| T12 | Customer status: rising/falling at +/- 30%, or at least 5% when that is 100,000 t or more; "too few ships to judge" under 4 calls in 6 months | Judgement threshold | TO CONFIRM |
| T13 | Gone quiet = no ship for at least 30 days and 3 times the customer's usual gap (needs 5 past calls) | Judgement threshold | TO CONFIRM |
| T14 | Customer names: only spellings of the same name are merged (e.g. HP/HPCL, PARADEEP PHOS/PPL); different labels that may be the same company (ADANI, MCF) are NOT merged; joint entries kept together; agent names flagged | Daily reports are typed by hand | Customer-name CSV for NMPA to confirm |
| T15 | APL = Adani Power Ltd (formerly UPCL) | Reconciled with NMPA's PPP disclosure; the label stays APL | ADANI = AWL Agri NOT applied (unresolved) |
| T16 | Waiting reasons grouped by the words port staff wrote (receiver/shipper/cargo not ready; vessel not ready; want of berth; other) | Free-text field | Rule |
| T17 | Foreign/coastal by cargo uses the F/C flag in the daily reports (F = foreign-going, C = coastal) | Confirmed from NMPA's report header and against Ministry totals (about 3.5 points average difference) | Checked |
| T18 | Container lines: the agent named in the daily report stands for the line; the reports catch about a third of container calls | Daily reports | Shown on screen; NMPA's official count used for numbers |
| T20 | The Ministry's annual and monthly reports are not combined for LPG: their LPG/LNG figures do not reconcile (see question 8) | Different definitions | The March gap for crude, POL products and LPG stays |
| T19 | Seasonal pattern called "regular" only if the years agree (median correlation at least 0.4) and the cargo moves in at least 75% of months | Avoids false patterns | Rule |

### Incentive Engine

| # | Assumption / rule | Why | Status |
|---|---|---|---|
| I1 | Wharfage = tonnes x Scale of Rates rate; both this year and last year priced at **today's** rates | Shows the effect of tonnes, not tariff revisions | Labelled on screen |
| I2 | Foreign/coastal split of each cargo's official tonnes uses the share of tonnes on F and C ships in the daily reports | No official foreign/coastal split by cargo | Estimate |
| I3 | Crude: 64% at the SPM (Rs 34.90/t) and 36% at berths (Rs 96.60/t), from the berth recorded for each crude ship in the daily reports | Different rates by place of discharge | Estimate; crude is the largest gap against NMPA's accounts (-14%) |
| I4 | KIOCL iron ore and UPCL coal are removed using their share of the cargo in the daily reports | They have their own billing arrangements | TO CONFIRM how they are billed |
| I5 | Coal other than UPCL is handled at Berth 16 (PPP), so it is not priced at NMPA wharfage | Daily reports show all such coal at Berth 16 | TO CONFIRM that NMPA collects no wharfage on it |
| I6 | Containers: NMPA earns Rs 951 per TEU handled (plus licence fee, indexed) at Berth 14 (confirmed by JSW's filing); estimated with what NMPA booked per laden TEU in 2023-24 (Rs 1,625), because NMPA's statements give laden TEU only | Its accounts; FY24 total TEU 1.96 lakh of which 1.22 lakh laden | TO CONFIRM current indexed royalty and total TEU for 2026-27 |
| I7 | Cargo groups with several different rates (other cargo, other liquids, petrochemicals, cement) are not priced | A single rate would be a guess | Rule |
| I8 | No waiver is deducted for April 2026 onward | The only waiver held (Trade Circular NMPA/TM/2025-26/Gen.2) covered crude and LPG vessels berthed 14 to 31 Mar 2026 | Confirmed by the circular |
| I8b | The March 2026 waiver is assessed with monthly figures for March 2026 | NMPA and Ministry publish monthly figures only; the waiver covered about half the month | Stated on screen |
| I9 | Customer wharfage: fertilizer and chemicals priced at the finished-fertilizer rate | The daily reports do not separate them | Estimate |
| I10 | Scenarios: "per year" = this financial year so far scaled to 12 months (seasonality ignored) | Simple, stated | Labelled |
| I11 | Extra cargo in every scenario is the user's input, never a prediction | No historical evidence of customer response | Rule |
| I12 | Scheme baseline: chosen by a stated method (same months last year; average of the same months over 2-4 complete years; contractual commitment), from NMPA statements; missing months block it (never averaged over); new versions need a reason and keep earlier ones; frozen at approval | Prevents a baseline set low to make a scheme look successful | Rule |
| I14 | Tariff version by date: both NMPA versions are held (old format for 1-6 May 2026; validity from 7 May 2026). All 8 wharfage lines used have the same values in both (old format prints foreign, then coastal) | Checked line by line | Resolved |
| I15 | Eligibility: a benefit can be proposed only on a charge NMPA controls (not Berth 14 containers, Berth 16 coal, Berth 15 Adani Power cargo; KIOCL needs Finance); unresolved customer identities block; benefits cannot be combined unless an approved combination rule is recorded | Avoids offering benefits NMPA cannot give or double benefits | Rule; combination rules TO CONFIRM with NMPA |
| I20 | Scheme market context: New Mangalore against the OTHER 11 major ports (all ports minus New Mangalore), same commodity and months against a year earlier; months without comparable figures are left out. Labelled market context, not the incentive's effect | A simple benchmark, not a counterfactual | Rule |
| I22 | NMPA's own schemes in force (iron ore export rebate to 31 Mar 2027; container vessel rebate to 31 Mar 2027) are in the eligibility rules: a new proposal overlapping one is blocked unless an approved combination rule is recorded | From NMPA's notices | Rule |
| I23 | March 2026 waiver cost = wharfage at the 2025-26 rates on every crude/LPG ship berthed 14-31 Mar 2026 (declaration dates unknown), by berth (SPM or berth) and run; other cargo-related charges not included | Upper estimate | Estimated |
| I24 | VOC comparison uses the same year (2025-26) for both ports; VOC lines charged by volume (KL, cubic metre) are not compared | No assumed densities | Rule |
| I21 | Monthly update is all-or-nothing: the data folder is copied first and restored if any step or check fails; identical files are skipped, so re-running changes nothing. Drafts saved on older data are flagged; approved schemes keep the data version, terms and baseline they were approved on; approved terms change only by an amendment that returns to Traffic review | Reproducible decisions | Rule; tested |
| I19 | Key customers: those making up the first 90% of traced wharfage; warning signs = wharfage down 10%+ on the previous quarter (or status Falling), gone quiet, or 20+ ship-days waiting because the customer was not ready; risk High = a warning sign and 5%+ of traced wharfage | Judgement thresholds | TO CONFIRM with NMPA |
| I18 | Port charge calculator: vessel-related charges from NMPA Scale of Rates Chapter II (port dues p.17, concessions 2.1.2, pilotage slabs p.18-19 with minimums, berth hire p.27-29 per GRT per hour or part thereof with hourly minimums, SPM p.37); wharfage from Chapter III. The ship's GRT, run, type, hours and cargo are user inputs; US$ charges need the RBI reference rate for the day of entry (General Terms iii), entered by the user, never assumed. Charges the tariff leaves blank ('as and when applicable') are listed as not calculated | Published tariff | Estimate until checked against NMPA bills (KPI: calculation accuracy) |
| I18 | Seasonal windows: a quiet month is at or below 90% of an average month of its financial year, over the complete years held, and only for cargos whose years agree (regular pattern). Berth occupancy = share of daily-report days a berth had a ship with cargo (empty berths printed '----' excluded); one year of data; not live availability | Seasonal offers cost less only if cargo is really low then and berths have time | Estimated; Marine / Operations to confirm capacity |
| I17 | Deal desk (customer proposal): the customer's baseline uses the customer's TRACED tonnes in NMPA daily reports (same months last year, recent 3-month run-rate, or a contractual figure); months before Sep 2025 are not covered and block the "same months last year" method. Every proposal is labelled "Draft for internal discussion - not an offer" | Customer-level billing not available | Estimated |
| I16 | Rebate slabs are marginal (each block above the baseline at its own rate), capped by the scheme budget; only "potential" rebates are calculated: accrued, approved and paid need NMPA billing | Clear, auditable definition | Rule |
| I13 | "Cargo not won" = last year's share x this year's all-major-port tonnes, minus NMPA's tonnes | Statistical gap, not proof of customer switching | Labelled on screen |

## 4. Unresolved items and how they are treated

| Item | Evidence needed | Treatment until then |
|---|---|---|
| Daily vessel reports | All 323 originals now held (226 downloaded from NMPA's archive on 6 Nov 2026 with scripts/download_daily_reports.py, with NMPA's permission). Compared field by field with the earlier records: 215 identical, 8 differed in dates or the movements list, 3 in ships/cargo/quantity (16 Oct 2025: Vishva Prerna was loading iron ore pellets for NMDC, not discharging fines; 16 Feb 2026: raw cashew 2,050 t, quantity was missing; 6 Dec 2025: an empty-berth row). The PDF reading is used; earlier copies kept as .json.before_pdf | Resolved |
| Customer identities (ADANI, MCF, PPL(MCF), AW) | NMPA's written confirmation of its report labels, with dates and customer codes | Kept as written, not merged; proposals in `data/customer_identity_proposals.csv` |
| Current indexed container royalty; TEU (incl. empties) for FY 2026-27 year to date | NMPA's royalty schedule / concession terms; official TEU statement for a stated period | Rs 951 is the concession figure, not the confirmed current rate; royalty shown as an estimate |
| Annual vs monthly LPG/LNG (2024-25) | Ministry or IPA reconciliation of definitions, coverage and revisions | March gap kept; not filled by subtraction |

Questions to send, worded for the purpose:
- To NMPA: "Please confirm the customer identities corresponding to the attached daily-report labels, including ADANI, MCF and
  PPL, with applicable dates and customer codes."
- To NMPA: "Please provide the currently applicable indexed container royalty, effective dates, indexation method, minimum-
  guarantee treatment, and actual TEUs handled for FY2026-27 through the latest completed reporting month."
- To the Ministry / IPA: "Please reconcile the April-February 2024-25 monthly LPG/LNG figure with the FY2024-25 annual figure,
  identifying differences in commodity definitions, port coverage and revisions, and provide the compatible March 2025 figure."

## 5. Questions for NMPA (to replace assumptions with facts)

1. Confirm customer names (CSV in Data & checks), including APL = UPCL and ADANI = AWL Agri.
2. Actual wharfage billed by cargo, latest year.
3. Current container royalty per TEU, and total TEU including empties.
4. How KIOCL and UPCL cargo is billed; whether any wharfage is collected on Berth 16 coal.
5. Any incentive, rebate or waiver schemes other than the March 2026 circular; and the income given up under that waiver.
6. The thresholds NMPA would like for alerts (T7, T8, T9, T12, T13).
7. The actual approval hierarchy for incentive schemes.
8. (Ministry, not NMPA) Why the annual report's LPG/LNG for all major ports (20.2 MMT in 2024-25) is much higher than the monthly
   reports' "LPG or LNG" (15.3 MMT for April-February). Until this is known, March is not filled from the annual report.
