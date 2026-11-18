"""
NMPA's official monthly "Traffic & Performance" (Operational Performance)
report → tidy KPI table.

Source: newmangaloreport.gov.in → Notifications → Statistics →
"Operational Performance" (one PDF per month, Jan 2021 onwards).
Drop the PDFs in nmpa_public_data/operational_performance/ (the
collector script scripts/update_vessel_intel_data.py does this) — any
operational-performance PDF directly in nmpa_public_data/ is read too.

Every value is copied from the PDF text; nothing is estimated. Each
PDF yields four numbers per line (this month / same month last year /
year-to-date / previous YTD), so one report also back-fills the same
month of the previous year.

Output rows:
    month         'YYYY-MM' the value belongs to
    metric        vessels_handled | pre_berthing_days | turnaround_hours |
                  idle_time_pct | output_per_berthday_t | traffic_t |
                  container_dwell_days
    component     total | port_account | other_than_port_account
                  (pre-berthing only; 'total' elsewhere) or import/export
    cargo_class   dry_bulk_total | dry_bulk_conventional | dry_bulk_mechanical |
                  break_bulk | liquid_bulk | container | overall
    period        month | ytd
    value         float (None when the report prints '-')
    source_file, report_month
"""

from __future__ import annotations

import csv
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services import vi_reference as ref

PDF_DIRS = [ref.ROOT / "nmpa_public_data" / "operational_performance", ref.ROOT / "nmpa_public_data"]
OUT_PATH = ref.DATA_DIR / "official" / "operational_performance.csv"

