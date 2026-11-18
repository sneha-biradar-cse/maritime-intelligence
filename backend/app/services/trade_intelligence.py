"""
trade_intelligence.py — Real cargo-flow analytics for New Mangalore Port (NMPA)
-------------------------------------------------------------------------------
Everything here is computed from ``data/port_cargo_monthly.csv`` (the NMPA monthly
commodity-wise traffic statements). Nothing is simulated.

What "inbound" and "outbound" mean
    The NMPA statements split cargo into UNLOADED (cargo arriving at the port) and
    LOADED (cargo leaving it). The source does NOT separate foreign trade from
    coastal movement, so these are *all* cargo flows, not strictly imports/exports.
    The API labels them "inbound" and "outbound" for that reason.

Design decisions (each one was checked against the data, see tests/):

1. Only months from 2023-01 onward are used. 2021 uses a different, itemised cargo
   list (57 loaded labels vs 9 today) and contains duplicate rows; it cannot be
   compared like-for-like with 2023+.

2. 2022 is missing from the file, but every 2023 row carries the same month of the
   previous year (``traffic_tonnes_prev_year``). Those figures are used to rebuild
   2022, flagged as ``reconstructed``. They were cross-checked against reports that
   exist in both places (see ``prior_year_crosscheck`` in the data-quality block);
   treat reconstructed months as approximate because later reports can revise them.

3. Year-on-year is recomputed from tonnes, matched by *calendar date*. The file's own
   ``pct_variation_yoy`` column is NOT monthly: it is the financial-year-to-date
   (April-start) variation, so using it as a monthly YoY would be wrong.

4. Missing months stay missing (never zero) and are listed in the data-quality block.
   Windows only compare months present in both years, and report how many were used.

5. Momentum = fast EMA (span 3 months) vs slow EMA (span 12 months) of the monthly
   series, as a percentage. EMAs are time-aware so gaps do not distort them. It does
   not remove seasonality, and cargos that move in fewer than 6 of the last 12 months
   are labelled "Irregular" instead of being given a misleading trend.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from backend.app.services.forecasting import _ttl_cache, load_cargo_dataset

INBOUND = "UNLOADED"
OUTBOUND = "LOADED"
DIRECTION = {INBOUND: "inbound", OUTBOUND: "outbound"}
SECTION = {v: k for k, v in DIRECTION.items()}

FIRST_CONSISTENT_MONTH = pd.Timestamp("2023-01-01")
FAST_SPAN_MONTHS = 3
SLOW_SPAN_MONTHS = 12
MOMENTUM_THRESHOLD_PCT = 5.0   # |momentum| at or above this is "Rising"/"Falling"
MIN_ACTIVE_MONTHS = 6          # of the last 12 months, else "Irregular"
MIN_SHARE_FOR_MOVERS_PCT = 1.0 # ignore tiny cargos when listing top movers
DAYS_PER_MONTH = 30.4375


# ═══════════════════════════════════════════════════════════════════
# Small helpers
# ═══════════════════════════════════════════════════════════════════

def _num(x: Any, nd: int = 1) -> float | None:
    """JSON-safe number: NaN/inf/None -> None (Starlette rejects NaN in responses)."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


