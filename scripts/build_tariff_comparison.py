"""
Published wharfage lines: NMPA vs Cochin, for the cargos where a like-for-like line exists in both Scales of Rates.
Every value is located in its PDF (page recorded); the build stops if a value is not found where expected.
Wharfage only: not the total cost to a ship or cargo owner. Usage: python scripts/build_tariff_comparison.py
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NMPA = ROOT / "nmpa_public_data" / "Microsoft Word - NMPA SOR indexation 0.65.doc.pdf"
COCHIN = ROOT / "nmpa_public_data" / "cochin" / "Cochin SoR w.e.f. 01.05.2026 (Trade Circular dated 13.04.2026).pdf"

# cargo, NMPA line text, NMPA coastal, NMPA foreign, Cochin line text, Cochin coastal, Cochin foreign, comparability, note
LINES = [
    ("POL products (at berth)", "Crude Oil", 96.60, 96.60, "POL products - at Port Berth", 152.70, 152.70, "Like-for-like line",
     "NMPA line '(d) Crude Oil' under POL products (diesel, petrol etc. at the same rate)."),
    ("Crude oil (at berth)", "Crude Oil", 96.60, 96.60, "Crude oil - at Port Berth", 152.70, 152.70, "Like-for-like line", ""),
    ("Crude oil (SPM / SBM)", "Single Point Mooring", 34.89, 34.90, "Crude oil - SBM", 25.00, 25.00, "Contractual benchmark only",
     "Cochin's SBM rate is fixed under an MoU between Cochin Port and BPCL Kochi Refinery and is not indexed; not a generally available rate."),
    ("Edible oil", "", 41.59, 68.45, "Molasses, edible oils & other liquids", 97.25, 161.89, "Like-for-like line", ""),
    ("Finished fertiliser", "MOP", 26.65, 45.71, "Finished fertilisers", 71.02, 118.31, "Like-for-like line",
     "Cochin rate at berths other than Q10; at Q10 Cochin charges 50.71 / 84.50."),
    ("Rock phosphate / sulphate", "Rock phosphate", 30.47, 52.04, "Rock phosphate", 78.13, 130.16, "Like-for-like line",
     "Cochin rate at berths other than Q10; at Q10 Cochin charges 55.89 / 92.96."),
    ("Food grains", "Rice", 30.47, 52.04, "Food grains, oilseeds, cereals", 60.33, 100.51, "Like-for-like line", ""),
    ("Thermal coal", "Thermal Coal (other than UPCL)", 31.73, 31.73, "Thermal Coal", 83.03, 83.03, "Line comparable; NMPA coal is mostly at PPP Berth 16",
     "Most NMPA thermal coal is handled at Berth 16 (PPP) and UPCL's Berth 15, so this NMPA line applies to little of it."),
]
UNRESOLVED = [
    ("LPG", "Cochin's Scale of Rates has no line naming LPG; which line applies (other liquids, any other item) is not stated."),
    ("Iron ore", "Cochin has no iron ore line; its 'Minerals and ores - Others' (71.32 / 118.75) is not like-for-like."),
    ("Containers", "At New Mangalore containers are handled at JSW's PPP Berth 14; at Cochin, at a PPP terminal (ICTT). Port wharfage lines are not the charges these customers pay."),
]


def text(pdf: Path) -> list[str]:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout.split("\f")


def find(pages: list[str], label: str, a: float, b: float) -> int:
    sa, sb = f"{a:.2f}", f"{b:.2f}"
    for n, pg in enumerate(pages, 1):
        L = pg.splitlines()
        for i, line in enumerate(L):
            w = line + " " + (L[i + 1] if i + 1 < len(L) else "")
            if sa in w and sb in w and (not label or label.lower() in (line + " " + (L[i - 1] if i else "")).lower()):
                return n
    raise SystemExit(f"not found: '{label}' {sa} / {sb}")


def main() -> None:
    np_, cp_ = text(NMPA), text(COCHIN)
    rows = []
    for cargo, nl, nc, nf, cl, cc, cf, comp, note in LINES:
        rows.append({"cargo": cargo, "nmpa_coastal": nc, "nmpa_foreign": nf, "nmpa_page": find(np_, nl, nc, nf),
                     "cochin_coastal": cc, "cochin_foreign": cf, "cochin_page": find(cp_, cl, cc, cf),
                     "nmpa_vs_cochin_foreign_pct": round((nf / cf - 1) * 100, 1), "comparability": comp, "note": note})
    for cargo, why in UNRESOLVED:
        rows.append({"cargo": cargo, "comparability": "Unresolved", "note": why})
    out = pd.DataFrame(rows)
    out["nmpa_source"] = f"{NMPA.relative_to(ROOT)} (validity from 7 May 2026; same lines in the 1-6 May 2026 version)"
    out["cochin_source"] = (f"{COCHIN.relative_to(ROOT)} (w.e.f. 01-05-2026; corrigendum of 22.04.2026 changes only wharf-entry "
                            "permit fees)")
    out.to_csv(ROOT / "data" / "port_tariff_comparison.csv", index=False)
    print(out[["cargo", "nmpa_foreign", "nmpa_page", "cochin_foreign", "cochin_page", "nmpa_vs_cochin_foreign_pct", "comparability"]].to_string())


if __name__ == "__main__":
    main()
