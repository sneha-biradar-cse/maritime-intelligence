# 25 — Vessel Intelligence: Data Architecture (ADR-001)

**Status:** Proposed
**Date:** 2026-10-27
**Deciders:** Bhaskar (YellowSense), MPIP dev team; NMPA Traffic Dept / Port Control contact for the data-access items
**Supersedes:** nothing. Extends `21_DATA_AUDIT_REAL_VS_SYNTHETIC.md`, `22_NMPA_VISIT_BRIEFING.md`, `23_DASHBOARD_TAB_GUIDE.md`.

---

## 1. Context

The Vessel Intelligence tab currently shows:

| Widget | Today | Backing |
| :--- | :--- | :--- |
| Vessel Tracker table (name, MMSI/IMO, speed, ETA, delay prob., route risk) | 🟡 SCRIPTED | `nmpa_vessels.VESSEL_FLEET`, 15 hard-coded ships with invented MMSI/IMO; positions from list index |
| Next 15 Arrivals chart | 🟡 SCRIPTED | same fleet |
| Congestion Alerts | 🟡 SCRIPTED | same fleet |
| Route Risk vs Delay scatter | 🟡 SCRIPTED | same fleet |
| Vessel Call Forecast (monthly count) | 🟢 REAL (ML) | `port_cargo_monthly.csv` |
| Real call spacing / stay duration | 🟢 REAL (derived) | Daily Vessel Position (DVP) archive → `vessel_stays.json` |

"Make it real" here means: **every number on the tab can be traced back to a named source record, carries a freshness timestamp, and a model output is only shown if it beats a stated baseline.**

The main finding below is that **most of what the tab needs is already in the DVP archive we have, and we are not using it yet.** Live AIS is only needed for at-sea position, speed and route. It is not needed for ETAs, queues, delay or congestion.

---

## 2. What each widget actually needs

Start from the question each widget answers, then the data, the grain and how fresh it has to be.

| Widget | Question it answers | Minimum data | Grain | Freshness |
| :--- | :--- | :--- | :--- | :--- |
| Port Call Board (replaces Tracker) | Which ships are expected, waiting, alongside? | Expected / anchorage / berthed lists | port call | daily (the DVP is daily) |
| ETA prediction | When will this ship actually arrive / berth? | Declared ETA + actual arrival history (labels) | port call | daily |
| Delay probability | How likely is this ship to wait more than X h before berthing? | Anchorage waits + berthing times + queue state | port call | daily |
| Congestion alerts | Which berths have a real queue right now? | Anchorage list with the stated reason + berth occupancy | berth × day | daily |
| Live position / speed | Where is the ship right now? | AIS position reports | vessel × minute | minutes |
| Route risk | Is the voyage exposed to weather / security / draft risk? | AIS track + risk-zone reference + weather + vessel draft | voyage | hours |
| Vessel call forecast | How many calls next month, by commodity? | Monthly traffic statement | commodity × month | monthly (already real) |

---

## 3. Dataset inventory: what we have and what we don't

### 3.1 HAVE (in `data/`)

| Dataset | Content | Volume / quality (profiled 2026-10-27) |
| :--- | :--- | :--- |
| **DVP raw PDFs** `daily_vessel_position/` | NMPA Traffic Dept "Proceedings of the Operation Meeting", one per day | 288 reports, Sep 2025 to Sep 2026. About 76% of calendar days (about 88% of working days; Sundays not published) |
| **DVP parsed** `daily_vessel_position_parsed/*.json` | 5 sections per day: `berthed`, `anchorage`, `tankers_scheduled`, `expected`, `movements` | In a Jul–Aug 2026 sample of 50 reports: 725 berthed, 141 anchorage, 161 tankers-scheduled, **794 expected**, 643 movement rows |
| **Vessel stays** `vessel_stays.json` | Linked berthing → sailing per vessel/berth | 1,688 stays: 640 `exact`, 642 `date_only`, 406 `unconfirmed_lower_bound` |
| **Vessel registry** `vessel_registry.json` | Normalised name → raw variants, first/last seen | 1,506 names. **273 still carry a leading serial number** ("10 BARROW ISLAND"), and 436 are seen only once. Entity resolution is not finished |
| **Name review queue** `vessel_name_review_candidates.json` | Fuzzy near-duplicates for human review | 107 pairs, none adjudicated |
| **Berths** `berths.csv`, `berth_capacity.csv` | 17 berths: cargo types, max draught, quay length, max DWT, capacity | Official, static |
| **Monthly traffic** `port_cargo_monthly(_v2).csv`, `nmpa_commodity_traffic_2024_2026.csv` | Vessels and tonnes per commodity per month | 54 months; reconciliation target |
| **SOR 2026-27** | Includes the Annexure-II standards: 37 h average turnaround, 7 h average pre-berthing | The baseline that delay KPIs should be judged against |