MONTHS = {m: i for i, m in enumerate(
    ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
     "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], start=1)}
MONTH_ABBR = {k[:3]: v for k, v in MONTHS.items()}
MONTH_ABBR["SEPT"] = 9

SECTION_PATTERNS = [
    (re.compile(r"^\s*1\)\s*No\.?\s*of\s*vessels", re.I), "vessels_handled"),
    (re.compile(r"^\s*2\)\s*Avg\.?\s*Pre-?\s*berthing", re.I), "pre_berthing_days"),
    (re.compile(r"^\s*3\)\s*Av\w*\.?\s*Turn", re.I), "turnaround_hours"),
    (re.compile(r"^\s*4\)\s*%\s*of\s*Idle", re.I), "idle_time_pct"),
    (re.compile(r"^\s*5\)\s*Av\w*\.?\s*Output", re.I), "output_per_berthday_t"),
    (re.compile(r"^\s*6\)\s*Avg\.?\s*Dwell", re.I), "container_dwell_days"),
    (re.compile(r"^\s*7\)\s*Total\s*Traffic", re.I), "traffic_t"),
    (re.compile(r"^\s*8\)\s*Cruise", re.I), None),
]
COMPONENT_PATTERNS = [
    (re.compile(r"^\s*Port\s*Account", re.I), "port_account"),
    (re.compile(r"^\s*Other\s*than\s*Port", re.I), "other_than_port_account"),
    (re.compile(r"^\s*Total\s*\(In\s*days\)", re.I), "total"),
]
CLASS_PATTERNS = [
    (re.compile(r"^\s*a\)\s*Dry\s*Bulk", re.I), "dry_bulk_total"),
    (re.compile(r"^\s*i\)\s*Conventional", re.I), "dry_bulk_conventional"),
    (re.compile(r"^\s*ii\)\s*Mechani", re.I), "dry_bulk_mechanical"),
    (re.compile(r"^\s*b\)\s*Break\s*Bulk", re.I), "break_bulk"),
    (re.compile(r"^\s*c\)\s*Liquid\s*Bulk", re.I), "liquid_bulk"),
    (re.compile(r"^\s*d\)\s*Container", re.I), "container"),
    (re.compile(r"^\s*e\)\s*Overall", re.I), "overall"),
]
DWELL_PATTERNS = [
    (re.compile(r"^\s*a\)\s*Import", re.I), "import"),
    (re.compile(r"^\s*b\)\s*Export", re.I), "export"),
    (re.compile(r"^\s*c\)\s*Overall", re.I), "overall"),
]
VALUE_RE = re.compile(r"(-|\d[\d,]*\.?\d*)\**")


def _num(tok: str) -> Optional[float]:
    tok = tok.strip().rstrip("*")
    if tok in ("-", ""):
        return None
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def _values(line: str) -> List[Optional[float]]:
    # standalone numbers (Indian digit grouping allowed) or '-' placeholders,
    # optionally followed by footnote asterisks; the last four are the values
    toks = re.findall(r"(?:(?<=\s)|^)(-|\d[\d,]*(?:\.\d+)?)\**(?=\s|$)", line)
    vals = [_num(t) for t in toks]
    return vals[-4:] if len(vals) >= 4 else []


def report_month_from_text(text: str) -> Optional[date]:
    m = re.search(r"FOR\s+THE\s+MONTH\s+OF\s+([A-Z]+)[\s,.-]*(\d{4})", text.upper())
    if not m:
        return None
    mon = MONTHS.get(m.group(1)) or MONTH_ABBR.get(m.group(1)[:4]) or MONTH_ABBR.get(m.group(1)[:3])
    return date(int(m.group(2)), mon, 1) if mon else None


def parse_text(text: str, source_file: str = "") -> Tuple[Optional[date], List[Dict[str, Any]]]:
    rm = report_month_from_text(text)
    if rm is None:
        return None, []
    prev = date(rm.year - 1, rm.month, 1)
    rows: List[Dict[str, Any]] = []
    metric, component = None, "total"
    for line in text.splitlines():
        for pat, name in SECTION_PATTERNS:
            if pat.search(line):
                metric, component = name, "total"
                break
        else:
            if metric is None:
                continue
            if metric == "pre_berthing_days":
                for pat, comp in COMPONENT_PATTERNS:
                    if pat.search(line):
                        component = comp
                        break
            patterns = DWELL_PATTERNS if metric == "container_dwell_days" else CLASS_PATTERNS
            for pat, cls in patterns:
                if pat.search(line):
                    vals = _values(line)
                    if len(vals) != 4:
                        break
                    comp = cls if metric == "container_dwell_days" else component
                    ccls = "container" if metric == "container_dwell_days" else cls
                    for (m_, period), v in zip([(rm, "month"), (prev, "month"), (rm, "ytd"), (prev, "ytd")], vals):
                        rows.append({
                            "month": m_.strftime("%Y-%m"), "metric": metric, "component": comp,
                            "cargo_class": ccls, "period": period, "value": v,
                            "source_file": source_file, "report_month": rm.strftime("%Y-%m"),
                        })
                    break
    return rm, rows


def parse_pdf(path: Path) -> Tuple[Optional[date], List[Dict[str, Any]], str]:
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as exc:  # unreadable / scanned PDF
        return None, [], f"unreadable: {exc}"
    rm, rows = parse_text(text, path.name)
    if rm is None:
        return None, [], "no 'FOR THE MONTH OF <MONTH> <YEAR>' title found (scanned or different layout?)"
    if not rows:
        return rm, [], "title found but no KPI lines matched (layout changed?)"
    return rm, rows, "ok"


def _pdf_files() -> List[Path]:
    files: Dict[str, Path] = {}
    for d in PDF_DIRS:
        if d.exists():
            for p in d.glob("*.pdf"):
                if "operational" in p.name.lower() or "performance" in p.name.lower():
                    files.setdefault(p.name.lower(), p)
    return sorted(files.values())


def _fingerprint() -> Tuple[Tuple[str, float], ...]:
    return tuple((p.name, p.stat().st_mtime) for p in _pdf_files())


@lru_cache(maxsize=2)
def _load(fp: Tuple[Tuple[str, float], ...]) -> Dict[str, Any]:
    by_key: Dict[tuple, Dict[str, Any]] = {}
    files = []
    for p in _pdf_files():
        rm, rows, status = parse_pdf(p)
        files.append({"file": p.name, "report_month": rm.strftime("%Y-%m") if rm else None,
                      "status": status, "values": len(rows)})
        for r in rows:
            key = (r["month"], r["metric"], r["component"], r["cargo_class"], r["period"])
            # a month's own report wins over the 'previous year' column of a later report
            own = r["report_month"] == r["month"]
            if key not in by_key or own:
                by_key[key] = r
    return {"rows": sorted(by_key.values(), key=lambda r: (r["month"], r["metric"], r["cargo_class"])),
            "files": files}


def load() -> Dict[str, Any]:
    return _load(_fingerprint())


def value(month: str, metric: str, cargo_class: str = "overall", component: str = "total",
          period: str = "month") -> Optional[float]:
    for r in load()["rows"]:
        if (r["month"], r["metric"], r["cargo_class"], r["component"], r["period"]) == (month, metric, cargo_class, component, period):
            return r["value"]
    return None


def months_available() -> List[str]:
    return sorted({r["month"] for r in load()["rows"] if r["period"] == "month"})


def export(path: Path = OUT_PATH) -> int:
    rows = load()["rows"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month", "metric", "component", "cargo_class", "period", "value", "source_file", "report_month"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    data = load()
    for f in data["files"]:
        print(f)
    print("rows:", export(), "->", OUT_PATH)
    print("months:", months_available())
