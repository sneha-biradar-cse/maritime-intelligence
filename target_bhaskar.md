# target.md: Maritime Port Intelligence Platform (MPIP)

**Owner:** Bhaskar · **Pilot user:** New Mangalore Port Authority (NMPA) · **Grant period:** 20 Jul 2026 to 15 Nov 2026
**Last updated:** 10 Nov 2026

---

## 1. Project Target

Build a working proof of concept that gives NMPA's Traffic Department and berth planners **real-data decision support**. It should:

- forecast monthly cargo volume per commodity, with measured accuracy
- show the port's vessel situation (expected, waiting, alongside) and waiting causes from NMPA's own daily reports
- estimate port charges from the official Schedule of Rates 2026-27
- recommend berths and flag unusual cargo months

Success means the PoC is demonstrated to NMPA, their feedback is recorded, and the final PoC report and scale-up plan are submitted by **15 Nov 2026**.

## 2. Problem Statement

NMPA's planning information is spread across daily PDF reports (Daily Vessel Position), monthly statistics PDFs and an 87-page tariff document. There is no single place to answer:

- How much cargo of each commodity will come next month?
- Which ships are waiting, why, and is the waiting the port's fault or the user's?
- Which berth fits this ship and cargo?
- What will this shipment cost in port charges?

Today these answers are worked out by hand, after the fact. This makes berth planning reactive and makes it hard to spot traffic loss early.

## 3. Steps to Complete

| # | Step / milestone | Status |
|---|---|---|
| 1 | Planning, stakeholder consultation, architecture (M1) | Done (meeting log pending) |
| 2 | Dev environment, FastAPI + Streamlit + Docker, ML pipeline (M2) | Done (procurement proofs pending) |
| 3 | Cargo forecasting engine (Random Forest, backtested vs seasonal baseline) | Done |
| 4 | Port cost & tariff calculator (SOR 2026-27, 116 wharfage lines) | Done |
| 5 | Berth routing, anomaly detection, incentive engine | Done |
| 6 | Vessel Intelligence on real NMPA daily reports (port-call board, ETA band, waiting analytics, reconciliation with NMPA official KPIs) | Done (6 Nov) |
| 7 | Vessel Intelligence hardening: stay-duration fix, 2021+ back-fill, multi-month NMPA reconciliation, container counts, permissible draft | In progress (10–14 Nov) |
| 7a | Trade Intelligence (M3) | Owned by a teammate |
| 7b | Digital Twin on real port-call data (berth-queue simulation + scenarios) | Starts 15–16 Nov, continues next week |
| 8 | In-house Test & Validation Report (M4) | Due 12 Nov |
| 9 | Demo to NMPA, written feedback, scale-up plan (M5) | Due 13 Nov |
| 10 | Final PoC report, user guide, fund utilisation, submission (M6) | Due 14–15 Nov |
| 11 | Hosted demo + Phase 2 backlog | 16 Nov |

## 4. Execution Track

**Approach:** real NMPA public data first. No number appears on screen without its source, and no model ships without beating a simple baseline. Screens without real data stay labelled as demo.

**Plan for the final week:**

| Day | Goal |
|---|---|
| Tue 10 Nov | Push target.md, add mentor as collaborator, book NMPA demo, refresh data |
| Wed 11 Nov | Freeze demo-ready build (fix labels, all tests pass, tag `v1.0-poc`), update demo script |
| Thu 12 Nov | Write Test & Validation Report (M4) + API validation log |
| Fri 13 Nov | NMPA demo, collect written feedback, draft scale-up plan (M5) |
| Sat 14 Nov | Final PoC report, user guide, fund utilisation sheet (M6) |
| Sun 15 Nov | Review, update tracker, push and submit |
| Mon 16 Nov | Fix review gaps, hosted demo, Phase 2 backlog |

**Phase 2 (after PoC):** AIS feed, PostgreSQL/TimescaleDB, GenAI copilot grounded on NMPA data, permissible-draft and tide rules, login/RBAC, cloud deployment.

This file is updated at the end of each working day.
