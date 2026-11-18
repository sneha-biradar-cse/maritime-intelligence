"""
Rebuild data/daily_reports_manifest.csv and data/daily_reports_missing_pdfs.csv: one row per daily-report day, whether the
original PDF is held, its MD5, and its status. Statuses already recorded are kept; new days get a status from what is held.
Days passed with --verified (an original PDF that matched the record held) become 'Extraction checked'.
Usage: python scripts/build_daily_manifest.py [--verified 01-09-2025 02-09-2025 ...]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CHECKED = "Extraction checked (two independent readings match)"
OBTAINED = "Original obtained (read by this project's parser)"
MISSING = "Original not obtained (record not checked)"
CORRECTED = "Original obtained (PDF reading used; earlier data corrected)"


def main(verified: list[str], corrected: list[str] | None = None) -> None:
    corrected = corrected or []
    js = {p.stem: p for p in (ROOT / "data" / "daily_vessel_position_parsed").glob("*.json")}
    pdfs = {p.stem: p for p in (ROOT / "data" / "daily_vessel_position").glob("*.pdf")}
    mf = ROOT / "data" / "daily_reports_manifest.csv"
    old = pd.read_csv(mf).set_index("file_date")["status"].to_dict() if mf.exists() else {}
    rows = []
    for stem, jp in js.items():
        d = pd.to_datetime(stem, format="%d-%m-%Y")
        j = json.loads(jp.read_text(encoding="utf-8"))
        has = stem in pdfs
        status = (CHECKED if stem in verified else CORRECTED if stem in corrected else
                  (old.get(stem) if (has and old.get(stem) and old[stem] != MISSING) else (OBTAINED if has else MISSING)))
        rows.append({"report_date": d.strftime("%Y-%m-%d"), "file_date": stem, "weekday": d.strftime("%A"),
                     "parsed_json": f"data/daily_vessel_position_parsed/{stem}.json", "original_pdf_held": "yes" if has else "no",
                     "original_pdf": f"data/daily_vessel_position/{stem}.pdf" if has else "",
                     "pdf_md5": hashlib.md5(pdfs[stem].read_bytes()).hexdigest() if has else "",
                     "berthed_rows": len(j.get("berthed", [])), "anchorage_rows": len(j.get("anchorage", [])),
                     "expected_rows": len(j.get("expected", [])),
                     "json_origin": "read from the PDF held here" if has else "came with the original project (no PDF held)",
                     "status": status})
    m = pd.DataFrame(rows).sort_values("report_date")
    m.to_csv(mf, index=False)
    m[m.status == MISSING][["report_date", "file_date", "weekday", "parsed_json", "berthed_rows"]].to_csv(
        ROOT / "data" / "daily_reports_missing_pdfs.csv", index=False)
    print(f"{len(m)} days: " + "; ".join(f"{v} {k}" for k, v in m.status.value_counts().items()))


if __name__ == "__main__":
    args = sys.argv[1:]
    ver = args[args.index("--verified") + 1:] if "--verified" in args else []
    cor = []
    if "--corrected" in ver:
        i = ver.index("--corrected")
        ver, cor = ver[:i], ver[i + 1:]
    main(ver, cor)
