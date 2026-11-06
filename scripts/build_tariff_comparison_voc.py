"""
Published wharfage, NMPA vs V.O. Chidambaranar (Tuticorin) Port, SAME PERIOD (2025-26: both Scales of Rates w.e.f. 01.05.2025).
Every value is located in its PDF (page recorded); the build stops if one is not found. VOC charges by zone (A, B).
Lines VOC charges by volume (KL, cubic metre) are not compared: converting to tonnes would need an assumed density.
Usage: python scripts/build_tariff_comparison_voc.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_tariff_comparison import find, text  # noqa: E402

NMPA = ROOT / "nmpa_public_data" / "tariff_history" / "NMPA SOR w.e.f. 01.05.2025 to 30.04.2026 (1.74pc indexation).pdf"
VOC = ROOT / "nmpa_public_data" / "competitors" / "VOC Port SOR (general).pdf"
# cargo, NMPA line, NMPA foreign, NMPA coastal, VOC line, VOC A foreign, A coastal, B foreign, B coastal
LINES = [
    ("Iron ore", "Iron Ore Fines/Lumps", 42.88, 42.88, "Iron Ore", 104.09, 104.09, 89.42, 89.42),
    ("Thermal coal", "Thermal Coal (other than UPCL)", 31.53, 31.53, "", 143.93, 143.93, 143.93, 143.93),
    ("Rock phosphate", "Rock phosphate", 51.70, 30.27, "Rock Phosphate", 133.44, 80.07, 94.44, 56.66),
    ("Finished fertiliser (urea)", "MOP, SOP, Urea", 45.41, 26.48, "Urea", 150.23, 90.11, 104.09, 62.45),
    ("Food grains", "Rice,Wheat", 51.70, 30.27, "", 106.20, 63.72, 63.72, 53.66),
]
UNRESOLVED = [("POL products and crude", "VOC charges per kilolitre (KL); NMPA per tonne. Not compared without an assumed density."),
              ("LPG", "VOC charges per cubic metre; NMPA per tonne. Not compared."),
              ("Edible oil", "VOC charges per cubic metre (CBM); NMPA per tonne. Not compared."),
              ("Containers", "Handled at PPP terminals at both ports; port wharfage lines are not what these customers pay.")]


def main() -> None:
    npg, vpg = text(NMPA), text(VOC)
    rows = []
    for cargo, nl, nf, nc, vl, af, ac, bf, bc in LINES:
        rows.append({"cargo": cargo, "nmpa_foreign": nf, "nmpa_coastal": nc, "nmpa_page": find(npg, nl, nf, nc),
                     "voc_zone_a_foreign": af, "voc_zone_a_coastal": ac, "voc_zone_b_foreign": bf, "voc_zone_b_coastal": bc,
                     "voc_page": find(vpg, vl, af, ac), "nmpa_vs_voc_a_foreign_pct": round((nf / af - 1) * 100, 1),
                     "nmpa_vs_voc_b_foreign_pct": round((nf / bf - 1) * 100, 1), "comparability": "Like-for-like line (per tonne, same year)"})
    for cargo, why in UNRESOLVED:
        rows.append({"cargo": cargo, "comparability": "Unresolved", "note": why})
    d = pd.DataFrame(rows)
    d["period"] = "2025-26 (both Scales of Rates w.e.f. 01.05.2025)"
    d["nmpa_source"] = str(NMPA.relative_to(ROOT))
    d["voc_source"] = str(VOC.relative_to(ROOT))
    d.to_csv(ROOT / "data" / "port_tariff_comparison_voc.csv", index=False)
    print(d[["cargo", "nmpa_foreign", "voc_zone_a_foreign", "voc_zone_b_foreign", "nmpa_vs_voc_a_foreign_pct", "comparability"]].to_string())


if __name__ == "__main__":
    main()
