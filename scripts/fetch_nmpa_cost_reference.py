"""
Read NMPA's published budget document (Revised Estimate / Budget Estimate, "at a glance") and save the cost figures the
Incentive Engine uses as a public reference for the cost of handling an extra tonne:
cargo handling & storage expenditure, port & dock expenditure, management & general administration, total operating
expenditure, cargo traffic (lakh tonnes) and cargo handling income, for each year in the document.

  python scripts/fetch_nmpa_cost_reference.py --url <link to NMPA's budget PDF>      (newest budget document)
  python scripts/fetch_nmpa_cost_reference.py --file <downloaded PDF>
  Add --dry-run to print what was read without saving.

Saves data/nmpa_cost_reference.csv (one row per year and basis, with the source link). Figures not found are left out,
never guessed. Average cost per tonne includes fixed costs (salaries), so the true cost of an extra tonne is lower.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nmpa_cost_reference.csv"
FIELDS = ["year", "basis", "cargo_handling_expenditure_cr", "port_dock_expenditure_cr", "management_admin_cr",
          "operating_expenditure_cr", "traffic_lakh_t", "cargo_handling_income_cr", "source", "url"]
NUM = r"([\d,]+\.\d+|[\d]+,[\d]{2})"


def _nums(line: str) -> list[float]:
    """Numbers on a line; the 'at a glance' table writes 350,55 for 350.55 (lakh-style comma decimals)."""
    out = []
    for tok in re.findall(r"\d[\d,]*\.?\d*", line):
        if re.fullmatch(r"\d+,\d{2}", tok):
            tok = tok.replace(",", ".")
        out.append(float(tok.replace(",", "")))
    return out


def parse_budget_text(text: str) -> list[dict]:
    """Rows per year from the budget note: columns are Actuals Y-1, BE Y, RE Y, BE Y+1."""
    head = re.search(r"Actuals\s+(\d{4})-(\d{2})\s+BE\s+(\d{4})-(\d{2})\s+RE\s+(\d{4})-(\d{2})\s+BE\s+(\d{4})-(\d{2})", text)
    if not head:
        return []
    g = head.groups()
    cols = [(f"{g[0]}-{g[1]}", "Actual"), (f"{g[2]}-{g[3]}", "Budget Estimate"), (f"{g[4]}-{g[5]}", "Revised Estimate"),
            (f"{g[6]}-{g[7]}", "Budget Estimate")]
    exp = text.split("Expenditure Projections", 1)[-1] if "Expenditure Projections" in text else ""
    inc = text.split("Income Projections", 1)[-1].split("Expenditure Projections", 1)[0] if "Income Projections" in text else ""

    def first(section: str, label: str) -> list[float] | None:
        m = re.search(label + r"[^\d]*?((?:\d[\d,]*\.?\d*\s+){3}\d[\d,]*\.?\d*)", section, re.S)
        return _nums(m.group(1))[:4] if m else None

    vals = {"cargo_handling_expenditure_cr": first(exp, r"CARGO HANDLING\s*&\s*STORAGE\s*CHARGES"),
            "port_dock_expenditure_cr": first(exp, r"PORT\s*&\s*DOCK\s*CHARGES"),
            "management_admin_cr": first(exp, r"MANAGEMENT\s*&\s*GEN\.?\s*ADMN"),
            "operating_expenditure_cr": first(exp, r"TOTAL"),
            "cargo_handling_income_cr": first(inc, r"CARGO HANDLING\s*&\s*STORAGE\s*CHARGES"),
            "traffic_lakh_t": first(text, r"TOTAL CARGO")}
    rows = []
    for i, (yr, basis) in enumerate(cols):
        if basis == "Budget Estimate" and i == 1:
            continue                                                   # keep Actual, Revised and the next year's Budget
        r = {"year": yr, "basis": basis}
        for k, v in vals.items():
            r[k] = v[i] if v and len(v) > i else ""
        rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"); ap.add_argument("--file"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not (a.url or a.file):
        ap.error("give --url or --file")
    pdf = Path(a.file) if a.file else None
    if a.url:
        import requests
        r = requests.get(a.url, timeout=60, headers={"User-Agent": "NMPA-incentive-engine (public budget document)"})
        r.raise_for_status()
        pdf = Path(tempfile.mkdtemp()) / "budget.pdf"; pdf.write_bytes(r.content)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _poppler import ensure_on_path
    ensure_on_path()
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, encoding="utf-8").stdout
    rows = parse_budget_text(text)
    if not rows:
        print("Could not read the budget table from this document; nothing saved."); return 1
    for r in rows:
        r["source"], r["url"] = "NMPA budget document (Revised Estimate / Budget Estimate)", a.url or str(pdf)
        print(r)
    if a.dry_run:
        return 0
    old = list(csv.DictReader(OUT.open(encoding="utf-8"))) if OUT.exists() else []
    keep = [o for o in old if (o["year"], o["basis"]) not in {(r["year"], r["basis"]) for r in rows}]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(keep + rows)
    print(f"Saved {len(rows)} row(s) to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
