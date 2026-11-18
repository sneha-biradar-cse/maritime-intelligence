"""
Read NMPA "Traffic & Performance for the month of ..." PDFs (nmpa_public_data/operational performance *.pdf)
into data/nmpa_performance_monthly.csv.

Each PDF has, for every indicator and cargo category, four numbers:
  this month | same month last year | year to date | same period last year
They become rows: month, period (month / ytd), year (current / previous), metric, basis, category, value.
The yearly traffic target printed at the bottom is written to the same file as metric "traffic_target_t".

Usage: python scripts/parse_nmpa_performance.py
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MONTHS = {m: i for i, m in enumerate(["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                                       "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], 1)}
CATEGORIES = [(r"^a\)\s*Dry Bulk", "dry_bulk"), (r"^i\)\s*Conventional", "dry_bulk_conventional"),
              (r"^ii\)\s*Mechanical", "dry_bulk_mechanical"), (r"^b\)\s*Break Bulk", "break_bulk"),
              (r"^c\)\s*Liquid Bulk", "liquid_bulk"), (r"^d\)\s*Container", "container"), (r"^e\)\s*Overall", "overall"),
              (r"^a\)\s*Import", "import"), (r"^b\)\s*Export", "export"), (r"^c\)\s*Overall", "overall")]
NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?![\w])|(?<=\s)-(?=\s|$)")


def _num(tok: str) -> float | None:
    return None if tok == "-" else float(tok.replace(",", ""))


def parse(pdf: Path) -> pd.DataFrame:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, encoding="utf-8", errors="replace", check=True).stdout
    m = re.search(r"FOR THE MONTH OF\s+([A-Z]+)\s+(\d{4})", text)
    month = f"{m.group(2)}-{MONTHS[m.group(1)]:02d}"
    prev = f"{int(m.group(2)) - 1}-{MONTHS[m.group(1)]:02d}"
    rows, metric, basis = [], None, ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = {r"^1\)\s*No\. of vessels": "vessels", r"^2\)\s*Avg\. Pre-berthing": "pre_berthing_detention_days",
                r"^3\)\s*Ave?\. Turn-Round": "turn_round_time_hrs", r"^4\)\s*% of Idle": "idle_time_pct",
                r"^5\)\s*Av\. Output per berthday": "output_per_berth_day_t", r"^6\)\s*Avg\. Dwell": "container_dwell_days",
                r"^7\)\s*Total Traffic": "traffic_t", r"^8\)\s*Coastal Traffic": "coastal_traffic_t", r"^9\)": None}
        hit = next((v for k, v in head.items() if re.search(k, line)), "nohit")
        if hit != "nohit":
            metric, basis = hit, ""
            if metric == "coastal_traffic_t":
                vals = [_num(t) for t in NUM.findall(line.split(")", 1)[1])][-4:]
                rows += _four(month, prev, metric, "", "overall", vals)
            continue
        if metric == "pre_berthing_detention_days":
            if line.startswith("Port Account"):
                basis = "port_account"; continue
            if line.startswith("Other than Port"):
                basis = "other_than_port_account"; continue
            if line.startswith("Total (In days)"):
                basis = "total"; continue
        if metric == "turn_round_time_hrs":
            if "As per Readiness" in line:
                basis = "readiness"; continue
            if "Pilot boarding" in line:
                basis = "pilot"; continue
        if metric is None:
            continue
        cat = next((c for pat, c in CATEGORIES if re.search(pat, line)), None)
        if cat is None:
            continue
        label_end = re.search(r"[A-Za-z.)\]]\s{2,}", line)
        nums = [_num(t) for t in NUM.findall(line[label_end.end() - 2:] if label_end else line)]
        if len(nums) >= 4:
            rows += _four(month, prev, metric, basis, cat, nums[-4:])
        elif len(nums) == 3 and metric == "pre_berthing_detention_days":
            pass
    t = re.search(r"Traffic target for the year (\d{4})-(\d{4}) is ([\d.]+) Million Tonnes", text)
    if t:
        rows.append({"report_month": month, "month": month, "period": "financial_year", "year": f"{t.group(1)}-{t.group(2)[2:]}",
                     "metric": "traffic_target_t", "basis": "", "category": "overall", "value": float(t.group(3)) * 1e6})
    df = pd.DataFrame(rows)
    df["source"] = pdf.name
    return df


def _four(month, prev, metric, basis, cat, vals):
    out = []
    for (period, which, mth), v in zip([("month", "current", month), ("month", "previous", prev),
                                        ("ytd", "current", month), ("ytd", "previous", prev)], vals):
        out.append({"report_month": month, "month": mth, "period": period, "year": which,
                    "metric": metric, "basis": basis, "category": cat, "value": v})
    return out


def main() -> None:
    frames = [parse(p) for p in sorted((ROOT / "nmpa_public_data").glob("*performance*.pdf"))]
    df = pd.concat(frames, ignore_index=True)
    out = ROOT / "data" / "nmpa_performance_monthly.csv"
    df.to_csv(out, index=False)
    print(f"{len(df)} values from {len(frames)} reports -> {out.relative_to(ROOT)}")
    for f in frames:
        m = f[(f["period"] == "month") & (f["year"] == "current")]
        print(f"  {f['report_month'].iloc[0]}: {m['metric'].nunique()} indicators")


if __name__ == "__main__":
    main()
