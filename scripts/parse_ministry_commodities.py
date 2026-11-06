"""
Read TABLE-2 (commodity-wise cargo at all major ports together) from every Ministry "Cargo handled at Major Ports"
PDF in nmpa_public_data/ into data/major_ports_commodity_monthly.csv.

Each row of Table-2 gives: same month last year, this month, (share, % change), April-to-date last year,
April-to-date this year (tonnes). Check: the commodities add up to the printed Total in every column.

Usage: python scripts/parse_ministry_commodities.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from parse_ministry_major_ports import month_of, shift_year  # noqa: E402

ORDER = ["POL Crude", "POL Products", "LPG or LNG", "Thermal Coal", "Coking Coal", "Other Coal", "Iron Ore Pellets/Fine",
         "FRM-Liquid", "Fertilizer", "FRM-Dry", "Food Grains excluding Pulses", "Edible Oil", "Other Ores", "Pulses", "Sugar",
         "Cement", "Iron and Steel", "Project Cargo", "Other Commodities", "Container Tonnes", "TEUs", "Total"]
# Some reports (e.g. March) print only the principal groups.
ORDER_PRINCIPAL = ["P:POL and Crude Products", "P:Coal", "P:Iron Ore", "P:Fertilizer", "P:Foodgrains", "P:Other Commodities",
                   "Container Tonnes", "TEUs", "Total"]
NUM = re.compile(r"(?<![\d.\-*])\d+(?![\d.%])")


def read_table2(pdf: Path) -> dict[str, list[int]]:
    """Table-2 lists the same rows in the same order, each with 4 whole-number columns (shares and % changes have
    decimals). A row's numbers sometimes wrap over two lines in either order, so every number is placed by its
    horizontal position into one of the 4 columns, and a row is complete when all 4 are filled."""
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    start = text.find("Table-2")
    if start < 0:
        return {}
    body = text[start:]
    detailed = "POL Crude" in body[:6000]
    order = ORDER if detailed else ORDER_PRINCIPAL
    first = body.find("POL Crude" if detailed else "POL and Crude")
    if first < 0:
        return {}
    lines = []
    for line in body[body.rfind("\n", 0, first) + 1:].splitlines():
        if re.search(r"Provisional|Advance|Source", line):
            break
        toks = [(m.end(), int(m.group())) for m in NUM.finditer(line)]          # numbers are right-aligned: use where they end
        if toks:
            lines.append(toks)
    full = [t for t in lines if len(t) == 4]
    if len(full) < 2:
        return {}
    centres = [sum(t[k][0] for t in full) / len(full) for k in range(4)]
    rows, slot = [], [None] * 4
    for toks in lines:
        for pos, val in toks:
            k = min(range(4), key=lambda c: abs(pos - centres[c]))
            if slot[k] is not None:                     # a new row started before this one was complete
                rows.append(slot); slot = [None] * 4
            slot[k] = val
        if all(v is not None for v in slot):
            rows.append(slot); slot = [None] * 4
    rows = [r for r in rows if all(v is not None for v in r)]
    if len(rows) < len(order):
        return {}
    return dict(zip(order, rows[:len(order)]))


def _prev_month(m: str) -> str:
    y, mo = int(m[:4]), int(m[5:])
    return f"{y if mo > 1 else y - 1}-{(mo - 2) % 12 + 1:02d}"


def _derive_months(df: pd.DataFrame) -> pd.DataFrame:
    """A month with no table of its own: (April to that month) - (April to the month before); April = April-to-date."""
    ytd = df[df["period"] == "ytd"].set_index(["through", "commodity"])["tonnes"]
    have = set(zip(df.loc[df["period"] == "month", "through"], df.loc[df["period"] == "month", "commodity"]))
    add = []
    for (through, com), v in ytd.items():
        if (through, com) in have:
            continue
        if through[5:] == "04":
            add.append({"period": "month", "through": through, "commodity": com, "tonnes": int(v), "basis": "derived", "report": "", "source": "April-to-date"})
            continue
        prev = _prev_month(through)
        if (prev, com) in ytd.index:
            add.append({"period": "month", "through": through, "commodity": com, "tonnes": int(v - ytd[(prev, com)]),
                        "basis": "derived", "report": "", "source": f"April-to-{through} minus April-to-{prev}"})
    df2 = pd.concat([df, pd.DataFrame(add)], ignore_index=True) if add else df
    # Second pass, for a month with no April-to-date figure of its own (no report that month):
    #   April = (April to May) - May;   month X = (April to X+1) - (X+1) - (April to X-1)
    mon = df2[df2["period"] == "month"].set_index(["through", "commodity"])["tonnes"]
    more = []
    for (nxt, com), ytd_next in ytd.items():
        y, mo = int(nxt[:4]), int(nxt[5:])
        x = _prev_month(nxt)
        if (x, com) in mon.index or (nxt, com) not in mon.index or x[5:] == "03":
            continue
        if x[5:] == "04":
            val = ytd_next - mon[(nxt, com)]
            src = f"April-to-{nxt} minus {nxt}"
        else:
            before = _prev_month(x)
            if (before, com) not in ytd.index:
                continue
            val = ytd_next - mon[(nxt, com)] - ytd[(before, com)]
            src = f"April-to-{nxt} minus {nxt} minus April-to-{before}"
        more.append({"period": "month", "through": x, "commodity": com, "tonnes": int(val), "basis": "derived", "report": "", "source": src})
    add += more
    if add:
        print(f"  derived {len({a['through'] for a in add})} months from the April-to-date columns")
    return pd.concat([df, pd.DataFrame(add)], ignore_index=True) if add else df


def _march_from_annual(df: pd.DataFrame) -> pd.DataFrame:
    """March reports give crude, POL products and LPG only together. The Ministry's annual 'Update on Indian Ports Sector'
    gives the full-year LPG/LNG for all major ports, so March = full year - April-to-February (both all major ports)."""
    f = ROOT / "data" / "major_ports_annual_port_commodity.csv"
    if not f.exists():
        return df
    a = pd.read_csv(f)
    add = []
    for _, r in a[a["port"] == "All Ports"].iterrows():
        y = int(r["financial_year"][:4]) + 1                       # '2024-25' -> March 2025
        mar, feb = f"{y}-03", f"{y}-02"
        have_mar = not df[(df.period == "month") & (df.through == mar) & (df.commodity == "LPG or LNG")].empty
        ytd_feb = df[(df.period == "ytd") & (df.through == feb) & (df.commodity == "LPG or LNG")]
        if have_mar or ytd_feb.empty:
            continue
        add.append({"report": "", "period": "month", "through": mar, "commodity": "LPG or LNG",
                    "tonnes": int(round(r["lpg_lng"] * 1000 - ytd_feb["tonnes"].iloc[0])), "basis": "derived",
                    "source": "Update on Indian Ports Sector (annual, Annexure-I) minus April-to-February"})
    if add:
        print(f"  March from the annual report: {', '.join(x['through'] for x in add)} (LPG)")
    return pd.concat([df, pd.DataFrame(add)], ignore_index=True) if add else df


def main() -> None:
    rows = []
    for pdf in sorted((ROOT / "nmpa_public_data").glob("*Major*Port*.pdf")):
        m = month_of(pdf.stem)
        if not m:
            continue
        t = read_table2(pdf)
        if "Total" not in t:
            print(f"  skipped {pdf.name}: Table-2 not found")
            continue
        parts = {k: v for k, v in t.items() if k not in ("Total", "TEUs")}      # works for both formats
        gaps = [sum(v[i] for v in parts.values()) - t["Total"][i] for i in range(4)]
        if any(abs(g) > 25 for g in gaps):          # the reading went wrong for this layout: do not use it
            print(f"  skipped {pdf.name}: commodities do not add up to the printed Total (gaps {gaps})")
            continue
        for k, v in t.items():
            # April reports are different: their cumulative columns are the two previous FULL financial years
            # (April-March), not April-to-date. E.g. the April 2025 report gives April-March 2023-24 and 2024-25.
            if m[5:] == "04":
                y = int(m[:4])
                cols = (("month", shift_year(m, -1)), ("month", m), ("ytd", f"{y - 1}-03"), ("ytd", f"{y}-03"))
            else:
                cols = (("month", shift_year(m, -1)), ("month", m), ("ytd", shift_year(m, -1)), ("ytd", m))
            for i, (period, month) in enumerate(cols):
                rows.append({"report": m, "period": period, "through": month, "commodity": k, "tonnes": v[i],
                             "basis": "provisional" if i in (0, 2) else "advance_estimate", "source": pdf.name})
    df = pd.DataFrame(rows)
    # newest report wins for a given (period, through, commodity): its 'last year' column is the provisional figure
    df = df.sort_values(["report", "basis"]).drop_duplicates(["period", "through", "commodity"], keep="last")
    df = _derive_months(df)
    # March from the annual report is NOT applied: its LPG/LNG (20.2 MMT, 2024-25) does not reconcile with the monthly
    # reports (15.3 MMT for April-February), so the two use different definitions. See DATA_SOURCES_AND_ASSUMPTIONS.md.
    df.sort_values(["period", "through", "commodity"]).to_csv(ROOT / "data" / "major_ports_commodity_monthly.csv", index=False)
    print(f"{df['report'].nunique()} reports -> data/major_ports_commodity_monthly.csv: "
          f"{df[df.period == 'month']['through'].nunique()} months, {df['commodity'].nunique()} commodity lines")


if __name__ == "__main__":
    main()
