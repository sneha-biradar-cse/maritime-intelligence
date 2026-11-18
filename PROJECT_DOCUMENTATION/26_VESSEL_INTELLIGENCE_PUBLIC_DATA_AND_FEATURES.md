# 26 — Vessel Intelligence: NMPA Public Data & What the Tab Can Do

**Date:** 2026-10-27
**Builds on:** `25_VESSEL_INTELLIGENCE_DATA_ARCHITECTURE.md` (ADR-001)
**Users (confirmed):** NMPA **berth planner** and **Traffic Department**

The goal is a Vessel Intelligence tab where every number comes from real NMPA data. This doc covers what NMPA publishes, what each feature for the two users needs, and proposed answers to the open design questions.

---

## 1. What NMPA publishes that is relevant to vessels

The catalogue below was checked on newmangaloreport.gov.in on 2026-10-27.

| # | Dataset | Where on the site | Grain | History available | Format | We have it? |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Daily Vessel Position (DVP)**: berthed, anchorage + reason, tankers scheduled, vessels expected (ETA, draft, LOA, qty, preferred berth), movements | Notifications → Daily Vessel Positions → **Archive** (`/archive-daily-vessel-position`) | vessel × day | **About 1,294 reports, 31 May 2021 → 26 Oct 2026** (65 pages × 20) | PDF, published around noon on working days | Only 288 (Sep 2025 → Sep 2026). **About 4× more history is available** |
| 2 | **Monthly Operational Performance** | Statistics → Operational Performance | cargo class × month | Jan 2021 → Sep 2026 (about 69 months) | PDF | Only Aug 2026 |
| 3 | Monthly commodity-wise traffic | Statistics → Commodity Wise Traffic | commodity × month | Jan 2021 → Sep 2026 | PDF | Yes (`port_cargo_monthly.csv`) |
| 4 | Monthly container traffic | Statistics → Container Traffic | month | Jan 2021 → Sep 2026 | PDF | Aug 2026 only |
| 5 | Berth particulars, berth capacity | Facilities | berth | current | PDF | Yes (`berths.csv`, `berth_capacity.csv`) |
| 6 | Cargo handling equipment, floating craft (tugs, pilot launches), storage | Facilities | asset | current | PDF | No |
| 7 | **Predicted hourly tide, Panambur** | Facilities → Predicted Tidal Data | hour | 2021, 2023, 2025, **2026** | PDF | No |
| 8 | Hydrographic survey charts (approach channel zones II–IV, dumping ground, etc.) | Facilities → Hydrographic Survey Charts | survey | Latest surveys Mar–Apr 2026 | PDF maps | No |
| 9 | **Permissible draft circulars** | Circulars → Marine Dept | berth/channel × effective date | About 35 circulars, Apr 2020 → 14 Aug 2026 | PDF | No |
| 10 | **Berthing Policy for Dry Bulk Vessels** (Gazette notified, Trade Notice 07-04-2026) and priority-berthing notices (fertiliser, domestic coal, wheat, sugar) | Circulars → Traffic Dept | rule | 2020 → 2026 | PDF | No |
| 11 | Weather advisories, monsoon preparedness, cyclone SOP (for example, Local Cautionary Signal III hoisted 16-07-2024) | Circulars → Marine / Traffic | event | 2021 → 2026 | PDF | No |
| 12 | Berth maintenance / availability notices (for example, Berth 2 unavailable 01-04-2026 → 15-05-2026) | Circulars → Traffic Dept | berth × period | 2020 → 2026 | PDF | No |
| 13 | Administration Reports (annual) | Notifications → Reports | year | 2015-16 → 2024-25 | PDF | No |
| 14 | Citizen Charter 2026-27 (service standards) | Citizen's Corner | — | current | PDF | No |
| 15 | Scale of Rates 2026-27 | Port Tariff | — | current | PDF | Yes |

### 1.1 Monthly Operational Performance is official ground truth

The Aug 2026 report (already in `nmpa_public_data/`) gives the following, each split by cargo class (dry bulk conventional/mechanical, break bulk, liquid bulk, container), for the month and year-to-date, with the previous-year comparison:

- vessels handled
- **average pre-berthing detention, split into "Port Account" and "Other than Port Account"**
- average turn-round time in hours (pilot boarding to de-boarding)
- % idle time at berth
- average output per berth-day
- container dwell time

Aug 2026 example: overall pre-berthing detention was 0.88 days, of which only **0.08 days was on Port Account** and 0.80 days was other causes. Turn-round time was 42.2 h and idle time 17.6%.

