"""
Did a discount actually work?  Compare New Mangalore with the OTHER major ports over the same months.

Plain idea: if NMPA's cargo rose 15% during a scheme but the same cargo rose 12% at every other major port, only the
3% difference can be credited to the scheme. Comparing against last year alone would credit the whole 15%.

Method (a "difference-in-differences", written out in plain arithmetic):
    expected without the scheme = NMPA tonnes in the same months last year x (other ports this year / other ports last year)
    extra credited to the scheme = NMPA tonnes during the scheme - expected
The same calculation, run on every earlier stretch of months of the same length before the scheme started, gives the
port's normal ups and downs against other ports. An "extra" inside that normal range is not evidence that the scheme
worked.

Data (all already in the project):
  * NMPA monthly commodity statements (trade_intelligence._prepared())
  * Ministry of Ports monthly report, Table-2, all major ports by commodity (data/major_ports_commodity_monthly.csv)
"Other ports" = all major ports minus New Mangalore, so the port being judged is not part of its own benchmark.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_market as tmk

# Incentive Engine cargo -> Ministry cargo group (trade_market.GROUPS) and the broader main group used when the
# Ministry report for a month prints only principal groups (March reports do).
CARGO_GROUP = {
    "Crude oil": "Crude oil", "Crude oil out of ISPRL": "Crude oil",
    "POL products (out)": "POL products", "POL products (in)": "POL products",
    "LPG": "LPG", "Iron ore exports": "Iron ore", "Edible oil": "Edible oil",
    "Fertilizer (finished)": "Fertilizer and raw materials", "Fertilizer raw materials (dry)": "Fertilizer and raw materials",
    "Food grains": "Food grains",
}
CARGO_MAIN_GROUP = {
    "Crude oil": "Crude, POL products and LPG", "Crude oil out of ISPRL": "Crude, POL products and LPG",
    "POL products (out)": "Crude, POL products and LPG", "POL products (in)": "Crude, POL products and LPG",
    "LPG": "Crude, POL products and LPG", "Iron ore exports": "Iron ore",
    "Fertilizer (finished)": "Fertilizer and raw materials", "Fertilizer raw materials (dry)": "Fertilizer and raw materials",
    "Edible oil": "Other cargo (incl. edible oil, cement, food grains)",
    "Food grains": "Other cargo (incl. edible oil, cement, food grains)",
}
PRE_TREND_MONTHS = 6          # months just before the scheme used to see if NMPA was already pulling ahead
PRE_TREND_FLAG_PCT = 10.0     # NMPA already this far ahead of other ports before the scheme -> warn
MIN_WINDOWS = 4               # earlier windows needed before a "normal range" is shown
TOO_VOLATILE_PTS = 60.0       # normal range wider than this many points: NMPA's cargo moves too much on its own to judge


def _ministry_monthly() -> pd.DataFrame:
    m = pd.read_csv(tmk.FILE)
    return m[m["period"] == "month"].pivot_table(index="through", columns="commodity", values="tonnes", aggfunc="sum")


def _series(group: str, main: bool) -> tuple[dict[str, tuple[float, float]], str]:
    """{month: (NMPA tonnes, all major ports tonnes)} for the group, only months where both are present."""
    mon = _ministry_monthly()
    wide = ti._prepared()["wide"]
    if main:
        keys, lines, principal = tmk.MAIN_GROUPS[group]
    else:
        keys, lines = tmk.GROUPS[group]
        principal = [tmk.PRINCIPAL[group]] if group in tmk.PRINCIPAL else []
    cols = [c for c in wide.columns if c[1] in keys]
    out = {}
    for mth in mon.index:
        row = mon.loc[mth]
        if all(l in row.index and pd.notna(row[l]) for l in lines):
            a = float(sum(row[l] for l in lines))
        elif principal and all(p in row.index and pd.notna(row[p]) for p in principal):
            a = float(sum(row[p] for p in principal))
        else:
            continue
        d = pd.Timestamp(mth + "-01")
        if d not in wide.index or not cols or wide.loc[d, cols].isna().all():
            continue
        out[mth] = (float(wide.loc[d, cols].fillna(0).sum()), a)
    label = (f"Ministry main group '{group}'" if main else f"Ministry cargo group '{group}'")
    return out, label


def _shift(mth: str, years: int = 1) -> str:
    return (pd.Timestamp(mth + "-01") - pd.DateOffset(years=years)).strftime("%Y-%m")


def _window_extra(series: dict, months: list[str]) -> tuple[float, float] | None:
    """(NMPA actual, NMPA expected from other ports' growth) for these months, or None if a month is missing."""
    prev = [_shift(m) for m in months]
    if any(m not in series for m in months + prev):
        return None
    n_s = sum(series[m][0] for m in months)
    n_p = sum(series[m][0] for m in prev)
    o_s = sum(series[m][1] - series[m][0] for m in months)
    o_p = sum(series[m][1] - series[m][0] for m in prev)
    if n_p <= 0 or o_p <= 0:
        return None
    return n_s, n_p * o_s / o_p


def evaluate(cargo: str, start: str, end: str, rebate_cost_rs: float | None = None) -> dict[str, Any]:
    """Peer-port check for one cargo over a scheme's months (start/end as YYYY-MM-DD)."""
    if cargo not in CARGO_GROUP:
        raise KeyError(cargo)
    months = [d.strftime("%Y-%m") for d in pd.date_range(pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1), freq="MS")]
    series, label = _series(CARGO_GROUP[cargo], main=False)
    used_main = False
    held = [m for m in months if m in series and _shift(m) in series]
    alt, alt_label = _series(CARGO_MAIN_GROUP[cargo], main=True)
    alt_held = [m for m in months if m in alt and _shift(m) in alt]
    # Prefer the exact cargo group, skipping a month the Ministry printed only as main groups (March), as long as it still
    # covers at least half the scheme's months; otherwise fall back to the broader main group for every month.
    if len(alt_held) > len(held) and len(held) < len(months) / 2:
        series, label, held, used_main = alt, alt_label, alt_held, True
    base = {"cargo": cargo, "scheme_months": months, "months_compared": held, "comparison_group": label,
            "broader_group_used": used_main,
            "method": ("Expected without the scheme = NMPA's tonnes in the same months last year x the growth of the same cargo "
                       "at the other major ports. Extra credited to the scheme = actual - expected."),
            "source": "NMPA monthly commodity statements; Ministry of Ports monthly report Table-2 (all major ports)"}
    if not held:
        return {**base, "available": False,
                "plain_answer": "Not enough data yet: the Ministry's figures for these months (or the same months last year) are not held.",
                "limits": ["The Ministry's monthly report usually arrives 4 to 6 weeks after the month ends."]}
    w = _window_extra(series, held)
    if w is None:
        return {**base, "available": False, "plain_answer": ("Not enough data: NMPA handled none of this cargo in the same months last year, or a month needed "
                                                                "for the comparison is missing.")}
    actual, expected = w
    extra = actual - expected
    extra_pct = extra / expected * 100 if expected else None
    # normal ups and downs: same-length windows that end before the scheme starts
    k = len(held)
    first = pd.Timestamp(held[0] + "-01")
    hist = sorted(m for m in series if pd.Timestamp(m + "-01") < first)
    windows = []
    for i in range(len(hist) - k + 1):
        win = hist[i:i + k]
        if (pd.Timestamp(win[-1] + "-01") - pd.Timestamp(win[0] + "-01")).days > 31 * k:      # must be consecutive months
            continue
        r = _window_extra(series, win)
        if r and r[1]:
            windows.append((r[0] - r[1]) / r[1] * 100)
    normal = None
    if len(windows) >= MIN_WINDOWS:
        normal = {"low_pct": round(float(np.percentile(windows, 10)), 1), "high_pct": round(float(np.percentile(windows, 90)), 1),
                  "windows": len(windows)}
    # pre-trend: was NMPA already pulling ahead of other ports just before the scheme?
    pre = [m for m in hist[-PRE_TREND_MONTHS:]]
    pre_r = _window_extra(series, pre) if pre else None
    pre_gap = round((pre_r[0] - pre_r[1]) / pre_r[1] * 100, 1) if pre_r and pre_r[1] else None
    # verdict in plain words
    too_volatile = bool(normal and normal["high_pct"] - normal["low_pct"] > TOO_VOLATILE_PTS)
    if extra_pct is None:
        verdict = "Cannot judge"
    elif not normal:
        verdict = "Too few earlier months to judge yet (numbers shown for information)"
    elif too_volatile:
        verdict = "Cannot judge: NMPA's cargo of this type swings too much on its own against other ports"
    elif normal["low_pct"] <= extra_pct <= normal["high_pct"]:
        verdict = "Within normal ups and downs: no clear sign the scheme made a difference"
    elif extra_pct > normal["high_pct"]:
        verdict = "More cargo than other ports' trend explains: consistent with the scheme working"
    else:
        verdict = "Less cargo than NMPA usually handles against other ports: no sign the scheme helped"
    warnings = []
    skipped = [m for m in months if m not in held]
    if skipped:
        warnings.append("Months not compared (Ministry figures not held or printed only as main groups): " + ", ".join(skipped) + ".")
    if pre_gap is not None and pre_gap >= PRE_TREND_FLAG_PCT and extra > 0:
        warnings.append(f"In the {len(pre)} months before the scheme NMPA was already {pre_gap:.0f}% ahead of other ports' trend; "
                        "part of the 'extra' may have come anyway.")
    if used_main:
        warnings.append("A broader cargo group had to be used (the Ministry report for some months gives only main groups); "
                        "other cargo in the same group affects the result.")
    if not normal:
        warnings.append(f"Only {len(windows)} earlier comparison windows are held (at least {MIN_WINDOWS} needed), so the normal "
                        "range cannot be shown yet.")
    if cargo.startswith("POL products"):
        warnings.append("The Ministry groups POL products in and out together; the check covers both directions.")
    fmt = lambda m: pd.Timestamp(m + "-01").strftime("%b %Y")
    span = f"In {fmt(held[0])}" if len(held) == 1 else f"From {fmt(held[0])} to {fmt(held[-1])}"
    plain = (f"{span} NMPA handled {actual:,.0f} t. Going by how the other major ports moved, about "
             f"{expected:,.0f} t was expected without the scheme, a difference of {extra:+,.0f} t ({extra_pct:+.1f}%). " + verdict + ".")
    out = {**base, "available": True, "nmpa_actual_t": round(actual), "expected_without_scheme_t": round(expected),
           "extra_credited_t": round(extra), "extra_credited_pct": None if extra_pct is None else round(extra_pct, 1),
           "normal_range": normal, "too_volatile_to_judge": too_volatile, "pre_trend_gap_pct": pre_gap, "verdict": verdict, "warnings": warnings,
           "plain_answer": plain,
           "limits": ["This is a comparison, not proof: a local event (a refinery shutdown, a new plant, a monsoon) can move "
                      "NMPA's cargo without moving other ports'.",
                      "Customer-level schemes are judged on the whole cargo here; other ports' figures are not available by customer."]}
    if rebate_cost_rs is not None and extra > 0:
        out["cost_per_extra_tonne_rs"] = round(rebate_cost_rs / extra, 2)
        out["plain_answer"] += f" The discount cost about \u20b9{rebate_cost_rs / extra:,.2f} for each extra tonne."
    return out
