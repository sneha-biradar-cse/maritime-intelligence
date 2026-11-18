"""
Build data/source_register.csv: every original document in the project, with publisher, document, period / effective
period, the pages or tables used, units, revision status, what it is used for, and its check status.
Re-run after adding documents: python scripts/build_source_register.py
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MONTHS = {"jan": 1, "feb": 2, "febuary": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "jly": 7, "aug": 8, "sep": 9,
          "sept": 9, "oct": 10, "nov": 11, "dec": 12}


def month_of(name: str) -> str | None:
    """Month from a file name, tolerating abbreviations and the typos in NMPA's own file names ('Jly', 'febuary', 'Sept.')."""
    n = name.lower().replace(".", " ").replace("_", " ")
    y = re.search(r"(20\d\d)", n)
    if not y:
        return None
    for w in re.findall(r"[a-z]+", n):
        if w in MONTHS:
            return f"{y.group(1)}-{MONTHS[w]:02d}"
        if len(w) > 3 and w[:3] in MONTHS and w[:3] != "may" and not w.startswith(("maj", "man", "mar" + "i", "mon", "min")):
            return f"{y.group(1)}-{MONTHS[w[:3]]:02d}"         # january, august, september, october, ...
    return None


RULES = [  # (pattern on file name, publisher, kind, pages/tables used, units, revision status, used for, check status)
    (r"commodity", "New Mangalore Port Authority", "Monthly commodity-wise traffic statement", "Commodity table (loaded / unloaded)",
     "tonnes", "Actual (as published)", "Cargo by commodity, trends, tonnes for wharfage", "Extraction checked; Reconciled"),
    (r"container traffic", "New Mangalore Port Authority", "Statement II, containerised traffic", "Commodity table",
     "TEU and tonnes", "Actual (as published)", "Container trade; container royalty estimate", "Extraction checked"),
    (r"opera?tional performance|oparational", "New Mangalore Port Authority", "Traffic & Performance report", "Traffic and target tables",
     "tonnes", "Actual (as published)", "Target tracker; container ship count", "Original obtained"),
    (r"major port|monthly major port", "Ministry of Ports, Shipping and Waterways", "Cargo handled at Major Ports (monthly)",
     "Table-1 (ports, overseas/coastal), Table-2 (commodities)", "tonnes", "Current month advance estimate; earlier months provisional",
     "Market share, major-port comparison", "Extraction checked; Reconciled"),
    (r"SOR indexation", "New Mangalore Port Authority", "Scale of Rates", "Wharfage schedule (pages recorded in data/sor_reference.json); "
     "General Terms xix, xx(a)", "Rs per tonne", "In force: validity from 7 May 2026 (printed effective 01-05-2026 to 30-4-2027)",
     "Incentive Engine wharfage", "Extraction checked"),
    (r"Budget", "New Mangalore Port Authority", "Revised Estimate 2023-24 and Budget Estimate 2024-25", "Details of Revenue Account - "
     "Operating Income", "Rs thousand", "Actual 2022-23; RE 2023-24; BE 2024-25", "Check against NMPA's accounts", "Extraction checked"),
    (r"PPP", "New Mangalore Port Authority", "PPP project details (3.1.3)", "Berth 14, 15, 16 entries", "text", "As published",
     "PPP berths; customer identity APL", "Original obtained"),
    (r"Trade Circular", "New Mangalore Port Authority", "Trade Circular NMPA/TM/2025-26/Gen.2 (14 Mar 2026)", "Whole (1 page, scanned)",
     "text", "Final (signed)", "Past incentives: March 2026 waiver", "Original obtained"),
    (r"Non-Major", "Ministry of Ports, Shipping and Waterways", "Cargo handled at non-major ports (July 2026)", "State-board table",
     "tonnes", "Advance estimate", "Nearby non-major ports", "Extraction checked"),
    (r"Update on Indian Ports", "Ministry of Ports, Shipping and Waterways", "Update on Indian Ports Sector up to 31.03.2025",
     "Annexure-I (page 71)", "thousand tonnes", "2021-22 to 2023-24 final; 2024-25 provisional", "Which ports gained each cargo",
     "Extraction checked; Reconciled"),
    (r"IOF-Exp-Rebate|container vessel rebate", "New Mangalore Port Authority", "Trade notice: incentive scheme", "Whole (scanned)",
     "text / %", "Final (signed)", "NMPA's own incentive schemes; eligibility rules", "Original obtained"),
    (r"Phase-2 commissioned|West Asia customs", "New Mangalore Port Authority", "Trade notice / circular (context)", "Whole (scanned)",
     "text", "Final (signed)", "Context only (capacity; customs facilitation)", "Original obtained"),
    (r"PROPOSED - not in force", "New Mangalore Port Authority", "Proposed / draft Scale of Rates (NOT in force)", "Not used",
     "Rs", "Proposal only", "Not used for any figure", "Original obtained"),
    (r"SOR w\.e\.f\. 01\.05\.2025", "New Mangalore Port Authority", "Scale of Rates 2025-26 (1.74% indexation)",
     "Wharfage schedule (PDF p.16-18)", "Rs per tonne", "In force 1 May 2025 to 30 Apr 2026", "March 2026 waiver cost; VOC comparison",
     "Extraction checked"),
    (r"SOR w\.e\.f\. 01\.05\.2024|SOR w\.e\.f\. 02\.06\.2023|SOR w\.e\.f\. 01\.05\.2021|SOR from 20\.09\.2019", "New Mangalore Port Authority",
     "Scale of Rates (earlier year)", "Not used yet", "Rs", "In force in its year", "Tariff history (held for reference)", "Original obtained"),
    (r"VOC Port SOR", "V.O. Chidambaranar Port Authority", "Scale of Rates w.e.f. 01.05.2025", "Wharfage schedule 3.1.1 (PDF p.29-30)",
     "Rs per tonne / KL / cubic metre", "In force from 1 May 2025", "Tariff comparison (same year)", "Extraction checked"),
    (r"ARR Forms", "New Mangalore Port Authority", "Annual Revenue Requirement forms (tariff filing)", "Not used (port-wide totals)",
     "Rs lakh", "2022-23 to 2024-25", "Held for reference; not a cost per extra tonne", "Original obtained"),
    (r"old format", "New Mangalore Port Authority", "Scale of Rates, old format", "Wharfage schedule (columns foreign, coastal)",
     "Rs per tonne", "In force 1 to 6 May 2026", "Tariff version for 1-6 May 2026 (same lines as the later version)", "Extraction checked"),
    (r"Berth Capacity", "New Mangalore Port Authority", "Berth capacity as on 31-3-2025", "Whole (1 page)", "MMT per year",
     "As on 31 Mar 2025", "data/berth_capacity.csv (rated and usable)", "Extraction checked"),
    (r"Administration Report", "New Mangalore Port Authority", "Administration Report 2024-25", "Finance Department (PDF p.73); "
     "Table F-I (PDF p.221)", "Rs crore", "Actual 2024-25 and 2023-24", "NMPA's actual income by activity", "Extraction checked (scanned; read from page images)"),
    (r"Cochin SoR", "Cochin Port Authority", "Scale of Rates w.e.f. 01-05-2026 (Trade Circular 13.04.2026)", "Wharfage schedule 3.1 (PDF p.18)",
     "Rs per tonne", "In force from 1 May 2026 (indexed 0.65%)", "Tariff comparison", "Extraction checked"),
    (r"Cochin Corrigendum", "Cochin Port Authority", "Corrigendum dated 22.04.2026", "Whole (scanned)", "Rs", "Final (signed)",
     "Confirms only wharf-entry permit fees changed", "Original obtained"),
    (r"Cochin Trade Notice", "Cochin Port Authority", "Trade notice (scheme example)", "Whole (scanned)", "text / %", "Final (signed)",
     "Scheme design examples", "Original obtained"),
    (r"Adani Wilmar", "AWL Agri Business Ltd (stock-exchange filing)", "Name change intimation", "Whole", "text", "Final",
     "Customer identity proposal (ADANI)", "Original obtained"),
    (r"Paradeep", "Paradeep Phosphates Ltd (stock-exchange filing)", "Merger with Mangalore Chemicals & Fertilizers", "Whole",
     "text", "Final", "Customer identity proposal (MCF)", "Original obtained"),
    (r"credit rating", "JSW Infrastructure Ltd (filing of CARE Ratings rationale)", "JSW Mangalore Container Terminal rating",
     "Concession terms; TEU handled FY24, FY25", "Rs per TEU; TEU", "As published (5 Sep 2025)", "Container royalty", "Original obtained"),
]


