"""
Major-port benchmark - how New Mangalore compares with the other 11 major ports.

Data (real): data/major_ports_ministry_<month>.csv, transcribed from Table-1 of the Ministry of Ports, Shipping
and Waterways monthly report "Cargo handled at Major Ports" (every port, overseas / coastal / total). The test
suite checks that each port's overseas + coastal = total and that the ports add up to the Ministry's all-port total.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services.forecasting import _ttl_cache

ROOT = Path(__file__).resolve().parents[3]
HOME = "New Mangalore"


def _monthly_trend() -> dict[str, Any] | None:
    """Month by month from data/major_ports_monthly.csv (scripts/parse_ministry_major_ports.py)."""
    f = ROOT / "data" / "major_ports_monthly.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    piv = d.pivot_table(index="month", columns="port", values="total_t")
    ports = [c for c in piv.columns if c != "All major ports"]
    rows = []
    for m in piv.index:
        if piv.loc[m, ports].isna().any():
            continue
        prev = f"{int(m[:4]) - 1}{m[4:]}"
        has_prev = prev in piv.index and not piv.loc[prev, ports].isna().any()
        rank = int(piv.loc[m, ports].rank(ascending=False)[HOME])
        g = lambda col: round(float(piv.loc[m, col] / piv.loc[prev, col] - 1) * 100, 2) if has_prev else None
        growth = {p: g(p) for p in ports} if has_prev else {}
        grank = (int(pd.Series(growth).rank(ascending=False)[HOME]) if has_prev else None)
        rows.append({"month": m, "tonnes": int(piv.loc[m, HOME]),
                     "share_of_major_ports_pct": round(float(piv.loc[m, HOME] / piv.loc[m, "All major ports"]) * 100, 2),
                     "rank_by_tonnes": rank, "growth_pct": g(HOME), "all_ports_growth_pct": g("All major ports"),
                     "rank_by_growth": grank})
    basis = d[d["port"] == HOME].set_index("month")["basis"]
    return {"months": rows, "derived_months": sorted(m for m, b in basis.items() if str(b).startswith("derived")),
            "data_file": "data/major_ports_monthly.csv"}


def _home_ytd(period: str) -> int | None:
    """New Mangalore's tonnes for the same April-to-date period as a non-major report (e.g. '2026-27 Apr-Jul')."""
    f = ROOT / "data" / "major_ports_monthly.csv"
    if not f.exists():
        return None
    fy, span = period.split(" ")
    names = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    n = names.index(span.split("-")[1]) + 1
    months = [d.strftime("%Y-%m") for d in pd.date_range(f"{fy[:4]}-04-01", periods=n, freq="MS")]
    d = pd.read_csv(f)
    nm = d[(d["port"] == HOME) & d["month"].isin(months)]
    return int(nm["total_t"].sum()) if len(nm) == n else None


def _regional() -> dict[str, Any] | None:
    """Non-major ports by state board (Ministry non-major report), for the coast around New Mangalore."""
    files = sorted((ROOT / "data").glob("non_major_ports_*.csv"))
    if not files:
        return None
    d = pd.read_csv(files[-1])
    ytd = sorted(p for p in d["period"].unique() if "Apr-" in p)
    cur, prev = ytd[-1], ytd[0]
    out = []
    for name, g in d.groupby("state_board"):
        c = g[g["period"] == cur].iloc[0]
        pv = g[g["period"] == prev].iloc[0]
        out.append({"state_board": name, "coast": c["coast"], "ytd_tonnes": int(c["total_t"]),
                    "ytd_prev_tonnes": int(pv["total_t"]),
                    "growth_pct": None if _pct(c["total_t"], pv["total_t"]) is None else float(_pct(c["total_t"], pv["total_t"]))})
    out.sort(key=lambda r: -r["ytd_tonnes"])
    near = [r for r in out if r["state_board"].split(" ")[0] in ("Karnataka", "Kerala", "Goa")]
    return {"period": cur, "boards": out, "neighbours": near,
            "neighbours_total_tonnes": sum(r["ytd_tonnes"] for r in near),
            "home_same_period_tonnes": _home_ytd(cur),
            "source": str(d["source"].iloc[0]), "data_file": f"data/{files[-1].name}"}


def _latest_file() -> Path | None:
    files = sorted((ROOT / "data").glob("major_ports_ministry_*.csv"))
    return files[-1] if files else None


def _pct(a: float, b: float) -> float | None:
    return round((a / b - 1) * 100, 2) if b else None


