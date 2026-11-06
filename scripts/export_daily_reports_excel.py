"""
Combine every NMPA daily vessel position report held (data/daily_vessel_position_parsed/*.json) into ONE Excel workbook:

  Berthed            one row per ship at berth per report day (berth, ship, run F/C, cargo, agent, receiver/shipper, quantities)
  Waiting            one row per ship waiting at anchorage per day (waiting time, reason as written by port staff)
  Expected           one row per expected ship per day (ETA, cargo, preferred berth)
  Report days        one row per report day: rows read, whether the original PDF is held, its check status, source file
  About              what each sheet is, where it comes from, and its limits

Every row carries its report date, source PDF name and the check status of that day. Values are as written in the reports.
Usage: python scripts\\export_daily_reports_excel.py   ->  output\\NMPA_daily_vessel_reports.xlsx
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "daily_vessel_position_parsed"
OUT = ROOT / "output" / "NMPA_daily_vessel_reports.xlsx"
SECTIONS = {"berthed": "Berthed", "anchorage": "Waiting", "expected": "Expected"}


def main() -> Path:
    man = pd.read_csv(ROOT / "data" / "daily_reports_manifest.csv").set_index("file_date")
    tables = {k: [] for k in SECTIONS}
    days = []
    for f in sorted(SRC.glob("*.json"), key=lambda p: datetime.strptime(p.stem, "%d-%m-%Y")):
        j = json.loads(f.read_text(encoding="utf-8"))
        d = datetime.strptime(f.stem, "%d-%m-%Y").date()
        m = man.loc[f.stem] if f.stem in man.index else None
        status = m["status"] if m is not None else "not in manifest"
        pdf = m["original_pdf"] if (m is not None and isinstance(m["original_pdf"], str) and m["original_pdf"]) else "(original PDF not held)"
        for k in SECTIONS:
            for r in j.get(k, []):
                name = str(r.get("vessel_name") or "").strip()
                if k == "berthed" and (not name or name.startswith("-")):
                    continue                                   # empty berths are printed as '----'
                row = {"report_date": d, **{c: v for c, v in r.items() if c != "report_date"},
                       "source_pdf": pdf, "day_check_status": status}
                tables[k].append(row)
        days.append({"report_date": d, "weekday": d.strftime("%A"),
                     "ships_at_berth": sum(1 for r in j.get("berthed", []) if str(r.get("vessel_name") or "").strip()[:1] not in ("", "-")),
                     "ships_waiting": len(j.get("anchorage", [])), "ships_expected": len(j.get("expected", [])),
                     "rows_not_read": len(j.get("unparsed_rows", [])), "original_pdf": pdf, "check_status": status})
    about = pd.DataFrame([
        ("Source", "NMPA Daily Vessel Position reports, as published by New Mangalore Port Authority; read by this project's parser."),
        ("Period", f"{days[0]['report_date']} to {days[-1]['report_date']} ({len(days)} report days)"),
        ("Berthed", "Ships at berth on the report day. A ship staying several days appears once per day. qty_total = cargo of the call; "
                    "qty_day = handled that day; qty_balance = still to handle."),
        ("Waiting", "Ships at anchorage; waiting_duration and reason_or_note as written by port staff."),
        ("Expected", "Ships expected, with ETA and preferred berth, as published that day."),
        ("Check status", "Extraction checked = two independent readings of the original PDF match; Original obtained = read from the PDF "
                         "held; Original not obtained = the day's PDF is not held, so its rows are not checked."),
        ("Names", "Customer, agent and ship names are as written in the reports (not merged or confirmed)."),
        ("Created", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ], columns=["Item", "Meaning"])
    OUT.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        about.to_excel(xw, sheet_name="About", index=False)
        pd.DataFrame(days).to_excel(xw, sheet_name="Report days", index=False)
        for k, sheet in SECTIONS.items():
            pd.DataFrame(tables[k]).to_excel(xw, sheet_name=sheet, index=False)
        for ws in xw.book.worksheets:                         # readable column widths, frozen header row
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    print(f"{len(days)} report days: {len(tables['berthed'])} berthed rows, {len(tables['anchorage'])} waiting rows, "
          f"{len(tables['expected'])} expected rows -> {OUT.relative_to(ROOT)}")
    return OUT


if __name__ == "__main__":
    main()