def main() -> None:
    rows = []
    for p in sorted((ROOT / "nmpa_public_data").rglob("*.pdf")):
        rule = next((r for r in RULES if re.search(r[0], p.name, re.I)), None)
        if rule is None:
            continue
        m = month_of(re.sub(r"\(.*?\)", "", p.stem)) if rule[2].startswith(("Monthly", "Statement", "Traffic", "Cargo handled at Major")) else None
        rows.append({"file": str(p.relative_to(ROOT)), "publisher": rule[1], "document": rule[2],
                     "period": m or "", "pages_or_tables_used": rule[3], "units": rule[4], "revision_status": rule[5],
                     "used_for": rule[6], "check_status": rule[7],
                     "md5": hashlib.md5(p.read_bytes()).hexdigest()})
    daily = pd.read_csv(ROOT / "data" / "daily_reports_manifest.csv")
    rows.append({"file": "data/daily_vessel_position/ (see data/daily_reports_manifest.csv)", "publisher": "New Mangalore Port Authority",
                 "document": "Daily Vessel Positions", "period": f"{daily.report_date.min()} to {daily.report_date.max()} ({len(daily)} days)",
                 "pages_or_tables_used": "Berthed, anchorage, expected", "units": "tonnes, ship calls", "revision_status": "As published daily",
                 "used_for": "Customers, waiting, foreign/coastal and SPM/berth splits", "check_status":
                 "; ".join(f"{v} {k}" for k, v in daily.status.value_counts().items()), "md5": "per file in the manifest"})
    pd.DataFrame(rows).to_csv(ROOT / "data" / "source_register.csv", index=False)
    print(f"{len(rows)} entries -> data/source_register.csv")


if __name__ == "__main__":
    main()