@_ttl_cache(seconds=300)
def get_benchmark() -> dict[str, Any]:
    f = _latest_file()
    if f is None:
        return {"available": False}
    d = pd.read_csv(f)
    periods = sorted(d["period"].unique())
    ytd_cur = [p for p in periods if "Apr-" in p][-1]
    ytd_prev = [p for p in periods if "Apr-" in p and p != ytd_cur][-1]
    mon_cur = [p for p in periods if "Apr-" not in p][-1]
    mon_prev = [p for p in periods if "Apr-" not in p and p != mon_cur][-1]
    w = d.pivot_table(index=["port", "coast"], columns="period", values=["overseas_t", "coastal_t", "total_t"], aggfunc="sum")
    all_cur = float(d.loc[d["period"] == ytd_cur, "total_t"].sum())
    all_prev = float(d.loc[d["period"] == ytd_prev, "total_t"].sum())
    rows = []
    for (port, coast), r in w.iterrows():
        rows.append({
            "port": port, "coast": coast, "is_home": port == HOME,
            "ytd_tonnes": int(r[("total_t", ytd_cur)]), "ytd_prev_tonnes": int(r[("total_t", ytd_prev)]),
            "ytd_growth_pct": _pct(r[("total_t", ytd_cur)], r[("total_t", ytd_prev)]),
            "overseas_growth_pct": _pct(r[("overseas_t", ytd_cur)], r[("overseas_t", ytd_prev)]),
            "coastal_growth_pct": _pct(r[("coastal_t", ytd_cur)], r[("coastal_t", ytd_prev)]),
            "coastal_share_pct": round(r[("coastal_t", ytd_cur)] / r[("total_t", ytd_cur)] * 100, 1),
            "share_of_all_ports_pct": round(r[("total_t", ytd_cur)] / all_cur * 100, 2),
            "month_tonnes": int(r[("total_t", mon_cur)]),
            "month_growth_pct": _pct(r[("total_t", mon_cur)], r[("total_t", mon_prev)]),
        })
    rows.sort(key=lambda x: -x["ytd_tonnes"])
    for i, x in enumerate(rows, 1):
        x["rank_by_tonnes"] = i
    for i, x in enumerate(sorted(rows, key=lambda x: -(x["ytd_growth_pct"] or -1e9)), 1):
        x["rank_by_growth"] = i
    home = next(x for x in rows if x["is_home"])
    west = [x for x in rows if x["coast"] == "west"]
    all_growth = _pct(all_cur, all_prev)
    months = {"Apr": "April", "May": "May", "Jun": "June", "Jul": "July", "Aug": "August", "Sep": "September", "Oct": "October",
              "Nov": "November", "Dec": "December", "Jan": "January", "Feb": "February", "Mar": "March"}
    fy, span = ytd_cur.split(" ")
    end = months[span.split("-")[1]]
    end_year = int(fy[:4]) + (1 if end in ("January", "February", "March") else 0)
    period_label = f"April to {end} {end_year}"
    for key, col in (("rank_overseas_growth", "overseas_growth_pct"), ("rank_coastal_growth", "coastal_growth_pct")):
        for i, x in enumerate(sorted(rows, key=lambda x: -(x[col] if x[col] is not None else -1e9)), 1):
            x[key] = i
    side = "above" if home["ytd_growth_pct"] > all_growth else "below"
    headline = (f"New Mangalore grew {home['ytd_growth_pct']:+.1f}% from {period_label}, {side} the {all_growth:+.1f}% of all major ports: "
                f"number {home['rank_by_growth']} of {len(rows)} for growth and number {home['rank_by_tonnes']} for tonnes")
    return {
        "available": True,
        "period": ytd_cur, "period_label": period_label, "previous_period": ytd_prev, "month": mon_cur,
        "all_ports_ytd_tonnes": int(all_cur), "all_ports_ytd_growth_pct": all_growth,
        "home": home, "headline": headline,
        "west_coast_rank_by_growth": sorted(west, key=lambda x: -(x["ytd_growth_pct"] or -1e9)).index(home) + 1,
        "west_coast_ports": len(west),
        "ports": rows,
        "trend": _monthly_trend(),
        "regional": _regional(),
        "source": str(d["source"].iloc[0]),
        "data_file": f"data/{f.name}",
        "limits": ["Current-year figures are the Ministry's advance estimates and can be revised.",
                   "SMP Kolkata is shown as one port (Kolkata Dock System + Haldia Dock Complex)."],
    }
