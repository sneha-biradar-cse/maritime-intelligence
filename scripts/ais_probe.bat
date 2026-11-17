@echo off
REM Listen to live AIS (aisstream.io) around New Mangalore Port and summarise.
REM Needs AISSTREAM_API_KEY in .env at the project root. Usage: scripts\ais_probe.bat --minutes 10 [--wide]
cd /d "%~dp0\.."
call venv\Scripts\activate.bat 2>nul
python -c "import websockets" 2>nul || pip install websockets
python scripts\ais_probe.py %*
pause