This matches what we found in the DVP anchorage reasons ("receiver not ready" dominates). NMPA itself separates port-caused waiting from user-caused waiting, so **our delay and congestion metrics should use the same split.** These monthly figures are also the reference our DVP-derived KPIs must reconcile against.

### 1.2 Not published by NMPA (still needs an official ask or another source)

- IMO / MMSI / GRT per vessel
- live positions
- the VTS log
- the internal berth plan
- actual pilot boarding times per vessel

Outside NMPA:

- **MoPSW Basic Port Statistics** (annual, benchmarking against other major ports)
- **Open-Meteo Marine** and **INCOIS** (sea state)
- **AIS** (see ADR-001)

---

## 2. What the tab can do for the berth planner and Traffic Dept

Every feature below uses public NMPA data only, unless it is marked otherwise.

| # | Feature | Who | Question it answers | Data | How it works |
| :- | :--- | :--- | :--- | :--- | :--- |
| F1 | **Port Call Board** (replaces the scripted tracker) | both | What's expected, waiting and alongside today? | DVP (all 5 sections) | Latest report parsed into one row per vessel, with status, berth, cargo, qty, agent, waiting reason and hours waiting. "As of" date shown |
| F2 | **Arrival outlook (next 7 days)** | berth planner | How many ships arrive per day and per berth group? | DVP expected section + ETA history | Declared ETAs bucketed by day, with a reliability band from historical ETA error (about 84% within ±1 day in the Jul–Aug sample) |
| F3 | **Berth completion / ETD forecast** | berth planner | When will each berth free up? | DVP berthed section: `qty_balance`, `qty_day` + output-per-berth-day history | Remaining days = balance ÷ (recent daily rate, or the historical rate for that cargo and berth). Checked against the actual "sails" events |
| F4 | **Berth conflict / queue forecast** | berth planner | Which berth will have a queue in the next 72 h? | F2 + F3 + preferred berth + maintenance notices + permissible draft | Expected demand per berth vs predicted free time; alert when two or more vessels compete for one berth window |
| F5 | **Pre-berthing wait prediction** | both | How long will this ship wait, and why? | DVP history 2021–2026 (anchorage → berths) | Model of P(wait > threshold), split into Port-Account vs other causes. Baseline = historical median for that cargo and berth |
| F6 | **Draft & tide fit check** | berth planner | Can this vessel enter or berth at its declared draft, and when? | DVP expected `draft`, `loa` + permissible-draft circulars + hourly tide table + berth max draught/LOA | Rule check: vessel draft vs permissible draft at the preferred berth. If it only fits at high water, show the tide windows |
| F7 | **Priority & policy view** | Traffic Dept | Which waiting vessels qualify for priority or a window under current policy? | Berthing policy + priority-berthing notices + DVP anchorage ("window / non-window vessel") | Encode the policy rules and flag eligible waiting vessels. Advisory only, no automated decisions |
| F8 | **Performance monitor** | Traffic Dept | Are we on track for turn-round time, pre-berthing and idle-time norms? | Monthly Operational Performance 2021–2026 + DVP-derived daily KPIs | Official monthly series plus a daily nowcast from the DVP; flag when the nowcast drifts from the official figures |
| F9 | **Waiting-cause analytics** | Traffic Dept | Who or what causes waiting? | DVP anchorage reasons, receiver/shipper, agent | Waiting hours by reason / receiver / cargo / berth, and ETA accuracy by agent. Internal use only (commercially sensitive) |
| F10 | **Weather & disruption overlay** | both | Did weather or a closure drive this delay? Is a disruption coming? | Weather advisories + monsoon circulars + Open-Meteo marine forecast | Advisory periods become event flags on the timeline; forecast wave height becomes a feature for F5 |
| F11 | Vessel call forecast (existing) | Traffic Dept | How many calls next month? | Monthly traffic | Already 🟢 REAL |

**Remove or rename:**

- **"Route risk":** no voyage data exists. Replace it with F6, a berthing-fit risk.
- **Live map:** only add it back with AIS (Phase 3 in ADR-001).

---

## 3. Proposed answers to the open questions (defaults to confirm with Traffic Dept)

