# Target: Trade Intelligence and Incentive Engine

**Owner:** Sneha Biradar
**Project:** Maritime Port Intelligence Platform (YellowSense) for New Mangalore Port Authority (NMPA)
**My module:** Trade Intelligence and Incentive Engine (teammates own Cargo Forecasting and Vessel Intelligence)
**Last updated:** 10-11-2026

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
| 7 | All automated tests passing | Done (257 tests) |
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

**Waiting on publication:**
- NMPA October 2026 container and Traffic & Performance statements
- Ministry of Ports October 2026 major ports report

**My own work:**
- Add schemes of the remaining major ports (Mumbai, Chennai, Kamarajar, Visakhapatnam, Kolkata) as design references
- Update the presentation script to the new tab names
- Decide with the mentor: demo only, or pilot with individual logins

## 5. This week (10-11-2026 to 16-11-2026)

- [ ] Check the new "Plan a discount" and "Schemes" tabs on screen and fix anything that looks off
- [ ] Rehearse the 10-minute demo using `DEMO_SCRIPT_NMPA.md`
- [ ] Send the data request to NMPA (list in section 4)
- [ ] Run the weekly refresh on Monday (`python scripts\refresh_all.py`)
- [ ] Add the remaining five major ports' scheme designs
- [ ] Create a new branch every day, named `feature_name_date`

## 6. Today: 10-11-2026

**Branch:** `incentive_engine_ui_10-11-2026`

- [x] Split "Proposals & schemes" into two tabs: "Plan a discount" and "Schemes"
- [x] Fix the missing test package (`pypdf`) and the update script's import path
- [x] Create `target.md`
- [ ] Check the new tabs on screen

## 7. Daily log

One line per day: date, branch name, work done.

| Date | Branch | Work done |
|---|---|---|
| 10-11-2026 | incentive_engine_ui_10-11-2026 | Two-tab layout ("Plan a discount" and "Schemes"); two setup fixes; target.md created |
