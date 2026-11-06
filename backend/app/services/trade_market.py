"""
Market share by cargo - New Mangalore's share of each cargo handled at all 12 major ports, and whether it is
gaining or losing ground (the "growth opportunity" view).

Data (real):
  * NMPA monthly commodity statements (trade_intelligence._prepared()) - New Mangalore's tonnes, loaded + unloaded.
  * Ministry of Ports monthly report, Table-2 (data/major_ports_commodity_monthly.csv, scripts/parse_ministry_commodities.py)
    - all major ports together, by commodity.
The two sources group cargo slightly differently; GROUPS below maps one onto the other. NMPA's statements leave
out shore handling, so its share is very slightly understated (by well under 1%).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services import trade_intelligence as ti
from backend.app.services.forecasting import _ttl_cache

ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / "data" / "major_ports_commodity_monthly.csv"

# cargo group: (NMPA statement keys, Ministry Table-2 lines)
GROUPS = {
    "Crude oil": (["TOTALCRUDE", "CRUDEISPRL"], ["POL Crude"]),
    "POL products": (["POLPRODUCTS"], ["POL Products"]),
    "LPG": (["TOTALLPG"], ["LPG or LNG"]),
    "Coal": (["TOTALCOAL"], ["Thermal Coal", "Coking Coal", "Other Coal"]),
    "Iron ore": (["IRONORE"], ["Iron Ore Pellets/Fine"]),
    "Fertilizer and raw materials": (["FERTILIZER", "FRMDRY"], ["FRM-Liquid", "Fertilizer", "FRM-Dry"]),
    "Edible oil": (["EDIBLEOIL"], ["Edible Oil"]),
    "Cement": (["TOTALCEMENT"], ["Cement"]),
    "Food grains": (["FOODGRAINS"], ["Food Grains excluding Pulses", "Pulses"]),
    "Containers (tonnes)": (["CONTAINERJSW"], ["Container Tonnes"]),
    "Other cargo": (["OTHERCARGO", "OTHLIQCARGOES", "PETROCHEMICALS"],
                    ["Other Ores", "Sugar", "Iron and Steel", "Project Cargo", "Other Commodities"]),
}
# Some Ministry reports (March) print only principal groups; these groups can still be matched from them.
PRINCIPAL = {"Coal": "P:Coal", "Iron ore": "P:Iron Ore", "Fertilizer and raw materials": "P:Fertilizer",
             "Food grains": "P:Foodgrains"}
# Main groups, available in EVERY Ministry report (March reports print only these), so their lines have no gaps.
MAIN_GROUPS = {
    "Crude, POL products and LPG": (["TOTALCRUDE", "CRUDEISPRL", "POLPRODUCTS", "TOTALLPG"],
                                    ["POL Crude", "POL Products", "LPG or LNG"], ["P:POL and Crude Products"]),
    "Coal": (["TOTALCOAL"], ["Thermal Coal", "Coking Coal", "Other Coal"], ["P:Coal"]),
    "Iron ore": (["IRONORE"], ["Iron Ore Pellets/Fine"], ["P:Iron Ore"]),
    "Fertilizer and raw materials": (["FERTILIZER", "FRMDRY"], ["FRM-Liquid", "Fertilizer", "FRM-Dry"], ["P:Fertilizer"]),
    "Containers (tonnes)": (["CONTAINERJSW"], ["Container Tonnes"], ["Container Tonnes"]),
    "Other cargo (incl. edible oil, cement, food grains)": (
        ["OTHERCARGO", "OTHLIQCARGOES", "PETROCHEMICALS", "EDIBLEOIL", "TOTALCEMENT", "FOODGRAINS"],
        ["Food Grains excluding Pulses", "Pulses", "Edible Oil", "Other Ores", "Sugar", "Cement", "Iron and Steel",
         "Project Cargo", "Other Commodities"], ["P:Foodgrains", "P:Other Commodities"]),
}
GAP_POINTS = 5.0     # NMPA growth this many points above / below all major ports = gaining / losing share
GROWING_PCT = 5.0    # a cargo growing at least this much at all major ports counts as growing nationally


def _pct(a, b):
    return round((a / b - 1) * 100, 1) if b else None


def _nmpa_sum(wide: pd.DataFrame, keys: list[str], months: pd.DatetimeIndex) -> float:
    cols = [c for c in wide.columns if c[1] in keys]
    return float(wide.reindex(months)[cols].fillna(0).to_numpy().sum()) if cols else 0.0


@_ttl_cache(seconds=300)
def get_market_share() -> dict[str, Any]:
    if not FILE.exists():
        return {"available": False, "note": "Run scripts/parse_ministry_commodities.py"}
    m = pd.read_csv(FILE)
    wide = ti._prepared()["wide"]
    ytd = m[m["period"] == "ytd"]
    held = sorted(set(ytd["through"]) & {d.strftime("%Y-%m") for d in wide.index})
    if not held:
        return {"available": False}
    through = pd.Timestamp(held[-1] + "-01")
    start = pd.Timestamp(through.year if through.month >= 4 else through.year - 1, 4, 1)
    cur_m = pd.date_range(start, through, freq="MS")
    prev_m = cur_m - pd.DateOffset(years=1)
    prev_through = prev_m[-1].strftime("%Y-%m")
    tab = ytd.pivot_table(index="through", columns="commodity", values="tonnes", aggfunc="sum")
    if prev_through not in tab.index:
        return {"available": False}
    rows = []
    for g, (keys, lines) in GROUPS.items():
        n_cur, n_prev = _nmpa_sum(wide, keys, cur_m), _nmpa_sum(wide, keys, prev_m)
        a_cur = float(tab.loc[held[-1], lines].sum())
        a_prev = float(tab.loc[prev_through, lines].sum())
        if not a_cur:
            continue
        sh, sh_prev = n_cur / a_cur * 100, (n_prev / a_prev * 100 if a_prev else None)
        g_n, g_a = _pct(n_cur, n_prev), _pct(a_cur, a_prev)
        # Benchmark = the OTHER major ports (all ports minus New Mangalore), so the comparison does not include
        # the port being judged. g_a (all ports) is still reported for reference.
        g_o = _pct(a_cur - n_cur, a_prev - n_prev)
        diff = None if g_n is None or g_o is None else g_n - g_o
        status = ("Too small to compare" if min(n_cur, n_prev) < 10_000 else
                  "Gaining share" if diff is not None and diff >= GAP_POINTS else
                  "Losing share" if diff is not None and diff <= -GAP_POINTS else "In line with ports")
        note = ""
        if status == "Losing share" and g_o is not None and g_o >= GROWING_PCT:
            note = "Opportunity: growing at major ports, not here"
        elif status == "Losing share" and g_o is not None and g_o <= -GROWING_PCT:
            note = "Falling at all major ports too"
        elif g_n is not None and g_n < 0 and g_o is not None and g_o < 0 and status != "Losing share":
            note = "Falling nationally, not a local problem"
        if g == "Crude oil":
            isprl = _nmpa_sum(wide, ["CRUDEISPRL"], cur_m)
            if isprl:
                imp_c, imp_p = _nmpa_sum(wide, ["TOTALCRUDE"], cur_m), _nmpa_sum(wide, ["TOTALCRUDE"], prev_m)
                note = (note + "; " if note else "") + (f"Includes {isprl:,.0f} t loaded out of the ISPRL reserve; "
                                                        f"imports alone {_pct(imp_c, imp_p):+.1f}%")
        rows.append({"cargo": g, "nmpa_tonnes": round(n_cur), "all_ports_tonnes": round(a_cur),
                     "nmpa_prev_tonnes": round(n_prev), "all_ports_prev_tonnes": round(a_prev),
                     "share_pct": round(sh, 2), "share_prev_pct": None if sh_prev is None else round(sh_prev, 2),
                     "share_change_points": None if sh_prev is None else round(sh - sh_prev, 2),
                     "nmpa_growth_pct": g_n, "all_ports_growth_pct": g_a, "other_ports_growth_pct": g_o,
                     "growth_gap_points": None if diff is None else round(diff, 1), "status": status, "note": note})
    rows.sort(key=lambda r: -r["nmpa_tonnes"])
    tot_n = sum(r["nmpa_tonnes"] for r in rows)
    tot_np = sum(r["nmpa_prev_tonnes"] for r in rows)
    tot_ap = float(tab.loc[prev_through, "Total"]) if "Total" in tab.columns else sum(r["all_ports_prev_tonnes"] for r in rows)
    tot_a = float(tab.loc[held[-1], "Total"]) if "Total" in tab.columns else sum(r["all_ports_tonnes"] for r in rows)
    # Month-by-month share on a continuous calendar: a month the Ministry table does not cover stays empty
    # (shown as a gap), never joined across.
    mon = m[m["period"] == "month"].pivot_table(index="through", columns="commodity", values="tonnes", aggfunc="sum")
    held_months = [mth for mth in sorted(mon.index) if pd.Timestamp(mth + "-01") in wide.index]
    monthly = []
    if held_months:
        for d in pd.date_range(held_months[0] + "-01", held_months[-1] + "-01", freq="MS"):
            mth = d.strftime("%Y-%m")
            rec = {"month": mth}
            for g, (keys, lines) in GROUPS.items():
                val = None
                if mth in mon.index:
                    row = mon.loc[mth]
                    if all(l in row.index and pd.notna(row[l]) for l in lines):
                        a = float(row[lines].sum())
                    elif g in PRINCIPAL and PRINCIPAL[g] in row.index and pd.notna(row[PRINCIPAL[g]]):
                        a = float(row[PRINCIPAL[g]])
                    else:
                        a = 0.0
                    val = round(_nmpa_sum(wide, keys, pd.DatetimeIndex([d])) / a * 100, 2) if a else None
                rec[g] = val
            monthly.append(rec)
    monthly_groups = []
    if held_months:
        for d in pd.date_range(held_months[0] + "-01", held_months[-1] + "-01", freq="MS"):
            mth = d.strftime("%Y-%m")
            rec = {"month": mth}
            for g, (keys, detailed, principal) in MAIN_GROUPS.items():
                val = None
                if mth in mon.index:
                    row = mon.loc[mth]
                    have = lambda ls: all(l in row.index and pd.notna(row[l]) for l in ls)
                    a = float(row[detailed].sum()) if have(detailed) else (float(row[principal].sum()) if have(principal) else 0.0)
                    val = round(_nmpa_sum(wide, keys, pd.DatetimeIndex([d])) / a * 100, 2) if a else None
                rec[g] = val
            monthly_groups.append(rec)
    label = f"April to {through.strftime('%B %Y')}"
    tot_a_ = float(tab.loc[held[-1], "Total"]) if "Total" in tab.columns else sum(r["all_ports_tonnes"] for r in rows)
    total_row = {"cargo": "All cargo", "nmpa_prev_tonnes": round(tot_np), "nmpa_tonnes": round(tot_n),
                 "all_ports_prev_tonnes": round(tot_ap), "all_ports_tonnes": round(tot_a_),
                 "share_prev_pct": round(tot_np / tot_ap * 100, 2) if tot_ap else None,
                 "share_pct": round(tot_n / tot_a_ * 100, 2) if tot_a_ else None,
                 "nmpa_growth_pct": _pct(tot_n, tot_np), "all_ports_growth_pct": _pct(tot_a_, tot_ap),
                 "other_ports_growth_pct": _pct(tot_a_ - tot_n, tot_ap - tot_np)}
    total_row["share_change_points"] = (round(total_row["share_pct"] - total_row["share_prev_pct"], 2)
                                        if total_row["share_pct"] is not None and total_row["share_prev_pct"] is not None else None)
    prev_label = f"April to {prev_m[-1].strftime('%B %Y')}"
    return {"available": True, "period_label": label, "previous_period_label": prev_label, "through": held[-1],
            "cargos": rows, "total": total_row,
            "nmpa_share_of_all_major_ports_pct": round(tot_n / tot_a * 100, 2) if tot_a else None,
            "gaining": [r["cargo"] for r in rows if r["status"] == "Gaining share"],
            "losing": [r["cargo"] for r in rows if r["status"] == "Losing share"],
            "opportunities": [r for r in rows if r["note"].startswith("Opportunity")],
            "monthly_share": monthly, "monthly_share_groups": monthly_groups,
            "march_note": ("The Ministry's March and April reports give only main groups (e.g. crude, POL products and LPG "
                           "together), so individual cargos have no figure for March; the main-group view has every month."),
            "rules": {"gap_points": GAP_POINTS, "growing_pct": GROWING_PCT,
                      "benchmark": "the other 11 major ports (all major ports minus New Mangalore)"},
            "source": "NMPA monthly commodity statements; Ministry of Ports 'Cargo handled at Major Ports', Table-2",
            "limits": ["Cargo groups are matched between the two sources (e.g. NMPA 'Other cargo' against the Ministry's other "
                       "commodities), so a share is approximate for the mixed groups.",
                       "NMPA statements exclude shore handling, so shares are slightly understated."]}


# ── Which ports gained each cargo: Ministry annual report, Annexure-I (each major port, four financial years) ──
ANNUAL_FILE = ROOT / "data" / "major_ports_annual_port_commodity.csv"
ANNUAL_GROUPS = {"Crude and POL products": ["pol_crude_and_products"], "LPG / LNG": ["lpg_lng"], "Iron ore": ["iron_ore"],
                 "Coal (all)": ["thermal_coal", "coking_coal", "other_coal"], "Fertilizer and raw materials": ["fertilizer_frm_dry"],
                 "Containers (tonnes)": ["container_tonnes"], "Food grains": ["food_grain"], "Other cargo": ["others"],
                 "All cargo": ["total"]}


@_ttl_cache(seconds=300)
def get_port_competition() -> dict[str, Any]:
    if not ANNUAL_FILE.exists():
        return {"available": False}
    a = pd.read_csv(ANNUAL_FILE)
    years = sorted(a["financial_year"].unique())
    first, prev, last = years[1] if len(years) > 2 else years[0], years[-2], years[-1]
    out = {}
    for g, cols in ANNUAL_GROUPS.items():
        a[g] = a[cols].sum(axis=1)
        piv = a.pivot_table(index="port", columns="financial_year", values=g, aggfunc="sum")
        allp = piv.loc["All Ports"]
        ports = piv.drop(index="All Ports")
        rows = []
        for port, r in ports.iterrows():
            if not r.sum():
                continue
            rows.append({"port": port, **{fy: round(float(r[fy]) * 1000) for fy in years},
                         "change_t": round(float(r[last] - r[first]) * 1000),
                         "change_last_year_t": round(float(r[last] - r[prev]) * 1000),
                         "share_pct": round(float(r[last] / allp[last] * 100), 2) if allp[last] else None,
                         "share_first_pct": round(float(r[first] / allp[first] * 100), 2) if allp[first] else None})
        rows.sort(key=lambda x: -x[last])
        nm = next((x for x in rows if x["port"] == "New Mangalore"), None)
        gainers = sorted(rows, key=lambda x: -x["change_t"])
        out[g] = {"ports": rows, "all_ports": {fy: round(float(allp[fy]) * 1000) for fy in years},
                  "all_ports_change_t": round(float(allp[last] - allp[first]) * 1000),
                  "top_gainers": [x["port"] for x in gainers[:3] if x["change_t"] > 0],
                  "new_mangalore": nm, "new_mangalore_rank": (rows.index(nm) + 1) if nm else None}
    return {"available": True, "years": years, "from": first, "to": last, "groups": out,
            "source": ("Ministry of Ports, Shipping and Waterways, 'Update on Indian Ports Sector up to 31.03.2025', Annexure-I "
                       "(each major port, thousand tonnes; 2024-25 provisional)"),
            "note": "Financial years to March 2025. For April to September 2026, see the market share above."}