| Question | Proposed default | Why |
| :--- | :--- | :--- |
| Decision supported | Next-72-h berth sequencing (planner); monthly performance review and waiting-cause follow-up (Traffic Dept) | These are what F1–F9 serve |
| Refresh cadence | Daily, after the DVP is published (about 12:00–13:30 IST). Monthly for the performance reports (published around the 5th–7th) | Matches when the source data is released; nothing is fresher |
| Unit of analysis | One **port call** = vessel + arrival at NMPA (spans anchorage → berth(s) → sail) | Shifting between berths stays within one call |
| "Delay" | **Pre-berthing detention** = arrival at anchorage → berthing. Reported both in total and split into Port Account / Other, matching NMPA's monthly report | Uses NMPA's own definition, so our numbers can be reconciled with theirs |
| Delay threshold for alerts | Wait > 24 h for Port-Account reasons (want of berth). Other reasons are shown but don't raise a congestion alert | Aug 2026 Port-Account average was 0.08 days, so 24 h is clearly abnormal. Tune with the planner |
| Turn-round time | NMPA definition: pilot boarding → de-boarding (hours). We can only approximate it from DVP arrival/sail times, so label it "approx." | Pilot times are not public |
| ETA accuracy target | Model must beat declared ETA on mean absolute error over a 2025-26 hold-out | Declared ETA is already good |
| Where numbers must reconcile | Monthly vessels handled, pre-berthing and turn-round time vs the official Operational Performance report, within ±10% | Independent official check |
| Who owns corrections | YellowSense team maintains the vessel-name and cargo alias tables; Traffic Dept is the contact for disputed figures | Needs to be agreed with NMPA |

---

## 4. Data connections (public-data version)

```text
DVP (daily, 2021→)                     Circulars (event-dated)          Facilities / Stats
 ├ expected ──▶ PORT_CALL.declared_eta, draft, loa, qty, pref_berth
 ├ anchorage ─▶ CALL_EVENT(anchored, reason → port_account? Y/N)
 ├ berthed ───▶ CALL_EVENT(berthed), qty_day/total/balance ─▶ F3
 ├ tankers ───▶ CALL_EVENT(scheduled)
 └ movements ─▶ CALL_EVENT(berths/shifts/sails, exact time)
                                    Permissible draft ─▶ BERTH_DRAFT(berth, max_draft, valid_from, valid_to)
                                    Berth maintenance ─▶ BERTH_AVAILABILITY(berth, from, to)
                                    Berthing policy   ─▶ PRIORITY_RULE(cargo/condition → priority)
                                    Weather advisory  ─▶ DISRUPTION_EVENT(type, from, to)
 Tide table ─────────────────────────────────────────▶ TIDE(hour, height)
 Berths / capacity ──────────────────────────────────▶ BERTH(max_draught, LOA, DWT, cargo types)
 Monthly Operational Performance ────────────────────▶ OFFICIAL_KPI(month, cargo_class, metric, value)
                                                              ▲ reconcile
 Gold layer: fact_port_call ─▶ daily KPIs ────────────────────┘
```

Join keys for the new tables:

- `berth_id`: normalise "B.10/11", "14W", "SPM".
- dates: circulars are joined by validity period.
- `cargo_class`: map commodity → NMPA's 5 classes (dry bulk conv / mech, break bulk, liquid bulk, container) to reconcile with the official KPIs.

---

## 5. Sourcing notes and risks

- **Usage terms.** NMPA's copyright policy says material provided for download may be downloaded without specific permission; any other use needs approval from the NMPA directorate. Collect politely: once a day, rate-limited, keeping the originals. Keep asking for sanctioned access (vessel-call register, PCS1x), as in doc 22.
- **The format changes over time.** 2021 DVP PDFs are about 60 KB vs about 255 KB now, so the layout changed. Expect one parser template per era, plus spot-checks before trusting 2021–2024 history.
- **Circular PDFs not yet read.** The permissible-draft tables and the berthing-policy rules were catalogued from their titles only, because the research tool couldn't open those PDFs. Someone on the team needs to read them before encoding F6/F7.
- **Commercial sensitivity.** F9 names receivers and agents. Keep it internal to NMPA users.
- **Coverage gaps.** No DVP on Sundays/holidays; treat missing days as unknown, not as zero activity.

---

## 6. Next steps (ordered)

1. [ ] Back-fill the DVP from the official archive (31 May 2021 → today). Build a coverage calendar and per-era parser templates.
2. [ ] Download and parse the 69 monthly Operational Performance reports into `OFFICIAL_KPI`.
3. [ ] Read and tabulate the permissible-draft circulars, the dry-bulk berthing policy and the priority notices.
4. [ ] Load the 2026 hourly tide table.
5. [ ] Build F1 (Port Call Board) and F8 (Performance monitor) first. Both are pure data with no ML, and they are the fastest way to a fully real tab.
6. [ ] Then build F3, F2 and F4 (planner features), then F5 (wait model) and F6 (draft/tide fit).
7. [ ] Show F1 + F8 to Traffic Dept and confirm the defaults in section 3.