**Fields the DVP gives per call:** vessel name (free text), run (C = coastal / F = foreign), LOA, draft (expected section only), declared ETA date and time, arrival date, berthing date, cargo plus a D/L marker, quantity (manifest, daily, cumulative, balance), agent, receiver/shipper, preferred berth, ETD, stevedore, the anchorage **reason**, and timestamped berths / sails / shifts events.

#### Two findings from profiling (Jul–Aug 2026 sample, 50 reports)

1. **The `expected` section already holds a real ETA label set.** It lists 181 distinct vessels. 157 of them (87%) were matched to a later actual arrival or berthing. The declared ETA's error has a median of **0 days**, and **84% are within ±1 day**. The median lead time is 3 days, and there is a long tail (a few ships were 7 to 25 days late). This gives two things:
   - The declared ETA is a **strong baseline**. An ETA model only goes on the screen if it beats this baseline.
   - Every past (declared ETA → actual) pair is a training label. We do not need AIS to build an ETA-correction model or a delay model.
2. **Most anchorage waits are commercial, not congestion.** Top stated reasons: *Receiver not ready* (161 row-days), *Shipper not ready* (35), *Want of berth* (about 35, spread across B.8, B.9, B.12, B.13 and B.15), *Non-cargo vessel*, *Non-window vessel*. A congestion alert built on "ships at anchor" would mostly fire on cargo-readiness problems. **Only *want of berth* is port congestion.** This has to be a first-class field.

> Caveat: the matching above uses a quick name-normalisation heuristic on two months of data. Treat the numbers as indicative until they are re-run over the full archive with the resolved vessel IDs.

### 3.2 PARTIAL (we have it, but it isn't usable yet)

| Gap | Why it matters | Fix |
| :--- | :--- | :--- |
| Vessel identity is name-only (no IMO/MMSI) | Every join depends on it; duplicates inflate call counts and split stay histories | Finish normalisation (strip the leading serial), adjudicate the 107 review pairs, assign a surrogate `vessel_id`, then attach IMO when a source provides it |
| 259 distinct raw cargo strings | Each one has to map to a commodity, an SOR line and a traffic-statement heading | One maintained `cargo_alias → commodity_code` table (`historical_calls.traffic_group` is a start) |
| Dates written as `DD/MM` with no year | Long-stay craft show arrival dates from the previous year (for example a tug on 2026-08-01 with arrival "28/09") | Infer the year relative to `report_date` and flag the inference |
| 24% of calendar days missing; 406 stays with no departure | Biases durations and occupancy | Store coverage explicitly; never treat a missing day as "no activity" |
| Free-text berth references ("B.10/11", "13/12", SPM) | Breaks berth-level joins | Normalise to `berth_id` plus a list of alternates |

### 3.3 DON'T HAVE

| Dataset | Needed for | Candidate sources | Access / cost | Priority |
| :--- | :--- | :--- | :--- | :--- |
| **NMPA vessel-call register** (IMO, GRT, ETA/ATA/ATB/ATD, berth, cargo, qty) | Fills every DVP gap, gives an official key, removes scraping | NMPA Port Control / VTMS, or PCS1x | Official ask, already in the visit briefing | **P0** |
| **Vessel master data** (IMO, MMSI, GRT, DWT, type, flag, year built) | Identity, tariff (GRT), capacity, draft checks | NMPA register (best); AIS static messages (IMO, MMSI, dimensions, type); Equasis (free account, manual lookup, no bulk/scraping); S&P / Lloyd's (paid) | Free to paid | **P0** |
| **Live AIS positions** (lat, lon, SOG, COG, nav status, AIS destination/ETA) | Live map, speed, distance-to-go, route risk | aisstream.io (free websocket, community terrestrial coverage, so check Mangalore coverage first); AISHub (free if you share your own receiver feed); a port-side AIS receiver (cheap, about 20–40 nm range); India's National AIS via DG Shipping (government); Spire / Kpler-MarineTraffic / VesselFinder (paid, global) | Free to paid | P2 |
| **Marine weather** (wave height, wind, swell) | Delay features, monsoon pilotage limits | Open-Meteo Marine API (free); IMD / INCOIS | Free | P1 |
| **Tide / channel depth** | Draft-restricted berthing windows | NMPA tide table, INCOIS | Free / ask | P2 |
| **Route-risk reference** (JWC listed areas, UKMTO / IMB advisories) | Route risk score | Public advisories, kept as a slowly changing reference table | Free, manual | P3 |
| **Last / next port of call** | Origin, trade lane | AIS destination (unreliable), PCS1x, agent data | Ask | P3 |

