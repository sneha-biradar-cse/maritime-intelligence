"""
Incentive rules: which tariff version applies on a date, which charges NMPA controls, whether a proposed benefit is
eligible, how the baseline is set, and how a marginal slab rebate is calculated.

Principle: a missing or unconfirmed input BLOCKS an official proposal from moving past Draft; nothing is assumed.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_market as tmk

# Tariff versions by date. Only versions whose original is held can be used.
TARIFF_VERSIONS = [
    {"id": "NMPA-SOR-2025-26", "name": "NMPA Scale of Rates 2025-26 (1.74% indexation)", "from": "2025-05-01", "to": "2026-04-30",
     "held": True, "file": "nmpa_public_data/tariff_history/NMPA SOR w.e.f. 01.05.2025 to 30.04.2026 (1.74pc indexation).pdf",
     "note": "Printed 'Scale of Rates w.e.f 01.05.2025 to 30.04.2026'. Columns are foreign then coastal. Used to price past "
             "events in that year (e.g. the March 2026 waiver); not used for new proposals."},
    {"id": "NMPA-SOR-2026-OLD", "name": "NMPA Scale of Rates, old format", "from": "2026-05-01", "to": "2026-05-06",
     "held": True, "file": "nmpa_public_data/finance_and_policy/NMPA SOR 01-05-2026 to 06-05-2026 (old format).pdf",
     "note": "Printed 'Scale of Rates w.e.f. 01.05.2026 to 06.05.2026'. Columns are foreign then coastal. All 8 wharfage lines used "
             "here have the same values as in the version from 7 May 2026 (checked line by line)."},
    {"id": "NMPA-SOR-2026-0507", "name": "NMPA Scale of Rates, validity from 7 May 2026", "from": "2026-05-07", "to": "2027-04-30",
     "held": True, "file": "nmpa_public_data/Microsoft Word - NMPA SOR indexation 0.65.doc.pdf",
     "note": "Printed: 'SOR effective Date 01-05-2026 to 30-4-2027'; 'Period of validity 3 Years (w.e.f 07-05-2026)'."},
]

# Who controls each charge. A benefit can only be proposed on a charge NMPA controls.
CHARGE_CONTROL = {
    "Wharfage at NMPA berths (2-13, SPM)": {"nmpa_controls": True, "basis": "NMPA Scale of Rates"},
    "Containers at Berth 14": {"nmpa_controls": False, "basis": "JSW Mangalore Container Terminal (PPP): JSW sets and collects charges; NMPA earns a royalty"},
    "Coal at Berth 16": {"nmpa_controls": False, "basis": "Mangalore Coal Terminal Pvt Ltd (PPP, JSW-owned): NMPA earns 31% of gross revenue"},
    "Adani Power (UPCL) cargo at Berth 15": {"nmpa_controls": False, "basis": "Captive jetty under concession; billed under its own arrangement"},
    "KIOCL iron ore": {"nmpa_controls": None, "basis": "Own arrangement ('other than KIOCL' in the Scale of Rates): Finance must confirm"},
    "Vessel-related charges (port dues, pilotage, berth hire)": {"nmpa_controls": True, "basis": "NMPA Scale of Rates; not modelled yet (needs vessel size data)"},
}

COMBINATION_RULE = ("Benefits cannot be combined. A cargo or customer already covered by an approved or active scheme in an "
                    "overlapping period is blocked, unless an approved combination rule is recorded.")
KNOWN_BENEFIT_PERIODS = [  # benefits granted by NMPA, from its notices held (data/nmpa_incentive_notices.csv)
    {"cargos": ["LPG", "Crude oil"], "from": "2026-03-14", "to": "2026-03-31",
     "pct": 100, "charge": "wharfage", "name": "Waiver of cargo-related charges (NMPA Trade Circular NMPA/TM/2025-26/Gen.2)"},
    {"cargos": ["Iron ore exports"], "from": "2026-09-23", "to": "2027-03-31",
     "pct": 20, "charge": "wharfage", "name": "20% rebate on wharfage for incremental iron ore fines/lumps exports (NMPA Trade Notice NMPA/TM/IOF-Exp-Rebate/26-27)"},
    {"cargos": ["Containers"], "from": "2026-11-03", "to": "2027-03-31",
     "pct": 50, "charge": "vessel", "name": "35% / 50% rebate on vessel-related charges for feeder / mainline container vessels (NMPA Trade Notice Comrc/DTM(C)/2026-27/01)"},
    {"cargos": ["New bulk / break-bulk export cargo"], "from": "2026-07-29", "to": "2027-07-28",
     "pct": 25, "charge": "wharfage", "name": "25% wharfage concession for new export cargo not handled at NMPA in the preceding 5 years (NMPA Trade Notice NMPA/TM/SM/2026)"},
    {"cargos": ["Green fuel exports"], "from": "2025-07-01", "to": "2030-06-30",
     "pct": 75, "charge": "wharfage", "name": "40% / 75% wharfage concession for certified green fuel exports (NMPA Harit Cargo Concession Policy 2025)"},
    {"cargos": ["Cape-size vessels at Berth 16"], "from": "2025-04-03", "to": "2027-04-02",
     "pct": 30, "charge": "vessel", "name": "30% rebate on port dues and pilotage for Cape-size vessels at Berth 16 (NMPA Trade Notice 12/1/2021-22/ATM Gr.I (Com)/JSW)"},
]
BASELINE_METHODS = {
    "same_months_last_year": "Same months last year",
    "same_months_avg_years": "Average of the same months over several complete years",
    "contractual": "Contractual commitment (entered from the agreement)",
    "previous_fy": "Previous financial year, pro rata to the scheme's months (as NMPA's iron ore rebate)",
}


def tariff_for(date: str) -> dict | None:
    return next((v for v in TARIFF_VERSIONS if v["from"] <= date <= v["to"]), None)


def _identity_status() -> dict[str, str]:
    f = tmk.ROOT / "data" / "customer_identity_proposals.csv"
    if not f.exists():
        return {}
    d = pd.read_csv(f)
    out = {}
    for lab, stt in zip(d["label_in_daily_reports"], d["status"]):
        for part in str(lab).split("/"):
            out[part.strip().upper()] = stt
    return out


def check_eligibility(cargo: str, start: str, end: str, customers: list[str] | None = None,
                      existing_schemes: list[dict] | None = None, priced_cargos: list[str] | None = None,
                      exclude_id: str | None = None, discount_pct: float | None = None) -> dict[str, Any]:
    """discount_pct (optional): the proposed benefit; used only if the Board allows combining benefits up to a ceiling
    (data/incentive_policy.json). Without it, or without that policy, any overlap blocks, as before."""
    blocks, warnings, overlaps = [], [], []
    # 1. tariff version for every day of the scheme
    for d in pd.date_range(start, end, freq="D"):
        v = tariff_for(d.strftime("%Y-%m-%d"))
        if v is None:
            blocks.append(f"No NMPA tariff version is recorded for {d:%d %b %Y}.")
            break
        if not v["held"]:
            blocks.append(f"{d:%d %b %Y} falls under '{v['name']}', whose original is not held. {v['note']}")
            break
    # 2. charge controlled by NMPA, at a known rate
    if priced_cargos is not None and cargo not in priced_cargos:
        blocks.append(f"'{cargo}' has no NMPA wharfage rate in this tool (PPP berth, own arrangement or mixed rates).")
    # 3. customer identity
    ids = _identity_status()
    for c in customers or []:
        st = ids.get(c.strip().upper())
        if st and st.startswith("Unresolved"):
            blocks.append(f"Customer '{c}': identity not confirmed by NMPA ({st}).")
    if customers:
        from backend.app.services import incentive_engine as _ie
        warnings.append(_ie.daily_report_note())
    # 4. combination with other benefits
    for b in KNOWN_BENEFIT_PERIODS:
        if any(cargo.startswith(x) for x in b["cargos"]) and not (end < b["from"] or start > b["to"]):
            overlaps.append({"text": f"Overlaps an existing benefit: {b['name']} ({b['from']} to {b['to']}).", "pct": b.get("pct"),
                             "charge": b.get("charge", "wharfage")})
    for s in existing_schemes or []:
        if s.get("id") == exclude_id or s.get("status") not in ("Approved", "Active"):
            continue
        if s["cargo"] == cargo and not (end < s["start"] or start > s["end"]):
            overlaps.append({"text": f"Overlaps scheme {s['id']} ({s['status']}) on the same cargo.", "pct": s.get("discount_pct"),
                             "charge": "wharfage"})
    stacking = None
    if overlaps:
        from backend.app.services import incentive_portfolio as ipf
        stacking = ipf.combination_check(cargo, start, end, discount_pct, overlaps)
        if stacking.get("allowed"):
            warnings.extend(o["text"] + " Allowed by the Board's combination rule: " + stacking["plain"] for o in overlaps)
        else:
            extra = (" " + stacking["plain"]) if stacking.get("plain") else ""
            blocks.extend(o["text"] + " " + COMBINATION_RULE + extra for o in overlaps)
    # 5. things the tool cannot check yet
    warnings.append("Operational capacity (berth, equipment, storage, evacuation) is not checked: Marine / Operations to confirm.")
    warnings.append("Costs of handling extra cargo are not known: results are wharfage receipts, not profit.")
    return {"eligible": not blocks, "blocks": blocks, "warnings": warnings,
            "tariff": tariff_for(start), "combination_rule": COMBINATION_RULE, "stacking": stacking}


def baseline(keys: list, months: list[str], method: str, years: int = 3, contractual_t: float | None = None) -> dict[str, Any]:
    """The tonnes expected WITHOUT the scheme for the scheme's months. Missing months block the calculation."""
    if method not in BASELINE_METHODS:
        raise ValueError(f"method must be one of {list(BASELINE_METHODS)}")
    if method == "contractual":
        if not contractual_t or contractual_t <= 0:
            return {"method": method, "label": BASELINE_METHODS[method], "tonnes": None,
                    "blocked": "Enter the committed tonnes from the agreement."}
        return {"method": method, "label": BASELINE_METHODS[method], "tonnes": round(contractual_t), "blocked": None,
                "detail": "Entered from the agreement."}
    wide = ti._prepared()["wide"]
    if method == "previous_fy":
        start = pd.Timestamp(months[0] + "-01")
        fy = start.year if start.month >= 4 else start.year - 1          # the scheme's financial year starts in April of this year
        prev = pd.date_range(f"{fy - 1}-04-01", f"{fy}-03-01", freq="MS")
        miss, tot = [], 0.0
        for d in prev:
            vals = [wide.loc[d, k] for k in keys if d in wide.index and k in wide.columns]
            if not vals or any(pd.isna(v) for v in vals):
                miss.append(d.strftime("%b %Y"))
                continue
            tot += float(sum(vals))
        if miss:
            return {"method": method, "label": BASELINE_METHODS[method], "tonnes": None,
                    "blocked": "Months missing from NMPA's statements: " + ", ".join(miss) + "."}
        t = tot * len(months) / 12
        return {"method": method, "label": BASELINE_METHODS[method], "tonnes": round(t), "blocked": None,
                "detail": f"FY {fy - 1}-{str(fy)[2:]}: {tot:,.0f} t in 12 months x {len(months)}/12 months of the scheme",
                "source": "NMPA monthly commodity statements"}
    back = [1] if method == "same_months_last_year" else list(range(1, years + 1))
    per_year, missing = {}, []
    for b in back:
        tot = 0.0
        for m in months:
            d = pd.Timestamp(m + "-01") - pd.DateOffset(years=b)
            vals = [wide.loc[d, k] for k in keys if d in wide.index and k in wide.columns]
            if not vals or any(pd.isna(v) for v in vals):
                missing.append(d.strftime("%b %Y"))
                continue
            tot += float(sum(vals))
        per_year[f"{b} year(s) earlier"] = round(tot)
    if missing:
        return {"method": method, "label": BASELINE_METHODS[method], "tonnes": None,
                "blocked": "Months missing from NMPA's statements: " + ", ".join(sorted(set(missing))) + ". Not averaged over."}
    t = sum(per_year.values()) / len(per_year)
    return {"method": method, "label": BASELINE_METHODS[method], "tonnes": round(t), "blocked": None,
            "detail": "; ".join(f"{k}: {v:,} t" for k, v in per_year.items()), "source": "NMPA monthly commodity statements"}


