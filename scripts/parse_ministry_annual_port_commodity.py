"""
Read Annexure-I "Commodity-wise Traffic Handled at Major Ports" (thousand tonnes, each major port, four financial years)
from the Ministry's "Update on Indian Ports Sector" into data/major_ports_annual_port_commodity.csv.

Check: for every year and column, the 13 ports add up to the printed "All Ports" row.
Usage: python scripts/parse_ministry_annual_port_commodity.py
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "nmpa_public_data" / "finance_and_policy" / "Ministry Update on Indian Ports Sector upto 31.03.2025.pdf"
PORTS = ["SMP Kolkata", "SMP Haldia", "Paradip", "Visakhapatnam", "Chennai", "Kamarajar", "V.O. Chidambaranar", "Cochin",
         "New Mangalore", "Mormugao", "JNPA", "Mumbai", "Deendayal", "All Ports"]
COLS = ["pol_crude_and_products", "lpg_lng", "iron_ore", "thermal_coal", "coking_coal", "other_coal", "fertilizer_frm_dry",
        "food_grain", "container_tonnes", "teu_thousand", "others", "total"]
ROW = re.compile(r"(20\d\d-\d\d)\s*(\(P\))?\s+((?:[\d.]+\s+){11}[\d.]+)\s*$")


def find_page(pdf: Path) -> int:
    n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout).group(1))
    for p in range(1, n + 1):
        t = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"], capture_output=True, text=True).stdout
        if "Annexure-I\n" in t or re.search(r"Annexure-I\s*\n", t):
            if "Commodity-wise Traffic Handled at Major Ports" in t:
                return p
    raise SystemExit("Annexure-I not found")


def main() -> None:
    page = find_page(PDF)
    text = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(PDF), "-"], capture_output=True, text=True).stdout
    rows = []
    for line in text.splitlines():
        m = ROW.search(line)
        if m:
            rows.append((m.group(1), bool(m.group(2)), [float(x) for x in m.group(3).split()]))
    if len(rows) != 4 * len(PORTS):
        raise SystemExit(f"expected {4 * len(PORTS)} rows, read {len(rows)}")
    out = []
    for i, (fy, prov, vals) in enumerate(rows):
        port = PORTS[i // 4]
        out.append({"port": port, "financial_year": fy, "provisional": prov, **{c: v for c, v in zip(COLS, vals)}})
    df = pd.DataFrame(out)
    for fy, g in df.groupby("financial_year"):
        ports, allp = g[g.port != "All Ports"], g[g.port == "All Ports"].iloc[0]
        for c in COLS:
            gap = ports[c].sum() - allp[c]
            assert abs(gap) <= 2, f"{fy} {c}: ports add to {ports[c].sum()}, printed All Ports {allp[c]}"
    df["source"] = f"{PDF.name}, Annexure-I (page {page}), thousand tonnes"
    df.to_csv(ROOT / "data" / "major_ports_annual_port_commodity.csv", index=False)
    print(f"Annexure-I (page {page}): {df.port.nunique()} ports x {df.financial_year.nunique()} years -> "
          "data/major_ports_annual_port_commodity.csv; every column adds up to All Ports")


if __name__ == "__main__":
    main()