---

## 4. How the data connects

```text
                     ┌──────────────┐  IMO (gold key, when available)
   AIS static ──────▶│    VESSEL    │◀────── NMPA call register / Equasis
   (MMSI→IMO)        │ vessel_id PK │
                     └──────┬───────┘
          VESSEL_ALIAS      │ 1..n               AIS_POSITION (mmsi, ts, lat, lon, sog, cog, status)
  (raw DVP name → vessel_id)│                       │ mmsi → vessel_id
                     ┌──────▼───────┐               │
                     │  PORT_CALL   │◀──────────────┘ (positions inside the approach box
                     │ call_id PK   │                  get attached to the open call)
                     │ vessel_id    │
                     │ declared_eta │ ← first DVP `expected` row  (as-of report_date)
                     │ ata / atb /  │ ← anchorage doa, movements "berths"/"sails"
                     │ atd          │
                     │ berth_id ────┼──────▶ BERTH (berths.csv: draught, LOA, DWT, cargo types)
                     │ commodity ───┼──────▶ COMMODITY (cargo alias → SOR code → traffic heading)
                     │ qty, run C/F │                         │
                     │ agent, rcvr  │                         ▼
                     └──────┬───────┘              MONTHLY_TRAFFIC (reconciliation:
                            │ 1..n                  Σ calls per commodity-month ≈ statement vessels)
                     ┌──────▼───────┐
                     │  CALL_EVENT  │ event_type ∈ {expected, anchored, waiting_reason,
                     │              │   berthed, shifted, sailed}; event_ts; source_report_date;
                     │              │   source_section; confidence
                     └──────────────┘
   DVP_SNAPSHOT (raw, immutable, one per report_date) ──parses into──▶ CALL_EVENT
   WEATHER (grid cell × hour) ──joins on time to──▶ features for PORT_CALL
```

**Keys and how fragile each one is:**

| Join | Key | Risk |
| :--- | :--- | :--- |
| DVP row → vessel | normalised name → `vessel_alias` | **High.** Typos and fleets with similar names (the 8 SANMAR ships are 8 different vessels) |
| AIS → vessel | MMSI → IMO → `vessel_id` | Medium. MMSI can change on reflagging; IMO is permanent |
| Call → berth | normalised `berth_id` | Medium. Multi-berth references, SPM |
| Call → commodity | `cargo_alias` table | Medium. 259 raw strings |
| Expected → actual | `vessel_id` + time window | Medium. The same ship can call twice in a month |
| Calls → monthly statement | commodity heading × month | Low. Use it as a check, not a join |

**The core design decision is bitemporal (as-of) storage.** Every event keeps both *when it happened* (`event_ts`) and *when we learned it* (`source_report_date`). The ETA and delay models must train only on what was known **as of** the prediction date. If they don't, we leak the future: for example, training on an ETA that was corrected two days later.

---

## 5. How the data should flow

```text
BRONZE (raw, immutable)            SILVER (conformed)                    GOLD (serving)
──────────────────────            ──────────────────                    ──────────────
DVP PDFs (by date)        ──▶  call_event (as-of)              ──▶  fact_port_call (one row per call)
parsed JSON + parser_ver  ──▶  vessel / vessel_alias           ──▶  berth_day_occupancy
AIS raw msgs (later)      ──▶  ais_position (deduped, by MMSI) ──▶  anchorage_queue_daily (by reason)
weather pulls             ──▶  weather_hourly                  ──▶  features_eta / features_delay
NMPA register (when given)──▶  (source of truth, overrides DVP)──▶  API: /vessels/calls, /eta, /queue
```

Rules:

