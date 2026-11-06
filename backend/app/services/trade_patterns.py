"""
Commodity patterns - the seasonal shape of each cargo, and how the port's cargo mix has shifted year by year.

Data (real): NMPA monthly commodity-wise statements (data/port_cargo_monthly.csv, via trade_intelligence._prepared()),
January 2022 onward. Years are NMPA financial years (April to March).

Seasonal index for a month = that month's tonnes / the average month of the same financial year, averaged over the
complete financial years held. 100 = an average month; 130 = 30% busier than average.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import trade_intelligence as ti
from backend.app.services.forecasting import _ttl_cache

FY_MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
DIRECTIONS = {"UNLOADED": "inbound", "LOADED": "outbound"}


def _fy(d: pd.Timestamp) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def _fy_pos(d: pd.Timestamp) -> int:
    return (d.month - 4) % 12          # Apr = 0 ... Mar = 11


@_ttl_cache(seconds=300)
def get_seasonality(name: str) -> dict[str, Any] | None:
    p = ti._prepared()
    key = ti._canon(name)
    wide = p["wide"]
    out = {}
    for section, direction in DIRECTIONS.items():
        if (section, key) not in wide.columns:
            continue
        s = wide[(section, key)]
        if s.fillna(0).sum() == 0:
            continue
        df = pd.DataFrame({"t": s})
        df["fy"] = [_fy(d) for d in df.index]
        df["pos"] = [_fy_pos(d) for d in df.index]
        counts = df.dropna(subset=["t"]).groupby("fy").size()
        full = [fy for fy, n in counts.items() if n == 12]
        years = {fy: [None if pd.isna(v) else round(float(v)) for v in
                      g.set_index("pos")["t"].reindex(range(12)).tolist()]
                 for fy, g in df.groupby("fy") if counts.get(fy, 0) >= 3}
        idx = None
        consistency = None
        busiest = quietest = []
        if full:
            ratios = []
            for fy in full:
                g = df[df["fy"] == fy].set_index("pos")["t"].reindex(range(12))
                mean = g.mean()
                if mean and mean > 0:
                    ratios.append(g / mean * 100)
            if ratios:
                mat = pd.concat(ratios, axis=1, ignore_index=True)
                mean_profile = mat.mean(axis=1)
                # How much the years agree with each other: median correlation of each year with the average shape.
                cors = [mat.iloc[:, c].corr(mean_profile) for c in range(mat.shape[1]) if mat.iloc[:, c].std() > 0]
                consistency = float(np.nanmedian(cors)) if cors else None
                idx = mean_profile.round(0)
                order = idx.sort_values()
                quietest = [FY_MONTHS[i] for i in order.index[:3]]
                busiest = [FY_MONTHS[i] for i in order.index[::-1][:3]]
                idx = [None if pd.isna(v) else int(v) for v in idx.tolist()]
        active = float((df[df["fy"].isin(full)]["t"].fillna(0) > 0).mean()) if full else 0.0   # share of months with cargo
        swing = None
        if idx and all(v is not None for v in idx):
            swing = int(max(idx) - min(idx))
        out[direction] = {"years": years, "complete_years": full, "seasonal_index": idx,
                          "busiest_months": busiest, "quietest_months": quietest, "swing_points": swing,
                          "year_to_year_consistency": None if consistency is None else round(consistency, 2),
                          # A pattern is 'regular' when the years broadly agree on the shape (median correlation >= 0.4).
                          "months_with_cargo_pct": round(active * 100),
                          "regular": (consistency is not None and consistency >= 0.4 and swing is not None and swing >= 20
                                      and active >= 0.75)}
    if not out:
        return None
    return {"commodity": p["names"].get(key, name), "months": FY_MONTHS, "directions": out,
            "note": "Financial years April to March. Seasonal index 100 = an average month of that year, "
                    "averaged over the complete years held. 2021-22 holds January to March 2022 only.",
            "source": "NMPA monthly commodity-wise traffic statements"}


@_ttl_cache(seconds=300)
def get_cargo_mix() -> dict[str, Any]:
    """Each cargo's tonnes and share of the port's cargo, financial year by financial year."""
    p = ti._prepared()
    wide = p["wide"]
    df = wide.copy()
    df["fy"] = [_fy(d) for d in df.index]
    months_held = df.groupby("fy").size()
    fys = [fy for fy in months_held.index if months_held[fy] >= 6]
    totals = df.groupby("fy").sum(min_count=1)
    rows = []
    for (section, key) in wide.columns:
        vals = {fy: totals.loc[fy, (section, key)] for fy in fys}
        if all(pd.isna(v) or v == 0 for v in vals.values()):
            continue
        rows.append({"cargo": p["names"].get(key, key), "direction": DIRECTIONS[section],
                     "tonnes": {fy: None if pd.isna(v) else round(float(v)) for fy, v in vals.items()}})
    fy_total = {fy: sum((r["tonnes"][fy] or 0) for r in rows) for fy in fys}
    for r in rows:
        r["share_pct"] = {fy: round(r["tonnes"][fy] / fy_total[fy] * 100, 1) if r["tonnes"][fy] and fy_total[fy] else 0.0
                          for fy in fys}
    first_full = next((fy for fy in fys if months_held[fy] == 12), fys[0])
    last = fys[-1]
    for r in rows:
        r["share_change_points"] = round(r["share_pct"][last] - r["share_pct"][first_full], 1)
    rows.sort(key=lambda r: -(r["tonnes"][last] or 0))
    return {"financial_years": fys, "months_held": {fy: int(months_held[fy]) for fy in fys},
            "totals_tonnes": {fy: round(v) for fy, v in fy_total.items()},
            "compare_from": first_full, "compare_to": last, "cargos": rows,
            "source": "NMPA monthly commodity-wise traffic statements"}
