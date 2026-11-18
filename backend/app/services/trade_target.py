"""
Annual target tracker - is New Mangalore Port on course for its cargo target?

Data (all real):
  * data/port_targets.csv                    the target NMPA announced for each financial year, with its public source.
  * data/port_overseas_coastal_monthly.csv   Ministry monthly totals for New Mangalore. These include shore handling,
                                             like NMPA's announced figures, and equal NMPA's own "Traffic & Performance"
                                             totals (checked: August 2026 = 3,885,913 t in both).
  * data/port_cargo_monthly.csv              NMPA monthly commodity statements, used for months the Ministry file does
                                             not cover, plus the average shore handling measured where both exist.

Method (plain arithmetic, no model):
  done      = official tonnes from April to the latest month
  needed    = (target - done) / months left
  pace A    = done + the same remaining months of last year
  pace B    = done + last year's remaining months grown at this year's growth so far
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import trade_intelligence as ti
from backend.app.services.forecasting import _ttl_cache

ROOT = Path(__file__).resolve().parents[3]
TARGETS = ROOT / "data" / "port_targets.csv"
MINISTRY = ROOT / "data" / "port_overseas_coastal_monthly.csv"


def _fy_start(d: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(d.year if d.month >= 4 else d.year - 1, 4, 1)


def _fy_label(start: pd.Timestamp) -> str:
    return f"{start.year}-{str(start.year + 1)[2:]}"


def _shore_per_month(totals: pd.Series) -> tuple[float, int]:
    """Average monthly shore handling = Ministry total minus NMPA loaded + unloaded, over months both have."""
    off = _ministry_totals()
    diffs = [float(v) - float(totals[d]) for d, v in off.items() if d in totals.index and pd.notna(totals[d])]
    return (float(np.mean(diffs)) if diffs else 0.0), len(diffs)


def _ministry_totals() -> pd.Series:
    """Official monthly totals for New Mangalore from the Ministry file, including its 'same month last year' columns."""
    if not MINISTRY.exists():
        return pd.Series(dtype=float)
    m = pd.read_csv(MINISTRY)
    vals: dict[pd.Timestamp, float] = {}
    for _, r in m.iterrows():
        d = pd.Timestamp(r["month"] + "-01")
        prev = d - pd.DateOffset(years=1)
        if pd.notna(r.get("prev_year_total_t")) and prev not in vals:
            vals[prev] = float(r["prev_year_total_t"])
        vals[d] = float(r["total_t"])          # a month's own report wins over a later prior-year column
    # The all-port monthly file (every Ministry report held, March 2024 onward) fills months the overseas/coastal file lacks.
    mp_file = ROOT / "data" / "major_ports_monthly.csv"
    if mp_file.exists():
        mp = pd.read_csv(mp_file)
        for _, r in mp[mp["port"] == "New Mangalore"].iterrows():
            d = pd.Timestamp(r["month"] + "-01")
            vals.setdefault(d, float(r["total_t"]))
    return pd.Series(vals).sort_index()


def official_monthly_totals(totals: pd.Series) -> tuple[pd.Series, pd.Series, float, int]:
    """Best official figure per month: Ministry total where held, else NMPA statement + average shore handling.
    Returns (tonnes, basis, shore_per_month, months_compared)."""
    shore_m, shore_n = _shore_per_month(totals)
    off = _ministry_totals()
    idx = totals.index.union(off.index)
    tonnes, basis = {}, {}
    for d in idx:
        if d in off.index:
            tonnes[d], basis[d] = off[d], "ministry"
        elif d in totals.index and pd.notna(totals[d]):
            tonnes[d], basis[d] = float(totals[d]) + shore_m, "nmpa_statement_plus_shore"
    return pd.Series(tonnes).sort_index(), pd.Series(basis).sort_index(), shore_m, shore_n


@_ttl_cache(seconds=300)
def get_target_tracker() -> dict[str, Any]:
    p = ti._prepared()
    totals, basis, shore_m, shore_n = official_monthly_totals(p["totals"]["total"])
    latest = totals.index.max()
    start = _fy_start(latest)
    label = _fy_label(start)
    t = pd.read_csv(TARGETS, dtype={"financial_year": str}) if TARGETS.exists() else pd.DataFrame()
    row = t[t["financial_year"] == label] if not t.empty else t
    if row.empty:
        return {"available": False, "note": f"No target for {label} in data/port_targets.csv."}
    target = float(row.iloc[0]["target_tonnes"])

    done_months = pd.date_range(start, latest, freq="MS")
    left_months = pd.date_range(latest + pd.DateOffset(months=1), start + pd.DateOffset(months=11), freq="MS")
    done_vals = totals.reindex(done_months)
    if done_vals.isna().any():
        missing = [d.strftime("%Y-%m") for d in done_months[done_vals.isna()]]
        return {"available": False, "note": f"Months missing this financial year: {', '.join(missing)}."}
    done = float(done_vals.sum())
    prev_same = totals.reindex(done_months - pd.DateOffset(years=1))
    prev_left = totals.reindex(left_months - pd.DateOffset(years=1))
    prev_done = float(prev_same.sum()) if prev_same.notna().all() else None
    prev_rest = float(prev_left.sum()) if prev_left.notna().all() else None
    growth = (done / prev_done - 1) * 100 if prev_done else None

    n_left = len(left_months)
    needed_total = target - done
    needed_month = needed_total / n_left if n_left else None
    pace_a = done + prev_rest if prev_rest is not None else None
    pace_b = done + prev_rest * (1 + growth / 100) if (prev_rest is not None and growth is not None) else None
    growth_needed = (needed_total / prev_rest - 1) * 100 if prev_rest else None
    last_m = done_months[-1]
    month_growth = (totals[last_m] / totals[last_m - pd.DateOffset(years=1)] - 1) * 100 \
        if (last_m - pd.DateOffset(years=1)) in totals.index else None
    first, last = done_months[0].strftime("%b %Y"), latest.strftime("%b %Y")
    rest_lbl = f"{left_months[0].strftime('%b %Y')} to {left_months[-1].strftime('%b %Y')}" if n_left else ""

    r1 = lambda x: None if x is None else round(float(x), 1)
    r0 = lambda x: None if x is None else round(float(x))
    verdict = None
    if pace_a is not None and growth_needed is not None:
        gap = target - pace_a
        verdict = (
            f"{label} target {target / 1e6:.0f} MMT. Handled {done / 1e6:.2f} MMT from {first} to {last} "
            f"({growth:+.1f}% on the same months last year). The remaining {n_left} months need "
            f"{needed_month / 1e6:.2f} MMT a month, {growth_needed:+.1f}% on the same months last year. "
            + (f"If they only repeat last year, the year ends near {pace_a / 1e6:.1f} MMT, {gap / 1e6:.1f} MMT short."
               if gap > 0 else f"Even repeating last year would reach {pace_a / 1e6:.1f} MMT, above the target.")
        )
    return {
        "available": True,
        "financial_year": label,
        "target_tonnes": r0(target),
        "target_source": str(row.iloc[0]["source"]),
        "target_source_url": str(row.iloc[0]["source_url"]),
        "months_done": [d.strftime("%Y-%m") for d in done_months],
        "months_left": [d.strftime("%Y-%m") for d in left_months],
        "basis_by_month": {d.strftime("%Y-%m"): basis.get(d) for d in list(done_months) + list(left_months - pd.DateOffset(years=1))},
        "latest_month": last_m.strftime("%Y-%m"),
        "latest_month_growth_pct": r1(month_growth),
        "done_tonnes": r0(done),
        "done_share_of_target_pct": r1(done / target * 100),
        "same_months_last_year_tonnes": r0(prev_done),
        "growth_so_far_pct": r1(growth),
        "remaining_months_last_year_tonnes": r0(prev_rest),
        "needed_per_month_tonnes": r0(needed_month),
        "last_year_same_months_per_month_tonnes": r0(prev_rest / n_left) if (prev_rest and n_left) else None,
        "growth_needed_on_last_year_pct": r1(growth_needed),
        "projection_if_same_as_last_year_tonnes": r0(pace_a),
        "projection_if_growth_continues_tonnes": r0(pace_b),
        "shore_handling_per_month_tonnes": r0(shore_m),
        "shore_handling_months_compared": shore_n,
        "monthly": [{"month": d.strftime("%Y-%m"), "this_year_tonnes": r0(totals.get(d)) if d in done_months else None,
                     "last_year_tonnes": r0(totals.get(d - pd.DateOffset(years=1)))}
                    for d in list(done_months) + list(left_months)],
        "remaining_label": rest_lbl,
        "verdict": verdict,
        "how_it_works": [
            "Monthly tonnes are the Ministry's official totals for New Mangalore, which include shore handling like NMPA's "
            "announced figures (August 2026: 3,885,913 t, the same as NMPA's own Traffic & Performance report).",
            "Months the Ministry file does not cover use NMPA's commodity statement plus the average shore handling "
            "measured where both sources exist.",
            "'Needed per month' spreads what is left of the target evenly over the remaining months.",
            "Projections are arithmetic, not forecasts: last year's remaining months as they were, or grown at this year's rate so far.",
        ],
        "limits": [
            "Seasonal swings are taken from last year only. The real peak (December to March) can differ.",
            "The target is as announced publicly; NMPA may track a revised internal figure.",
        ],
    }


@_ttl_cache(seconds=300)
def get_target_by_cargo() -> dict[str, Any]:
    """
    Which cargos are behind or ahead this financial year, from NMPA's commodity statements:
    tonnes from April to the latest statement against the same months last year, per cargo and direction,
    plus what each cargo handled in the remaining months last year (its normal contribution to the rest of the year).
    """
    p = ti._prepared()
    wide = p["wide"]
    latest = wide.index.max()
    start = _fy_start(latest)
    done = pd.date_range(start, latest, freq="MS")
    prev = done - pd.DateOffset(years=1)
    rest_prev = pd.date_range(latest + pd.DateOffset(months=1), start + pd.DateOffset(months=11), freq="MS") - pd.DateOffset(years=1)
    rows = []
    for (section, key) in wide.columns:
        cur = wide[(section, key)].reindex(done)
        old = wide[(section, key)].reindex(prev)
        if cur.isna().all() and old.isna().all():
            continue
        c, o = float(cur.fillna(0).sum()), float(old.fillna(0).sum())
        r = float(wide[(section, key)].reindex(rest_prev).fillna(0).sum())
        name = p["names"].get(key, key)
        rows.append({"cargo": name, "direction": "inbound" if section == "UNLOADED" else "outbound",
                     "this_year_tonnes": round(c), "same_months_last_year_tonnes": round(o),
                     "change_tonnes": round(c - o), "change_pct": round((c / o - 1) * 100, 1) if o else None,
                     "rest_of_year_last_year_tonnes": round(r)})
    total_change = sum(x["change_tonnes"] for x in rows)
    rows.sort(key=lambda x: x["change_tonnes"])
    return {"available": True, "from": start.strftime("%Y-%m"), "to": latest.strftime("%Y-%m"),
            "total_change_tonnes": round(total_change), "cargos": rows,
            "note": "NMPA commodity statements (shore handling not included). Change = this year so far minus the same months last year."}
