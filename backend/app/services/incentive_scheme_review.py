"""
Every NMPA scheme judged so far, in one list; and a customer-readiness condition for rebates.

1. Scheme review
   Each scheme from NMPA's notices is judged with incentive_evaluation.evaluate() (the full check: NMPA against the
   other major ports, with the port's normal ups and downs and a pre-scheme trend check) whenever that check covers the
   cargo. Coal and containers are not in its cargo list, so for those a SIMPLE CHECK is used and labelled as such:
   NMPA's growth minus the other major ports' growth for the Ministry's main cargo group, each against a year earlier.
   Schemes whose cargo the Ministry does not show separately are marked "Cannot be measured", never guessed.

2. Customer-readiness condition (performance condition from ship data)
   From the daily vessel reports: for each ship call of a customer, did the ship wait at anchorage because the
   customer side was not ready (receiver / shipper / cargo)? A rebate tied to readiness would pay only on calls
   where that waiting stayed within an allowed number of days. Same waiting rules as Customers & cargo.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import incentive_evaluation as iev
from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_market as tm
from backend.app.services.forecasting import _ttl_cache

EFFECT_POINTS = 5.0          # simple check: NMPA this many points above / below the other ports = a clear difference
SMALL_TONNES = 10_000

RELIEF_NOTE = ("A relief measure: a weak result means New Mangalore was hit harder than other ports, not that the "
               "waiver failed.")

# NMPA's schemes (data/nmpa_incentive_notices.csv). "cargo" = a cargo the full check covers; "group" = Ministry main
# group for the simple check; neither = cannot be measured with public data.
SCHEMES = [
    {"short": "Fertiliser priority berthing", "notice": "NMPA/TM/Fertiliser/2025-26", "start": "2025-07", "end": "2025-10",
     "cargo": "Fertilizer (finished)", "aim": "Faster fertiliser imports for the Kharif season"},
    {"short": "Crude & LPG waiver, Mar 2026", "notice": "NMPA/TM/2025-26/Gen.2, amended by Gen.3", "start": "2026-03",
     "end": "2026-03", "cargo": "Crude oil", "relief": True, "aim": "Relief during the West Asia disruption",
     "note": "The Ministry's March report gives crude oil, POL products and LPG only together, so the waiver is judged on that group."},
    {"short": "Iron ore export rebate", "notice": "NMPA/TM/IOF-Exp-Rebate/26-27", "start": "2026-10", "end": "2027-03",
     "cargo": "Iron ore exports", "aim": "More iron ore exports than last year"},
    {"short": "Cape-size rebate, Berth 16 (coal)", "notice": "12/1/2021-22/ATM Gr.I (Com)/JSW", "start": "2025-04",
     "end": "2027-03", "group": "Coal", "aim": "Bring larger coal vessels to Berth 16",
     "note": "Covers all coal; the scheme covers only Cape-size vessels at Berth 16, so this is a broad check."},
    {"short": "Middle East container waiver", "notice": "NMPA/TM/Trade Notice/2026 (corrigendum)", "start": "2026-03",
     "end": "2026-04", "group": "Containers (tonnes)", "relief": True, "aim": "Keep export containers moving"},
    {"short": "Container vessel rebate", "notice": "Comrc/DTM(C)/2026-27/01", "start": "2026-11", "end": "2027-03",
     "group": "Containers (tonnes)", "aim": "More container services and calls"},
    {"short": "New export cargo concession", "notice": "NMPA/TM/SM/2026", "start": "2026-07", "end": "2027-07",
     "why_not": "New cargo types are not shown separately in the Ministry's tables."},
    {"short": "Harit green cargo concession", "notice": "NMPA/Traffic/Com/Green Policy/01", "start": "2025-07",
     "end": "2030-06", "why_not": "Green fuels are not shown separately in the Ministry's tables."},
]


def _pct(a: float, b: float) -> float | None:
    return round((a / b - 1) * 100, 1) if b else None


@_ttl_cache(seconds=300)
def _monthly_by_group() -> dict[str, pd.DataFrame]:
    """For each main cargo group: month -> NMPA tonnes, all major ports' tonnes, other ports' tonnes."""
    m = pd.read_csv(tm.FILE)
    mon = m[m["period"] == "month"].pivot_table(index="through", columns="commodity", values="tonnes", aggfunc="sum")
    wide = ti._prepared()["wide"]
    out = {}
    for g, (keys, lines, principal) in tm.MAIN_GROUPS.items():
        rows = []
        for mth in mon.index:
            ts = pd.Timestamp(mth + "-01")
            if ts not in wide.index:
                continue
            have = [c for c in lines if c in mon.columns and pd.notna(mon.loc[mth, c])]
            if have:
                allp = float(mon.loc[mth, have].sum())
            else:
                pc = [c for c in principal if c in mon.columns and pd.notna(mon.loc[mth, c])]
                if not pc:
                    continue
                allp = float(mon.loc[mth, pc].sum())
            n = tm._nmpa_sum(wide, keys, pd.DatetimeIndex([ts]))
            rows.append({"month": mth, "nmpa": n, "all_ports": allp, "others": allp - n})
        out[g] = pd.DataFrame(rows).set_index("month") if rows else pd.DataFrame(columns=["nmpa", "all_ports", "others"])
    return out


def months_held() -> list[str]:
    s = set()
    for d in _monthly_by_group().values():
        s |= set(d.index)
    return sorted(s)


def simple_compare(group: str, start: str, end: str) -> dict[str, Any]:
    """Compare NMPA with the other major ports for one cargo group over start..end (YYYY-MM), against a year earlier."""
    data = _monthly_by_group().get(group)
    if data is None:
        return {"available": False, "reason": f"Unknown cargo group: {group}"}
    want = [d.strftime("%Y-%m") for d in pd.date_range(start + "-01", end + "-01", freq="MS")]
    held = [mm for mm in want if mm in data.index]
    if not held:
        latest = data.index.max() if len(data) else None
        return {"available": False, "status": "Too early",
                "reason": f"No month of this period is in the Ministry's published data yet (latest held: {latest})."}
    prev = [(pd.Timestamp(mm + "-01") - pd.DateOffset(years=1)).strftime("%Y-%m") for mm in held]
    pairs = [(c, p) for c, p in zip(held, prev) if p in data.index]
    if not pairs:
        return {"available": False, "status": "No comparison year", "reason": "The same months a year earlier are not held."}
    cur_m, prev_m = [c for c, _ in pairs], [p for _, p in pairs]
    n_c, n_p = data.loc[cur_m, "nmpa"].sum(), data.loc[prev_m, "nmpa"].sum()
    o_c, o_p = data.loc[cur_m, "others"].sum(), data.loc[prev_m, "others"].sum()
    g_n, g_o = _pct(n_c, n_p), _pct(o_c, o_p)
    if n_p < SMALL_TONNES or g_n is None or g_o is None:
        return {"available": False, "status": "Too small to judge",
                "reason": "New Mangalore handled too little of this cargo a year earlier for a percentage to mean much."}
    effect = round(g_n - g_o, 1)
    extra_t = round(n_p * effect / 100)
    verdict = ("Better than the market" if effect >= EFFECT_POINTS else
               "Worse than the market" if effect <= -EFFECT_POINTS else "In line with the market")
    share_c = n_c / (n_c + o_c) * 100 if n_c + o_c else None
    share_p = n_p / (n_p + o_p) * 100 if n_p + o_p else None
    return {
        "available": True, "group": group, "months": cur_m, "compared_with": prev_m,
        "period": f"{pd.Timestamp(cur_m[0] + '-01'):%b %Y} to {pd.Timestamp(cur_m[-1] + '-01'):%b %Y}" if len(cur_m) > 1
                  else f"{pd.Timestamp(cur_m[0] + '-01'):%b %Y}",
        "partial": len(cur_m) < len(want), "months_wanted": len(want), "months_held": len(cur_m),
        "nmpa_tonnes": round(n_c), "nmpa_prev_tonnes": round(n_p), "nmpa_growth_pct": g_n,
        "others_tonnes": round(o_c), "others_prev_tonnes": round(o_p), "others_growth_pct": g_o,
        "effect_points": effect, "extra_tonnes": extra_t, "verdict": verdict,
        "share_pct": None if share_c is None else round(share_c, 2),
        "share_prev_pct": None if share_p is None else round(share_p, 2),
    }




def _period(start: str, end: str) -> str:
    f = lambda m: pd.Timestamp(m + "-01").strftime("%b %Y")
    return f(start) if start == end else f"{f(start)} to {f(end)}"


@_ttl_cache(seconds=300)
def get_scheme_review() -> dict[str, Any]:
    rows = []
    for s in SCHEMES:
        r = {"short": s["short"], "notice": s["notice"], "scheme_period": _period(s["start"], s["end"]), "aim": s.get("aim", "")}
        notes = [s["note"]] if s.get("note") else []
        if s.get("cargo"):
            e = iev.evaluate(s["cargo"], s["start"], s["end"])
            r["check"] = "Full check"
            if e.get("available"):
                r.update({"available": True, "result": e["verdict"], "extra_t": e["extra_credited_t"],
                          "extra_pct": e["extra_credited_pct"], "months_compared": len(e["months_compared"]),
                          "normal_range": e.get("normal_range"), "plain": e["plain_answer"]})
                notes += e.get("warnings", [])
            else:
                r.update({"available": False, "result": "Too early" if s["start"] > (iev_months_latest() or "") else "Not enough data",
                          "plain": e.get("plain_answer", "")})
        elif s.get("group"):
            e = simple_compare(s["group"], s["start"], s["end"])
            r["check"] = "Simple check"
            if e.get("available"):
                r.update({"available": True, "result": e["verdict"] + (" (so far)" if e["partial"] else ""),
                          "extra_t": e["extra_tonnes"], "extra_pct": e["effect_points"],
                          "months_compared": len(e["months"]),
                          "plain": (f"New Mangalore {e['nmpa_growth_pct']:+.1f}% against the other major ports "
                                    f"{e['others_growth_pct']:+.1f}% over {e['period']}, each against a year earlier: "
                                    f"a difference of {e['effect_points']:+.1f} points.")})
            else:
                r.update({"available": False, "result": e.get("status", "Not available"), "plain": e.get("reason", "")})
        else:
            r.update({"available": False, "check": "\u2014", "result": "Cannot be measured", "plain": s["why_not"]})
        if s.get("relief") and r.get("available"):
            notes.append(RELIEF_NOTE)
        r["notes"] = " ".join(notes)
        rows.append(r)
    judged = [r for r in rows if r.get("available")]
    return {"available": True, "rows": rows, "judged": len(judged), "total": len(rows),
            "latest_month": iev_months_latest(),
            "method": ("Full check: NMPA against the other major ports' trend, with the port's normal ups and downs "
                       "(see 'Did a discount work?' below). Simple check (coal and containers, which the full check does "
                       "not cover yet): NMPA's growth minus the other major ports' growth, each against a year earlier."),
            "source": "NMPA monthly commodity statements; Ministry of Ports monthly reports (Table-2)"}


def iev_months_latest() -> str | None:
    held = months_held()
    return held[-1] if held else None

# ═══════════════════════════════════════════════════════════════════
# 2. Customer-readiness condition
# ═══════════════════════════════════════════════════════════════════

def readiness_condition(customer: str | None = None, months: int = 6, max_wait_days: float = 0.0) -> dict[str, Any]:
    """If a rebate paid only on calls where the ship did not wait (beyond max_wait_days) because the customer side
    was not ready: how many calls and tonnes would have qualified over the last `months` complete months?"""
    from backend.app.services import trade_customers as tc
    b = tc.build()
    if not b.get("available"):
        return {"available": False}
    v, ev = b["voyages"].copy(), b["waiting"].copy()
    window = b["complete"][-months:] if b.get("complete") else sorted(v["month"].unique())[-months:]
    v = v[v["month"].isin(window)]
    if customer:
        v = v[v["customer"] == customer]
    if v.empty:
        return {"available": False, "reason": "No ship calls for this choice in the period."}
    nr = ev[ev["who"] == tc.CUSTOMER_NR][["vessel", "customer", "first_seen", "wait"]].copy() if not ev.empty else pd.DataFrame()
    calls = []
    for _, r in v.iterrows():
        w = 0.0
        if not nr.empty:
            hit = nr[(nr["vessel"] == r["vessel"]) & (nr["customer"] == r["customer"]) &
                     (nr["first_seen"] >= r["first_seen"] - pd.Timedelta(days=30)) & (nr["first_seen"] <= r["last_seen"])]
            w = float(pd.to_numeric(hit["wait"], errors="coerce").fillna(0).sum())
        calls.append({"vessel": r["vessel"], "customer": r["customer"], "month": r["month"], "cargo": r["family"],
                      "tonnes": r["tonnes"], "not_ready_days": round(w, 1), "qualifies": w <= max_wait_days})
    c = pd.DataFrame(calls)
    q = c[c["qualifies"]]
    by_cust = (c.assign(t=c["tonnes"].fillna(0), lost=c["not_ready_days"])
                 .groupby("customer").agg(calls=("vessel", "size"), qualifying=("qualifies", "sum"),
                                          ship_days_lost=("lost", "sum"), tonnes=("t", "sum"))
                 .reset_index().sort_values("ship_days_lost", ascending=False))
    by_cust["qualifying_pct"] = (by_cust["qualifying"] / by_cust["calls"] * 100).round(0)
    tot_t = float(c["tonnes"].fillna(0).sum())
    return {
        "available": True, "customer": customer or "All customers", "window": tc._window_label(window),
        "max_wait_days": max_wait_days, "calls": int(len(c)), "qualifying_calls": int(len(q)),
        "qualifying_pct": round(len(q) / len(c) * 100, 1),
        "tonnes": round(tot_t), "qualifying_tonnes": round(float(q["tonnes"].fillna(0).sum())),
        "qualifying_tonnes_pct": round(float(q["tonnes"].fillna(0).sum()) / tot_t * 100, 1) if tot_t else None,
        "ship_days_lost": round(float(c["not_ready_days"].sum()), 1),
        "by_customer": by_cust.head(15).round(1).to_dict(orient="records"),
        "calls_failing": c[~c["qualifies"]].sort_values("not_ready_days", ascending=False).head(15).to_dict(orient="records"),
        "customers": sorted(b["voyages"]["customer"].dropna().unique().tolist()),
        "source": "NMPA daily vessel position reports: ship calls and anchorage waiting with NMPA's recorded reason",
        "how": ("A call qualifies if its ship waited at most the allowed days at anchorage because the receiver, shipper "
                "or cargo was not ready. Waiting for a free berth or for the port's own reasons never counts against "
                "the customer."),
    }