1. **Raw data is never edited.** Re-parsing from bronze has to rebuild silver and gold exactly. Version the parser (`parser_version` on every row).
2. **Daily incremental, idempotent.** The archive collector already skips files it has. The pipeline does the same: same input, same output.
3. **Source precedence:** NMPA register > AIS > DVP > inferred. Store the source on every field, not just every row.
4. **Coverage is data.** Keep a `report_calendar` table (date, published?, parsed?). Downstream metrics divide by observed days, not calendar days.
5. **Data-quality gates before gold:** unique `(vessel_id, atb)`; `atb >= ata`; `atd > atb`; stay < 60 days; berth exists; commodity mapped; the monthly vessel count reconciles within ±10% of the official statement, otherwise raise a flag.
6. **Every API payload carries lineage:** `source`, `as_of`, `coverage_pct`, `confidence`. The UI badge (🟢/🟡/🔴) is computed from these fields, not written by hand.

---

## 6. Options considered (storage and processing)

### Option A — Keep JSON/CSV files + pandas (status quo)
| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Zero |
| Scalability | Fine for DVP (about 25–60 rows/day); breaks with AIS |
| Team familiarity | High |

**Pros:** nothing new to learn; works today. **Cons:** no as-of queries, no constraints, joins are re-done in every service, and it can't hold AIS.

### Option B — PostgreSQL (+ TimescaleDB when AIS arrives), daily batch, medallion layers ✅ *recommended*
| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Free (local or a small VM) |
| Scalability | DVP is trivial. Port-area AIS (a few hundred vessels) is well within Timescale's range |
| Team familiarity | Medium; SQL and Python |

**Pros:** keys and constraints enforce the data-quality rules; as-of queries are easy; one source of truth for every tab; the existing `16_TECH_STACK` already names Postgres/Timescale. **Cons:** a migration step; needs a scheduler (cron or a simple Prefect/Airflow flow).

### Option C — Kafka + Spark Streaming (as drawn in `platform_overview`)
| Dimension | Assessment |
|---|---|
| Complexity | High |
| Cost | High (infrastructure and operations) |
| Scalability | Global-AIS scale |
| Team familiarity | Low |

**Pros:** it is the long-term picture if MPIP ever ingests global AIS. **Cons:** it solves a volume problem we don't have. The main data source is one PDF per day.

### Trade-off
Our data volume is tiny and the hard problems are **identity, time and honesty**, not throughput. Option B solves those. Option C adds operational burden for no user-visible gain until there is a paid global AIS feed. Revisit C only when ingest goes above about 1M messages/day or several ports are added.

---

## 7. Decision

1. Adopt **Option B**.
2. Replace the scripted fleet with a **Port Call Board built from the DVP**.
3. Make **declared ETA the baseline** for every ETA and delay model.
4. Separate **commercial waiting from congestion** using the anchorage reason field.
5. Treat AIS as a **later enrichment** (position, speed, route), not a prerequisite.

### What each widget becomes

| Widget | Phase 1 (DVP only, no new data) | Phase 2 (+ NMPA register / vessel master, weather) | Phase 3 (+ AIS) |
| :--- | :--- | :--- | :--- |
| Tracker | **Port Call Board**: expected / waiting / alongside, declared ETA, cargo, qty, LOA, preferred berth, agent. 🟢 REAL, daily | + IMO, GRT, DWT, flag | + live position, speed, distance-to-go |
| ETA | Declared ETA + measured historical bias by agent / cargo / run. Backtested | ETA-correction model (must beat the declared-ETA baseline) | + AIS-based ETA from distance and speed |
| Delay probability | Defined as **P(pre-berthing wait > 7 h)** (the SOR standard). Labels from anchorage → berths. Features: cargo, berth queue, berth occupancy, run, LOA, month | + weather, receiver history | + approach speed anomalies |
| Congestion alerts | **Want-of-berth** queue per berth and wait vs the 7 h standard. Commercial waits shown separately | + tide/draft windows | — |
| Route risk | Rename to **Berthing-fit risk** (draft vs berth max draught, LOA vs quay, DWT vs berth) | + monsoon / sea state | True route risk: AIS track × risk zones × weather |
| Scatter | Wait hours vs berth occupancy | — | — |
| Call forecast | Already real; add reconciliation of DVP call counts vs the monthly statement | — | — |

---

## 8. How a senior data engineer approaches this *before* writing pipeline code

