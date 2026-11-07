"""
One command for the monthly (or weekly) refresh. In order:
  1. NMPA documents (statements, notices, tariffs) and the Ministry of Ports' monthly reports (scripts/harvest_nmpa_documents.py)
  2. NMPA daily vessel reports since the last one held   (scripts/download_daily_reports.py --from <next day> --to <today>)
  3. Read and check everything new, refresh all figures  (scripts/update_trade_data.py; all-or-nothing)
  4. Rebuild the Excel workbook of daily reports         (scripts/export_daily_reports_excel.py)
Then restart the backend so the dashboard shows the new data.

Usage (PowerShell, from the project folder, venv active):
  python scripts\\refresh_all.py --dry-run      show what would be downloaded; change nothing
  python scripts\\refresh_all.py                do everything
  python scripts\\refresh_all.py --skip-harvest only daily reports + update
To run it every Monday at 7:00 automatically, see USER_GUIDE_INCENTIVE_ENGINE.md (Windows Task Scheduler).
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def step(title: str, args: list[str]) -> int:
    print(f"\n=== {title} ===", flush=True)
    return subprocess.run([sys.executable, *args], cwd=ROOT).returncode


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    last = pd.read_csv(ROOT / "data" / "daily_reports_manifest.csv")["report_date"].max()
    start = (pd.Timestamp(last) + timedelta(days=1)).date()
    codes = {}
    if "--skip-harvest" not in argv:
        codes["NMPA documents"] = step("1. NMPA documents (statements, notices, tariffs)",
                                       ["scripts/harvest_nmpa_documents.py"] + (["--dry-run"] if dry else []))
    if start <= date.today():
        codes["Daily reports"] = step(f"2. NMPA daily vessel reports from {start} to {date.today()}",
                                      ["scripts/download_daily_reports.py", "--from", start.isoformat(), "--to",
                                       date.today().isoformat()] + (["--dry-run"] if dry else []))
    if dry:
        print("\nDry run: nothing downloaded or changed. Run without --dry-run to do it.")
        return 0
    sys.path.insert(0, str(ROOT / "scripts"))
    from _poppler import ensure_on_path
    if not ensure_on_path() and any(not p.stem[:2].isdigit() for p in (ROOT / "incoming").glob("*.pdf")):
        codes["PDF tools"] = step("3a. Install the PDF text tools (Poppler) into the project folder, once",
                                  ["scripts/setup_poppler.py"])
        ensure_on_path()
    codes["Update"] = step("3. Read, check and refresh everything (all-or-nothing)", ["scripts/update_trade_data.py"])
    if codes["Update"] in (0, 1):
        codes["Excel"] = step("4. Rebuild the Excel workbook", ["scripts/export_daily_reports_excel.py"])
    print("\n=== Summary ===")
    for k, v in codes.items():
        print(f"  {k:16} {'OK' if v == 0 else ('done, see notes above' if v == 1 else 'FAILED - nothing was changed by this step')}")
    print("\nRestart the backend so the dashboard reads the new data.")
    return 0 if all(v in (0, 1) for v in codes.values()) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
