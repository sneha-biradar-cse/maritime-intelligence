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

## Q3 — We're missing live AIS. What should we actually ask for?

**Where we are today.** Our live-tracking screen is still a fixed, scripted fleet list, not real AIS. But
we no longer rely on looking vessels up by hand: we built a real historical archive from NMPA's own
public Daily Vessel Position reports (Traffic Department "Proceedings of the Operation Meeting") and used
it to compute the platform's first genuinely real vessel-stay and berth-occupancy numbers.

**How we built the historical archive.** NMPA's public "Daily Vessel Position" page only displays that
day's report, with no visible archive or bulk-download option. Its PDF link, however, follows a
predictable, date-based path — and we confirmed the same path resolves for past dates too, meaning a year
of history was already sitting on NMPA's own server, simply not linked from the page itself. We built a
collector that fetches each date directly and recovered roughly a year of daily reports, which we've
since parsed into structured records (arrivals, berthings, sailings, anchorage waits with stated reasons)
to link each vessel's actual stay duration. Coverage isn't complete — about 76% of calendar days
resolved, closer to 88% of working days once Sundays (which the report doesn't appear to cover) are
accounted for — so this is a self-built stopgap, not a substitute for sanctioned access.

**Why we still shouldn't just buy commercial AIS.** MarineTraffic/Spire-grade AIS is a paid subscription,
and most of what it would show — ships already inside NMPA's harbour limits — is redundant with data the
port already collects via its own Vessel Traffic Management System (VTMS) / Port Control, and largely
redundant with what our own archive now already recovers from NMPA's public reports.

**The actual ask, reframed.** Not "give us AIS," but: can Port Control / VTMS export the vessel-call log
it already keeps directly — vessel name/IMO, ETA/ATA, berth assigned, ATB, ATD, cargo type and quantity?
That would both fill the ~12-24% gap in our self-built archive and remove our dependency on scraping a
page never designed for bulk historical access.

**Secondary ask.** 2–3 years of historical vessel-call data (redacted if needed) to extend what we've
already built and validate it further against NMPA's own committed performance standard — 37-hour average
vessel turnaround, 7-hour average pre-berthing time (SOR Annexure-II). Our own measured median so far,
from the self-built archive, is already close to that standard — worth showing them directly.

**Ask them:** Does Port Control / VTMS maintain a per-vessel call log we could get official bulk access
to, instead of us scraping the public reports? Could a historical extract predating our archive (pre
August 2025) be shared? Who's the right department?

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
- **Vessel stay duration & real call spacing — self-built from NMPA's own public Daily Vessel Position
  reports** (see Q3): ~1 year of daily reports collected and parsed, vessel identities resolved across
  reporting inconsistencies, and each call's berthing-to-sailing duration linked from real timestamps
  where available. High-confidence median stay duration measured so far: within a few hours of NMPA's own
  37-hour turnaround standard (SOR Annexure-II).
- **NMPA Circulars & Trade Notices** — not yet built, but confirmed scrapable from the public site with
  no NMPA dependency.

## Project Status, Part B — What's blocked, and why

- **Vessel stay duration / berth occupancy — PARTIALLY SOLVED, self-built.** No longer blocked: see Part
  A. What's missing is completeness, not the mechanism — about 12-24% of days aren't recoverable from the
  public page alone, and roughly a quarter of linked calls have no confirmed departure event yet
  (vessel may still be in port, or its sailing fell in a gap). Official bulk access (Q3) would close both
  gaps and extend history further back than August 2025.
- **Real-time AIS — BLOCKED, though partially superseded.** True live tracking is still not solved (cost
  of commercial AIS, redundant with NMPA's own VTMS) — but our self-built archive already recovers most of
  the *value* we originally wanted AIS for (real stay/occupancy data), just not live, and not with vessel
  position at sea.
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
1. Does Port Control / VTMS keep a per-vessel call log we could get official bulk/API access to — to
   replace our own scraped archive and fill its ~12-24% coverage gaps?
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