1. **Start from decisions, not datasets.** Who uses this tab (berth planner, Traffic Dept, agent) and what decision does it change? Write a one-line metric contract for each number: definition, unit, grain, source, freshness, owner. "Delay probability" with no definition is not a metric.
2. **Profile what you already have before buying anything.** One afternoon of profiling found a real ETA label set and the waiting-reason field, and both change the plan. Profile volume, null rates, cardinality, key uniqueness, date ranges and coverage gaps.
3. **Set the baseline first.** Declared ETA is about 84% within ±1 day. Any model has to beat it on a backtest, or it doesn't ship.
4. **Settle grain and identity early.** Choose the fact grain (one row per port call) and the entity key (surrogate `vessel_id`, with IMO attached later). Entity resolution is the riskiest part of this project, so handle it by design: humans review fuzzy matches and nothing is auto-merged.
5. **Model time explicitly.** Event time vs knowledge time, timezone (IST), year inference, late-arriving corrections. Leakage-safe training depends on this.
6. **Treat raw data as immutable and every step as replayable.** Version the parsers and allow backfills. You will re-parse when you find a parser bug, and the audit already found one (the Berth 1 substring match).
7. **Write down data contracts and quality tests per source.** Schema, allowed values, freshness SLA. Break the build when a contract fails, instead of letting bad data show up silently on the dashboard.
8. **Reconcile against an independent source.** DVP calls per commodity-month should match the official monthly statement. If they don't, the joins are wrong.
9. **Check legal access and sourcing before engineering.** Scraping public NMPA PDFs is a stopgap. Equasis forbids bulk scraping, and AIS licences limit redistribution. Get sanctioned access (the NMPA register, PCS1x) before building anything production-critical on top.
10. **Size the tech to the data.** One PDF a day doesn't justify Kafka. Choose the simplest stack that enforces correctness.
11. **Design for honesty in the UI.** Lineage, coverage and confidence travel with every payload. Demo data is labelled by the system, not by a presenter's memory.
12. **Plan operations from day one.** Scheduler, freshness monitor (alert if today's DVP is missing), backfill runbook, and an owner for the alias and review tables.
13. **Write it down and get sign-off** (this ADR) before implementation, so scope and definitions don't drift.

---

## 9. Consequences

- **Easier:** the tab becomes mostly 🟢 REAL in Phase 1 with no new data. ETA and delay models have labels. Congestion alerts become defensible. The tariff module gets a clean call table to price.
- **Harder:** we have to maintain the alias tables (vessel and cargo) and the human review queue, and run a Postgres instance plus a scheduler.
- **Revisit:** streaming (Option C) when there is a paid AIS feed or multiple ports; the source-precedence rules once the NMPA register arrives; the 7 h delay threshold after review with Traffic Dept.

---

## 10. Action items

**Phase 0 — Foundations (no new data)**
1. [ ] Write metric contracts for the 7 widgets in section 2.
2. [ ] Run the full-archive profile (all 288 reports): ETA error, match rate, waiting reasons, coverage calendar.
3. [ ] Finish vessel entity resolution: strip leading serials, adjudicate the 107 review pairs, issue `vessel_id`.
4. [ ] Build the `cargo_alias → commodity_code` and `berth_ref → berth_id` tables.
5. [ ] Stand up the Postgres schema: `vessel`, `vessel_alias`, `port_call`, `call_event`, `berth`, `commodity`, `report_calendar`.

**Phase 1 — Real tab from the DVP**
6. [ ] Daily job: collect → parse → `call_event` → `port_call`, with data-quality gates and monthly reconciliation.
7. [ ] Replace `/vessels/` with the Port Call Board API, including lineage fields.
8. [ ] Declared-ETA baseline + bias table; delay model P(wait > 7 h) with a backtest vs the baseline.
9. [ ] Want-of-berth congestion alerts; rename route risk to berthing-fit risk.

**Phase 2 — Enrich**
10. [ ] Follow up with NMPA on the call register / PCS1x (P0 ask).
11. [ ] Vessel master data (IMO, GRT, DWT) from the register or AIS static messages.
12. [ ] Open-Meteo marine weather features.

**Phase 3 — Live**
13. [ ] Check free AIS coverage off Mangalore (aisstream.io / AISHub); decide between that, a port-side receiver and a paid feed.
14. [ ] TimescaleDB `ais_position`; live map and AIS ETA; real route risk.
