# Merge: Bhaskar's Vessel Intelligence and tariff work + Sneha's Incentive Engine and Trade Intelligence (17-11-2026)

Bhaskar's repository (maritime-main, 437 files) was an older copy of the shared platform plus his new work. Each shared file
was compared line by line; nothing either person built was dropped. Result: 414 automated tests pass (Sneha's 325 + Bhaskar's
89 in test_tariff_calculator.py and test_vessel_intel.py); the backend and the whole dashboard run without errors.

| Area | Decision | Why |
|---|---|---|
| 31 files only in Bhaskar's repo (vi_* services, historical_calls, sor_wharfage, tariff_validation, AIS probe, data/derived, data/official, data/reference, his tests and docs) | Added | New work |
| backend/app/routes/vessels.py | Bhaskar's | 15 new Vessel Intelligence routes; old illustrative routes relabelled [DEMO] |
| backend/app/routes/cost.py, services/cost_engine.py | Bhaskar's | Rebuilt tariff calculator (full SOR 3.1.1, matching, validation) |
| cost_engine.WHARFAGE_RATES | Rebuilt from Bhaskar's SOR schedule by SOR code (WHARFAGE_SOR_CODES) | The Incentive Engine uses it; all 22 rates checked identical to the previous table, so there is one transcription of the SOR |
| backend/app/main.py | Both | Sneha's logins route + Bhaskar's Vessel Intelligence warm-up at startup |
| frontend/app.py | Sneha's file with Bhaskar's Vessel Intelligence tab and his Port Cost & Tariff Calculator | Each changed different tabs; his code converted to the newer full-width setting (_W_*) used across the file |
| frontend/app.js, index.html | Bhaskar's | His Vessel Intelligence and port-cost views |
| services/forecasting.py, routes/incentive.py, routes/trade.py | Sneha's | Bhaskar's were the older versions |
| data (parsed reports, vessel_stays.json, berth_capacity.csv, port_cargo_monthly.csv) | Sneha's | Newer: 337 reports to 7 Nov 2026 (11 corrected against the PDFs), stays to 7 Nov 2026, usable berth capacity |
| PROJECT_DOCUMENTATION | Sneha's, except 22_NMPA_VISIT_BRIEFING (Bhaskar's) | Sneha's versions contain everything in his plus the Trade routes; his briefing describes the new vessel archive |
| requirements.txt, .gitignore | Combined | Streamlit 1.66.1 kept; websockets added for the AIS probe; both ignore lists |
| target.md | Each keeps their own | Sneha's target.md; Bhaskar's kept as target_bhaskar.md (swap the names in Bhaskar's repository) |

Note: .gitignore now includes Bhaskar's rule data/daily_vessel_position/*.pdf, so new daily report PDFs stay on the computer and
are not uploaded to Git (files already tracked stay tracked).
