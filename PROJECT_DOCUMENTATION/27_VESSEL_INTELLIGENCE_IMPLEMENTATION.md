# 27 — Vessel Intelligence: Implementation (real NMPA data)

**Date:** 2026-10-27
**Builds on:** `25_VESSEL_INTELLIGENCE_DATA_ARCHITECTURE.md` (ADR-001) and `26_VESSEL_INTELLIGENCE_PUBLIC_DATA_AND_FEATURES.md`
**Users:** NMPA berth planner and Traffic Department
**Status:** Implemented. All 86 tests pass. Ready for review and reverse engineering.

The Vessel Intelligence tab no longer shows the scripted 15-ship demo fleet. Every number now comes from one of two places:

- NMPA's **Daily Vessel Position (DVP)** reports.
- NMPA's **monthly Operational Performance** report.

Each payload carries a lineage block (source, as-of report, coverage, method, status). Model outputs appear only next to their backtest.

---

## 1. What changed, file by file

| File | New / changed | What it does |
| :--- | :--- | :--- |
| `data/reference/vessel_intel_reference.json` | new | **All human-editable rules**: waiting reason → Port / Other account, cargo-text → NMPA cargo class, mechanical berths, single-purpose berth defaults, alert thresholds, linking tolerances |
| `data/reference/permissible_draft.csv` | new (empty template) | Fill in from NMPA "Permissible draft" circulars → the berthing-fit check uses it instead of `berths.csv` |
| `data/reference/tide_panambur.csv` | new (empty template) | Hook for NMPA's predicted hourly tide table (not used yet) |
| `backend/app/services/vi_reference.py` | new | Loads the rules file; field parsers (`DD/MM` dates with year wrap, `HH:MM` / AM / PM, quantities, container boxes, NMPA's "0.87 Day" waiting clock); berth normalisation; vessel-name clean-up |
| `backend/app/services/vi_port_calls.py` | new | **Conformed layer.** DVP JSON → observations → movements (programme vs actual) → **port calls** (one row per ship visit). Exports `data/derived/port_calls.csv` and `report_calendar.csv` |
| `backend/app/services/vi_official_kpis.py` | new | Parses NMPA's monthly Operational Performance PDFs → `data/official/operational_performance.csv` |
| `backend/app/services/vi_features.py` | new | Features F1–F9 with backtests (section 4) |
| `backend/app/routes/vessels.py` | changed | New `/vessels/intel/*` endpoints. Legacy `/vessels/`, `/eta` and `/congestion-alerts` are kept for the Executive tab and labelled DEMO |
| `backend/app/main.py` | changed | Warms the caches in a background thread at start-up |
| `frontend/app.py` (Streamlit) | changed | Vessel Intelligence tab rebuilt with six sub-tabs. The real monthly vessel-call forecast panel is kept |
| `frontend/app.js` (web UI) | changed | `renderVessels()` rebuilt on the same endpoints |
| `scripts/update_vessel_intel_data.py` + `.bat` | new | Daily collector: DVP archive listing → download → parse → monthly reports → rebuild |
| `tests/test_vessel_intel.py` | new | 41 tests: parsers, a synthetic 5-day archive with known answers, and real-archive checks including reconciliation with NMPA's official numbers |

Nothing else was modified. The cargo, tariff and routing modules are untouched, and the existing 45 tests still pass.

---

## 2. Data flow

```text
newmangaloreport.gov.in
 ├─ /archive-daily-vessel-position  (1,294 PDFs, May 2021 →)  ──► data/daily_vessel_position/*.pdf
 │                                                              └► vessel_position_parser.py ► data/daily_vessel_position_parsed/*.json  (288 today)
 └─ /statistics  "Operational Performance" (monthly PDF)       ──► nmpa_public_data/operational_performance/*.pdf
                                                                    └► vi_official_kpis.py ► data/official/operational_performance.csv

vi_port_calls.py  (silver / gold)
  observations   one row per vessel row per report (berthed / anchorage / tankers / expected), normalised
  movements      programme lines + post-operation changes, de-duplicated across revisions
  port_calls     expected → anchorage → berth(s) → sailed   ► data/derived/port_calls.csv

vi_features.py   F1 board · F2 arrivals/ETA · F3 departure · F4 berth plan · F5 wait model · F6 fit · F8 performance · F9 waiting
routes/vessels.py  /vessels/intel/*   ► Streamlit tab + web tab
```

Caches are keyed on the archive fingerprint (file count + newest mtime, re-checked every 30 s). New reports are picked up without a restart. `POST /vessels/intel/refresh` clears everything, including after you edit the reference JSON.

---

## 3. How a port call is built (the part to review first)

**Unit = one ship visit.** The key is (vessel, arrival date). This matches NMPA's own KPIs, which count a vessel when it sails. A shift between berths stays inside the same call.

1. **Vessel identity.** `normalize_vessel_name()` (existing) runs first. Then we strip a serial number glued to the front ("10 BARROW ISLAND") and a run code glued to the end ("MSC MANASA F"). Look-alike names are **never** merged automatically. The 107-pair human review queue is unchanged.
2. **Arrival clusters.** Anchorage, tankers-scheduled and berthed rows each print an arrival date. Rows of one vessel whose arrival dates are within 1 day of each other, and that are seen within 15 days of each other, form one call.
3. **Movement lines — an important finding.** The "Movements" block in report D is NMPA's **berthing programme**: what the morning operations meeting planned from ~10:00 onwards, often 1–3 days ahead. It is not a log of what happened. The "Post-operation changes" block is the record of what actually happened.
   - The same event is revised across reports (for example 20:00 → 22:00).
   - We keep the **last revision issued before the event**, or the post-operation change if one exists.
   - Programme lines still in the future (relative to the newest report) are never used as actual times.
   - The existing `vessel_stay_duration.py` treats programme lines as actual times; it should get the same fix later.
4. **Calls seen only in the programme.** Some ships berth and sail between two daily snapshots. We create those calls from the programme lines. Their arrival time and wait are **unknown, not zero**.
5. **Expected → arrival.** Each run of "Vessels Expected" appearances is one expectation. A new one starts after a gap of more than 6 days, after the ship has been seen in port, or when the ETA jumps by more than 4 days. The **first** declared ETA is kept, because that is what the planner knew at the time. It is matched to the earliest arrival in [first seen − 2 d, ETA + 10 d].
6. **Derived times and precision.**
   - Arrival = DOA + clock time from the anchorage list (exact). If there is none, the arrival date at 12:00.
   - First berthing = programme/actual movement, else the berthed-list date.
   - Departure = last sailing event.
   - Every field carries a precision value (`exact` / `half_day` / `date` / `assumed_at_berthing`) and a basis.
7. **Waiting split (Port account vs Other).** Each anchorage row's reason is mapped by the rules file. The wait is split in proportion to the days each reason was printed. NMPA's monthly report uses the same two buckets.
8. **Report time.** NMPA prints its own waiting clock next to DOA + time. Arrival + waiting = report time, so the report is "as of" about **10:01 IST**. This is measured from the archive, not assumed.

Flags are kept, never hidden. Counts in today's archive:

| Flag | Calls |
| :--- | ---: |
| `no_sailing_event_in_archive` | 616 |
| `movement_only_call` | 253 |
| `expected_but_no_arrival_found` | 207 |
| `arrival_date_inferred_from_berthing_date` | 174 |
| `left_from_anchorage_without_berthing` | 110 |

**To trace any call:** `GET /vessels/intel/calls/{call_id}` returns every source row and movement used to build it. The Streamlit tab has the same view under "Trace a vessel".

---

## 4. Features and their honest results

Results below are on the archive as loaded: 288 reports, 2025-09-01 → 2026-09-15, 88.3% of working days.

| # | Feature | Method | Validation result |
| :- | :--- | :--- | :--- |
| F1 | **Port Call Board**: alongside / waiting / expected / NMPA programme, alerts | The report of the selected date, normalised and enriched | Same rows as the PDF; replay any past date with `as_of` |
| F2 | **Arrival outlook + ETA band** | Each declared ETA spread by the empirical error distribution of its trade × cargo class | Declared ETA is within ±24 h for **82.2%** of 1,460 arrivals; median error 6.0 h. A learned correction did **not** beat NMPA's ETA, so the ETA is used unchanged and only widened into a band |
| F3 | **Departure forecast** | Best of: NMPA ETD + learned time-of-day offset → balance ÷ handling rate → typical stay. The ranking is learned from past days only | Mean error **12.0 h** vs 12.7 h for NMPA's ETD as printed, and 21 h / 22 h for the rate and stay methods (1,910 vessel-days). In plain words: NMPA's own ETD is the best predictor; we add a time of day and fallbacks |
| F3* | NMPA programme sailing time | Shown, not ranked | Can only be scored on 107 non-circular points (mean error 11.1 h). 1,025 points were excluded because the "actual" time is itself that programme line |
| F4 | **Berth plan / conflicts** | Calls already in NMPA's programme are placed first at their programmed berth/time. The rest follow FIFO over stated berth preferences, skipping berths the vessel does not fit; service time = median stay for the class at that berth | Rule-based planning aid — no accuracy claim. Ignores priority policy, tide and pilots |
| F5 | **P(wait > 24 h)** for expected vessels | HistGradientBoosting on features known before arrival: class, trade, LOA, qty, season, queue state in the last report. Chronological 70/30 split | AUC 0.664 vs base rate 0.630; Brier 0.2117 vs 0.2118 — **only marginally better**. The code switches to the base rate automatically whenever the model stops beating it |
| F5b | **Likely more wait** for vessels already waiting | Empirical: how much longer did past vessels wait, given the same reason type, class and time already waited | n is shown per row |
| F6 | **Berthing fit** | Declared draft and LOA vs berth limits; permissible-draft circulars when loaded | Rule check; uses `berths.csv` design draught until `permissible_draft.csv` is filled |
| F8 | **Performance vs NMPA official** | Same KPIs rebuilt from the DVP and compared with the monthly report | See section 5 |
| F9 | **Waiting analytics** | Month, reason, berth (port account), receiver (internal) | Derived |

---

## 5. Validation against NMPA's own published numbers (August 2026)

This is the strongest evidence that the stitching works. None of these numbers was tuned to match, except the mechanical-berth rule noted below.

| Class | Metric | NMPA official | Rebuilt from daily reports | Verdict |
| :--- | :--- | ---: | ---: | :--- |
| Overall | Vessels handled | 107 | 102 | matches |
| Overall | Pre-berthing detention, total (days) | 0.88 | 0.87 | close |
| Overall | Pre-berthing, Port Account (days) | 0.08 | 0.10 | close |
| Overall | Pre-berthing, other (days) | 0.80 | 0.69 | close |
| Liquid bulk | Vessels handled | 58 | 62 | matches |
| Liquid bulk | Pre-berthing total / Port Account (days) | 1.22 / 0.04 | 1.13 / 0.05 | close |
| Dry bulk total | Vessels handled | 27 | 28 | matches |
| Dry bulk total | Port Account (days) | 0.23 | 0.23 | close |
| Container | Vessels handled | 16 | 8 | **under-detected** |
| Overall | Turn-round (h) | 42.2 | 50.7 (time at berth, proxy) | close |

Notes:

- **Mechanical vs conventional dry bulk** is calibrated. Treating Berths 8, 15 and 16 as mechanical reproduces NMPA's 17 / 10 split (we get 18–19 / 9–10). The `berths.csv` labels alone gave 10 / 17. This is in the rules file with the reasoning; please confirm with Traffic Dept.
- **Container calls are under-detected.** Most container calls at the PPP Berth 14 last less than a day and rarely appear in either the 10:00 snapshot or the programme. Container counts and waits from the DVP are not reliable.
- Only one official month is loaded (August 2026; the PDF also gives August 2025). Running the collector loads all months from January 2021, and the reconciliation then covers every overlapping month automatically.

---

## 6. API (all GET unless noted; `as_of=YYYY-MM-DD` replays any report day)

| Endpoint | Returns |
| :--- | :--- |
| `/vessels/intel/overview` | Board summary, alerts, model cards |
| `/vessels/intel/board` | F1 lists + NMPA programme |
| `/vessels/intel/arrivals?days=7` | F2 per-day outlook + per-vessel band |
| `/vessels/intel/eta-accuracy` | F2 backtest, error histogram, by agent (internal) |
| `/vessels/intel/departure-backtest` | F3 method comparison |
| `/vessels/intel/berth-plan?horizon_h=72` | F4 timeline, sequenced, conflicts |
| `/vessels/intel/wait-model` | F5 model card |
| `/vessels/intel/berthing-fit` | F6 |
| `/vessels/intel/performance` | F8 reconciliation + monthly series |
| `/vessels/intel/waiting?months=12` | F9 |
| `/vessels/intel/data-quality` | Coverage, gaps, flags, reason mapping, unclassified cargo |
| `/vessels/intel/calls?q=` and `/vessels/intel/calls/{id}` | Search, and full trace of one call |
| `/vessels/intel/report-dates` | Dates available for replay |
| `POST /vessels/intel/refresh` | Clear caches |

---

## 7. How to run

```bash
pip install -r requirements.txt                      # no new dependencies
python scripts/update_vessel_intel_data.py           # fetch new reports since the last one, parse, rebuild
python scripts/update_vessel_intel_data.py --all     # optional: back-fill DVP from May 2021 + all monthly reports
uvicorn backend.app.main:app --port 8000
streamlit run frontend/app.py                        # tab "Vessel Intelligence"
pytest tests/test_vessel_intel.py -q
```

The loaded archive ends on **2026-09-15**. The tab says so and shows a freshness alert until the collector is run. The collector could not be run from the build environment, because outbound access to NMPA's site was blocked there. Run it on your machine. 2021–2023 reports use an older, smaller PDF layout, so watch the parser's failure list on the first `--all` run.

---

## 8. Known limitations (say these out loud in a demo)

1. **No live position, speed or route.** Those need AIS (ADR-001, Phase 3). The live map remains a demo on the Executive tab only.
2. **No actual sailing/berthing log is published.** "Actual" times are NMPA's last programme revision before the event, or a post-operation change. The KPI reconciliation shows this is good at the monthly level.
3. **Snapshot sampling misses short calls** (most container calls). Counts are reconciled, not assumed.
4. **24% of calendar days are missing** (Sundays and holidays, plus some unpublished days). Durations next to gaps are lower bounds and are flagged.
5. **Berth plan** ignores priority-berthing policy, tide windows, pilots and tugs. Encoding the April 2026 dry-bulk berthing policy and the priority notices is the next step (doc 26 §5).
6. **Permissible-draft circulars and the tide table are not loaded yet.** The templates are in `data/reference/`.
7. **The wait model is only marginally better than the base rate.** It is kept because it switches itself off when it stops helping.

---

## 9. Review checklist (reverse-engineering order)

1. Open `data/derived/port_calls.csv` and pick 3 vessels you know. Trace each with `/vessels/intel/calls/{id}` against the original PDFs.
2. Read `vessel_intel_reference.json`. Is every reason → account mapping right? Is the mechanical-berth calibration right?
3. Read `vi_port_calls._resolve_movements` and `_derive_call`. Are the programme-vs-actual and wait-split rules acceptable?
4. Run the tests: `test_synthetic_call_stitching` is the executable specification of a call.
5. Check the Performance sub-tab after loading more monthly reports. Do the verdicts stay "close"?
6. Decide the open defaults with Traffic Dept: 24 h port-account alert, 72 h long-wait alert, 72 h plan horizon.
