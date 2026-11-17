"""
Read the Ministry's port-wise average turnaround time table (hours, by year) from a public web page or a saved copy and
save it to data/major_ports_turnaround.csv. The Ministry publishes it in Parliament replies, its 'Update on the Indian
Ports Sector' and Basic Port Statistics.

  python scripts/fetch_turnaround_benchmark.py --url <page with the table>
  python scripts/fetch_turnaround_benchmark.py --file <saved page or text>
  Add --dry-run to print what was read without saving.

A row is kept only if it names a port and has one number per year column; nothing is guessed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "major_ports_turnaround.csv"
PORT_WORDS = ("Port", "All Major Ports")


def parse_table(text: str) -> tuple[list[str], list[list]]:
    """Find the header with year columns (2021-22 ...) and the port rows under it (markdown, HTML text or plain)."""
    text = re.sub(r"<[^>]+>", " | ", text).replace("**", "")
    years, rows = [], []
    for line in text.splitlines():
        ys = re.findall(r"\b(20\d{2}-\d{2})\b", line)
        if len(ys) >= 3 and not years:
            years = ys
            continue
        if years:
            name = re.split(r"[|\d]", line.strip(" |"))[0].strip(" |")
            nums = re.findall(r"\b\d{1,3}(?:\.\d{1,2})?\b", line[len(name):] if name else line)
            if name and any(w in name for w in PORT_WORDS) and len(nums) == len(years):
                rows.append([name] + [float(n) for n in nums])
    return years, rows


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--url"); ap.add_argument("--file"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.url:
        import requests
        text = requests.get(a.url, timeout=60, headers={"User-Agent": "NMPA-incentive-engine (public statistics)"}).text
    elif a.file:
        text = Path(a.file).read_text(encoding="utf-8", errors="replace")
    else:
        ap.error("give --url or --file")
    years, rows = parse_table(text)
    if not rows:
        print("No port-wise turnaround table found; nothing saved."); return 1
    for r in rows:
        print(r)
    if not a.dry_run:
        OUT.write_text("port," + ",".join(years) + "\n" + "".join(f"{r[0]}," + ",".join(f"{v:.2f}" for v in r[1:]) + "\n" for r in rows), encoding="utf-8")
        print(f"Saved {len(rows)} ports to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
