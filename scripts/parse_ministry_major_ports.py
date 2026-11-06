"""
Read TABLE-1 of every Ministry of Ports "Cargo handled at Major Ports" PDF in nmpa_public_data/ (and any
transcribed tables in data/ministry_table1_manual.csv) into data/major_ports_monthly.csv:
one row per port and month with overseas, coastal and total tonnes.

Each report gives, for every port: same month last year, this month, April-to-date last year, April-to-date this
year. Rules:
  * a month's figure is taken from the newest report that prints it (the later "same month last year" column is
    the provisional figure and replaces the earlier advance estimate);
  * a month with no report of its own is derived from the April-to-date columns:
    month = (April to that month) - (April to the month before), when both are held.
Checks: each port's overseas + coastal = total, and the ports add up to the printed all-port total.

Usage: python scripts/parse_ministry_major_ports.py
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
SUBS = {"KDS", "HDC"}
KINDS = ("overseas", "coastal", "total")


def month_of(name: str) -> str | None:
    name = name.replace("Sep ", "September ").replace("Sept ", "September ")
    for i, m in enumerate(MONTHS, 1):
        y = re.search(rf"{m}\s+(\d{{4}})", name)
        if y:
            return f"{y.group(1)}-{i:02d}"
    return None


def read_table(pdf: Path) -> pd.DataFrame:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    start = text.upper().find("TABLE-1")
    end = text.find("Table-2", start)
    rows, block = [], {}
    for line in text[start:end].splitlines():
        k = next((kind for kind in KINDS if re.search(rf"\b{kind.title()}\b", line)), None)
        if k is None:
            # Some reports print the port name on a line of its own between the Overseas and Coastal lines.
            name = re.sub(r"^\s*\d+\s*", "", line).strip()
            if name and re.fullmatch(r"[A-Za-z][A-Za-z .]*", name) and block:
                block["port"] = name
            continue
        ints = [int(x) for x in re.findall(r"(?<![\d.])\d{3,}(?![\d.])", line)]
        if len(ints) < 4:
            continue
        if k == "coastal":
            label = re.sub(r"^\s*\d+\s*", "", line.split("Coastal")[0]).strip()
            if label:
                block["port"] = label
        block[k] = ints[:4]
        if k == "total":
            if block.get("port") and block["port"] not in SUBS and all(x in block for x in KINDS):
                rows.append(block)
            block = {}
    out = []
    for b in rows:
        port = "All major ports" if b["port"] == "Total" else b["port"]
        for i, col in enumerate(("month_prev", "month_cur", "ytd_prev", "ytd_cur")):
            out.append({"port": port, "column": col, **{f"{k}_t": b[k][i] for k in KINDS}})
    return pd.DataFrame(out)


def read_text_table(path: Path) -> pd.DataFrame:
    """TABLE-1 as plain text: a port-name line, then Overseas / Coastal / Total lines with 8 numbers each."""
    out, port = [], None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind = line.split()[0].lower()
        if kind not in KINDS or not re.search(r"\d{3,}", line):
            port = re.sub(r"^\d+\s*", "", line).strip()
            continue
        if port in SUBS:
            continue
        ints = [int(x) for x in re.findall(r"(?<![\d.-])\d{3,}(?![\d.])", line)]
        name = "All major ports" if port == "Total" else port
        for i, col in enumerate(("month_prev", "month_cur", "ytd_prev", "ytd_cur")):
            out.append({"port": name, "column": col, "kind": kind, "value": ints[i]})
    t = pd.DataFrame(out).pivot_table(index=["port", "column"], columns="kind", values="value").reset_index()
    return t.rename(columns={k: f"{k}_t" for k in KINDS})[["port", "column", "overseas_t", "coastal_t", "total_t"]]


def shift_year(m: str, years: int) -> str:
    return f"{int(m[:4]) + years}{m[4:]}"


def main() -> None:
    month_vals: dict[tuple[str, str], tuple[dict, int, str]] = {}   # (port, month) -> (values, report rank, basis)
    ytd: dict[tuple[str, str], dict] = {}                            # (port, through-month) -> values
    reports = []
    for pdf in sorted((ROOT / "nmpa_public_data").glob("*Major*Port*.pdf")):
        m = month_of(pdf.stem)
        if not m:
            continue
        t = read_table(pdf)
        reports.append((m, pdf.name, t))
    # Reports read from the web as text (data/ministry_table1_text/<YYYY-MM>.txt, TABLE-1 as extracted).
    for txt in sorted((ROOT / "data" / "ministry_table1_text").glob("*.txt")):
        if any(r[0] == txt.stem for r in reports):
            continue
        reports.append((txt.stem, f"{txt.name} ({txt.read_text().splitlines()[0].lstrip('# ')[:90]})", read_text_table(txt)))
    for m, src, t in sorted(reports, key=lambda r: r[0]):
        allp = t[t["port"] == "All major ports"].set_index("column")
        ports = t[t["port"] != "All major ports"]
        for col in ("month_prev", "month_cur", "ytd_prev", "ytd_cur"):
            s = ports[ports["column"] == col]
            bad = s[(s["overseas_t"] + s["coastal_t"] - s["total_t"]).abs() > 0]
            for b in bad.itertuples():   # the Ministry's own rounding, printed as is (never more than a few tonnes)
                gap = b.overseas_t + b.coastal_t - b.total_t
                assert abs(gap) <= 5, f"{src}: {b.port} overseas + coastal != total by {gap} ({col})"
                print(f"  note: {src}: {b.port} {col}: overseas + coastal - total = {gap} t in the printed table")
            gap = s["total_t"].sum() - allp.loc[col, "total_t"]
            assert abs(gap) <= 12, f"{src}: ports do not add up to printed total ({col}, {gap})"
        for r in t.itertuples():
            vals = {"overseas_t": r.overseas_t, "coastal_t": r.coastal_t, "total_t": r.total_t}
            if r.column in ("month_cur", "month_prev"):
                month = m if r.column == "month_cur" else shift_year(m, -1)
                rank = 1 if r.column == "month_prev" else 0      # provisional (later) beats advance estimate
                key = (r.port, month)
                if key not in month_vals or rank >= month_vals[key][1]:
                    month_vals[key] = (vals, rank, f"{'provisional' if rank else 'advance estimate'} - {src}")
            else:
                through = m if r.column == "ytd_cur" else shift_year(m, -1)
                ytd[(r.port, through)] = vals
    # Derive months that have no report of their own from consecutive April-to-date figures.
    derived = 0
    for (port, through), v in list(ytd.items()):
        if (port, through) in month_vals:
            continue
        y, mo = int(through[:4]), int(through[5:])
        if mo == 4:
            month_vals[(port, through)] = (v, -1, "derived: April-to-date of April")
            derived += 1
            continue
        prev = f"{y if mo > 1 else y - 1}-{(mo - 2) % 12 + 1:02d}"
        if (port, prev) in ytd:
            p = ytd[(port, prev)]
            month_vals[(port, through)] = ({k: v[k] - p[k] for k in v}, -1, f"derived: April-to-{through} minus April-to-{prev}")
            derived += 1
    # Second pass: month X = YTD(X+1) - YTD(X-1) - month(X+1)
    for (port, through), v in list(ytd.items()):
        y, mo = int(through[:4]), int(through[5:])
        x = f"{y if mo > 1 else y - 1}-{(mo - 2) % 12 + 1:02d}"              # month before 'through'
        before = f"{int(x[:4]) if int(x[5:]) > 1 else int(x[:4]) - 1}-{(int(x[5:]) - 2) % 12 + 1:02d}"
        if (port, x) in month_vals or (port, through) not in month_vals:
            continue
        if int(x[5:]) == 4:          # April = (April to May) - May; the year-to-date starts again in April
            nxt = month_vals[(port, through)][0]
            month_vals[(port, x)] = ({k: v[k] - nxt[k] for k in v}, -1, f"derived: April-to-{through} minus {through}")
            derived += 1
            continue
        if (port, before) not in ytd:
            continue
        b, nxt = ytd[(port, before)], month_vals[(port, through)][0]
        month_vals[(port, x)] = ({k: v[k] - b[k] - nxt[k] for k in v}, -1, f"derived: April-to-{through} minus April-to-{before} minus {through}")
        derived += 1
    rows = [{"month": m, "port": p, **v, "basis": basis} for (p, m), (v, _, basis) in month_vals.items()]
    df = pd.DataFrame(rows).sort_values(["month", "port"])
    df.to_csv(ROOT / "data" / "major_ports_monthly.csv", index=False)
    months = sorted(df["month"].unique())
    print(f"{len(reports)} reports -> data/major_ports_monthly.csv: {len(months)} months ({months[0]} to {months[-1]}), "
          f"{df['port'].nunique()} rows per month, {derived} port-months derived")


if __name__ == "__main__":
    main()
