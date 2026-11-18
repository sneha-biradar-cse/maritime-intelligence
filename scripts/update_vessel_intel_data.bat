@echo off
REM Daily update of the Vessel Intelligence data from newmangaloreport.gov.in
REM Schedule with Windows Task Scheduler at ~13:30 IST (after NMPA publishes the day's report).
cd /d "%~dp0\.."
call venv\Scripts\activate.bat 2>nul
python scripts\update_vessel_intel_data.py %*
curl -s -X POST http://127.0.0.1:8000/vessels/intel/refresh >nul 2>&1
