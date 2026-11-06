"""
Read NMPA "Statement II - Containerised traffic handled during <month>" PDFs (nmpa_public_data/container traffic*.pdf)
into data/nmpa_container_commodities.csv: one row per commodity and direction with TEUs and tonnes for
this month, the same month last year, year to date and the same period last year.

Empty containers, tare weight and totals are not commodities and are left out; the printed TOTAL is kept as
a check (commodities + tare = TOTAL tonnes).

Usage: python scripts/parse_nmpa_containers.py
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MONTHS = {m: i for i, m in enumerate(["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                                       "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], 1)}
TOK = re.compile(r"-|\d[\d,]*")
COLS = ["teu_month", "t_month", "teu_month_prev", "t_month_prev", "teu_ytd", "t_ytd", "teu_ytd_prev", "t_ytd_prev"]


def _n(t: str) -> float:
    return 0.0 if t == "-" else float(t.replace(",", ""))


def parse(pdf: Path) -> tuple[pd.DataFrame, list[dict]]:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    m = re.search(r'HANDLED DURING\s+"([A-Z]+),\s*(\d{4})"', text)
    month = f"{m.group(2)}-{MONTHS[m.group(1)]:02d}"
    rows, checks, direction = [], [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("A. UNLOADED"):
            direction = "import"; continue
        if s.startswith("B. LOADED"):
            direction = "export"; continue
        if direction is None:
            continue
        if s.startswith("TOTAL"):
            toks = TOK.findall(s)
            checks.append({"direction": direction, "teu_month": _n(toks[0]), "t_month": _n(toks[1])})
            continue
        r = re.match(r"^(\d+)\s+([A-Za-z][A-Za-z /&().-]*?)\s{2,}(.*)$", s)
        if not r or re.search(r"Empty|Tare|TOTAL", r.group(2), re.I):
            continue
        toks = TOK.findall(r.group(3))
        if len(toks) != 8:
            raise ValueError(f"{pdf.name}: cannot read line {s!r} ({len(toks)} numbers)")
        rows.append({"month": month, "direction": direction, "commodity": r.group(2).strip(),
                     **{c: _n(t) for c, t in zip(COLS, toks)}, "source": pdf.name})
    return pd.DataFrame(rows), checks


def main() -> None:
    frames = []
    for pdf in sorted((ROOT / "nmpa_public_data").glob("container traffic*.pdf")):
        df, checks = parse(pdf)
        frames.append(df)
        print(f"{pdf.name}: {len(df)} commodity rows for {df['month'].iloc[0]}")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(ROOT / "data" / "nmpa_container_commodities.csv", index=False)
    print(f"-> data/nmpa_container_commodities.csv ({len(out)} rows)")


if __name__ == "__main__":
    main()
