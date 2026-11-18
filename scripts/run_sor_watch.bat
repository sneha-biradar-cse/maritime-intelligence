@echo off
REM Runs the NMPA SOR/tariff circular watcher and appends output to a log file.
REM Registered as a scheduled task; see PROJECT_DOCUMENTATION/22_NMPA_VISIT_BRIEFING.md
REM for why this exists (SOR rates re-index annually and our cost_engine.py table
REM is static unless someone re-transcribes the new PDF).

cd /d "%~dp0.."
if not exist logs mkdir logs
python -m backend.app.services.sor_watcher >> logs\sor_watch.log 2>&1