def _month(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m")


def _canon(name: str) -> str:
    """'OTH.LIQ.CARGOES' (loaded) and 'OTH. LIQ. CARGOES' (unloaded) are one cargo."""
    return re.sub(r"[^A-Z0-9]", "", str(name).upper())


def _pct_change(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or not np.isfinite(cur) or not np.isfinite(prev) or prev <= 0:
        return None
    return (cur / prev - 1.0) * 100.0


# ═══════════════════════════════════════════════════════════════════
# 1. Build the tidy flow table
# ═══════════════════════════════════════════════════════════════════

def build_flow_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tidy table of LOADED/UNLOADED cargo: one row per (month, section, cargo).
    Columns: date, section, key, commodity, tonnes, source ('report' | 'prior_year_column').

    ``df`` is the frame returned by ``forecasting.load_cargo_dataset()``.
    """
    d = df[df["section"].isin([INBOUND, OUTBOUND]) & (df["date"] >= FIRST_CONSISTENT_MONTH)].copy()
    d["key"] = d["commodity"].map(_canon)

    reported = d[["date", "section", "key", "commodity"]].copy()
    reported["tonnes"] = d["traffic_tonnes_current"].astype(float)
    reported["source"] = "report"
    n_before = len(reported)
    reported = reported.drop_duplicates(["date", "section", "key"], keep="last")
    duplicates_dropped = n_before - len(reported)

    # Rebuild earlier months from each row's "same month last year" figure, but only
    # where no real report row exists for that month (so real data always wins).
    prior = d[["date", "section", "key", "commodity"]].copy()
    prior["date"] = prior["date"] - pd.DateOffset(years=1)
    prior["tonnes"] = d["traffic_tonnes_prev_year"].astype(float)
    prior["source"] = "prior_year_column"
    prior = prior.drop_duplicates(["date", "section", "key"], keep="last")
    existing = pd.MultiIndex.from_frame(reported[["date", "section", "key"]])
    prior = prior[~pd.MultiIndex.from_frame(prior[["date", "section", "key"]]).isin(existing)]

    # A month missing from the CSV but covered by a verified NMPA statement's financial-year-to-date
    # column: FY-to-date (this statement) minus the months we hold = that month, exactly. Used only when
    # a single month is missing, so the difference can belong to nothing else. See scripts/verify_trade_against_nmpa.py.
    derived = _derived_months_from_verification(set(pd.MultiIndex.from_frame(reported[["date", "section", "key"]])))

    flow = (
        pd.concat([reported, prior, derived], ignore_index=True)
        .sort_values(["date", "section", "key"])
        .reset_index(drop=True)
    )
    flow.attrs["duplicates_dropped"] = int(duplicates_dropped)
    return flow


DERIVED_SOURCE = "derived_from_fy_to_date"


def _derived_months_from_verification(existing: set) -> pd.DataFrame:
    """Rows for a missing month, from data/nmpa_verification_YYYY-MM.csv files written by the verify script."""
    from pathlib import Path
    cols = ["date", "section", "key", "commodity", "tonnes", "source"]
    rows = []
    for f in sorted((Path(__file__).resolve().parents[3] / "data").glob("nmpa_verification_*.csv")):
        v = pd.read_csv(f)
        need = {"section", "commodity", "csv_missing_months_this_fy", "implied_for_missing_months_t"}
        if not need <= set(v.columns):
            continue
        for _, r in v.iterrows():
            missing = str(r["csv_missing_months_this_fy"] or "")
            if not missing or missing == "nan" or "," in missing or pd.isna(r["implied_for_missing_months_t"]):
                continue                      # none missing, or several: cannot split the difference
            key = (pd.Timestamp(missing + "-01"), r["section"], _canon(r["commodity"]))
            if key in existing:
                continue
            rows.append({"date": key[0], "section": key[1], "key": key[2], "commodity": r["commodity"],
                         "tonnes": float(r["implied_for_missing_months_t"]), "source": DERIVED_SOURCE})
    return pd.DataFrame(rows, columns=cols)


def _prior_year_crosscheck(df: pd.DataFrame) -> dict:
    """
    How far can the prior-year column be trusted? For every (cargo, month) that exists
    both as a real report AND as the prior-year column of the following year's report,
    compare the two figures.
    """
    d = df[df["section"].isin([INBOUND, OUTBOUND]) & (df["date"] >= FIRST_CONSISTENT_MONTH)].copy()
    d["key"] = d["commodity"].map(_canon)
    cur = (
        d.drop_duplicates(["date", "section", "key"], keep="last")
        .rename(columns={"traffic_tonnes_current": "earlier_report"})[["date", "section", "key", "earlier_report"]]
        .rename(columns={"date": "target"})
    )
    later = d.assign(target=d["date"] - pd.DateOffset(years=1))[["target", "section", "key", "traffic_tonnes_prev_year"]]
    m = later.merge(cur, on=["target", "section", "key"], how="inner")
    if m.empty:
        return {"pairs_compared": 0, "exact_match": 0, "exact_match_pct": None, "total_tonnes_difference_pct": None}
    exact = int(((m["traffic_tonnes_prev_year"] - m["earlier_report"]).abs() < 0.5).sum())
    total_cur = float(m["earlier_report"].sum())
    total_diff = (float(m["traffic_tonnes_prev_year"].sum()) - total_cur) / total_cur * 100 if total_cur else None
    return {
        "pairs_compared": int(len(m)),
        "exact_match": exact,
        "exact_match_pct": _num(exact / len(m) * 100, 1),
        "total_tonnes_difference_pct": _num(total_diff, 2),
    }


@_ttl_cache(seconds=300)
def _prepared() -> dict:
    """Load once, build every derived structure the public functions need."""
    df = load_cargo_dataset()
    flow = build_flow_table(df)

    wide = flow.pivot_table(index="date", columns=["section", "key"], values="tonnes", aggfunc="sum")
    wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="MS"))  # calendar-continuous

    totals = pd.DataFrame(index=wide.index)
    for section in (INBOUND, OUTBOUND):
        block = wide[section]
        total = block.sum(axis=1, min_count=1)
        # A month that lists fewer cargos than usual would under-count: treat as missing.
        total[block.notna().sum(axis=1) < block.shape[1]] = np.nan
        totals[DIRECTION[section]] = total
    totals["total"] = totals["inbound"] + totals["outbound"]

    names: dict[str, str] = {}
    for key, raw in zip(flow["key"], flow["commodity"]):
        if len(raw) > len(names.get(key, "")):
            names[key] = raw  # prefer the spaced spelling, e.g. 'OTH. LIQ. CARGOES'

    report_dates = set(flow.loc[flow["source"] == "report", "date"])
    derived_dates = set(flow.loc[flow["source"] == DERIVED_SOURCE, "date"]) - report_dates
    reconstructed = sorted(set(flow["date"]) - report_dates - derived_dates)
    present = totals["total"].dropna().index
    partial = [
        _month(d) for d in wide.index
        if wide.loc[d].notna().any() and np.isnan(totals.loc[d, "total"])
    ]
    data_quality = {
        "first_month": _month(wide.index.min()),
        "latest_month": _month(present.max()),
        "months_in_span": int(len(wide.index)),
        "months_with_data": int(len(present)),
        "missing_months": [_month(d) for d in wide.index if d not in present and d not in partial],
        "incomplete_months": partial,
        "reconstructed_months": [_month(d) for d in reconstructed],
        "derived_months": [_month(d) for d in sorted(derived_dates)],
        "duplicates_dropped": flow.attrs.get("duplicates_dropped", 0),
        "prior_year_crosscheck": _prior_year_crosscheck(df),
        "notes": [
            "Inbound = UNLOADED cargo, outbound = LOADED cargo. The source does not separate "
            "foreign trade from coastal movement, so these are total cargo flows.",
            "Only months from 2023-01 are used; earlier data uses a different itemised cargo list.",
            "Reconstructed months come from the prior-year column of the following year's report "
            "and may differ slightly from the originally published figures.",
            "Year-on-year is recalculated from tonnes. The file's pct_variation_yoy column is "
            "financial-year-to-date (April start), not a monthly change.",
            "Missing months are shown as missing, never as zero.",
        ] + ([f"{', '.join(_month(d) for d in sorted(derived_dates))}: no statement held, so derived exactly from the next "
              "statement's financial-year-to-date total minus the months held. Marked 'derived'."] if derived_dates else []),
    }
    return {
        "wide": wide,
        "totals": totals,
        "names": names,
        "latest": present.max(),
        "reconstructed": set(reconstructed),
        "derived": derived_dates,
        "data_quality": data_quality,
    }


# ═══════════════════════════════════════════════════════════════════
# 2. Calculations
# ═══════════════════════════════════════════════════════════════════

def _window_compare(series: pd.Series, end: pd.Timestamp, n_months: int) -> tuple[float, float, float | None, int]:
    """
    Sum of the last ``n_months`` ending at ``end`` vs the same calendar months a year
    earlier, using only months present in BOTH. Returns (current, previous, yoy_pct, months_used).
    Matching by calendar date (not row position) keeps gaps from shifting the comparison.
    """
    months = pd.date_range(end=end, periods=n_months, freq="MS")
    cur = series.reindex(months)
    prev = series.reindex(months - pd.DateOffset(years=1))
    ok = cur.notna().to_numpy() & prev.notna().to_numpy()
    cur_sum = float(cur.to_numpy()[ok].sum())
    prev_sum = float(prev.to_numpy()[ok].sum())
    return cur_sum, prev_sum, _pct_change(cur_sum, prev_sum), int(ok.sum())


def _ema(series: pd.Series, span_months: int) -> pd.Series:
    """Time-aware exponential moving average (observations need not be evenly spaced)."""
    s = series.dropna()
    if s.empty:
        return s
    alpha = 2.0 / (span_months + 1)
    half_life_days = np.log(0.5) / np.log(1.0 - alpha) * DAYS_PER_MONTH
    return s.ewm(halflife=pd.Timedelta(days=half_life_days), times=s.index).mean()


def _momentum(series: pd.Series) -> dict:
    """Fast-vs-slow EMA momentum for one monthly series (calendar-continuous, NaN = missing)."""
    observed = series.dropna()
    active = int((series.iloc[-12:].fillna(0) > 0).sum())
    out = {"momentum_pct": None, "signal": "Insufficient data", "active_months_12": active}
    if len(observed) < SLOW_SPAN_MONTHS // 2:
        return out
    fast = float(_ema(observed, FAST_SPAN_MONTHS).iloc[-1])
    slow = float(_ema(observed, SLOW_SPAN_MONTHS).iloc[-1])
    pct = _pct_change(fast, slow)
    out["momentum_pct"] = _num(pct, 1)
    if active < MIN_ACTIVE_MONTHS:
        out["signal"] = "Irregular"
    elif pct is None:
        out["signal"] = "Insufficient data"
    elif pct >= MOMENTUM_THRESHOLD_PCT:
        out["signal"] = "Rising"
    elif pct <= -MOMENTUM_THRESHOLD_PCT:
        out["signal"] = "Falling"
    else:
        out["signal"] = "Steady"
    return out


def _commodity_rows(p: dict) -> list[dict]:
    wide, names, latest = p["wide"], p["names"], p["latest"]
    rows: list[dict] = []
    for section in (INBOUND, OUTBOUND):
        block = wide[section]
        cur12 = {k: _window_compare(block[k], latest, 12) for k in block.columns}
        direction_total = sum(v[0] for v in cur12.values()) or float("nan")
        for key in block.columns:
            s = block[key]
            c12, p12, yoy12, used12 = cur12[key]
            _, _, yoy3, used3 = _window_compare(s, latest, 3)
            latest_t = s.get(latest)
            last_year_t = s.get(latest - pd.DateOffset(years=1))
            rows.append({
                "commodity": names[key],
                "direction": DIRECTION[section],
                "latest_month_tonnes": _num(latest_t, 0),
                "same_month_last_year_tonnes": _num(last_year_t, 0),
                "yoy_pct_latest_month": _num(_pct_change(latest_t, last_year_t), 1),
                "yoy_pct_last_3_months": _num(yoy3, 1),
                "last_12_months_tonnes": _num(c12, 0),
                "last_12_months_prev_year_tonnes": _num(p12, 0),
                "yoy_pct_last_12_months": _num(yoy12, 1),
                "months_compared_12m": used12,
                "share_of_direction_pct": _num(c12 / direction_total * 100, 1),
                **_momentum(s),
            })
    rows.sort(key=lambda r: (r["direction"], -(r["last_12_months_tonnes"] or 0)))
    return rows


# ═══════════════════════════════════════════════════════════════════
# 3. Public API (used by routes/trade.py)
# ═══════════════════════════════════════════════════════════════════

@_ttl_cache(seconds=300)
def get_trade_summary() -> dict:
    p = _prepared()
    totals, latest = p["totals"], p["latest"]
    prev_year_month = latest - pd.DateOffset(years=1)

    def block(col: str) -> dict:
        s = totals[col]
        c1, p1, y1, _ = _window_compare(s, latest, 1)
        c12, p12, y12, used = _window_compare(s, latest, 12)
        return {
            "latest_month_tonnes": _num(s.get(latest), 0),
            "same_month_last_year_tonnes": _num(s.get(prev_year_month), 0),
            "yoy_pct_latest_month": _num(y1, 1),
            "last_12_months_tonnes": _num(c12, 0),
            "last_12_months_prev_year_tonnes": _num(p12, 0),
            "yoy_pct_last_12_months": _num(y12, 1),
            "months_compared_12m": used,
            **{k: v for k, v in _momentum(s).items() if k != "active_months_12"},
        }

    inbound, outbound, total = block("inbound"), block("outbound"), block("total")
    inb, out = totals["inbound"].get(latest), totals["outbound"].get(latest)
    commodities = _commodity_rows(p)
    movers = [
        r for r in commodities
        if r["signal"] in ("Rising", "Falling") and (r["share_of_direction_pct"] or 0) >= MIN_SHARE_FOR_MOVERS_PCT
    ]
    slim = lambda r: {k: r[k] for k in ("commodity", "direction", "momentum_pct", "yoy_pct_last_12_months", "share_of_direction_pct")}

    return {
        "data_source": "real: data/port_cargo_monthly.csv (NMPA monthly traffic statements)",
        "unit": "tonnes",
        "as_of": _month(latest),
        "latest_month": {
            "inbound_tonnes": _num(inb, 0),
            "outbound_tonnes": _num(out, 0),
            "total_tonnes": _num(inb + out, 0),
            "net_outbound_tonnes": _num(out - inb, 0),
            "outbound_share_pct": _num(out / (inb + out) * 100, 1),
        },
        "inbound": inbound,
        "outbound": outbound,
        "total": total,
        "momentum_method": (
            f"EMA({FAST_SPAN_MONTHS} months) vs EMA({SLOW_SPAN_MONTHS} months), in %. "
            f"Rising/Falling at +/-{MOMENTUM_THRESHOLD_PCT:.0f}%. Seasonality is not removed."
        ),
        "top_rising": [slim(r) for r in sorted(
            (r for r in movers if r["signal"] == "Rising"), key=lambda r: -r["momentum_pct"])[:3]],
        "top_falling": [slim(r) for r in sorted(
            (r for r in movers if r["signal"] == "Falling"), key=lambda r: r["momentum_pct"])[:3]],
        "data_quality": p["data_quality"],
    }


@_ttl_cache(seconds=300)
def get_monthly_flows(months: int = 36) -> dict:
    p = _prepared()
    totals = p["totals"]
    ema = {
        f"{col}_ema{span}": _ema(totals[col], span).reindex(totals.index)
        for col in ("inbound", "outbound") for span in (FAST_SPAN_MONTHS, SLOW_SPAN_MONTHS)
    }
    series = []
    for d in totals.index[-months:]:
        has_data = not np.isnan(totals.loc[d, "total"])
        inb, out = totals.loc[d, "inbound"], totals.loc[d, "outbound"]
        series.append({
            "month": _month(d),
            "status": "missing" if not has_data else ("derived" if d in p["derived"] else "reconstructed" if d in p["reconstructed"] else "reported"),
            "inbound_tonnes": _num(inb, 0),
            "outbound_tonnes": _num(out, 0),
            "total_tonnes": _num(inb + out, 0),
            "net_outbound_tonnes": _num(out - inb, 0),
            "outbound_share_pct": _num(out / (inb + out) * 100, 1) if has_data else None,
            **{name: _num(s.get(d), 0) for name, s in ema.items()},
        })
    return {
        "data_source": "real: data/port_cargo_monthly.csv",
        "unit": "tonnes",
        "months_returned": len(series),
        "series": series,
        "data_quality": p["data_quality"],
    }


@_ttl_cache(seconds=300)
def get_commodity_flows(direction: str = "all") -> dict:
    rows = _commodity_rows(_prepared())
    if direction in ("inbound", "outbound"):
        rows = [r for r in rows if r["direction"] == direction]
    return {
        "data_source": "real: data/port_cargo_monthly.csv",
        "unit": "tonnes",
        "as_of": _prepared()["data_quality"]["latest_month"],
        "direction": direction,
        "count": len(rows),
        "commodities": rows,
        "momentum_method": get_trade_summary()["momentum_method"],
    }


ALERT_YOY_3M_PCT = 20.0        # last-3-month YoY beyond this (with a matching momentum signal) raises an alert
ALERT_MIN_SHARE_PCT = 1.0      # ignore cargos below this share of their direction


def _fmt_t(v: float | None) -> str:
    return "n/a" if v is None else f"{v:,.0f} t"


@_ttl_cache(seconds=300)
def get_trade_alerts() -> dict:
    """
    Plain-language alerts for the port team, from simple, explainable rules:
      * warning  - a material cargo is down >= 20% vs last year over the last 3 months AND momentum is Falling
      * positive - up >= 20% over the last 3 months AND momentum is Rising
      * info     - a material cargo has become irregular (moved in fewer than 6 of the last 12 months)
    Requiring BOTH the year-on-year change and the momentum signal avoids alerts from a single odd month.
    """
    p = _prepared()
    rows = _commodity_rows(p)
    as_of = p["data_quality"]["latest_month"]
    alerts: list[dict] = []
    for r in rows:
        share = r["share_of_direction_pct"]
        if share is None or share < ALERT_MIN_SHARE_PCT:
            continue
        name, d = r["commodity"], r["direction"]
        yoy3, sig = r["yoy_pct_last_3_months"], r["signal"]
        base = {"commodity": name, "direction": d, "share_of_direction_pct": share,
                "yoy_pct_last_3_months": yoy3, "momentum_pct": r["momentum_pct"], "signal": sig}
        if yoy3 is not None and yoy3 <= -ALERT_YOY_3M_PCT and sig == "Falling":
            alerts.append({**base, "severity": "warning", "message":
                f"{name} ({d}) is down {abs(yoy3):.0f}% over the latest 3-month window versus the same months last year "
                f"and still trending down. It is {share:.1f}% of {d} cargo, so it is worth a call to the customers involved."})
        elif yoy3 is not None and yoy3 >= ALERT_YOY_3M_PCT and sig == "Rising":
            alerts.append({**base, "severity": "positive", "message":
                f"{name} ({d}) is up {yoy3:.0f}% over the latest 3-month window versus last year and still trending up "
                f"({share:.1f}% of {d} cargo). Check berth and storage capacity can keep up."})
        elif sig == "Irregular":
            alerts.append({**base, "severity": "info", "message":
                f"{name} ({d}) has moved in only {r['active_months_12']} of the last 12 months "
                f"({share:.1f}% of {d} cargo). Its flow is lumpy, so monthly changes may not mean a real trend."})
    order = {"warning": 0, "positive": 1, "info": 2}
    alerts.sort(key=lambda a: (order[a["severity"]], -a["share_of_direction_pct"]))
    return {
        "data_source": "real: data/port_cargo_monthly.csv",
        "as_of": as_of,
        "count": len(alerts),
        "rules": {"min_share_pct": ALERT_MIN_SHARE_PCT, "yoy_3m_threshold_pct": ALERT_YOY_3M_PCT,
                  "note": "Seasonality is not removed; a 3-month window can still be affected by it."},
        "alerts": alerts,
    }


@_ttl_cache(seconds=300)
def get_commodity_detail(name: str, months: int = 36) -> dict | None:
    """Monthly inbound/outbound series for one cargo, or None if the name is unknown."""
    p = _prepared()
    key = _canon(name)
    wide = p["wide"]
    if not any((section, key) in wide.columns for section in (INBOUND, OUTBOUND)):
        return None
    cols = {
        direction: wide[(section, key)] if (section, key) in wide.columns else pd.Series(np.nan, index=wide.index)
        for section, direction in DIRECTION.items()
    }
    series = []
    for d in wide.index[-months:]:
        inb, out = cols["inbound"].get(d), cols["outbound"].get(d)
        series.append({
            "month": _month(d),
            "inbound_tonnes": _num(inb, 0),
            "outbound_tonnes": _num(out, 0),
            "status": "missing" if np.isnan(inb) and np.isnan(out)
            else ("derived" if d in p["derived"] else "reconstructed" if d in p["reconstructed"] else "reported"),
        })
    metrics = [r for r in _commodity_rows(p) if _canon(r["commodity"]) == key]
    return {
        "data_source": "real: data/port_cargo_monthly.csv",
        "commodity": p["names"][key],
        "unit": "tonnes",
        "directions_present": [r["direction"] for r in metrics],
        "metrics": metrics,
        "series": series,
    }


def get_legacy_trade_snapshot() -> dict:
    """
    Real replacement for the numbers that ``forecasting.forecast_trade()`` used to type in
    by hand (3.8, 5.2, 4.2, 6.1). Keeps the same keys so /forecast/trade stays compatible.
    ``*_mom_growth_pct`` is None when the previous calendar month is missing (e.g. a gap).
    """
    p = _prepared()
    totals, latest = p["totals"], p["latest"]
    last12 = totals.loc[: latest].iloc[-12:].dropna(subset=["inbound", "outbound"])
    avg_in, avg_out = float(last12["inbound"].mean()), float(last12["outbound"].mean())
    balance = avg_out - avg_in
    prev = latest - pd.DateOffset(months=1)
    summary = get_trade_summary()

    def mom(col: str) -> float | None:
        return _num(_pct_change(totals[col].get(latest), totals[col].get(prev)), 1)

    return {
        "months_averaged": int(len(last12)),
        "trade_balance_mt000": _num(balance / 1000.0, 1),
        "balance_signal": "surplus" if balance > 0 else "deficit",
        "import_mom_growth_pct": mom("inbound"),
        "export_mom_growth_pct": mom("outbound"),
        "import_yoy_growth_pct": summary["inbound"]["yoy_pct_latest_month"],
        "export_yoy_growth_pct": summary["outbound"]["yoy_pct_latest_month"],
        "import_momentum": summary["inbound"]["momentum_pct"],
        "export_momentum": summary["outbound"]["momentum_pct"],
    }


# ═══════════════════════════════════════════════════════════════════
# 4. Overseas vs coastal split (Ministry of Ports, Shipping & Waterways monthly report)
# ═══════════════════════════════════════════════════════════════════
# NMPA's own commodity statement does not say whether cargo is foreign or coastal, but the
# Ministry's monthly "Cargo handled at Major Ports" report does, for the port as a whole.
# Its totals equal NMPA's published cargo (loaded + unloaded + shore handling).

def _overseas_coastal_csv():
    from pathlib import Path
    return Path(__file__).resolve().parents[3] / "data" / "port_overseas_coastal_monthly.csv"


@_ttl_cache(seconds=300)
def get_overseas_coastal() -> dict:
    d = pd.read_csv(_overseas_coastal_csv())
    d["date"] = pd.to_datetime(d["month"] + "-01")
    d = d.sort_values("date").reset_index(drop=True)

    def share(a, b):
        return _num(a / b * 100, 1) if b else None

    series = []
    for r in d.itertuples():
        series.append({
            "month": r.month, "basis": r.basis,
            "overseas_tonnes": _num(r.overseas_t, 0), "coastal_tonnes": _num(r.coastal_t, 0), "total_tonnes": _num(r.total_t, 0),
            "coastal_share_pct": share(r.coastal_t, r.total_t),
            "overseas_yoy_pct": _num(_pct_change(r.overseas_t, r.prev_year_overseas_t), 1),
            "coastal_yoy_pct": _num(_pct_change(r.coastal_t, r.prev_year_coastal_t), 1),
            "total_yoy_pct": _num(_pct_change(r.total_t, r.prev_year_total_t), 1),
        })
    # Financial-year-to-date (April onward) over the months we hold, vs the same months last year
    fy = d[d["date"] >= pd.Timestamp(d["date"].max().year if d["date"].max().month >= 4 else d["date"].max().year - 1, 4, 1)]
    ytd = {
        "from": fy["month"].iloc[0], "to": fy["month"].iloc[-1], "months": int(len(fy)),
        "overseas_tonnes": _num(fy.overseas_t.sum(), 0), "coastal_tonnes": _num(fy.coastal_t.sum(), 0),
        "total_tonnes": _num(fy.total_t.sum(), 0),
        "overseas_yoy_pct": _num(_pct_change(fy.overseas_t.sum(), fy.prev_year_overseas_t.sum()), 1),
        "coastal_yoy_pct": _num(_pct_change(fy.coastal_t.sum(), fy.prev_year_coastal_t.sum()), 1),
        "total_yoy_pct": _num(_pct_change(fy.total_t.sum(), fy.prev_year_total_t.sum()), 1),
        "coastal_share_pct": share(fy.coastal_t.sum(), fy.total_t.sum()),
        "coastal_share_prev_year_pct": share(fy.prev_year_coastal_t.sum(), fy.prev_year_total_t.sum()),
    }
    return {
        "data_source": "real: Ministry of Ports, Shipping & Waterways - 'Cargo handled at Major Ports' monthly reports (New Mangalore rows)",
        "data_file": "data/port_overseas_coastal_monthly.csv",
        "scope": "Whole-port totals only: the source does not split overseas vs coastal by commodity.",
        "as_of": d["month"].iloc[-1],
        "months_held": int(len(d)),
        "financial_year_to_date": ytd,
        "series": series,
        "notes": [
            "Figures for the current year are 'advance estimates' and may be revised.",
            "April 2026 is derived (April-May cumulative minus May), both from the same official report.",
            "Totals equal NMPA's published cargo including shore handling, so they are slightly higher than inbound + outbound in /trade/summary.",
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# 5. Plain-language brief + where every number comes from
# ═══════════════════════════════════════════════════════════════════

SOURCES = {
    "cargo": {
        "title": "NMPA monthly commodity-wise traffic statements",
        "data_file": "data/port_cargo_monthly.csv",
        "origin": "New Mangalore Port Authority (newmangaloreport.gov.in) - 'Commodity-wise traffic handled during the month of ...'. "
                  "August 2026 was read from nmpa_public_data/Commodity wise traffic statement August 2026.pdf.",
        "coverage": "January 2022 onward. 2022 is rebuilt from the 'same month last year' column of the 2023 statements (shown shaded).",
        "checked": "Every NMPA statement held (33 PDFs, 2024 to September 2026) is checked line by line against the data by scripts/verify_trade_against_nmpa.py; small differences in NMPA's own year-to-date columns are listed in the check output.",
    },
    "overseas_coastal": {
        "title": "Ministry of Ports, Shipping & Waterways - Cargo handled at Major Ports",
        "data_file": "data/port_overseas_coastal_monthly.csv",
        "origin": "Monthly 'Cargo handled at Major Ports' reports (shipmin.gov.in), New Mangalore rows, January to September 2026.",
        "coverage": "January to September 2026. Current-year figures are advance estimates. April and August are derived from the cumulative columns; August equals NMPA's own Traffic & Performance total exactly.",
        "checked": "Totals agree with NMPA's own totals (the Ministry figure also includes a small amount of shore handling).",
    },
    "forecast": {
        "title": "Back-tested forecast built only from the NMPA cargo figures",
        "data_file": "data/port_cargo_monthly.csv",
        "origin": "Same NMPA statements as above. No outside data. Code: backend/app/services/trade_forecast.py.",
        "coverage": "Back-test: month-by-month, from January 2024 to the latest month, 1-3 months ahead.",
        "checked": "A method replaces the plain 12-month average only if it wins in both halves of the back-test by at least 3%.",
    },
    "cargo_split": {
        "title": "NMPA Daily Vessel Positions (berthed ships)",
        "data_file": "data/daily_vessel_position_parsed/ (309 daily files, 2025-09-01 to 2026-10-26; none for 17-30 Sep 2026)",
        "origin": "NMPA website, Daily Vessel Positions page. Each ship row gives cargo, receiver/shipper, quantity and a run flag (F = foreign-going, C = coastal).",
        "coverage": 'September 2025 onward (one file per report day; NMPA publishes no report on Sundays and most holidays). Counts ships (one per cargo and stay), not official tonnes.',
        "checked": "Whole-port coastal share compared with the Ministry's official monthly figures (January to September 2026). The original NMPA PDFs for 62 report days (May to August 2026) were read again and match the data held exactly.",
    },
    "waiting": {
        "title": "NMPA Daily Vessel Positions (anchorage and tankers waiting for berth)",
        "data_file": "data/daily_vessel_position_parsed/ (309 daily files, 2025-09-01 to 2026-10-26; none for 17-30 Sep 2026)",
        "origin": "NMPA website, Daily Vessel Positions page. Waiting days and reasons are as written by port staff.",
        "coverage": "About 13 months. Only ships that waited are counted.",
        "checked": "Not the same basis as NMPA's official pre-berthing detention (which averages all ships).",
    },
    "customers": {
        "title": "NMPA Daily Vessel Positions (receiver/shipper of every berthed ship) + customer name list",
        "data_file": "data/daily_vessel_position_parsed/ and data/customer_aliases.csv",
        "origin": "NMPA website, Daily Vessel Positions page. Receiver/shipper as written by port staff; spelling variants merged by data/customer_aliases.csv. Code: backend/app/services/trade_customers.py.",
        "coverage": "September 2025 onward. Tonnes are ship cargo parcels (handled + balance), container ships count as calls only.",
        "checked": "Monthly traced tonnes are compared with the non-container tonnes in NMPA's official monthly statements (see the coverage check in the section).",
    },
    "performance": {
        "title": "NMPA Traffic & Performance (monthly report to the Ministry)",
        "data_file": "data/nmpa_performance_monthly.csv",
        "origin": "Read from nmpa_public_data/operational performance *.pdf by scripts/parse_nmpa_performance.py.",
        "coverage": "Every month from April 2025 to September 2026 (each report also gives the same month a year earlier).",
        "checked": "August 2026 total traffic in the report (38,85,913 t) equals the Ministry figure for the same month.",
    },
    "containers": {
        "title": "NMPA Statement II - containerised traffic by commodity",
        "data_file": "data/nmpa_container_commodities.csv",
        "origin": "Read from nmpa_public_data/container traffic*.pdf by scripts/parse_nmpa_containers.py.",
        "coverage": "January 2025 to September 2026 (missing: none in that span except as listed in the file).",
        "checked": "Commodities plus tare weight add up to the printed totals (within 2 t of rounding).",
    },
    "target": {
        "title": "Annual cargo target announced by NMPA",
        "data_file": "data/port_targets.csv",
        "origin": "NMPA's own Traffic & Performance reports: 53.00 MMT for 2026-27, 48.50 MMT for 2025-26.",
        "coverage": "Current financial year, April to the latest NMPA statement.",
        "checked": "Tonnes so far are the Ministry's official monthly totals for New Mangalore, which equal NMPA's own Traffic & Performance totals (e.g. August 2026: 3,885,913 t in both).",
    },
    "benchmark": {
        "title": "Ministry of Ports, Shipping and Waterways - Cargo handled at Major Ports, Table-1 (all 12 major ports)",
        "data_file": "data/major_ports_ministry_2026-09.csv (and _2026-07.csv)",
        "origin": "Ministry monthly reports for July and September 2026, Table-1: overseas, coastal and total tonnes for every major port.",
        "coverage": "All 12 major ports: totals every month from November 2024 to September 2026 (plus March-May and August-October 2024), and tonnes by commodity for 26 months from April 2024 (data/major_ports_monthly.csv and data/major_ports_commodity_monthly.csv; months without their own report derived from April-to-date columns), plus non-major ports by state board for April to July 2026.",
        "checked": "Every port's overseas + coastal equals its total, the ports add up to the printed all-port totals, "
                   "and New Mangalore's row equals the overseas/coastal file above.",
    },
    "alerts": {
        "title": "Rules applied to the NMPA cargo figures",
        "data_file": "data/port_cargo_monthly.csv",
        "origin": "Same NMPA statements as above. Thresholds (20% change, 1% share) are analyst judgement calls, not published figures.",
        "coverage": "Latest 3 months versus the same 3 months a year earlier.",
        "checked": "Rules are covered by automated tests.",
    },
}


def _label(month: str) -> str:
    return pd.Timestamp(month + "-01").strftime("%B %Y")


@_ttl_cache(seconds=300)
def get_trade_brief() -> dict:
    """Key findings in plain sentences, every number computed from the real data."""
    s = get_trade_summary()
    rows = _commodity_rows(_prepared())
    oc = get_overseas_coastal()
    al = get_trade_alerts()
    lm, t_in, t_out, t_all = s["latest_month"], s["inbound"], s["outbound"], s["total"]

    def top(direction: str, n: int) -> list[dict]:
        r = sorted((x for x in rows if x["direction"] == direction and x["share_of_direction_pct"] is not None),
                   key=lambda x: -x["share_of_direction_pct"])[:n]
        return [{"commodity": x["commodity"], "share_pct": x["share_of_direction_pct"]} for x in r]

    ti_, to_ = top("inbound", 3), top("outbound", 2)
    acronyms = {"POL", "LPG", "JSW", "ISPRL", "FRM"}

    def nice(name: str) -> str:
        words = re.sub(r"^TOTAL\s+", "", name).split()
        return " ".join(w if w.strip(".()") in acronyms else w.title() for w in words)

    def names(lst: list[dict]) -> str:
        parts = [nice(x["commodity"]) for x in lst]
        return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]
    mt = lambda v: f"{v / 1e6:.2f} million tonnes"
    sign = lambda v: f"{v:+.1f}%"

    findings = []
    if lm["total_tonnes"]:
        tot_yoy = t_all["yoy_pct_latest_month"]
        findings.append(
            f"In {_label(s['as_of'])} the port handled {mt(lm['total_tonnes'])} of cargo "
            f"({mt(lm['inbound_tonnes'])} inbound, {mt(lm['outbound_tonnes'])} outbound)"
            + (f", {sign(tot_yoy)} compared with the same month last year." if tot_yoy is not None else "."))
    if t_all["yoy_pct_last_12_months"] is not None:
        findings.append(
            f"Over the last 12 months cargo is {sign(t_all['yoy_pct_last_12_months'])} year on year "
            f"(inbound {sign(t_in['yoy_pct_last_12_months'])}, outbound {sign(t_out['yoy_pct_last_12_months'])}), "
            f"based on the {t_all['months_compared_12m']} months present in both years.")
    in_share, out_share = sum(x["share_pct"] for x in ti_), sum(x["share_pct"] for x in to_)
    findings.append(
        f"The port leans on very few cargos: {names(ti_)} are {in_share:.0f}% of inbound cargo, "
        f"and {names(to_)} are {out_share:.0f}% of outbound cargo.")
    y = oc["financial_year_to_date"]
    findings.append(
        f"{_label(y['from'])} to {_label(y['to'])}: overseas cargo is {sign(y['overseas_yoy_pct'])} and coastal cargo is "
        f"{sign(y['coastal_yoy_pct'])} versus last year, so coastal is now {y['coastal_share_pct']:.0f}% of all cargo "
        f"(it was {y['coastal_share_prev_year_pct']:.0f}%).")
    n_w = sum(1 for a in al["alerts"] if a["severity"] == "warning")
    n_p = sum(1 for a in al["alerts"] if a["severity"] == "positive")
    findings.append(f"{n_w} cargo(s) are falling sharply and {n_p} are rising sharply against last year; see 'What needs attention'.")

    return {
        "as_of": s["as_of"],
        "findings": findings,
        "concentration": {"inbound_top3": ti_, "outbound_top2": to_},
        "sources": SOURCES,
        "limits": [
            "These are monthly published totals: they show what changed, not why.",
            "No customer, shipper or revenue data is available, so alerts cannot name who is behind a change.",
            "The overseas/coastal split exists for the whole port only, and only for January to September 2026.",
        ],
    }
