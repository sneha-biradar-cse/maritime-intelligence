# Target: Trade Intelligence and Incentive Engine

**Owner:** Sneha Biradar
**Project:** Maritime Port Intelligence Platform (YellowSense) for New Mangalore Port Authority (NMPA)
**My module:** Trade Intelligence and Incentive Engine (teammates own Cargo Forecasting and Vessel Intelligence)
**Last updated:** 17-11-2026

---

## 1. Goal

Help NMPA's Traffic, Finance and management teams decide **when to offer a discount to a customer, and when not to**.
The Incentive Engine shows what each cargo earns, which customers and cargos are at risk and why, and what a discount
would really cost, using only NMPA's own public documents.

## 2. Final targets (what "done" means)

| # | Target | Status |
|---|---|---|
| 1 | Built only on real NMPA and Ministry of Ports data, with every figure traceable to its source | Done |
| 2 | All 334 daily vessel reports held as original PDFs; 277 checked by two independent readings | Done (to 7 Nov 2026) |
| 3 | Clean, simple interface designed for port officers; to be tried with NMPA's team | Built (five tabs); NMPA trial pending |
| 4 | Discount calculator and scenarios based on real tonnes, not guesses | Done |
| 5 | Scheme register that follows NMPA's own way of designing and approving schemes | Done |
| 6 | Data refreshed automatically with one command (can run weekly) | Done |
| 7 | All automated tests passing | Done (414 tests, with Bhaskar's) |
| 8 | Demo to NMPA's team | Pending |
| 9 | Estimates turned into checked figures with NMPA's billing data | Pending NMPA data |
| 10 | Individual logins for NMPA officers (pilot use) | Built; waiting for the pilot decision |

## 3. Starting point (10-11-2026)

Tracking with daily branches starts today. What already exists in the project on this date:

- Trade Intelligence and Incentive Engine, built on NMPA and Ministry of Ports public data
- 334 daily vessel reports (to 7 Nov 2026), all held as original PDFs; 277 checked by two independent readings
- Five-tab interface: Start here, What we earn, Customers & cargo, Plan a discount, Schemes
- Discount calculator on actual last-12-months tonnes, with "What if" scenarios from real data
- Scheme register with NMPA scheme templates, expected cost and a "ready for review" checklist
- NMPA's 5 schemes in force, read from its own trade notices
- How other major ports design schemes (design references only)
- One-command data refresh (`scripts/refresh_all.py`)
- 257 automated tests, all passing

## 4. Pending

**Waiting on NMPA (through a nodal officer):**
- Billed wharfage by cargo for the latest year (turns estimates into checked figures)
- Confirmation of customer names (e.g. two spellings of the same company)
- Current container royalty per TEU at Berth 14
- Vessel charge rate for green-cargo ships (mentioned in the Harit policy, no rate given)
- A nodal officer for data and follow-up
- Ship sizes (GRT) of the ships calling at Berths 14 and 16, to price the container and Cape-size rebates

**Waiting on publication:**
- NMPA October 2026 container and Traffic & Performance statements
- Ministry of Ports October 2026 major ports report

**My own work:**
- Add schemes of the remaining major ports (Mumbai, Chennai, Kamarajar, Visakhapatnam, Kolkata) as design references
- Update the presentation script to the new tab names
- Decide with the mentor: demo only, or pilot with individual logins

## 5. This week (10-11-2026 to 16-11-2026)

- [x] Check the new "Plan a discount" and "Schemes" tabs on screen and fix anything that looks off
- [ ] Rehearse the 10-minute demo using `DEMO_SCRIPT_NMPA.md`
- [ ] Send the data request to NMPA (list in section 4)
- [ ] Run the weekly refresh on Monday (`python scripts\refresh_all.py`)
- [ ] Add the remaining five major ports' scheme designs
- [ ] Create a new branch every day, named `feature_name_date`

## 6. Today: 17-11-2026

**Branch:** `board_note_17-11-2026`

- [x] Board agenda note drafts carry the engine's evidence: earlier NMPA schemes for the cargo, kept per extra tonne after handling cost, berth room, approval route (to be confirmed by NMPA)
- [x] Data request for NMPA prepared (NMPA_Data_Needs_Questions: 5 datasets + 3 questions, checked against public sources)
- [x] Compare scheme designs side by side (Plan a discount): cost, net, break-even, customer duty, risk
- [x] Customer call sheet on request (Customers & cargo): facts and suggested talking points
- [x] NMPA circulars and trade notices (Sidhesh Sir's point 5): sorted, what each affects; automatic reading only after NMPA's permission
- [x] Five NMPA notices added (container rebate 2023-2026, coastal container free storage 2019-2022); settlement list applies the rebate in force on each date
- [x] Merged Bhaskar's Vessel Intelligence and tariff calculator work (MERGE_NOTES.md)
- [x] 414 automated tests passing (325 + Bhaskar's 89)
- [ ] Next: act on what NMPA agrees to share; "pay only when ready" template once the 2023 performance-norms notice is held

## Earlier: 14-11-2026

**Branch:** `settlement_list_14-11-2026`

- [x] Monthly settlement list for Finance: qualifying container and Cape-size calls, iron ore exporters; CSV download
- [x] Uploads yesterday's shared budget pool and rebate claims, which were not yet on GitHub
- [x] Ship stays rebuilt to 7 Nov 2026 (had stopped at 14 Sep 2026) and added to the weekly refresh
- [x] Public data: NMPA berth capacity (official); public ship sizes and USD-INR rates added to the weekly refresh
- [x] Berth check now also measures against NMPA's usable capacity and names berths with room
- [x] Pitch deck: learned berth times updated (21 / 44 / 52 hours)
- [x] Public data: NMPA's published handling cost per tonne (budget document); Ministry turnaround times of all 12 major ports
- [x] Back-fill of older daily reports (direct mode, Apr-Aug 2025) ready; iron ore base uses whatever months are held
- [x] Approval route: NMPA's delegation documents as references; limits used only after NMPA confirms them
- [x] Scheme history: Cape-size rebate since Apr 2021, container rebate since 2023, 2023 performance norms; every notice row sourced
- [x] NMPA Citizen's Charter standards next to turnaround; days in each step for rebate claims
- [x] Confirm customer names: one review list for Traffic, biggest cargo first; nothing changes until an officer applies
- [x] Prepare a claim from the settlement list (pre-fills the form; the officer checks and submits)
- [x] One-page brief on request (Start here): actions, customers, schemes ending, claims, other ports, busy berths
- [x] Did each scheme pay for itself? Net benefit after cost, never firmer than the evidence
- [x] 315 automated tests passing
- [ ] Next: one-page data request letter to NMPA (billing, ship sizes, customer names, FY 2025-26 by exporter, download permission)

## 7. Daily log

One line per day: date, branch name, work done.

| Date | Branch | Work done |
|---|---|---|
| 10-11-2026 | incentive_engine_ui_10-11-2026 | Two-tab layout ("Plan a discount" and "Schemes"); two setup fixes; target.md created |
| 12-11-2026 | incentive_engine_upgrade_12-11-2026 | Did it work? (all schemes); customer-readiness condition; merged team upgrade; schemes ending soon; Board note and trade notice drafts; growth check; 283 tests |
| 13-11-2026 | berth_capacity_13-11-2026 | Billing check and competitor watch reviewed and tested; duplicates removed; berth capacity check; shared budget pool; rebate claims; 298 tests |
| 14-11-2026 | settlement_list_14-11-2026 | Monthly settlement list; ship stays rebuilt; NMPA berth capacity; public ship sizes in refresh; NMPA cost per tonne; turnaround benchmark; daily-report back-fill; approval route (references, nothing unconfirmed enforced); scheme history; Citizen's Charter standards; customer name review; prepare a claim from the settlement list; one-page brief on request; net benefit of schemes; uploads 13-11 pool and claims; 315 tests |
| 17-11-2026 | board_note_17-11-2026 | Board note drafts with earlier schemes, net per tonne, berth room, approval route; NMPA data request; compare scheme designs; customer call sheet; NMPA circulars; container rebate history from NMPA notices; merged Bhaskar's work; 414 tests |
