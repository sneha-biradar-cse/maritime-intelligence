# 22 — New Mangalore Port Authority Visit Briefing

Questions, data asks, and an honest project status report, prepared for an in-person visit to NMPA.
See `22_NMPA_VISIT_BRIEFING.pdf` for the presentation-ready, one-question-per-page version.

---

## Q1 — Their business runs on tariffs. How does that affect our project?

**What NMPA's business actually is.** NMPA is a Major Port Authority operating entirely on a
government-regulated Scale of Rates (SOR) — currently the 2026-27 SOR, effective 01 May 2026 to
30 Apr 2027. It covers vessel-related charges (port dues, berth hire, pilotage, anchorage, tug hire,
shifting) and cargo-related charges (wharfage across 60+ commodity lines, container box rates, transit
storage). Rates are ceiling levels set under the Tariff Authority for Major Ports (TAMP) framework and
re-indexed every 1 May to 60–100% of the Wholesale Price Index (WPI).

**Why this matters directly to us.** Our Port Cost Estimator is the one module that actually touches
NMPA's real commercial business. Our forecasting/analytics screens are advisory; a cost estimate is
something an agent or shipper could act on — accuracy isn't optional here.

**What we've already built.** Wharfage, berth hire, port dues, pilotage, anchorage, tug hire, shifting,
and transit storage are all transcribed directly from the published SOR — e.g. crude-via-SPM wharfage
(₹34.89 coastal / ₹34.90 foreign per MT) and dry-bulk berth hire (₹0.07602/GRT/hr coastal, ₹262.83/hr
minimum) match the SOR line-for-line.

**Where we're still exposed.**
- Static table, manual yearly refresh — the SOR re-indexes every 1 May.
- A few components have no fixed numeric rate in the SOR itself (cruise composite charges, container
  scanning, LDB mandatory user charges) — "as per separate order."
- Zero real invoices to check our math against.

**Ask them:** Do you keep the SOR in structured/spreadsheet form, or only as PDF? Could billing
sanity-check a few sample cost estimates against a real invoice? Who owns the annual WPI re-indexation
notice?

---

## Q2 — Which APIs do we actually need, and which can NMPA realistically give us?

Separate what NMPA generates/owns from what NMPA merely consumes from someone else — only ask for the
former.

**Likely theirs to give:**
- Vessel-call register (arrival / berth / departure per ship, IMO number, cargo handled) — HIGH VALUE,
  almost certainly exists internally for Port Control / berth planning.
- Live/periodic berth occupancy status.
- Structured tariff feed (removes our manual PDF transcription).
- Circulars & Trade Notice feed (we already scrape the public page; ask if an API/RSS exists instead).

**Probably not theirs to give:**
- Cargo manifest / import-export documentation — that's Customs (ICEGATE).
- Live global AIS — that's a commercial vendor's product (see Q3 for the in-harbour alternative).
- Commodity market prices / trade-lane statistics — DGCIS / World Bank, not the port.

**Ask them:** Does Port Control keep a structured vessel-call log? Is there an RSS/API for the Circular
& Trade Notice page? Who's the right contact — Traffic, IT, or Harbour Master's office?

---

## Q3 — We're missing AIS and currently download vessel data by hand. What should we actually ask for?

**Where we are today.** Our "live vessel" screen is a fixed, scripted 25-ship list — not live, not
historical. Getting anything real today means looking up vessels one at a time by hand.

**Why we shouldn't just buy commercial AIS.** MarineTraffic/Spire-grade AIS is a paid subscription, and
most of what it would show — ships already inside NMPA's harbour limits — is redundant with data the
port already collects via its own Vessel Traffic Management System (VTMS) / Port Control.

**The actual ask, reframed.** Not "give us AIS," but: can Port Control / VTMS export the vessel-call log
it already keeps — vessel name/IMO, ETA/ATA, berth assigned, ATB, ATD, cargo type and quantity. Even a
periodic bulk CSV/Excel extract (not live streaming) would be transformative for real stay-duration and
berth-occupancy modeling.

**Secondary ask.** 2–3 years of historical vessel-call data (redacted if needed) to backtest a real
turnaround-time model and validate it against NMPA's own committed performance standard — 37-hour
average vessel turnaround, 7-hour average pre-berthing time (SOR Annexure-II).

