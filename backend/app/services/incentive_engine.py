"""
Incentive Engine - evidence-based: what cargo earns the port, what concessions cost, what past incentives were
followed by, where an incentive could win cargo back, and the break-even arithmetic of any discount.

Everything here is built from real records and the port's own tariff. Nothing assumes how shippers react to a
price change; where the data cannot show cause and effect, the output says so.

Data (all real, all already in the project):
  * NMPA monthly commodity statements                    tonnes per cargo (trade_intelligence._prepared())
  * NMPA Scale of Rates (nmpa_public_data/Microsoft Word - NMPA SOR indexation 0.65.doc.pdf), wharfage rates per
    tonne, as coded in cost_engine.WHARFAGE_RATES. The test suite checks every rate used here against the PDF text.
  * NMPA daily vessel reports                            coastal share of each cargo, and customer mix (KIOCL, UPCL)
  * Ministry of Ports Table-2                            all-major-port tonnes per cargo (via trade_market)

Legal basis for incentives: Scale of Rates, General Terms (xx)(a): "The rates prescribed in the Scale of Rates are
ceiling levels ... The Port may, if it so desires, charge lower rates than the notified rates and/or allow higher
rebates and discounts or increase the prescribed free period."
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.app.services import cost_engine as ce
from backend.app.services import trade_customers as tcu
from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_market as tmk
from backend.app.services import trade_split as ts
from backend.app.services.forecasting import _ttl_cache

SOR_FILE = "nmpa_public_data/Microsoft Word - NMPA SOR indexation 0.65.doc.pdf"
SOR_NOTE = ("NMPA Scale of Rates, validity from 7 May 2026 (printed 'SOR effective Date 01-05-2026 to 30-4-2027'; 'validity 3 "
            "Years w.e.f. 07-05-2026'). The old-format version for 1 to 6 May 2026 has the same values for every wharfage line used. Rates are ceilings; the port may charge lower rates or allow higher rebates "
            "(General Terms xx(a)).")
TARIFF_VERSION = ("NMPA Scale of Rates: 1-6 May 2026 old-format version and version with validity from 7 May 2026 "
                  "(same values for every wharfage line used)")
TARIFF_FROM, TARIFF_TO = "2026-05-01", "2027-04-30"

# Cargo -> NMPA statement keys, the Scale of Rates wharfage line (cost_engine key + the SOR wording), the cargo
# group in the daily reports used for the coastal share, and customers whose cargo is billed outside these rates.
CARGO = {
    "Crude oil":             {"keys": [("UNLOADED", "TOTALCRUDE")], "sor_find": "Single Point Mooring", "rate": "crude_spm",
                              "berth_rate": "pol_products", "berth_sor_find": "Crude Oil",
                              "sor_line": "Crude oil through SPM (34.89/34.90); crude at berths: POL Products (d) Crude Oil (96.60)",
                              "family": ("Crude oil", "inbound")},
    "Crude oil out of ISPRL": {"keys": [("LOADED", "CRUDEISPRL")], "sor_find": "Single Point Mooring", "rate": "crude_spm",
                              "sor_line": "Crude oil through Single Point Mooring (ISPRL crude is loaded at the SPM in the daily reports)",
                              "family": None, "coastal_share": 0.0},
    "POL products (out)":    {"keys": [("LOADED", "POLPRODUCTS")], "sor_find": "Diesel Oil", "rate": "pol_products",
                              "sor_line": "POL Products (petrol, diesel, naphtha, fuel oil, ...)", "family": ("Petroleum products (fuels)", "outbound")},
    "POL products (in)":     {"keys": [("UNLOADED", "POLPRODUCTS")], "sor_find": "Diesel Oil", "rate": "pol_products",
                              "sor_line": "POL Products", "family": ("Petroleum products (fuels)", "inbound")},
    "LPG":                   {"keys": [("UNLOADED", "TOTALLPG")], "sor_find": "LPG/LNG", "rate": "lpg_lng_gas",
                              "sor_line": "LPG/LNG or any gas in any other form", "family": ("LPG", "inbound")},
    "Iron ore exports":      {"keys": [("LOADED", "IRONORE")], "sor_find": "Iron Ore Fines", "rate": "iron_ore_fines_lumps",
                              "sor_line": "Iron Ore Fines/Lumps", "family": ("Iron ore", "outbound"), "exclude_customer": "KIOCL"},
    "Edible oil":            {"keys": [("UNLOADED", "EDIBLEOIL")], "sor_find": "", "rate": "edible_oil",
                              "sor_line": "Edible Oil and other liquids", "family": ("Edible oil", "inbound")},
    "Fertilizer (finished)": {"keys": [("UNLOADED", "FERTILIZER")], "sor_find": "MOP", "rate": "fertilizer",
                              "sor_line": "MOP, SOP, Urea, DAP, NPK ... finished fertilizer", "family": ("Fertilizer and chemicals", "inbound")},
    "Fertilizer raw materials (dry)": {"keys": [("UNLOADED", "FRMDRY")], "sor_find": "Rock phosphate", "rate": "rock_phosphate_sulphate",
                              "sor_line": "Sulphate / Rock phosphate", "family": ("Fertilizer and chemicals", "inbound")},
    "Food grains":           {"keys": [("UNLOADED", "FOODGRAINS"), ("LOADED", "FOODGRAINS")], "sor_find": "Rice", "rate": "food_grains",
                              "sor_line": "Rice, Wheat, Maize, Pulses", "family": ("Food grains and sugar", "outbound")},
}
# Scale of Rates lines not (yet) in cost_engine.WHARFAGE_RATES - same tariff, checked against the PDF by the tests.
EXTRA_RATES = {
    "rock_phosphate_sulphate": {"coastal": 30.47, "foreign": 52.04},   # II Fertilizer & Raw Materials, b) Sulphate/ Rock phosphate
    "food_grains": {"coastal": 30.47, "foreign": 52.04},                # a) Rice, Wheat, Maize, Pulses
}


def _rate(key: str) -> dict[str, float]:
    return ce.WHARFAGE_RATES.get(key) or EXTRA_RATES[key]
NOT_ESTIMATED = [
    ("Iron ore imports (KIOCL)", "KIOCL's iron ore is billed under its own arrangement ('other than KIOCL' in the Scale of Rates)."),
    ("Coal for UPCL / Adani Power", "Handled at Berth 15, UPCL's captive jetty under a 30-year concession (UPCL is now Adani "
     "Power Ltd, shown as APL in the daily reports; NMPA PPP disclosure 3.1.3). Billed under its own arrangement ('other than "
     "UPCL' in the Scale of Rates)."),
    ("Other coal (Berth 16)", "Handled at Berth 16, a PPP terminal (Mangalore Coal Terminal Pvt Ltd, owned by JSW Infrastructure "
     "since Dec 2020), where NMPA earns a royalty of 31% "
     "of the operator's gross revenue (NMPA, PPP disclosure 3.1.3). The operator's charges are not in the documents held."),
    ("Containers (Berth 14)", "Handled at Berth 14 by JSW Mangalore Container Terminal under a PPP concession: JSW collects the "
     "container charges and NMPA earns a royalty per TEU. Shown separately below as royalty, not wharfage."),
    ("Other cargo, other liquids, petrochemicals, cement",
     "Each covers several items with different rates in the Scale of Rates; a single rate would be a guess."),
    ("Vessel-related charges", "Port dues, pilotage and berth hire depend on each ship's size and stay; not included here."),
    ("Waivers, rebates and discounts granted by NMPA", "From NMPA's notices held (all listed under Schemes, NMPA's "
     "own incentive schemes): the March 2026 crude/LPG waiver ended on 31 Mar 2026 and does not affect these figures; the 20% "
     "rebate on incremental iron ore exports (to 31 Mar 2027) is NOT deducted, because it is paid per exporter after the year "
     "against each exporter's 2025-26 quantity, which public data cannot show; the new-export-cargo policy (25%) and the Harit "
     "green cargo policy (40% / 75%) apply only to cargo not in the cargos priced here; the container (35% / 50%) and Cape-size "
     "(30%) rebates are on vessel-related charges, not wharfage."),
]


def _fy_months(latest: pd.Timestamp) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    start = pd.Timestamp(latest.year if latest.month >= 4 else latest.year - 1, 4, 1)
    cur = pd.date_range(start, latest, freq="MS")
    return cur, cur - pd.DateOffset(years=1)


def _crude_spm_share() -> float | None:
    """Share of inbound crude tonnes discharged at the SPM (berth 'SPM' in NMPA's daily reports); the rest at berths 10/11."""
    import json
    seen = {}
    for p in ts.DAILY_DIR.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        day = pd.Timestamp(d["report_date"])
        for r in d.get("berthed", []):
            seen[(ts._vessel_norm(r.get("vessel_name")), day)] = str(r.get("berth_no") or "").upper()
    v = ts.build_voyages()
    c = v[(v["family"] == "Crude oil") & (v["direction"] == "inbound") & v["qty"].notna()]
    if c.empty:
        return None
    spm = [("SPM" in seen.get((r.vessel, r.last_seen), "")) for r in c.itertuples()]
    return float(c.loc[spm, "qty"].sum() / c["qty"].sum())


def _sor_ref() -> dict:
    import json
    f = tmk.ROOT / "data" / "sor_reference.json"
    return json.loads(f.read_text(encoding="utf-8"))["lines"] if f.exists() else {}


def _coastal_shares() -> dict[tuple[str, str], float]:
    """Coastal share of each cargo group, by quantity, from the F/C flag in NMPA's daily reports."""
    out = {}
    for f in ts.get_cargo_split().get("families", []):
        q = f.get("coastal_share_by_quantity_pct")
        if q is None:
            q = f.get("coastal_share_by_ships_pct")
        if q is not None:
            out[(f["cargo"], f["direction"])] = float(q) / 100
    return out


def _customer_share(family: tuple[str, str], customer: str) -> float | None:
    """Share of a cargo group's traced tonnes that belongs to one customer (daily reports)."""
    b = tcu.build()
    v = b["voyages"]
    g = v[(v["family"] == family[0]) & (v["direction"] == family[1])]
    tot = g["tonnes"].sum()
    if not tot:
        return None
    return float(g.loc[g["customer"] == customer, "tonnes"].sum() / tot)


@_ttl_cache(seconds=300)
def get_revenue() -> dict[str, Any]:
    """Estimated wharfage earned per cargo, this financial year so far and the same months last year, at today's rates;
    and the revenue the coastal concession gives up."""
    p = ti._prepared()
    wide = p["wide"]
    cur_m, prev_m = _fy_months(wide.index.max())
    shares = _coastal_shares()
    spm_share = _crude_spm_share()
    ref = _sor_ref()
    rows = []
    for name, c in CARGO.items():
        rate = _rate(c["rate"])
        coastal = c.get("coastal_share", shares.get(c["family"], 0.0) if c["family"] else 0.0)
        excl_share = _customer_share(c["family"], c["exclude_customer"]) if c.get("exclude_customer") else 0.0
        keep = 1.0 - (excl_share or 0.0)

        def tonnes(months):
            return float(sum(wide.reindex(months)[k].fillna(0).sum() for k in c["keys"] if k in wide.columns)) * keep
        t_cur, t_prev = tonnes(cur_m), tonnes(prev_m)
        blend = lambda r_: (1 - coastal) * r_["foreign"] + coastal * r_["coastal"]
        conc = lambda r_: coastal * (r_["foreign"] - r_["coastal"])
        if c.get("berth_rate") and spm_share is not None:
            br = _rate(c["berth_rate"])
            blended = spm_share * blend(rate) + (1 - spm_share) * blend(br)
            conc_per_t = spm_share * conc(rate) + (1 - spm_share) * conc(br)
        else:
            blended, conc_per_t = blend(rate), conc(rate)
        src = ref.get(c["rate"], {})
        months_txt = f"{cur_m[0]:%b %Y} to {cur_m[-1]:%b %Y}"
        steps = [
            f"Tonnes: NMPA monthly commodity statements, {', '.join(p['names'].get(k[1], k[1]) + ' (' + ('unloaded' if k[0] == 'UNLOADED' else 'loaded') + ')' for k in c['keys'])}, "
            f"{months_txt}: {t_cur / keep if keep else 0:,.0f} t.",
        ]
        if excl_share:
            steps.append(f"Less {c['exclude_customer']}'s share ({excl_share * 100:.1f}% of this cargo in the daily reports; billed under its own "
                         f"arrangement): {t_cur:,.0f} t priced here.")
        steps.append(f"Tariff: Scale of Rates, page {src.get('printed_page', '?')}: \"{src.get('line', c['sor_line'])}\" "
                     f"(coastal \u20b9{rate['coastal']:.2f}, foreign \u20b9{rate['foreign']:.2f} per tonne).")
        if c.get("berth_rate") and spm_share is not None:
            bsrc = ref.get(c["berth_rate"], {})
            steps.append(f"{spm_share * 100:.0f}% of crude tonnes were discharged at the SPM and {100 - spm_share * 100:.0f}% at berths "
                         f"(daily reports). Crude at berths: Scale of Rates page {bsrc.get('printed_page', '?')}, POL Products (d) Crude Oil, "
                         f"\u20b9{_rate(c['berth_rate'])['foreign']:.2f}/t.")
        steps.append(f"Foreign/coastal: {coastal * 100:.0f}% coastal (F/C flag in NMPA's daily reports).")
        steps.append(f"Average rate \u20b9{blended:.2f}/t x {t_cur:,.0f} t = \u20b9{t_cur * blended:,.0f}.")
        rows.append({
            "cargo": name, "sor_line": c["sor_line"], "sor_page": src.get("printed_page"),
            "rate_foreign": rate["foreign"], "rate_coastal": rate["coastal"],
            "spm_share_pct": round(spm_share * 100, 1) if (c.get("berth_rate") and spm_share is not None) else None,
            "coastal_share_pct": round(coastal * 100, 1),
            "excluded_customer": c.get("exclude_customer"), "excluded_share_pct": None if not excl_share else round(excl_share * 100, 1),
            "tonnes": round(t_cur), "tonnes_prev": round(t_prev),
            "revenue_rs": round(t_cur * blended), "revenue_prev_rs": round(t_prev * blended),
            "revenue_change_rs": round((t_cur - t_prev) * blended),
            "coastal_concession_rs": round(t_cur * conc_per_t),
            "avg_rate_rs_per_t": round(blended, 2),
            # Three separate money figures - never substituted for one another.
            "estimate_full_tariff_rs": round(t_cur * blended),
            "estimate_after_known_adjustments_rs": None,
            "adjustments_status": ("None in this period: the March 2026 waiver (Trade Circular NMPA/TM/2025-26/Gen.2) applied only "
                                   "to vessels berthed up to 31 Mar 2026" if name in ("LPG", "Crude oil") else
                                   "Not deducted: the 20% rebate on incremental exports (from 23 Sep 2026) is settled per exporter "
                                   "after 31 Mar 2027" if name == "Iron ore exports" else "None known"),
            "billed_rs": None, "billed_status": "Not provided yet (NMPA Finance)",
            "evidence": "Estimated",
            "calculation": steps,
        })
    rows.sort(key=lambda r: -r["revenue_rs"])
    tot = {k: sum(r[k] for r in rows) for k in ("revenue_rs", "revenue_prev_rs", "revenue_change_rs", "coastal_concession_rs", "tonnes", "tonnes_prev")}
    lbl = lambda ms: f"{ms[0]:%b %Y} to {ms[-1]:%b %Y}"
    return {"available": True, "period": lbl(cur_m), "previous_period": lbl(prev_m), "cargos": rows, "total": tot,
            "not_estimated": [{"item": a, "why": b} for a, b in NOT_ESTIMATED],
            "basis": ["Wharfage only, at the Scale of Rates in force today, for both periods (so the change reflects tonnes, not tariff revisions).",
                      "Foreign/coastal split per cargo from the F/C flag in NMPA's daily vessel reports (share of tonnes).",
                      "Customers billed under their own arrangements (UPCL coal, KIOCL iron ore) are taken out using their share "
                      "of the cargo in the daily reports.",
                      "Crude: the SPM rate applies only to crude discharged at the SPM; crude at berths 10/11 pays the POL rate. The split "
                      "comes from the berth recorded for each crude ship in the daily reports.",
                      "No waiver applies to April 2026 onward: the March 2026 LPG/crude waiver ended on 31 Mar 2026 (Trade Circular "
                      "NMPA/TM/2025-26/Gen.2).",
                      "These are estimates for comparison and planning. NMPA Finance's billed figures are the authority."],
            "tariff": SOR_NOTE, "tariff_file": SOR_FILE}


@_ttl_cache(seconds=300)
def get_evidence() -> dict[str, Any]:
    """What happened around real incentives. Shown as before/after against all major ports, never as proven cause."""
    m = pd.read_csv(tmk.FILE)
    wide = ti._prepared()["wide"]
    mon = m[m["period"] == "month"].pivot_table(index="through", columns="commodity", values="tonnes", aggfunc="sum")

    def month_share(mth, keys, lines):
        """New Mangalore tonnes and all-major-port tonnes for one month, or None if the Ministry table lacks the cargo."""
        if mth not in mon.index or not all(l in mon.columns and pd.notna(mon.loc[mth, l]) for l in lines):
            return None
        d = pd.Timestamp(mth + "-01")
        if d not in wide.index:
            return None
        n = sum(float(wide.loc[d, k]) for k in keys if k in wide.columns and pd.notna(wide.loc[d, k]))
        return n, float(mon.loc[mth, lines].sum())

    cases = []
    # Trade Circular NMPA/TM/2025-26/Gen.2 (14 Mar 2026): cargo-related charges waived for crude oil and LPG, vessels declared
    # after 14 Mar and berthed up to 31 Mar 2026. So the waiver covered part of March 2026 only.
    def nm(mth, key):
        d = pd.Timestamp(mth + "-01")
        return float(wide.loc[d, key]) if d in wide.index and key in wide.columns and pd.notna(wide.loc[d, key]) else None
    shares = {r["month"]: r.get("Crude, POL products and LPG") for r in tmk.get_market_share().get("monthly_share_groups", [])}
    for cargo, key in (("LPG", ("UNLOADED", "TOTALLPG")), ("Crude oil", ("UNLOADED", "TOTALCRUDE"))):
        mar, feb, mar_ly = nm("2026-03", key), nm("2026-02", key), nm("2025-03", key)
        if None in (mar, feb, mar_ly):
            cases.append({"incentive": f"Waiver of cargo-related charges for {cargo} (14-31 Mar 2026)", "cargo": cargo,
                          "measurable": False, "result": "Monthly tonnes around March 2026 are not all held."})
            continue
        cases.append({"incentive": f"Waiver of cargo-related charges for {cargo} (14-31 Mar 2026)", "cargo": cargo, "measurable": True,
                      "waiver_window": True, "march_2026_t": round(mar), "feb_2026_t": round(feb), "march_2025_t": round(mar_ly),
                      "vs_feb_pct": round((mar / feb - 1) * 100, 1), "vs_march_2025_pct": round((mar / mar_ly - 1) * 100, 1),
                      "group_share_march_2026": shares.get("2026-03"), "group_share_dec_feb": (
                          round(sum(shares[m] for m in ("2025-12", "2026-01", "2026-02") if shares.get(m)) / 3, 2)
                          if all(shares.get(m) for m in ("2025-12", "2026-01", "2026-02")) else None),
                      "group_share_march_2025": shares.get("2025-03"),
                      "source": "NMPA Trade Circular NMPA/TM/2025-26/Gen.2 (14 Mar 2026); NMPA monthly statements; Ministry of Ports "
                                "report (March gives crude, POL products and LPG only together)"})
    # The coastal concession applies at every major port, so NMPA vs all ports shows what is specific to NMPA.
    mp = pd.read_csv(tmk.ROOT / "data" / "major_ports_monthly.csv")
    oc = None
    for f in sorted((tmk.ROOT / "data").glob("major_ports_ministry_*.csv")):
        oc = pd.read_csv(f)
    if oc is not None:
        ytd = sorted(p for p in oc["period"].unique() if "Apr-" in p)
        cur, prev = ytd[-1], ytd[0]
        nm = oc[oc["port"] == "New Mangalore"].set_index("period")
        allp = oc.groupby("period")[["coastal_t", "overseas_t"]].sum()
        g = lambda a, b: round(float(a / b - 1) * 100, 1)
        cases.append({"incentive": "Concessional coastal rates (Scale of Rates; national coastal policy)", "cargo": "Coastal cargo",
                      "measurable": True, "comparison_only": True,
                      "nmpa_coastal_growth_pct": g(nm.loc[cur, "coastal_t"], nm.loc[prev, "coastal_t"]),
                      "all_ports_coastal_growth_pct": g(allp.loc[cur, "coastal_t"], allp.loc[prev, "coastal_t"]),
                      "other_ports_coastal_growth_pct": g(allp.loc[cur, "coastal_t"] - nm.loc[cur, "coastal_t"],
                                                          allp.loc[prev, "coastal_t"] - nm.loc[prev, "coastal_t"]),
                      "nmpa_overseas_growth_pct": g(nm.loc[cur, "overseas_t"], nm.loc[prev, "overseas_t"]),
                      "period": cur, "source": "Ministry of Ports, Table-1"})
    return {"available": True, "cases": cases,
            "caution": ("The March 2026 waiver lasted about two and a half weeks (vessels declared after 14 March and berthed by "
                        "31 March), during the West Asia supply disruption, so a monthly figure cannot isolate its effect. "
                        "These compare New Mangalore before and after an incentive with the other 11 major ports. A change in share "
                        "after an incentive is consistent with an effect but does not prove it: other events (refinery schedules, "
                        "the West Asia situation, monsoon) happen at the same time. The coastal concession applies at every major "
                        "port, so it cannot explain why New Mangalore's coastal cargo grew faster than other ports'.")}


ACTION_TYPES = ["Commercial follow-up with the customer", "Documentation or process improvement",
                "Receiver / shipper readiness coordination", "Equipment or evacuation coordination",
                "Tariff incentive (only where approved by NMPA)", "No action: monitor"]
FAMILIES = {"POL products": ["Petroleum products (fuels)"], "Iron ore": ["Iron ore"], "Coal": ["Coal"],
            "Containers (tonnes)": ["Containers"], "Crude oil": ["Crude oil"], "LPG": ["LPG"], "Edible oil": ["Edible oil"]}


@_ttl_cache(seconds=300)
def get_opportunities() -> dict[str, Any]:
    """Cargos losing share at New Mangalore. Each is a STATISTICAL VOLUME GAP that should trigger a commercial review,
    not a discount: the output lists who to talk to, what the data already says, and why an incentive may not fit."""
    ms = tmk.get_market_share()
    if not ms.get("available"):
        return {"available": False}
    rev = {r["cargo"]: r for r in get_revenue()["cargos"]}
    link = {"POL products": ["POL products (out)", "POL products (in)"], "Iron ore": ["Iron ore exports"],
            "Crude oil": ["Crude oil"], "LPG": ["LPG"],
            "Edible oil": ["Edible oil"], "Fertilizer and raw materials": ["Fertilizer (finished)", "Fertilizer raw materials (dry)"],
            "Food grains": ["Food grains"]}
    cw = tcu.get_customer_watch()
    out = []
    for r in ms["cargos"]:
        if r["share_prev_pct"] is None or r["share_change_points"] is None or r["share_change_points"] >= 0:
            continue
        lost_t = r["share_prev_pct"] / 100 * r["all_ports_tonnes"] - r["nmpa_tonnes"]
        rates = [rev[n]["avg_rate_rs_per_t"] for n in link.get(r["cargo"], []) if n in rev]
        rate = sum(rates) / len(rates) if rates else None
        fams = FAMILIES.get(r["cargo"], [])
        # Customers who actually move this cargo (any customer, ranked by their tonnes of it in the daily reports)
        custs = []
        if cw.get("available") and fams:
            v = tcu.build()["voyages"]
            g = v[v["family"].isin(fams) & (v["customer"] != tcu.NOT_STATED)]
            top_names = (g.groupby("customer")["tonnes"].sum().sort_values(ascending=False).head(3).index.tolist()
                         if g["tonnes"].notna().any() else g["customer"].value_counts().head(3).index.tolist())
            by = {c["customer"]: c for c in cw["customers"]}
            custs = [by[n] for n in top_names if n in by]
        flags = []
        if r["note"].startswith("Falling at all"):
            flags.append("Falling at other major ports too: not a local problem, so an incentive is unlikely to help.")
        if r["cargo"] == "Coal":
            flags.append("Coal is handled at Berth 15 (UPCL, own arrangement) and Berth 16 (a PPP terminal, where NMPA earns a "
                         "31% revenue share): any incentive would involve the terminal operator and Finance.")
        if r["cargo"] == "Iron ore":
            flags.append("KIOCL's iron ore is billed under its own arrangement: Finance review needed for that part.")
        if r["cargo"] in ("LPG", "Crude oil"):
            flags.append("A full waiver of cargo charges was tried for crude and LPG in late March 2026 (Trade Circular "
                         "NMPA/TM/2025-26/Gen.2); see 'What happened after past incentives' before proposing another.")
        if r["cargo"].startswith("Containers"):
            flags.append("Containers are handled at Berth 14 by JSW under a PPP concession: JSW sets and collects the container "
                         "charges, NMPA earns a royalty per TEU. A tariff incentive would be JSW's decision, not NMPA's.")
        if any(c["joint_entry"] or c["agent_name_warning"] for c in custs):
            flags.append("Some customer names are joint entries or agent names: confirm customer identity first.")
        nr = sum(c["not_ready_ship_days"] or 0 for c in custs)
        if nr >= 20:
            flags.append(f"These customers' ships waited {nr:.0f} ship-days because the customer side was not ready: "
                         "a readiness issue, which a discount would not fix.")
        names = ", ".join(c["customer"] for c in custs) or "the main customers of this cargo"
        action = (f"Commercial review with {names}: confirm the reason for the gap (production or shipment timing, switching to "
                  "another port, capacity or service at New Mangalore, or charges). Consider a tariff incentive only if charges are "
                  "confirmed as the barrier.")
        out.append({"cargo": r["cargo"], "status": r["status"], "share_prev_pct": r["share_prev_pct"], "share_pct": r["share_pct"],
                    "nmpa_growth_pct": r["nmpa_growth_pct"], "other_ports_growth_pct": r.get("other_ports_growth_pct"),
                    "tonnes_not_won": round(lost_t), "avg_rate_rs_per_t": None if rate is None else round(rate, 2),
                    "wharfage_at_stake_rs": None if rate is None else round(lost_t * rate),
                    "signal": "Statistical volume gap (not yet confirmed by Traffic)",
                    "customers": [{"customer": c["customer"], "status": c["status"], "change_pct": c["change_pct"],
                                   "share_pct": c["share_of_traced_tonnes_pct"], "not_ready_ship_days": c["not_ready_ship_days"]} for c in custs],
                    "flags": flags, "suggested_next_step": action, "note": r["note"]})
    out.sort(key=lambda x: -(x["wharfage_at_stake_rs"] or 0))
    return {"available": True, "period": ms["period_label"], "cargos": out, "action_types": ACTION_TYPES,
            "explain": ("Tonnes not won = what New Mangalore would have handled had it kept last year's share of this year's "
                        "all-major-port volume, minus what it handled. Priced at the average wharfage rate for that cargo. "
                        "This is a statistical gap: it starts a commercial review; it is not a recommendation to discount.")}


def break_even(cargo: str, discount_pct: float) -> dict[str, Any]:
    """Pure arithmetic for a wharfage discount on one cargo: revenue given up on today's volume, and the extra tonnes
    needed at the discounted rate to earn the same as before. No assumption about how shippers respond."""
    rev = {r["cargo"]: r for r in get_revenue()["cargos"]}
    if cargo not in rev:
        raise KeyError(cargo)
    if not 0 < discount_pct < 100:
        raise ValueError("discount_pct must be between 0 and 100")
    r = rev[cargo]
    months = len(_fy_months(ti._prepared()["wide"].index.max())[0])
    annual_t = r["tonnes"] / months * 12
    rate, d = r["avg_rate_rs_per_t"], discount_pct / 100
    given_up = annual_t * rate * d
    extra_t = given_up / (rate * (1 - d))
    return {"cargo": cargo, "discount_pct": discount_pct, "rate_rs_per_t": rate, "discounted_rate_rs_per_t": round(rate * (1 - d), 2),
            "annual_tonnes_now": round(annual_t), "revenue_given_up_rs": round(given_up),
            "extra_tonnes_to_break_even": round(extra_t), "extra_pct_to_break_even": round(extra_t / annual_t * 100, 1),
            "formula": "Extra tonnes = (annual tonnes x rate x discount) / (rate x (1 - discount)) = annual tonnes x discount / (1 - discount)",
            "note": "Annual tonnes = this financial year so far, scaled to 12 months. Wharfage only."}


def scenario(cargo: str, discount_pct: float, cost_per_t: float = 0.0, fixed_cost: float = 0.0,
             low_response_pct: float = 2.0, target_t: float | None = None) -> dict[str, Any]:
    """
    Compare two ways of offering a wharfage discount on one cargo, with plain arithmetic only.

      r  = average wharfage per tonne today            d  = discount (fraction)
      Q0 = baseline: this year's tonnes, annualised     dQ = extra tonnes won
      c  = extra cost to the port per extra tonne       F  = fixed cost of running the scheme
    Blanket discount (every tonne pays less):
      change = [r(1-d) - c] dQ - r d Q0 - F            break-even dQ = (r d Q0 + F) / (r(1-d) - c)
    Rebate only on tonnes above the baseline:
      change = [r(1-d) - c] dQ - F                     break-even dQ = F / (r(1-d) - c)
    Without costs entered, "change" is the change in wharfage receipts, not profit.
    Nothing here predicts how much cargo a discount would win: each scenario's extra tonnes are stated inputs.
    """
    rev = {r_["cargo"]: r_ for r_ in get_revenue()["cargos"]}
    if cargo not in rev:
        raise KeyError(cargo)
    if not 0 <= discount_pct < 100:
        raise ValueError("discount_pct must be between 0 and 100")
    row = rev[cargo]
    wide = ti._prepared()["wide"]
    latest = wide.index.max()
    fy_now = _fy_months(latest)[0]
    months = len(fy_now)
    keys = CARGO[cargo]["keys"]

    def raw(dates):
        tot, ok = 0.0, True
        for d in dates:
            vals = [wide.loc[d, k] for k in keys if d in wide.index and k in wide.columns]
            if not vals or any(pd.isna(v) for v in vals):
                ok = False
                continue
            tot += float(sum(vals))
        return tot, ok
    raw_ytd, _ = raw(fy_now)
    share = row["tonnes"] / raw_ytd if raw_ytd else 1.0       # same exclusions as the wharfage estimate (e.g. KIOCL's own arrangement)
    last12 = pd.date_range(end=latest, periods=12, freq="MS")
    raw12, ok12 = raw(last12)
    annualised = row["tonnes"] / months * 12
    if ok12 and raw12 > 0:
        q0 = raw12 * share
        q0_basis = (f"actual tonnes in the last 12 months ({last12[0].strftime('%b %Y')} to {last12[-1].strftime('%b %Y')}), "
                    "NMPA monthly commodity statements")
    else:
        q0 = annualised
        q0_basis = f"this financial year's {months} months scaled to 12 (a full 12 months of statements is not available)"
    # real reference points from NMPA's own history and the Ministry's figures
    fy_hist = {}
    fy0 = fy_now[0].year
    for y in range(fy0 - 3, fy0):
        t, ok = raw(pd.date_range(f"{y}-04-01", f"{y + 1}-03-01", freq="MS"))
        if ok and t > 0:
            fy_hist[f"FY {y}-{str(y + 1)[2:]}"] = t * share
    r, d, c, F = row["avg_rate_rs_per_t"], discount_pct / 100, max(cost_per_t, 0.0), max(fixed_cost, 0.0)
    margin = r * (1 - d) - c                       # what one extra tonne earns at the discounted rate, after its cost
    blanket = lambda dq: margin * dq - r * d * q0 - F
    rebate = lambda dq: margin * dq - F
    be_blanket = (r * d * q0 + F) / margin if margin > 0 else None
    be_rebate = (F / margin if F > 0 else 0.0) if margin > 0 else None
    scen = [("No extra cargo comes", 0.0, "The discount is announced, but customers send the same cargo as before")]
    if low_response_pct:
        scen.append((f"Your estimate: {low_response_pct:g}% more cargo", q0 * low_response_pct / 100,
                     f"Your input: {low_response_pct:g}% of the baseline of {q0:,.0f} t a year"))
    link = {"POL products": ["POL products (out)", "POL products (in)"], "Iron ore": ["Iron ore exports"],
            "Crude oil": ["Crude oil"], "LPG": ["LPG"], "Edible oil": ["Edible oil"],
            "Fertilizer and raw materials": ["Fertilizer (finished)", "Fertilizer raw materials (dry)"], "Food grains": ["Food grains"]}
    op_all = get_opportunities()
    grp = next((g for g, names in link.items() if cargo in names), None)
    opp = next((o for o in op_all.get("cargos", []) if o["cargo"] == grp), None) if grp else None
    if opp and (opp.get("tonnes_not_won") or 0) > 0:
        through = pd.Timestamp(tmk.get_market_share()["through"] + "-01")
        n_m = (through.year - (through.year if through.month >= 4 else through.year - 1)) * 12 + (through.month - 4) % 12 + 1
        group_t = sum(rev[n]["tonnes"] for n in link[grp] if n in rev)
        part = row["tonnes"] / group_t if group_t else 1.0          # this cargo's part of the group's gap
        gap_year = opp["tonnes_not_won"] * part * 12 / n_m
        scen.append(("Win back last year's share of all major ports", gap_year,
                     f"Ministry of Ports figures: New Mangalore's {grp} share fell from {opp['share_prev_pct']:.1f}% to "
                     f"{opp['share_pct']:.1f}% ({op_all.get('period', '')}); gap of {opp['tonnes_not_won'] * part:,.0f} t in "
                     f"{n_m} months" + (f" ({part:.0%} of the {grp} gap, by tonnes)" if part < 0.999 else "") + ", scaled to a year"))
    if fy_hist:
        best_fy, best_t = max(fy_hist.items(), key=lambda kv: kv[1])
        if best_t > q0 * 1.005:
            scen.append((f"Back to NMPA's best recent year ({best_fy})", best_t - q0,
                         f"NMPA monthly statements: {best_t:,.0f} t in {best_fy}, against {q0:,.0f} t in the last 12 months. "
                         "Shows the port has handled this much before"))
    scen.append(("Break-even for a discount on all cargo", be_blanket, "Calculated: the extra cargo at which a discount on all cargo stops losing money"))
    if target_t:
        scen.append(("Your target", float(target_t), "Your input (e.g. a volume a customer has committed to)"))
    rows = [{"scenario": n, "extra_tonnes": None if dq is None else round(dq), "source": src,
             "blanket_change_rs": None if dq is None else round(blanket(dq)),
             "rebate_change_rs": None if dq is None else round(rebate(dq))} for n, dq, src in scen]
    costs_entered = c > 0 or F > 0
    return {
        "cargo": cargo, "discount_pct": discount_pct, "rate_rs_per_t": r, "discounted_rate_rs_per_t": round(r * (1 - d), 2),
        "tariff_version": TARIFF_VERSION, "baseline_tonnes_per_year": round(q0), "baseline_basis": q0_basis,
        "this_year_scaled_tonnes": round(annualised), "history_tonnes": {k: round(v) for k, v in fy_hist.items()},
        "months_this_year": months, "cost_per_t": c, "fixed_cost_rs": F,
        "measure": "Change in contribution (after the costs entered)" if costs_entered else
                   "Change in wharfage receipts only (operating costs not included)",
        "blanket_given_up_on_baseline_rs": round(r * d * q0),
        "break_even_extra_tonnes_blanket": None if be_blanket is None else round(be_blanket),
        "break_even_extra_pct_blanket": None if be_blanket is None else round(be_blanket / q0 * 100, 1),
        "break_even_extra_tonnes_rebate": None if be_rebate is None else round(be_rebate),
        "never_breaks_even": margin <= 0,
        "scenarios": rows,
        "formulas": {"blanket": "change = [r(1-d) - c] x extra t - r x d x baseline t - F",
                     "rebate": "change = [r(1-d) - c] x extra t - F (rebate paid only on tonnes above the baseline)"},
        "conditions": [
            "A rebate on extra volume needs an agreed baseline (period, tonnes, seasonal adjustment), eligible cargo and "
            "customers, start and end dates, a budget cap, and rules so existing cargo is not reclassified as new.",
            "The Scale of Rates allows lower rates and higher rebates (General Terms xx(a)); a customer-specific baseline "
            "scheme still needs NMPA's legal and Finance approval and must be applied equally to similarly placed users.",
            "The extra tonnes in each scenario are inputs, not predictions. Confirm likely volumes with the customers first.",
        ],
    }


# ── PPP berths: what NMPA earns there is a royalty, not Scale of Rates wharfage ─────────────────────
PPP = {
    "containers": {
        "berth": "Berth 14", "operator": "JSW Mangalore Container Terminal Pvt Ltd",
        "basis": "Royalty per TEU",
        "royalty_rs_per_teu": 951.0,
        "royalty_source": ("Royalty of Rs 951 per TEU handled, paid monthly, plus a licence fee, with a minimum guaranteed "
                           "throughput: CARE Ratings rationale disclosed by JSW Infrastructure on 5 Sep 2025 (nmpa_public_data/"
                           "company_notices/JSW Mangalore Container Terminal credit rating (05.09.2025).pdf). The same filing gives "
                           "1.96 lakh TEU handled in FY24 and 1.84 lakh TEU in FY25. NMPA booked Rs 19.89 cr of container-terminal "
                           "royalty in 2023-24 (its budget document), which is Rs 1,015 per TEU on 1.96 lakh TEU: Rs 951 plus "
                           "indexation. Concession signed 27 Jan 2020 for 30 years; operations from 29 Mar 2022 (NMPA PPP disclosure 3.1.3)."),
        "teu_total": {"FY24": 196000, "FY25": 184000},
    },
    "coal_berth_16": {
        "berth": "Berth 16", "operator": "Mangalore Coal Terminal Pvt Ltd (owned by JSW Infrastructure since Dec 2020)",
        "basis": "31% of the operator's gross revenue (NMPA PPP disclosure 3.1.3)",
    },
}


@_ttl_cache(seconds=300)
def get_ppp_royalty() -> dict[str, Any]:
    """Container royalty estimate: laden TEU this financial year (NMPA container statement) x royalty per TEU."""
    from pathlib import Path
    f = tmk.ROOT / "data" / "nmpa_container_commodities.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f)
    latest = d["month"].max()
    m = d[d["month"] == latest]
    teu, teu_prev = float(m["teu_ytd"].sum()), float(m["teu_ytd_prev"].sum())
    roy = PPP["containers"]["royalty_rs_per_teu"]
    lbl_end = pd.Timestamp(latest + "-01")
    start = pd.Timestamp(lbl_end.year if lbl_end.month >= 4 else lbl_end.year - 1, 4, 1)
    implied = None
    try:
        b = _budget()
        prev_fy = d[d["month"] == "2025-03"]
        if not prev_fy.empty:
            implied = float(b.loc["61030400", "re_2023_24"]) * 1000 / float(prev_fy["teu_ytd_prev"].sum())   # FY 2023-24 laden TEU
    except Exception:
        implied = None
    extra = {}
    if implied:
        extra = {"implied_rs_per_laden_teu_2023_24": round(implied), "royalty_at_implied_rs": round(teu * implied),
                 "implied_note": ("What NMPA actually booked per LADEN TEU in 2023-24: its container-terminal royalty (Revised "
                                  "Estimate 2023-24) / laden TEU in its container statements. Royalty is paid on every TEU handled, "
                                  "including empties (1.96 lakh TEU in FY24, of which 1.22 lakh laden), so per laden TEU it is higher "
                                  "than the Rs 951 per TEU in the concession.")}
    return {"available": True, "period": f"{start:%b %Y} to {lbl_end:%b %Y}",
            "containers": {**PPP["containers"], **extra, "laden_teu": round(teu), "laden_teu_prev": round(teu_prev),
                           "royalty_estimate_rs": round(teu * roy), "royalty_estimate_prev_rs": round(teu_prev * roy),
                           "limits": ["Status: Estimated. The current indexed royalty is not confirmed by NMPA, so neither "
                                      "figure is the confirmed current rate.",
                                      "NMPA's container statements give laden TEU only (year to date); the estimate uses what NMPA "
                                      "booked per laden TEU in 2023-24, so it assumes the share of empty containers has stayed about "
                                      "the same. The concession's Rs 951 per TEU applied to laden TEU alone is shown as the minimum."]},
            "coal_berth_16": {**PPP["coal_berth_16"], "note": "Not estimated: the operator's gross revenue is not public in the documents held."}}


# ── Wharfage by customer: customer tonnes from the daily reports x the average rate of their cargo ──
FAMILY_TO_CARGO = {("Crude oil", "inbound"): "Crude oil", ("Petroleum products (fuels)", "outbound"): "POL products (out)",
                   ("Petroleum products (fuels)", "inbound"): "POL products (in)", ("LPG", "inbound"): "LPG",
                   ("Iron ore", "outbound"): "Iron ore exports", ("Edible oil", "inbound"): "Edible oil",
                   ("Fertilizer and chemicals", "inbound"): "Fertilizer (finished)", ("Food grains and sugar", "outbound"): "Food grains"}
NOT_PRICED_CUSTOMERS = {("KIOCL", "Iron ore"): "own arrangement", ("APL", "Coal"): "UPCL's own arrangement (Berth 15)"}


def last_complete_daily_month() -> pd.Timestamp:
    """The last month fully covered by NMPA daily reports: the month of the last report if it is the month's last day,
    otherwise the month before (e.g. reports to 26 Oct 2026 -> Sep 2026)."""
    last = pd.Timestamp(pd.read_csv(tmk.ROOT / "data" / "daily_reports_manifest.csv")["report_date"].max())
    first = last.replace(day=1)
    return first if (last + pd.Timedelta(days=1)).month != last.month else first - pd.DateOffset(months=1)


@_ttl_cache(seconds=300)
def get_customer_wharfage() -> dict[str, Any]:
    rev = {r["cargo"]: r for r in get_revenue()["cargos"]}
    v = tcu.build()["voyages"]
    latest = min(ti._prepared()["wide"].index.max(), last_complete_daily_month())   # only months the daily reports fully cover
    cur_m, _ = _fy_months(latest)
    months = {d.strftime("%Y-%m") for d in cur_m}
    q2 = {d.strftime("%Y-%m") for d in cur_m[-3:]}
    q1 = {d.strftime("%Y-%m") for d in cur_m[-6:-3]}
    v = v[v["month"].isin(months) & (v["customer"] != tcu.NOT_STATED)].copy()
    v["cargo_key"] = [FAMILY_TO_CARGO.get((f, d)) for f, d in zip(v["family"], v["direction"])]
    for (cust, fam), why in NOT_PRICED_CUSTOMERS.items():
        v.loc[(v["customer"] == cust) & (v["family"] == fam), "cargo_key"] = None
    v["rate"] = [rev[k]["avg_rate_rs_per_t"] if k in rev else None for k in v["cargo_key"]]
    v["rs"] = v["tonnes"].fillna(0) * v["rate"].fillna(0)
    rows = []
    for cust, g in v.groupby("customer"):
        priced = g[g["rate"].notna() & g["tonnes"].notna()]
        if priced.empty:
            continue
        unpriced = g[g["rate"].isna()]
        rows.append({"customer": cust,
                     "main_cargo_priced": priced.groupby("cargo_key")["rs"].sum().idxmax(),
                     "tonnes_priced": round(priced["tonnes"].sum()), "wharfage_rs": round(priced["rs"].sum()),
                     "wharfage_q1_rs": round(priced.loc[priced["month"].isin(q1), "rs"].sum()),
                     "wharfage_q2_rs": round(priced.loc[priced["month"].isin(q2), "rs"].sum()),
                     "not_priced": sorted(set(unpriced["family"])) })
    for r in rows:
        r["change_q2_vs_q1_rs"] = r["wharfage_q2_rs"] - r["wharfage_q1_rs"]
    rows.sort(key=lambda r: -r["wharfage_rs"])
    tot = sum(r["wharfage_rs"] for r in rows)
    for r in rows:
        r["share_pct"] = round(r["wharfage_rs"] / tot * 100, 1) if tot else None
    lab = lambda ms: f"{pd.Timestamp(min(ms) + '-01'):%b %Y} to {pd.Timestamp(max(ms) + '-01'):%b %Y}" if ms else ""
    return {"available": True, "period": lab(months), "q1_label": lab(q1), "q2_label": lab(q2), "customers": rows,
            "total_rs": tot,
            "basis": ["Customer tonnes from NMPA's daily vessel reports (about 85% of official tonnes are traced to a customer), "
                      "priced at the average wharfage rate of each cargo in the table above.",
                      "Not priced: containers and coal at the PPP berths, KIOCL's iron ore and UPCL's coal (own arrangements), "
                      "and cargo groups with several different rates.",
                      daily_report_note() + " Names NMPA has not confirmed (e.g. ADANI, MCF) are kept as written.",
                      "Estimates for comparing customers. Not billing figures."]}


# ── Check against NMPA's own accounts (Budget document: Actual 2022-23, Revised Estimate 2023-24) ─────────────
BUDGET_FILE = "data/nmpa_budget_income.csv"
BUDGET_SOURCE = ("NMPA, Revised Estimate 2023-24 and Budget Estimate 2024-25, Details of Revenue Account - Operating Income "
                 "(newmangaloreport.gov.in/sites/default/files/2024-08/7-36.pdf)")
CHECK = [  # cargo shown, NMPA income line(s), NMPA statement keys, our cargo row(s) for today's rate
    ("Crude oil (berths + SPM)", ["61010228", "61010249"], [("UNLOADED", "TOTALCRUDE")], ["Crude oil"]),
    ("LPG", ["61010230"], [("UNLOADED", "TOTALLPG")], ["LPG"]),
    ("POL products, exports", ["61010222"], [("LOADED", "POLPRODUCTS")], ["POL products (out)"]),
    ("POL products, imports", ["61010221"], [("UNLOADED", "POLPRODUCTS")], ["POL products (in)"]),
]
OWN_ARRANGEMENT_LINES = [("KIOCL iron ore (wharfage)", "61010207"), ("UPCL cargo, Berth 15 (royalty)", "61010210"),
                         ("Coal terminal, Berth 16 (royalty)", "61010215"), ("Container terminal, Berth 14 (royalty)", "61030400")]


def _budget() -> pd.DataFrame:
    return pd.read_csv(tmk.ROOT / BUDGET_FILE, comment="#", dtype={"erp_code": str}).set_index("erp_code")


@_ttl_cache(seconds=300)
def get_accounts_check() -> dict[str, Any]:
    """Income per tonne actually earned by NMPA (its income line / its own tonnes) against the rate used here."""
    b = _budget()
    wide = ti._prepared()["wide"]
    rev = {r["cargo"]: r for r in get_revenue()["cargos"]}
    fy = lambda y: pd.date_range(f"{y}-04-01", f"{y + 1}-03-01", freq="MS")
    tonnes = lambda keys, y: float(sum(wide.reindex(fy(y))[k].fillna(0).sum() for k in keys if k in wide.columns))
    rows = []
    for name, lines, keys, ours in CHECK:
        rec = {"cargo": name, "our_rate_today": round(sum(rev[o]["avg_rate_rs_per_t"] for o in ours if o in rev) / len(ours), 2)}
        for y, col, lab in ((2022, "actual_2022_23", "2022_23"), (2023, "re_2023_24", "2023_24")):
            inc = float(b.loc[lines, col].sum()) * 1000
            t = tonnes(keys, y)
            rec[f"income_{lab}_rs"] = round(inc)
            rec[f"tonnes_{lab}"] = round(t)
            rec[f"implied_rate_{lab}"] = round(inc / t, 2) if t else None
        r23 = rec["implied_rate_2023_24"]
        rec["difference_pct_vs_2023_24"] = round((rec["our_rate_today"] / r23 - 1) * 100, 1) if r23 else None
        rows.append(rec)
    other = [{"line": n, "actual_2022_23_rs": int(b.loc[c, "actual_2022_23"]) * 1000, "re_2023_24_rs": int(b.loc[c, "re_2023_24"]) * 1000,
              "be_2024_25_rs": int(b.loc[c, "be_2024_25"]) * 1000} for n, c in OWN_ARRANGEMENT_LINES]
    tot = {k: int(b.loc[k, "re_2023_24"]) * 1000 for k in ("TOTAL_CHSC", "TOTAL_PDC", "TOTAL_OPINC")}
    return {"available": True, "rows": rows, "other_lines": other, "totals_re_2023_24": tot, "source": BUDGET_SOURCE,
            "explain": ("Implied rate = NMPA's income on that line / tonnes in NMPA's monthly statements for the same year. "
                        "Today's Scale of Rates (from 7 May 2026) has been revised and indexed since, so today's rate is expected "
                        "to be somewhat higher; a much larger gap would mean the estimate is wrong.")}


# ── Reason -> action guidance (the reason is entered by Traffic; the tool never guesses it from tonnage) ──
REASON_ACTIONS = [
    ("Charges are affecting the customer's choice of port", "Evaluate an incentive (scenarios above), then Traffic and Finance review"),
    ("Repeated operational delays", "Operational improvement review (with Marine / Operations)"),
    ("Receiver or shipper not ready", "Customer coordination; no discount"),
    ("Customer demand has fallen", "Monitor and discuss expected demand with the customer"),
    ("Seasonal shipment pattern", "Compare with the same season of earlier years (Trade Intelligence, Cargo detail)"),
    ("Reason not known yet", "Investigate first; do not consider a discount yet"),
]

# ── Scheme register: draft -> reviews -> approval -> active -> completed, with an audit trail ─────────
import json as _json
import threading as _threading
from datetime import date as _date, datetime as _dt

SCHEMES_FILE = "data/incentive_schemes.json"
SCHEME_STATUSES = ["Draft", "Traffic review", "Finance review", "Approved", "Rejected", "Active", "Completed"]
NEXT_STATUS = {"Draft": ["Traffic review"], "Traffic review": ["Finance review", "Draft", "Rejected"],
               "Finance review": ["Approved", "Rejected", "Traffic review"], "Approved": ["Active"],
               "Active": ["Completed"], "Rejected": [], "Completed": []}
_slock = _threading.Lock()


def _schemes_path():
    return tmk.ROOT / SCHEMES_FILE


def _load_schemes() -> list[dict]:
    f = _schemes_path()
    if not f.exists():
        return []
    try:
        return _json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_schemes(rows: list[dict]) -> None:
    f = _schemes_path()
    f.parent.mkdir(exist_ok=True)
    f.write_text(_json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def create_scheme(cargo: str, scope: str, discount_pct: float, start: str, end: str, budget_cap_rs: float,
                  customers: str = "", conditions: str = "", by: str = "", baseline_method: str = "same_months_last_year",
                  baseline_years: int = 3, contractual_t: float | None = None, tiers: list[dict] | None = None,
                  success_target_t: float | None = None, stop_rule: str = "", customer: str = "",
                  baseline_tonnes: float | None = None, baseline_label: str = "", baseline_detail: str = "") -> dict:
    """Save a scenario as a DRAFT scheme with its eligibility check, its baseline (version 1) and, for a rebate, its marginal
    slabs. Nothing is offered to customers and no billing changes. A draft with blocks cannot move to review."""
    from backend.app.services import incentive_rules as ir
    if scope not in ("Blanket discount", "Rebate on extra volume"):
        raise ValueError("scope must be 'Blanket discount' or 'Rebate on extra volume'")
    d0, d1 = _dt.strptime(start, "%Y-%m-%d").date(), _dt.strptime(end, "%Y-%m-%d").date()
    if d1 < d0:
        raise ValueError("end date is before start date")
    if not (TARIFF_FROM <= start <= TARIFF_TO):
        raise ValueError(f"start date is outside the tariff version used ({TARIFF_VERSION}); use the tariff in force then")
    sc = scenario(cargo, discount_pct)
    months = [m.strftime("%Y-%m") for m in pd.date_range(d0.replace(day=1), d1.replace(day=1), freq="MS")]
    if customer and customer not in customers:
        customers = customer + (", " + customers if customers else "")     # the review gate re-checks this customer's identity
    custs = [c.strip() for c in customers.replace(";", ",").split(",") if c.strip()]
    rows = _load_schemes()
    elig = ir.check_eligibility(cargo, start, end, custs, rows, [r["cargo"] for r in get_revenue()["cargos"]])
    if customer and baseline_tonnes:
        # from the deal desk: the customer's own baseline (traced tonnes in NMPA daily reports), as shown in the proposal
        bl = {"method": "customer_traced", "label": baseline_label or "Customer's traced tonnes (NMPA daily reports)",
              "tonnes": round(baseline_tonnes), "blocked": None, "detail": baseline_detail}
    else:
        bl = ir.baseline(CARGO[cargo]["keys"], months, baseline_method, baseline_years, contractual_t)
    if scope == "Rebate on extra volume" and not tiers:
        tiers = [{"up_to_pct_above_baseline": None, "rebate_pct": discount_pct}]
    with _slock:
        rows = _load_schemes()
        sid = f"NMPA-INC-{len(rows) + 1:03d}"
        now = _dt.now().isoformat(timespec="minutes")
        rec = {"id": sid, "status": "Draft", "cargo": cargo, "scope": scope, "discount_pct": discount_pct,
               "start": start, "end": end, "months": months,
               "baseline_tonnes": bl["tonnes"],
               "baseline_basis": bl["label"] + (f" ({bl.get('detail')})" if bl.get("detail") else ""),
               "baselines": [{"version": 1, "at": now, "by": by, **bl, "frozen": False}],
               "tiers": tiers or [], "success_target_t": success_target_t, "stop_rule": stop_rule,
               "customer": customer, "data_version": data_version(),
               "eligibility": elig,
               "rate_rs_per_t": sc["rate_rs_per_t"], "tariff_version": TARIFF_VERSION,
               "budget_cap_rs": budget_cap_rs, "customers": customers, "conditions": conditions,
               "approval_reference": "", "results": [],
               "audit": [{"at": now, "by": by, "event": "Created as draft",
                          "detail": f"{scope}, {discount_pct}%, {start} to {end}; baseline: {bl['label']}"
                                    + ("" if elig["eligible"] else f"; BLOCKED: {len(elig['blocks'])} issue(s)")}]}
        rows.append(rec)
        _save_schemes(rows)
    return rec


def rebaseline(sid: str, method: str, years: int = 3, contractual_t: float | None = None, reason: str = "", by: str = "") -> dict:
    """A new baseline version (only while the scheme is a Draft); earlier versions are kept, never overwritten."""
    from backend.app.services import incentive_rules as ir
    with _slock:
        rows = _load_schemes()
        rec = next((r for r in rows if r["id"] == sid), None)
        if rec is None:
            raise KeyError(sid)
        if rec["status"] != "Draft":
            raise ValueError("the baseline is frozen once the scheme leaves Draft")
        if not reason.strip():
            raise ValueError("a reason is required to change the baseline")
        bl = ir.baseline(CARGO[rec["cargo"]]["keys"], rec["months"], method, years, contractual_t)
        now = _dt.now().isoformat(timespec="minutes")
        rec.setdefault("baselines", []).append({"version": len(rec["baselines"]) + 1, "at": now, "by": by, "reason": reason,
                                                **bl, "frozen": False})
        rec["baseline_tonnes"], rec["baseline_basis"] = bl["tonnes"], bl["label"] + (f" ({bl.get('detail')})" if bl.get("detail") else "")
        rec["audit"].append({"at": now, "by": by, "event": f"Baseline version {len(rec['baselines'])}", "detail": reason})
        _save_schemes(rows)
    return rec


def update_scheme(sid: str, status: str | None = None, approval_reference: str | None = None, note: str = "", by: str = "") -> dict:
    with _slock:
        rows = _load_schemes()
        rec = next((r for r in rows if r["id"] == sid), None)
        if rec is None:
            raise KeyError(sid)
        now = _dt.now().isoformat(timespec="minutes")
        if status and status != rec["status"]:
            if status not in NEXT_STATUS[rec["status"]]:
                raise ValueError(f"{rec['status']} can move to {NEXT_STATUS[rec['status']] or 'nothing (closed)'}")
            if status == "Traffic review":
                from backend.app.services import incentive_rules as ir
                custs = [c.strip() for c in rec.get("customers", "").replace(";", ",").split(",") if c.strip()]
                elig = ir.check_eligibility(rec["cargo"], rec["start"], rec["end"], custs, rows,
                                            [r["cargo"] for r in get_revenue()["cargos"]], exclude_id=rec["id"])
                rec["eligibility"] = elig
                if not elig["eligible"]:
                    raise ValueError("cannot go to review: " + " | ".join(elig["blocks"]))
                if rec.get("baseline_tonnes") is None:
                    raise ValueError("cannot go to review: the baseline could not be set (" +
                                     str((rec.get("baselines") or [{}])[-1].get("blocked")) + ")")
            if status == "Approved":
                rec["approved_on_data"] = data_version()
                for b in rec.get("baselines", []):
                    b["frozen"] = b["version"] == rec["baselines"][-1]["version"]
            if status == "Approved" and not (approval_reference or rec.get("approval_reference")):
                raise ValueError("an approval reference (order / file number) is required to approve")
            rec["audit"].append({"at": now, "by": by, "event": f"{rec['status']} -> {status}", "detail": note})
            rec["status"] = status
        if approval_reference is not None and approval_reference != rec.get("approval_reference"):
            rec["approval_reference"] = approval_reference
            rec["audit"].append({"at": now, "by": by, "event": "Approval reference recorded", "detail": approval_reference})
        elif note and not status:
            rec["audit"].append({"at": now, "by": by, "event": "Note", "detail": note})
        _save_schemes(rows)
    return rec


def scheme_results(rec: dict) -> dict:
    """Observed cargo during the scheme months against the baseline recorded at the draft stage: for a customer scheme, that
    customer's traced tonnes in NMPA daily reports; otherwise the cargo's tonnes in NMPA monthly statements."""
    if rec.get("customer"):
        from backend.app.services import incentive_proposal as ipr
        monthly, complete = ipr._customer_monthly(rec["customer"], rec["cargo"])
        held = [m for m in rec["months"] if m in monthly]
        actual = sum(monthly[m] for m in held) if held else None
        base = rec["baseline_tonnes"] / max(len(rec["months"]), 1) * len(held) if (held and rec.get("baseline_tonnes")) else None
        out = {"months_held": held, "months_total": len(rec["months"]), "actual_tonnes": None if actual is None else round(actual),
               "baseline_tonnes_for_months_held": None if base is None else round(base),
               "label": ("Observed traced tonnes of this customer (NMPA daily reports) during the scheme; causal impact not "
                         "established.")}
        if actual is not None and base:
            from backend.app.services import incentive_rules as ir
            r = rec["rate_rs_per_t"]
            if rec["scope"] == "Blanket discount":
                cost = actual * r * rec["discount_pct"] / 100
            else:
                mr = ir.marginal_rebate(actual, base, r, rec.get("tiers") or [{"up_to_pct_above_baseline": None, "rebate_pct": rec["discount_pct"]}],
                                        rec["budget_cap_rs"] or None)
                cost = mr["rebate_rs"]
                out["slabs"] = mr
            out.update({"extra_tonnes_vs_baseline": round(actual - base), "estimated_discount_cost_rs": round(cost),
                        "budget_used_pct": round(cost / rec["budget_cap_rs"] * 100, 1) if rec["budget_cap_rs"] else None})
        return out
    keys = next((c["keys"] for n, c in CARGO.items() if n == rec["cargo"]), [])
    wide = ti._prepared()["wide"]
    held = [m for m in rec["months"] if pd.Timestamp(m + "-01") in wide.index]
    actual = float(sum(wide.reindex(pd.DatetimeIndex([pd.Timestamp(m + "-01") for m in held]))[k].fillna(0).sum()
                       for k in keys if k in wide.columns)) if held else None
    base = rec["baseline_tonnes"] / max(len(rec["months"]), 1) * len(held) if held else None
    out = {"months_held": held, "months_total": len(rec["months"]), "actual_tonnes": None if actual is None else round(actual),
           "baseline_tonnes_for_months_held": None if base is None else round(base),
           "label": "Observed performance during the scheme; causal impact not established."}
    if actual is not None and base:
        extra = actual - base
        r, d = rec["rate_rs_per_t"], rec["discount_pct"] / 100
        if rec["scope"] == "Blanket discount":
            cost = actual * r * d
        else:
            from backend.app.services import incentive_rules as ir
            mr = ir.marginal_rebate(actual, base, r, rec.get("tiers") or [{"up_to_pct_above_baseline": None, "rebate_pct": rec["discount_pct"]}],
                                    rec["budget_cap_rs"] or None)
            cost = mr["rebate_rs"]
            out["slabs"] = mr
        out.update({"extra_tonnes_vs_baseline": round(extra), "estimated_discount_cost_rs": round(cost),
                    "budget_used_pct": round(cost / rec["budget_cap_rs"] * 100, 1) if rec["budget_cap_rs"] else None})
    return out


def list_schemes() -> dict:
    rows = _load_schemes()
    dv = data_version()
    for r in rows:
        if r["status"] in ("Active", "Completed"):
            r["observed"] = scheme_results(r)
            r["market_context"] = market_context(r["cargo"], r["observed"]["months_held"] or r["months"])
        saved = r.get("data_version") or {}
        if r["status"] in ("Draft", "Traffic review", "Finance review") and saved and saved.get("fingerprint") != dv["fingerprint"]:
            r["data_changed"] = [f"{k.replace('_', ' ')}: {saved.get(k)} -> {dv[k]}" for k in
                                 ("nmpa_statements_through", "ministry_reports_through", "daily_reports_through", "tariff")
                                 if saved.get(k) != dv[k]] or ["Source figures were revised"]
    return {"schemes": rows, "data_version": dv, "statuses": SCHEME_STATUSES, "next_status": NEXT_STATUS, "reason_actions": REASON_ACTIONS,
            "tariff_version": TARIFF_VERSION,
            "note": ("A scheme here is a record for review and approval. The tool does not send offers to customers or change "
                     "billing. NMPA should confirm its actual approval hierarchy.")}



def get_tariff_comparison() -> dict:
    """Published wharfage lines, NMPA vs Cochin (data/port_tariff_comparison.csv, built from both PDFs with page numbers)."""
    f = tmk.ROOT / "data" / "port_tariff_comparison.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f)
    rows = d.astype(object).where(pd.notna(d), None).to_dict(orient="records")
    return {"available": True, "rows": rows,
            "conclusion": ("For the selected foreign POL wharfage line, NMPA's published rate (Rs 96.60) is about 36.7% lower than "
                           "Cochin's (Rs 152.70). This comparison does not support reducing NMPA wharfage solely to match Cochin. It "
                           "does not show that price cannot explain cargo movement: concessions, handling, vessel charges, transport "
                           "and service still need comparing."),
            "scope": "Wharfage lines only, as published; not the total cost to a ship or cargo owner. Statuses: Extraction checked.",
            "sources": {"nmpa": d["nmpa_source"].iloc[0], "cochin": d["cochin_source"].iloc[0]}}


def get_cochin_schemes() -> dict:
    f = tmk.ROOT / "data" / "cochin_schemes.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f)
    return {"available": True, "schemes": d.to_dict(orient="records"),
            "note": ("Transcribed from Cochin Port Authority's signed notices (scanned; notice numbers and dates checked inside each). "
                     "They show how another major port designs schemes; they are not NMPA policy.")}



def get_published_accounts() -> dict:
    """NMPA's actual income by activity (Administration Report 2024-25, Table F-I), for scale and historical reference."""
    f = tmk.ROOT / "data" / "nmpa_actual_income_2023_25.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f, comment="#")
    return {"available": True, "rows": d.to_dict(orient="records"),
            "source": "NMPA Administration Report 2024-25, Table F-I (PDF page 221), Rs crore, actual",
            "note": ("For scale, not reconciliation: 'handling and storage charges' covers every cargo (including KIOCL, UPCL and "
                     "cargo groups not priced here), storage and handling, for a full year; the wharfage estimate above covers "
                     "selected cargos at NMPA berths for this financial year so far. Royalty income (Rs 102.11 cr in 2024-25) includes the "
                     "PPP terminals at Berths 14, 15 and 16 and stevedoring royalty.")}


# ── Seasonal windows: a benefit only in a cargo's regularly quiet months ─────────────────────────────────────────
QUIET_INDEX = 90            # a month at or below 90% of an average month of its year
FY_ORDER = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


@_ttl_cache(seconds=600)
def _berth_occupancy() -> dict:
    """Days each berth had a ship, by month, and which cargo families used which berths (NMPA daily reports)."""
    import glob, json as js
    from backend.app.services import trade_split as tsp
    occ, days, fam_berths = {}, {}, {}
    from pathlib import Path as _P
    for f in glob.glob(str(tmk.ROOT / "data" / "daily_vessel_position_parsed" / "*.json")):
        d = pd.to_datetime(_P(f).stem[:10], format="%d-%m-%Y")          # works with Windows and Linux paths
        m = d.strftime("%Y-%m")
        days[m] = days.get(m, 0) + 1
        seen = set()
        for r in js.load(open(f, encoding="utf-8")).get("berthed", []):
            b = str(r.get("berth_no") or "").strip().split("(")[0].strip()
            code = tsp._clean_code(str(r.get("cargo") or ""))
            vessel = str(r.get("vessel_name") or "").strip()
            if not b or not vessel or vessel.startswith("-") or not code:      # empty berths are printed as '----'
                continue
            seen.add(b)
            if code:
                fam = tsp.classify_cargo(code)
                fam_berths.setdefault(fam, {}).setdefault(b, 0)
                fam_berths[fam][b] += 1
        for b in seen:
            occ[(b, m)] = occ.get((b, m), 0) + 1
    return {"occ": occ, "days": days, "fam_berths": fam_berths}


@_ttl_cache(seconds=600)
def get_seasonal_windows(discount_pct: float = 10.0) -> dict[str, Any]:
    from backend.app.services import trade_patterns as tp
    wide = ti._prepared()["wide"]
    latest = wide.index.max()
    last12 = pd.date_range(end=latest, periods=12, freq="MS")
    rev = {r["cargo"]: r for r in get_revenue()["cargos"]}
    occ = _berth_occupancy()
    inv = {}
    for (fam, d), k in FAMILY_TO_CARGO.items():
        inv.setdefault(k, []).append((fam, d))
    d = discount_pct / 100
    rows = []
    for cargo, c in CARGO.items():
        if cargo not in rev:
            continue
        section, key = c["keys"][0]
        sea = tp.get_seasonality(key)
        direction = "inbound" if section == "UNLOADED" else "outbound"
        s = (sea or {}).get("directions", {}).get(direction)
        if not s or not s.get("seasonal_index"):
            continue
        idx = s["seasonal_index"]
        quiet = [FY_ORDER[i] for i, v in enumerate(idx) if v is not None and v <= QUIET_INDEX]
        monthly = {dt.strftime("%b"): float(sum(wide.loc[dt, k] for k in c["keys"] if k in wide.columns and pd.notna(wide.loc[dt, k])))
                   for dt in last12 if dt in wide.index}
        rate = rev[cargo]["avg_rate_rs_per_t"]
        annual = sum(monthly.values())
        quiet_t = sum(monthly.get(m, 0.0) for m in quiet)
        row = {"cargo": cargo, "regular": bool(s.get("regular")), "complete_years": len(s.get("complete_years") or []),
               "consistency": s.get("year_to_year_consistency"), "seasonal_index": dict(zip(FY_ORDER, idx)),
               "quiet_months": quiet, "rate_rs_per_t": rate,
               "last12_tonnes": round(annual), "quiet_months_tonnes": round(quiet_t),
               "cost_all_year_rs": round(annual * rate * d), "cost_quiet_months_rs": round(quiet_t * rate * d)}
        # berths this cargo uses (NMPA berths only), and how busy they were in its quiet months vs other months
        fams = inv.get(cargo, [])
        bc = {}
        for fam in fams:
            for b, n in occ["fam_berths"].get(fam, {}).items():
                bc[b] = bc.get(b, 0) + n
        tot = sum(bc.values()) or 1
        berths = sorted([b for b, n in bc.items() if n / tot >= 0.10 and b not in ("14", "15", "16")], key=lambda b: -bc[b])
        mon_by_abbr = {}
        for m, nd in occ["days"].items():
            if nd >= 15:
                mon_by_abbr.setdefault(pd.Timestamp(m + "-01").strftime("%b"), []).append(m)
        def occ_pct(abbrs):
            num = den = 0
            for a in abbrs:
                for m in mon_by_abbr.get(a, []):
                    for b in berths:
                        num += occ["occ"].get((b, m), 0)
                        den += occ["days"][m]
            return round(num / den * 100) if den else None
        others = [m for m in FY_ORDER if m not in quiet]
        row.update({"berths": berths, "occupancy_quiet_pct": occ_pct(quiet) if quiet else None, "occupancy_other_pct": occ_pct(others)})
        if not row["regular"]:
            row["verdict"] = "No regular seasonal pattern: a seasonal offer would rest on a guess."
        elif not quiet:
            row["verdict"] = f"Regular pattern but no month at or below {QUIET_INDEX}% of an average month."
        else:
            share = row["cost_quiet_months_rs"] / row["cost_all_year_rs"] * 100 if row["cost_all_year_rs"] else None
            row["quiet_cost_share_pct"] = None if share is None else round(share)
            row["verdict"] = (f"Quiet in {', '.join(quiet)}. A {discount_pct:g}% discount in those months only costs "
                              f"{share:.0f}% of the same discount all year." if share is not None else "")
        rows.append(row)
    rows.sort(key=lambda r: (not r["regular"] or not r["quiet_months"], -(r["cost_all_year_rs"] - r["cost_quiet_months_rs"])))
    return {"available": True, "discount_pct": discount_pct, "rows": rows, "last12": f"{last12[0]:%b %Y} to {last12[-1]:%b %Y}",
            "status": "Seasonal commercial opportunity; capacity and customer feasibility unconfirmed",
            "caveats": ["Quiet months come from NMPA's monthly statements over the complete financial years held; low volume can "
                        "reflect weather, maintenance or customers' production, not spare capacity.",
                        "Berth occupancy is from NMPA's daily reports (Sep 2025 onward, one year): the share of report days a berth "
                        "had a ship. It is not live availability; Marine / Operations must confirm berth, equipment, storage and "
                        "evacuation capacity.",
                        "A seasonal offer may only move cargo from busy months into quiet ones without adding to the year: track "
                        "both effects separately.",
                        "Costs use the last 12 months' tonnes at today's rates; wharfage only."]}


# ── Protect key customers: wharfage at risk before chasing new cargo ─────────────────────────────────────────────
KEY_SHARE_CUM = 90.0        # customers making up the first 90% of traced wharfage
NOT_READY_HIGH = 20.0       # ship-days waiting because the customer was not ready, since Sep 2025


@_ttl_cache(seconds=300)
def get_key_customers() -> dict[str, Any]:
    from backend.app.services import trade_feedback as tfb
    cw = get_customer_wharfage()
    watch = {r["customer"]: r for r in tcu.get_customer_watch()["customers"]}
    notes = tfb.get_customer_notes()
    acct = notes["customers"]
    due = {d["customer"] for d in notes.get("follow_ups_due", [])}
    rows, cum = [], 0.0
    for c in cw["customers"]:
        if cum >= KEY_SHARE_CUM:
            break
        cum += c["share_pct"] or 0
        w = watch.get(c["customer"], {})
        n = acct.get(c["customer"], {})
        signals = []
        if w.get("status") == "Falling" or (c["change_q2_vs_q1_rs"] < 0 and c["wharfage_q1_rs"] and
                                            c["change_q2_vs_q1_rs"] / c["wharfage_q1_rs"] <= -0.10):
            signals.append(f"Wharfage down {cr_text(-c['change_q2_vs_q1_rs'])} on the previous quarter")
        if w.get("status") == "Gone quiet":
            signals.append(f"No ship for {w.get('days_since_last_call')} days (usual gap {w.get('usual_gap_days')} days)")
        if (w.get("not_ready_ship_days") or 0) >= NOT_READY_HIGH:
            signals.append(f"Ships waited {w['not_ready_ship_days']:.0f} ship-days because the customer was not ready")
        level = ("High" if signals and (c["share_pct"] or 0) >= 5 else "Medium" if signals else "None found")
        if not signals:
            step = "Keep in regular contact; no warning sign in the data."
        elif any("not ready" in s for s in signals) and not any("down" in s or "No ship" in s for s in signals):
            step = "Coordinate readiness with the customer (non-price)."
        else:
            step = "Traffic to confirm the reason with the customer before considering any benefit (see the deal desk)."
        rows.append({"customer": c["customer"], "main_cargo": c["main_cargo_priced"], "share_pct": c["share_pct"],
                     "wharfage_rs": c["wharfage_rs"], "wharfage_q1_rs": c["wharfage_q1_rs"], "wharfage_q2_rs": c["wharfage_q2_rs"],
                     "change_q2_vs_q1_rs": c["change_q2_vs_q1_rs"],
                     "annualised_change_rs": c["change_q2_vs_q1_rs"] * 4,
                     "status": w.get("status"), "signals": signals, "risk": level,
                     "owner": n.get("owner") or "", "stage": n.get("stage") or "", "reason": n.get("reason") or "",
                     "follow_up": n.get("follow_up") or "", "follow_up_due": c["customer"] in due,
                     "engagement": ("Owner set" if n.get("owner") else "No owner") + ("; reason recorded" if n.get("reason") else "; reason not recorded"),
                     "next_step": step})
    at_risk = [r for r in rows if r["risk"] != "None found"]
    fall = sum(r["change_q2_vs_q1_rs"] for r in at_risk if r["change_q2_vs_q1_rs"] < 0)
    return {"available": True, "period": cw["period"], "q1_label": cw["q1_label"], "q2_label": cw["q2_label"], "rows": rows,
            "key_share_pct": round(cum, 1), "at_risk_count": len(at_risk), "at_risk_quarter_fall_rs": round(fall),
            "at_risk_falling_count": sum(1 for r in at_risk if (r["change_q2_vs_q1_rs"] or 0) < 0),
            "at_risk_waiting_count": sum(1 for r in at_risk if any("ship-days" in x for x in r["signals"])),
            "no_owner_count": sum(1 for r in rows if not r["owner"]),
            "rules": (f"Key customers: those making up the first {KEY_SHARE_CUM:.0f}% of traced wharfage. Warning signs: wharfage down "
                      "10% or more on the previous quarter (or status Falling), gone quiet, or 20+ ship-days waiting because the "
                      "customer was not ready. Risk High = a warning sign and 5%+ of traced wharfage."),
            "caveats": ["Wharfage per customer is estimated from NMPA daily reports (traced tonnes, about 85% of official) at tariff "
                        "rates; not billing figures.",
                        "Names NMPA has not confirmed (e.g. ADANI, MCF) are shown as written."]}


def cr_text(v: float) -> str:
    return f"Rs {v / 1e7:,.2f} cr" if abs(v) >= 1e6 else f"Rs {v / 1e5:,.1f} lakh"


# ── Data currency, change flags on drafts, amendments needing re-approval, market context ───────────────────────
def data_version() -> dict[str, Any]:
    """What the figures rest on: latest month or date of each source, the tariff file, and a fingerprint of the data files."""
    import hashlib
    root = tmk.ROOT / "data"
    files = ["port_cargo_monthly.csv", "major_ports_monthly.csv", "major_ports_commodity_monthly.csv", "daily_reports_manifest.csv",
             "nmpa_container_commodities.csv", "sor_reference.json"]
    h = hashlib.md5()
    for f in files:
        p = root / f
        if p.exists():
            h.update(p.read_bytes())
    h.update((tmk.ROOT / SOR_FILE).read_bytes() if (tmk.ROOT / SOR_FILE).exists() else b"")
    wide = ti._prepared()["wide"]
    mp = pd.read_csv(root / "major_ports_monthly.csv")
    man = pd.read_csv(root / "daily_reports_manifest.csv")
    return {"nmpa_statements_through": wide.index.max().strftime("%Y-%m"), "ministry_reports_through": str(mp["month"].max()),
            "daily_reports_through": str(man["report_date"].max()), "tariff": TARIFF_VERSION, "fingerprint": h.hexdigest()[:12]}


CARGO_TO_MARKET = {"Crude oil": "Crude oil", "Crude oil out of ISPRL": "Crude oil", "LPG": "LPG", "POL products (out)": "POL products",
                   "POL products (in)": "POL products", "Iron ore exports": "Iron ore", "Edible oil": "Edible oil",
                   "Fertilizer (finished)": "Fertilizer and raw materials", "Fertilizer raw materials (dry)": "Fertilizer and raw materials",
                   "Food grains": "Food grains"}


def market_context(cargo: str, months: list[str]) -> dict[str, Any]:
    """NMPA and the OTHER 11 major ports, same commodity, same months, against the same months a year earlier.
    Months missing on either side are left out (never treated as zero). Market context only: not the incentive's effect."""
    grp = CARGO_TO_MARKET.get(cargo)
    label = ("Market context: New Mangalore against the other 11 major ports for the same commodity and months. It shows "
             "performance relative to the market; it does not by itself establish the incentive's effect.")
    if not grp:
        return {"available": False, "label": label, "reason": "No matching Ministry commodity line."}
    nm_keys, min_lines = tmk.GROUPS[grp]
    wide = ti._prepared()["wide"]
    d = pd.read_csv(tmk.ROOT / "data" / "major_ports_commodity_monthly.csv")
    mon = d[d["period"] == "month"].pivot_table(index="through", columns="commodity", values="tonnes", aggfunc="first")
    nm_cols = [("UNLOADED", k) for k in nm_keys] + [("LOADED", k) for k in nm_keys]

    def nm_t(m):
        ts = pd.Timestamp(m + "-01")
        if ts not in wide.index:
            return None
        vals = [wide.loc[ts, c] for c in nm_cols if c in wide.columns]
        return None if not vals or all(pd.isna(v) for v in vals) else float(sum(v for v in vals if pd.notna(v)))

    def all_t(m):
        if m not in mon.index or any(l not in mon.columns or pd.isna(mon.loc[m, l]) for l in min_lines):
            return None
        return float(sum(mon.loc[m, l] for l in min_lines))

    used, missing = [], []
    nm_now = nm_prev = oth_now = oth_prev = 0.0
    for m in months:
        prev = f"{int(m[:4]) - 1}{m[4:]}"
        vals = [nm_t(m), nm_t(prev), all_t(m), all_t(prev)]
        if any(v is None for v in vals):
            missing.append(m)
            continue
        a, b, c, e = vals
        nm_now, nm_prev, oth_now, oth_prev = nm_now + a, nm_prev + b, oth_now + (c - a), oth_prev + (e - b)
        used.append(m)
    if not used:
        return {"available": False, "label": label, "months_missing": missing,
                "reason": "No month in the period has both NMPA's and the Ministry's figures for this commodity (and a year earlier)."}
    g = lambda x, y: round((x / y - 1) * 100, 1) if y else None
    return {"available": True, "label": label, "commodity": grp, "months_compared": used, "months_missing": missing,
            "nmpa_growth_pct": g(nm_now, nm_prev), "other_ports_growth_pct": g(oth_now, oth_prev),
            "note": "Ministry totals include shore handling; NMPA's statements do not. Customer schemes are compared separately "
                    "(their own traced tonnes) from this port-wide market context."}


def amend_scheme(sid: str, changes: dict, reason: str, by: str = "") -> dict:
    """Approved or active terms can only change through an amendment: the old terms are kept, the approval reference is
    cleared and the scheme goes back to Traffic review for re-approval."""
    allowed = {"discount_pct", "tiers", "end", "budget_cap_rs", "conditions", "success_target_t", "stop_rule"}
    bad = set(changes) - allowed
    if bad:
        raise ValueError(f"cannot amend {sorted(bad)}; the cargo, customer, start and baseline stay as approved")
    if not reason.strip():
        raise ValueError("a reason is required for an amendment")
    with _slock:
        rows = _load_schemes()
        rec = next((r for r in rows if r["id"] == sid), None)
        if rec is None:
            raise KeyError(sid)
        if rec["status"] not in ("Approved", "Active"):
            raise ValueError("only Approved or Active schemes are amended; edit a Draft directly by saving a new draft")
        now = _dt.now().isoformat(timespec="minutes")
        old = {k: rec.get(k) for k in changes}
        rec.setdefault("amendments", []).append({"at": now, "by": by, "reason": reason, "previous_terms": old, "new_terms": changes,
                                                 "previous_approval_reference": rec.get("approval_reference"),
                                                 "previous_status": rec["status"]})
        rec.update(changes)
        rec["approval_reference"] = ""
        rec["audit"].append({"at": now, "by": by, "event": f"{rec['status']} -> Traffic review (amendment)",
                             "detail": f"{reason}; changed: {', '.join(changes)}"})
        rec["status"] = "Traffic review"
        _save_schemes(rows)
    return rec


# ── Past incentive, measured: ships and tonnes covered by the March 2026 waiver ─────────────────────────────────
@_ttl_cache(seconds=600)
def get_waiver_coverage() -> dict[str, Any]:
    """Crude and LPG ships that berthed in the waiver window (NMPA Trade Circular NMPA/TM/2025-26/Gen.2), from NMPA's daily
    reports: the ships that could have qualified. The cost needs the Scale of Rates in force in March 2026."""
    import json as js
    from backend.app.services import incentive_rules as ir
    b = ir.KNOWN_BENEFIT_PERIODS[0]
    v = tcu.build()["voyages"]
    fam = {"Crude oil": "Crude oil", "LPG": "LPG"}
    w = v[v["family"].isin(list(fam)) & (v["first_seen"] >= b["from"]) & (v["first_seen"] <= b["to"])].copy()
    before = v[v["family"].isin(list(fam)) & (v["first_seen"] < b["from"]) & (v["last_seen"] >= b["from"])]
    man = pd.read_csv(tmk.ROOT / "data" / "daily_reports_manifest.csv").set_index("report_date")["status"].to_dict()

    def berth_of(vessel, day):
        f = tmk.ROOT / "data" / "daily_vessel_position_parsed" / (pd.Timestamp(day).strftime("%d-%m-%Y") + ".json")
        if not f.exists():
            return None
        for r in js.loads(f.read_text(encoding="utf-8")).get("berthed", []):
            name = str(r.get("vessel_name", "")).split("(")[0].strip().upper()      # e.g. 'DESTAN (14.50)': draft in brackets
            if name == str(vessel).split("(")[0].strip().upper():
                return str(r.get("berth_no") or "").strip()
        return None
    ships = []
    for r in w.sort_values("first_seen").itertuples():
        ships.append({"vessel": r.vessel, "cargo": r.family, "customer": r.customer, "berthed": str(r.first_seen)[:10],
                      "last_seen": str(r.last_seen)[:10], "berth": berth_of(r.vessel, r.first_seen),
                      "tonnes": None if pd.isna(r.tonnes) else round(float(r.tonnes)), "run": r.run,
                      "report_status": man.get(str(r.first_seen)[:10], "no report")})
    tot = {}
    for s in ships:
        if s["tonnes"]:
            tot[s["cargo"]] = tot.get(s["cargo"], 0) + s["tonnes"]
    tariff = ir.tariff_for(b["from"])
    return {"available": True, "scheme": b["name"], "window": {"from": b["from"], "to": b["to"]},
            "ships": ships, "tonnes_by_cargo": tot,
            "ships_without_quantity": [s["vessel"] for s in ships if not s["tonnes"]],
            "excluded_already_working": sorted(set(before["vessel"])),
            "cost": None if tariff is None or not tariff["held"] else "calculable",
            "cost_status": ("Pending: the NMPA Scale of Rates in force in March 2026 (the 2025-26 version, before the indexation of "
                            "1 May 2026) is not held, so the charges waived cannot be priced without assuming a rate."
                            if tariff is None or not tariff["held"] else ""),
            "notes": ["The circular covers vessels DECLARED after 14 Mar 2026 and berthed by 31 Mar 2026 (12 pm). Daily reports do "
                      "not show declaration dates, so this is the list of ships that could have qualified, not a confirmed list.",
                      "Ships already berthed and working on 14 Mar are excluded, as the circular says.",
                      "Tonnes are the quantities in NMPA's daily reports; the original PDFs for these days are not held, so these "
                      "records are not checked."],
            "source": "NMPA Trade Circular NMPA/TM/2025-26/Gen.2 (14 Mar 2026); NMPA daily vessel position reports"}



# ── 2025-26 rates (for pricing past events in that year) and the cost of the March 2026 waiver ──────────────────
SOR_2025_26_FILE = "nmpa_public_data/tariff_history/NMPA SOR w.e.f. 01.05.2025 to 30.04.2026 (1.74pc indexation).pdf"
SOR_2025_26 = {  # (foreign, coastal, PDF page) as printed; columns foreign then coastal
    "crude_spm": (34.67, 34.66, 17), "crude_berth": (95.98, 95.98, 16), "lpg": (243.98, 146.66, 18), "iron_ore": (42.88, 42.88, 18)}


def waiver_cost() -> dict[str, Any]:
    """Wharfage waived on the ships that could have qualified for the March 2026 waiver, at the 2025-26 rates in force then."""
    w = get_waiver_coverage()
    rows, total = [], 0.0
    for s in w["ships"]:
        if s["cargo"] == "LPG":
            key = "lpg"
        else:
            key = "crude_spm" if (s["berth"] or "").upper() == "SPM" else "crude_berth"
        f, c, page = SOR_2025_26[key]
        rate = c if s["run"] == "C" else f
        amt = (s["tonnes"] or 0) * rate
        total += amt
        rows.append({**s, "rate_line": key, "rate_rs_per_t": rate, "sor_page": page, "wharfage_waived_rs": round(amt) if s["tonnes"] else None})
    return {"ships": rows, "total_rs": sum(r["wharfage_waived_rs"] or 0 for r in rows),     # the sum of the rounded ship amounts
            "basis": ("Wharfage at the 2025-26 Scale of Rates (in force 1 May 2025 to 30 April 2026): crude at the SPM or at a "
                      "berth, and LPG, by the ship's foreign/coastal run. An upper estimate: it covers every ship that berthed in "
                      "the window (declaration dates are not in the daily reports); other cargo-related charges, if any, are not "
                      "included; ships with no quantity recorded are not priced."),
            "source": SOR_2025_26_FILE}


# ── Iron ore export rebate in force (23 Sep 2026 - 31 Mar 2027): what the public data can and cannot show ─────
def iron_ore_rebate_monitor() -> dict[str, Any]:
    wide = ti._prepared()["wide"]
    key = ("LOADED", "IRONORE")
    latest = wide.index.max()
    fy = lambda y: pd.date_range(f"{y}-04-01", f"{y + 1}-03-01", freq="MS")
    t = lambda months: float(sum(wide.loc[m, key] for m in months if m in wide.index and pd.notna(wide.loc[m, key])))
    cur_months = [m for m in fy(2026) if m <= latest]
    prev_same = [m - pd.DateOffset(years=1) for m in cur_months]
    since = [m for m in cur_months if m >= pd.Timestamp("2026-10-01")]          # first full month after the scheme began
    rate = _rate(CARGO["Iron ore exports"]["rate"])["foreign"]
    v = tcu.build()["voyages"]
    ex = v[(v["family"] == "Iron ore") & (v["direction"] == "outbound") & v["tonnes"].notna()]
    ex = ex[~ex["customer"].isin(["KIOCL", tcu.NOT_STATED])]
    by = lambda a, b: ex[(ex["month"] >= a) & (ex["month"] <= b)].groupby("customer")["tonnes"].sum()
    cur_ex, base_ex = by("2026-04", latest.strftime("%Y-%m")), by("2025-09", "2026-03")
    ids = {}
    try:
        idp = pd.read_csv(tmk.ROOT / "data" / "customer_identity_proposals.csv")
        for lab, prop in zip(idp["label_in_daily_reports"], idp["proposed_identity"]):
            for part in str(lab).split("/"):
                ids[part.strip().upper()] = prop
    except Exception:
        pass

    def status(c):
        if "KIOCL" in c.upper().split(" + "):
            return "Joint entry including KIOCL (own arrangement): eligibility to confirm with Traffic"
        base = "New in the daily reports since Sep 2025" if base_ex.get(c, 0) == 0 else "Existing"
        if c.upper() in ("ERM", "E. RAMAMURTHY MINERALS"):
            base += "; 'ERM' and 'E. RAMAMURTHY MINERALS' may be the same exporter (not confirmed by NMPA)"
        return base
    exporters = [{"customer": c, "fy2026_27_to_date_t": round(cur_ex.get(c, 0)), "sep2025_mar2026_t": round(base_ex.get(c, 0)),
                  "status": status(c)}
                 for c in sorted(set(cur_ex.index) | set(base_ex.index), key=lambda c: -cur_ex.get(c, 0))]
    return {"scheme": "NMPA/TM/IOF-Exp-Rebate/26-27: 20% rebate on wharfage for incremental iron ore fines/lumps exports, "
                      "23 Sep 2026 to 31 Mar 2027",
            "fy2025_26_total_t": round(t(fy(2025))), "fy2026_27_to_date_t": round(t(cur_months)),
            "same_months_2025_t": round(t(prev_same)), "months": f"Apr to {latest:%b %Y}",
            "since_scheme_t": round(t(since)), "since_scheme_prev_t": round(t([m - pd.DateOffset(years=1) for m in since])),
            "rate_rs_per_t": rate, "rebate_per_extra_t_rs": round(rate * 0.20, 2), "exporters": exporters,
            "limits": ["The rebate is per exporter, on tonnes above each exporter's own FY 2025-26 quantity (or 1,00,000 t for a "
                       "new exporter), settled after 31 Mar 2027. Port totals cannot show it: one exporter's rise may offset "
                       "another's fall.",
                       "Exporters' FY 2025-26 base cannot be built from public data: NMPA's daily reports in this project start in "
                       "Sep 2025, so Apr-Aug 2025 is missing. The 'Sep 2025 to Mar 2026' column is a partial base only.",
                       "KIOCL's iron ore is under its own arrangement and is left out. Exporter names are as written in the daily "
                       "reports (not confirmed by NMPA).",
                       "Each extra tonne under the scheme earns NMPA 80% of the wharfage rate; the other 20% is the rebate."],
            "source": "NMPA Trade Notice (23.09.2026); NMPA monthly statements; NMPA daily vessel reports"}



def get_tariff_comparison_voc() -> dict:
    f = tmk.ROOT / "data" / "port_tariff_comparison_voc.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f)
    return {"available": True, "rows": d.astype(object).where(pd.notna(d), None).to_dict(orient="records"),
            "period": d["period"].iloc[0], "sources": {"nmpa": d["nmpa_source"].iloc[0], "voc": d["voc_source"].iloc[0]},
            "conclusion": ("Same year (2025-26): on every line that both ports charge per tonne, NMPA's published wharfage is lower "
                           "than VOC's, including iron ore (Rs 42.88 against Rs 104.09 in VOC's Zone A). As with Cochin, this does "
                           "not show that price cannot explain cargo movement: handling, vessel charges, transport and service are "
                           "not compared here.")}



def daily_report_note() -> str:
    """One line on how far the daily reports behind customer figures are checked (from the manifest, not hard-coded)."""
    m = pd.read_csv(tmk.ROOT / "data" / "daily_reports_manifest.csv")
    n, miss = len(m), int(m["status"].str.startswith("Original not obtained").sum())
    chk = int(m["status"].str.startswith("Extraction checked").sum())
    return (f"Customer tonnes come from {n} NMPA daily reports: the original PDF is held for {n - miss}"
            + (f" ({miss} not obtained, records not checked)" if miss else "") + f"; {chk} checked by two independent readings.")


# How other major ports design schemes, by kind, against what NMPA's own notices show. NMPA's use is taken only from the
# notices held (data/nmpa_incentive_notices.csv); "not found" means not among those notices, not that NMPA has never done it.
SCHEME_PATTERNS = [
    ("Incremental volume rebate", "NMPA/TM/IOF-Exp-Rebate/26-27 (iron ore, 20% above FY 2025-26)",
     "NMPA's own design: rebate only on tonnes above last year, paid after verification."),
    ("New cargo concession", "NMPA/TM/SM/2026 (25% for cargo not handled in 5 years)",
     "NMPA's own design: open to all users, by cargo type, for one year."),
    ("Container service incentive", "Comrc/DTM(C)/2026-27/01 (35% feeder / 50% mainline)",
     "Design idea only: other ports vary the benefit by vessel type, TEUs per call or route, and review it after a fixed period. "
     "Their percentages are set for their own traffic and costs, so they are not a benchmark for NMPA's rates."),
    ("Route or new-service incentive", None,
     "Not among NMPA's notices. Cochin, VOC and JNPA reward new routes or new services; NMPA's container rebate could be tied "
     "to new services or routes (for example West Asia) rather than all calls."),
    ("Vessel or parcel-size concession", "12/1/2021-22/ATM Gr.I (Com)/JSW (30% for Cape-size vessels at Berth 16)",
     "Larger parcels use berths better; Deendayal's salt scheme is linked to a rise of about 8.5 million t in a year."),
    ("Performance norms (incentive and penalty)", None,
     "Not among NMPA's notices. Cochin and Paradip reward handling faster than a norm and penalise slower handling. Relevant "
     "where berth time is lost: NMPA's daily reports show key customers' ships waiting because the customer was not ready."),
    ("Green ship discount", "NMPA/DC/Trade Circular/2025/01 (Harit Shrey, ended 31 Mar 2025)",
     "Mormugao started first (Oct 2023). NMPA's trial ended; no renewal found among its notices."),
    ("Green cargo concession", "NMPA/Traffic/Com/Green Policy/01 (Harit Cargo, 40% / 75%, to 2030)",
     "No similar cargo scheme recorded at other ports here."),
    ("Coastal concession", "NMPA Scale of Rates (coastal rates)",
     "National 40% coastal concession; NMPA's Scale of Rates applies it (POL and thermal coal excluded)."),
    ("Passenger ferry exemption", "NMPA/TM/2024-25/Gen-2 (RoPax, to 21 Jan 2026)",
     "Cochin renewed its exemption for 2026 (Trade Notice 01/2026); no NMPA renewal found among its notices."),
    ("Cargo-type (packaging) rebate", None,
     "Not among NMPA's notices. Deendayal gives a wharfage rebate on bagged cargo."),
    ("Hinterland (rail) concession", None,
     "Not among NMPA's notices. Deendayal gives a concession on railway terminal charges."),
    ("Route or handling-channel discount", None,
     "Not among NMPA's notices. Paradip discounts one cargo moved through a specific facility."),
    ("Transshipment rate", "NMPA Scale of Rates 2.5.3 and 4.2 (transhipment charges); 50% foreign + 50% coastal rate for coastal transshipment",
     "Deendayal charges 75% of wharfage on cargo landed only for reshipment; NMPA has its own transhipment charges."),
]


@_ttl_cache(seconds=600)
def get_other_ports_schemes() -> dict[str, Any]:
    f = tmk.ROOT / "data" / "other_ports_schemes.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f, dtype=str).fillna("")
    rows = []
    for name, nmpa, idea in SCHEME_PATTERNS:
        ex = d[d.design_pattern == name]
        rows.append({"pattern": name, "nmpa": nmpa, "used_by_nmpa": nmpa is not None,
                     "other_ports": sorted(set(ex.port)), "examples": len(ex), "idea": idea})
    gaps = [r["pattern"] for r in rows if not r["used_by_nmpa"] and r["examples"]]
    return {"available": True, "patterns": rows, "schemes": d.to_dict(orient="records"),
            "nmpa_used": sum(r["used_by_nmpa"] for r in rows), "kinds": len(rows), "not_at_nmpa": gaps,
            "legal_basis": ("Under Section 27(1) of the Major Port Authorities Act, 2021, each port's Board frames its Scale of Rates "
                            "and conditions; rates are ceilings, so the Board can approve lower rates and rebates, within the Tariff "
                            "Policy for Major Port Authorities 2021, and notify them by trade notice."),
            "source": "Each scheme's own source (official port documents, the Ministry, a port association list or a press report)"}
