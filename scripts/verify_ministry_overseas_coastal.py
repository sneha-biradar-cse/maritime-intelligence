"""
Check data/port_overseas_coastal_monthly.csv against the original Ministry PDFs in nmpa_public_data/.

Each monthly report "Cargo handled at Major Ports <Month> <Year>" has a TABLE-1 where every port takes three
lines: Overseas, Coastal (this line also carries the port name) and Total. The columns are: same month last year,
this month, share, % change, then the year-to-date figures. We compare the first two columns of each line.

Usage: python scripts/verify_ministry_overseas_coastal.py      (exit code 1 on any difference)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
PORT = "New Mangalore"


def month_of(pdf: Path) -> str | None:
    name = pdf.stem.replace("Sep ", "September ")
    for i, m in enumerate(MONTHS, 1):
        y = re.search(rf"{m}\s+(\d{{4}})", name)
        if y:
            return f"{y.group(1)}-{i:02d}"
    return None


def read_port_rows(pdf: Path) -> dict[str, list[int]]:
    lines = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout.splitlines()
    start = next(i for i, l in enumerate(lines) if "TABLE-1" in l.upper())
    k = next(i for i in range(start, len(lines)) if PORT in lines[i] and "Coastal" in lines[i])
    nums = lambda l: [int(x) for x in re.findall(r"(?<![\d.])\d{4,}(?![\d.])", l)]
    return {"overseas": nums(lines[k - 1]), "coastal": nums(lines[k]), "total": nums(lines[k + 1])}


def main() -> int:
    oc = pd.read_csv(ROOT / "data" / "port_overseas_coastal_monthly.csv").set_index("month")
    problems, checked = 0, 0
    for pdf in sorted((ROOT / "nmpa_public_data").glob("*Major*Port*.pdf")):
        month = month_of(pdf)
        if month is None or month not in oc.index:
            continue
        rows = read_port_rows(pdf)
        r = oc.loc[month]
        for kind in ("overseas", "coastal", "total"):
            pdf_prev, pdf_cur = rows[kind][0], rows[kind][1]
            csv_prev, csv_cur = int(r[f"prev_year_{kind}_t"]), int(r[f"{kind}_t"])
            if (pdf_prev, pdf_cur) != (csv_prev, csv_cur):
                problems += 1
                print(f"  DIFF {month} {kind}: PDF {pdf_prev:,} / {pdf_cur:,}  CSV {csv_prev:,} / {csv_cur:,}")
        checked += 1
        print(f"{month}: checked against {pdf.name}")
    print(f"RESULT: {'OK' if not problems else str(problems) + ' difference(s)'} ({checked} monthly reports checked)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