**Ask them:** Does Port Control / VTMS maintain a per-vessel call log? Could a historical bulk extract be
shared for a student/research project? Who's the right department?

---

## Q4 — Beyond an API, what else could NMPA help with?

- **Validation, not just data** — a few minutes from ops/billing eyeballing our cost estimates is cheaper
  than any dataset and directly de-risks our highest-stakes module (Q1).
- **Domain review of assumptions** — our what-if simulator's elasticities (vessel-arrival shift %, demand
  shift %, weather-delay days) are documented assumptions, not fitted; 20 minutes with a traffic/planning
  officer would help.
- **PCS1x (Port Community System)** — ask whether NMPA participates and whether a student/research
  integration is possible; could be a single doorway to several Q2/Q3 asks at once.
- **A named point of contact** — for the annual tariff re-indexation and for follow-up if the platform is
  demoed internally.
- **Digital / "Smart Port" initiatives** — ask if there's a digital transformation cell (many major ports
  have one under Sagarmala) — the natural home for a student project like ours.

**Ask them:** Could ops/billing sanity-check our cost estimates? Does NMPA participate in PCS1x? Is there
a Smart Port / digital cell we should be talking to?

---

## Project Status, Part A — What's genuinely real today

- **Cargo forecasting** — RandomForest on 1,354 real monthly NMPA commodity-traffic records
  (2021–2026), backtested out-of-sample (WAPE ≈ 17%, ≈ 83% accuracy). Real and validated.
- **Vessel-call forecasting & anomaly detection** — same real dataset, RandomForest / IsolationForest.
  Anomaly detection is real ML but unsupervised, no labeled ground truth.
- **Port cost estimator** — real SOR-derived tariff data, not yet checked against a real invoice.
- **Berth/facility routing** — real `berths.csv`/`berth_capacity.csv` NMPA data; our own audit caught and
  fixed a substring-matching bug that had silently misrouted crude/LPG/coal/containers to Berth 1.
- **NMPA Circulars & Trade Notices** — not yet built, but confirmed scrapable from the public site with
  no NMPA dependency.

## Project Status, Part B — What's blocked, and why

- **Vessel stay duration / berth occupancy prediction — BLOCKED.** Only monthly aggregated tonnage
  exists in our data; no per-vessel dwell-time signal. Solvable only via the Q3 vessel-call-log ask.
- **Real-time AIS — BLOCKED.** Cost (paid subscription) and redundancy (NMPA's own VTMS already has it).
  Solvable via Q3, or relabeled honestly as simulated.
- **Trade intelligence (lanes/prices/"opportunities") — BLOCKED, but not on NMPA.** No
  origin/destination or price dataset exists; currently randomly generated per request. Solvable via
  DGCIS/World Bank, independent of this visit.
- **Digital twin, executive KPIs, AI copilot, security/SOC module — NOT YET REAL.** Fully synthetic,
  including fabricated revenue and a fake `"postgresql_records": 847203` figure. Needs real data or
  honest "simulated" labeling.
- **What-if scenario simulator — mechanism real, calibration missing.** Elasticities are assumed, not
  fitted — same root cause as the vessel-stay gap: no real congestion/delay dataset to calibrate against.

---

## Cheat sheet — what to literally ask on the day

**Must-ask**
1. Does Port Control / VTMS keep a per-vessel call log? Could a historical bulk extract be shared?
2. Is there a digital transformation / Smart Port / PCS1x integration point we should be talking to?
3. Could billing/operations sanity-check a handful of our cost estimates against a real invoice?

**Nice-to-ask**
- Is the SOR maintained in structured form anywhere, or only as PDF?
- Is there an RSS/API for the Circular & Trade Notice page?
- Who owns the annual WPI re-indexation announcement each 1 May?
- Could a traffic/planning officer review our what-if simulator's assumptions?

**What not to ask NMPA for — redirect elsewhere**
- Global AIS / MarineTraffic-grade live positions (commercial vendor).
- Trade-lane and commodity-price data (DGCIS / World Bank).
- Import-export cargo manifests (Customs / ICEGATE).
