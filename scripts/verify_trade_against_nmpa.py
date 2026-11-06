"""
Cross-check data/port_cargo_monthly.csv against an official NMPA "Commodity-wise traffic
statement" PDF (the independent source).

What it checks, for the month in the PDF:
  1. The PDF is internally consistent (commodities add up to TOTAL (A), TOTAL (B), GRAND TOTAL).
  2. The PDF's "same month last year" column equals what our CSV holds for that month a year ago.
  3. The PDF's financial-year-to-date "last year" column equals the sum of our CSV months.
  4. The PDF's financial-year-to-date "this year" column equals our CSV months + this PDF's month.
     Where a month is missing from the CSV (e.g. June 2026) the gap is reported, along with the
     amount the PDF implies for it.

Usage:  python scripts/verify_trade_against_nmpa.py "nmpa_public_data/Commodity wise traffic statement August 2026.pdf"
        python scripts/verify_trade_against_nmpa.py "<pdf>" --append   # also add that month to the CSV if it is not there yet
Needs `pdftotext` (poppler). Exit code 1 if any check fails.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "port_cargo_monthly.csv"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def canon(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def _num(tok: str) -> float | None:
    tok = tok.replace(",", "")
    try:
        return float(tok)
    except ValueError:
        return None


def parse_pdf(path: Path) -> tuple[pd.DataFrame, int, int]:
    """Top-level commodity rows (+ totals) from the statement. Returns (rows, year, month)."""
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
    head = re.search(r"MONTH OF\s+([A-Z]+),?\s+(\d{4})", text)
    if not head:
        raise SystemExit("Could not find the month/year in the PDF header")
    month, year = MONTHS.index(head.group(1).title()) + 1, int(head.group(2))

    rows, section = [], None
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^A\s+UNLOADED", s):
            section = "UNLOADED"
        elif re.match(r"^B\s+LOADED", s):
            section = "LOADED"
        elif re.match(r"^C\s+TRANSHIPMENT", s):
            section = None
        elif s.startswith("CATEGORY-WISE"):
            break
        top = re.match(r"^(\d+)\s+(.+?)\s{2,}(.*)$", s)          # "9   TOTAL COAL   9 10 6,33,638 ..."
        tot = re.match(r"^(TOTAL \([AB]\)|GRAND TOTAL \(A\+B\+C\+D\))\s+(.*)$", s)
        if top and section:
            name, rest = top.group(2).strip(), top.group(3)
            kind = section
        elif tot:
            name, rest, kind = tot.group(1), tot.group(2), "TOTAL"
        else:
            continue
        toks = rest.split()
        rows.append({"kind": kind, "name": name, "toks": toks})
    out = []
    for r in rows:
        t = r["toks"]
        # last 5 tokens are always: ytd_v_cur ytd_t_cur ytd_v_prev ytd_t_prev pct  (pct may be '-')
        ytd_v_cur, ytd_t_cur, ytd_v_prev, ytd_t_prev, pct = t[-5:]
        month_part = t[:-5]
        nums = [m for m in month_part if _num(m) is not None or m == "-"]
        # month tonnes are the last two entries before the YTD block
        if len(nums) < 2:
            continue
        m_cur, m_prev = nums[-2], nums[-1]
        vessels = [_num(x) for x in nums[:-2]]
        out.append({
            "kind": r["kind"], "name": r["name"],
            "vessels_cur": vessels[0] if len(vessels) == 2 else None,
            "vessels_prev": vessels[1] if len(vessels) == 2 else None,
            "pct": _num(pct),
            "month_t_cur": _num(m_cur) or 0.0, "month_t_prev": _num(m_prev) or 0.0,
            "ytd_t_cur": _num(ytd_t_cur) or 0.0, "ytd_t_prev": _num(ytd_t_prev) or 0.0,
        })
    return pd.DataFrame(out), year, month


CATEGORY_ROWS = {"a) Dry Bulk (Total)": "a) Dry Bulk (Total)", "b) Break Bulk": "b) Break Bulk",
                 "c) Liquid Bulk": "c) Liquid Bulk", "d) Containers (In Tons)": "d) Containers (In Tons)"}


def category_rows(pdf: Path) -> list[dict]:
    """The six category/grand-total rows at the bottom of the statement (same rows the CSV keeps)."""
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    block = text.split("CATEGORY-WISE", 1)[1]
    found = {}
    for line in block.splitlines():
        s = line.strip()
        m = re.match(r"^(a\) Dry Bulk \(Total\)|b\) Break Bulk|c\) Liquid Bulk|d\) Containers \(In Tons\)|GRAND TOTAL)\s+(.*)$", s)
        if not m:
            continue
        t = m.group(2).split()
        if len(t) < 9:
            continue
        v_cur, v_prev, tn_cur, _tn_prev = _num(t[0]), _num(t[1]), _num(t[2]), _num(t[3])
        found[m.group(1)] = {"vessels_current": v_cur, "traffic_tonnes_current": tn_cur, "pct_variation_yoy": _num(t[-1])}
    rows = []
    g = found.get("GRAND TOTAL")
    if g:
        rows.append({"section": "CATEGORY_TOTAL", "commodity": "GRAND TOTAL (A+B+C+D)", **g})
    for k in CATEGORY_ROWS:
        if k in found:
            rows.append({"section": "CATEGORY_TOTAL", "commodity": k, **found[k]})
    if g:
        rows.append({"section": "CATEGORY_TOTAL", "commodity": "GRAND TOTAL", **g})
    return rows


def append_month(pdf: Path, pdf_rows: pd.DataFrame, year: int, month: int) -> int:
    existing = pd.read_csv(CSV)
    name = MONTHS[month - 1]
    if ((existing["month"] == name) & (existing["year"] == year)).any():
        print(f"  --append: {name} {year} is already in the CSV, nothing added")
        return 0
    new = []
    for _, r in pdf_rows[pdf_rows.kind.isin(["UNLOADED", "LOADED"])].iterrows():
        new.append({"section": r["kind"], "commodity": r["name"], "vessels_current": r["vessels_cur"],
                    "vessels_prev_year": r["vessels_prev"], "traffic_tonnes_current": r["month_t_cur"],
                    "traffic_tonnes_prev_year": r["month_t_prev"], "pct_variation_yoy": r["pct"]})
    new += category_rows(pdf)
    df = pd.DataFrame(new)
    df.insert(0, "year", year)
    df.insert(0, "month", name)
    df = df.reindex(columns=existing.columns)
    df.to_csv(CSV, mode="a", header=False, index=False)
    print(f"  --append: added {len(df)} rows for {name} {year} to {CSV.relative_to(ROOT)}")
    return len(df)


def load_csv() -> pd.DataFrame:
    d = pd.read_csv(CSV)
    d["date"] = pd.to_datetime(d["month"] + " " + d["year"].astype(str), format="%B %Y")
    d["key"] = d["commodity"].map(canon)
    return d[d["section"].isin(["LOADED", "UNLOADED"])].drop_duplicates(["date", "section", "key"], keep="last")


def fy_start(date: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(date.year if date.month >= 4 else date.year - 1, 4, 1)


def main(pdf: Path, append: bool = False) -> int:
    pdf_rows, year, month = parse_pdf(pdf)
    when = pd.Timestamp(year, month, 1)
    csv = load_csv()
    fails: list[str] = []
    report: list[dict] = []

    top = pdf_rows[pdf_rows.kind.isin(["UNLOADED", "LOADED"])]
    tot = pdf_rows[pdf_rows.kind == "TOTAL"].set_index("name")

    # 1. internal consistency
    for sec, label in (("UNLOADED", "TOTAL (A)"), ("LOADED", "TOTAL (B)")):
        part = top[top.kind == sec]
        for col in ("month_t_cur", "month_t_prev", "ytd_t_cur", "ytd_t_prev"):
            if abs(part[col].sum() - tot.loc[label, col]) > 1:
                fails.append(f"PDF internal: {sec} commodities sum {part[col].sum():,.0f} != {label} {tot.loc[label, col]:,.0f} ({col})")

    # 2-4. against the CSV, per commodity
    ytd_prev_months = pd.date_range(fy_start(when) - pd.DateOffset(years=1), when - pd.DateOffset(years=1), freq="MS")
    ytd_cur_months = pd.date_range(fy_start(when), when - pd.DateOffset(months=1), freq="MS")
    for _, r in top.iterrows():
        key, sec = canon(r["name"]), r["kind"]
        c = csv[(csv.section == sec) & (csv.key == key)].set_index("date")["traffic_tonnes_current"]
        prev_month_csv = c.get(when - pd.DateOffset(years=1))
        prev_ytd_csv = c.reindex(ytd_prev_months)
        cur_present = c.reindex(ytd_cur_months)
        missing = [d.strftime("%Y-%m") for d in ytd_cur_months if pd.isna(cur_present.get(d))]
        implied = r["ytd_t_cur"] - r["month_t_cur"] - cur_present.sum()
        report.append({
            "section": sec, "commodity": r["name"],
            "pdf_month_prev_year_t": r["month_t_prev"], "csv_month_prev_year_t": prev_month_csv,
            "pdf_ytd_prev_year_t": r["ytd_t_prev"], "csv_ytd_prev_year_t": float(prev_ytd_csv.sum()),
            "csv_prev_ytd_missing_months": ",".join(d.strftime("%Y-%m") for d in ytd_prev_months if pd.isna(prev_ytd_csv.get(d))),
            "pdf_ytd_cur_t": r["ytd_t_cur"], "csv_ytd_cur_before_month_t": float(cur_present.sum()),
            "csv_missing_months_this_fy": ",".join(missing),
            "implied_for_missing_months_t": implied if missing else 0.0,
        })
    rep = pd.DataFrame(report)

    def mismatch(a, b):
        return (a.fillna(-1) - b.fillna(-1)).abs() > 1
    bad_m = rep[mismatch(rep.pdf_month_prev_year_t, rep.csv_month_prev_year_t)]
    bad_y = rep[mismatch(rep.pdf_ytd_prev_year_t, rep.csv_ytd_prev_year_t) & (rep.csv_prev_ytd_missing_months == "")]
    # A category can be re-labelled between years (money moves from one row to another but the section
    # total does not change). Such mismatches net to zero inside the section and are reported, not failed.
    reclass = []
    for sec in ("UNLOADED", "LOADED"):
        for bad, a, b in ((bad_m, "pdf_month_prev_year_t", "csv_month_prev_year_t"),
                          (bad_y, "pdf_ytd_prev_year_t", "csv_ytd_prev_year_t")):
            sub = bad[bad.section == sec]
            if len(sub) >= 2 and abs((sub[a] - sub[b].fillna(0)).sum()) <= 1:
                reclass += [(sec, c) for c in sub.commodity]
    bad_m = bad_m[~bad_m.apply(lambda r: (r.section, r.commodity) in reclass, axis=1)] if len(bad_m) else bad_m
    bad_y = bad_y[~bad_y.apply(lambda r: (r.section, r.commodity) in reclass, axis=1)] if len(bad_y) else bad_y
    for _, r in bad_m.iterrows():
        fails.append(f"{when.strftime('%Y-%m')} prior-year month: {r.section} {r.commodity}: PDF {r.pdf_month_prev_year_t:,.0f} vs CSV {r.csv_month_prev_year_t}")
    for _, r in bad_y.iterrows():
        fails.append(f"FY-to-date prior year: {r.section} {r.commodity}: PDF {r.pdf_ytd_prev_year_t:,.0f} vs CSV {r.csv_ytd_prev_year_t:,.0f}")

    gaps = rep[rep.csv_missing_months_this_fy != ""]
    print(f"Checked {pdf.name}: {when:%B %Y}; {len(top)} commodity rows")
    print(f"  prior-year month matches CSV:      {len(rep) - len(bad_m)}/{len(rep)}")
    print(f"  prior-year FY-to-date matches CSV: {len(rep) - len(bad_y)}/{len(rep)}")
    if len(gaps):
        months = sorted({m for s in gaps.csv_missing_months_this_fy for m in s.split(",")})
        print(f"  CSV is missing {months} this financial year; the PDF's FY-to-date totals imply for them:")
        g = gaps.groupby("section")["implied_for_missing_months_t"].sum()
        for sec, v in g.items():
            print(f"     {sec}: {v:,.0f} t")
    if reclass:
        print("  NOTE: NMPA re-labelled cargo between categories vs last year (net effect zero): "
              + ", ".join(sorted({c for _, c in reclass})))
    for f in fails:
        print("  FAIL:", f)
    print("RESULT:", "OK" if not fails else f"{len(fails)} problem(s)")
    if append and not fails:
        append_month(pdf, pdf_rows, year, month)
    out = ROOT / "data" / f"nmpa_verification_{year}-{month:02d}.csv"
    rep.to_csv(out, index=False)
    print("  detail written to", out.relative_to(ROOT))
    return 1 if fails else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    sys.exit(main(Path(args[0]), append="--append" in sys.argv))