def marginal_rebate(actual_t: float, baseline_t: float, rate: float, tiers: list[dict], cap_rs: float | None = None) -> dict:
    """Marginal slabs: each block of tonnes ABOVE the baseline gets its own rebate rate.
    tiers: [{'up_to_pct_above_baseline': 10, 'rebate_pct': 5}, {'up_to_pct_above_baseline': 20, 'rebate_pct': 8}, ...];
    the last tier may have up_to_pct_above_baseline = None (no upper limit)."""
    extra = max(actual_t - baseline_t, 0.0)
    out, lower, total = [], 0.0, 0.0
    for t in sorted(tiers, key=lambda x: float("inf") if x.get("up_to_pct_above_baseline") is None else x["up_to_pct_above_baseline"]):
        upper = None if t.get("up_to_pct_above_baseline") is None else baseline_t * t["up_to_pct_above_baseline"] / 100
        block = max(min(extra, upper) - lower, 0.0) if upper is not None else max(extra - lower, 0.0)
        amt = block * rate * t["rebate_pct"] / 100
        out.append({"from_t": round(lower), "to_t": None if upper is None else round(upper), "tonnes": round(block),
                    "rebate_pct": t["rebate_pct"], "rebate_rs": round(amt)})
        total += amt
        if upper is None:
            break
        lower = upper
    capped = cap_rs is not None and cap_rs > 0 and total > cap_rs
    return {"extra_tonnes": round(extra), "tiers": out, "rebate_before_cap_rs": round(total),
            "rebate_rs": round(min(total, cap_rs) if capped else total), "capped": capped,
            "status": "Potential (scenario): accrued, approved and paid amounts need NMPA billing records"}
