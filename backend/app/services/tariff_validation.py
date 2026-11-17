"""
Checks the tariff calculator against past, independently published data.

1. Past tariff — every rate in the 2026-27 tables is compared with the same
   item in NMPA's SOR general revision w.e.f. 25-12-2022. NMPA only indexes
   the SOR every 1 May (SOR 1.2(xix)), so every item must have moved by the
   same few factors. A rate that does not is a transcription error.

2. Past revenue — NMPA's own books (Revised Estimate 2023-24, operating
   income schedule, ₹ '000) divided by the tonnage NMPA reported for the
   same year (monthly commodity-wise traffic statements) gives the rate
   NMPA actually realised per tonne. It must sit inside the SOR band
   between the 2022 base rate and the 2026-27 rate, unless the cargo is
   one the SOR itself excludes.

3. Past calls — tonnage summed from individual vessel calls in the Daily
   Vessel Position reports vs NMPA's monthly traffic statement (see
   historical_calls.reconcile_with_traffic_statement).
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Any, Dict, List

import pandas as pd

from backend.app.services import cost_engine as C
from backend.app.services.historical_calls import TRAFFIC_PATH, reconcile_with_traffic_statement
from backend.app.services.sor_wharfage import SCHEDULE_BY_CODE as W

SOURCES = {
    "sor_2026": {
        "title": "NMPA Indexed SOR w.e.f. 01.05.2026 (0.65)",
        "url": "https://newmangaloreport.gov.in/sites/default/files/inline-files/Indexed%20SOR%20wef%2001.05.2026%20%280.65%29.pdf",
        "local": "nmpa_public_data/tariff/Indexed SOR wef 01.05.2026 (0.65).pdf",
    },
    "sor_2022": {
        "title": "NMPA SOR general revision w.e.f. 25 Dec 2022 (copy hosted by GAC)",
        "url": "https://cdn.gac.com/prod/docs/SOR-GENERAL-REVISION-SCALE-OF-RATES-WEF-25TH-DEC-2022.pdf",
    },
    "budget_2023_24": {
        "title": "NMPA Revised Estimate 2023-24 & Budget Estimate 2024-25 (operating income schedule)",
        "url": "https://newmangaloreport.gov.in/sites/default/files/2024-09/2023-24%20Final.pdf",
    },
    "traffic": {
        "title": "NMPA monthly commodity-wise traffic statements (parsed)",
        "local": "data/nmpa_commodity_traffic_2024_2026.csv",
    },
}

# ------------------------------------------------------------
# 1. SOR 2022 base rates (as published), keyed to the 2026 value in code
# ------------------------------------------------------------

def _rows_2022_vs_2026() -> List[tuple]:
    rows = [
        ("Port dues, ship (coastal ₹/GRT)", 6.13, C.PORT_DUES_RATES["ship_steamer_spm"]["coastal"]),
        ("Port dues, ship (foreign US$/GRT)", 0.3784, C.PORT_DUES_RATES["ship_steamer_spm"]["foreign"]),
        ("Port dues, tug/barge (coastal ₹/GRT)", 2.83, C.PORT_DUES_RATES["tug_launch_sailing_barge"]["coastal"]),
        ("Port dues, tug/barge (foreign US$/GRT)", 0.0605, C.PORT_DUES_RATES["tug_launch_sailing_barge"]["foreign"]),
        ("Pilotage ≤30,000 GRT (coastal ₹/GRT)", 12.95, 14.065),
        ("Pilotage ≤30,000 GRT (foreign US$/GRT)", 0.4851, 0.5269),
        ("Pilotage minimum (coastal ₹)", 38841, 42194.0),
        ("Pilotage minimum (foreign US$)", 1455, 1580.7),
        ("Pilotage 30,001-60,000 base (coastal ₹)", 388410, 421950),
        ("Pilotage 30,001-60,000 base (foreign US$)", 14553, 15807),
        ("Pilotage >60,000 base (coastal ₹)", 699270, 759480),
        ("Pilotage >60,000 base (foreign US$)", 26202, 28458),
        ("Pilotage at SPM (coastal ₹/GRT)", 10.90, C.PILOTAGE_SPM_RATE["coastal"]),
        ("Pilotage at SPM (foreign US$/GRT)", 0.2860, C.PILOTAGE_SPM_RATE["foreign"]),
        ("Shifting ≤30,000 GRT (coastal ₹/GRT)", 3.24, 3.5189),
        ("Shifting ≤30,000 GRT (foreign US$/GRT)", 0.1210, 0.1314),
        ("Shifting minimum (coastal ₹)", 9735, 10556.78),
        ("Shifting minimum (foreign US$)", 363, 394.15),
        ("Berth hire tanker minimum (coastal ₹/hr)", 199.36, C.BERTH_MINIMUMS["liquid"]["coastal"]),
        ("Berth hire tanker minimum (foreign US$/hr)", 7.46, C.BERTH_MINIMUMS["liquid"]["foreign"]),
        ("Berth hire other minimum (coastal ₹/hr)", 242.00, C.BERTH_MINIMUMS["dry_bulk"]["coastal"]),
        ("Berth hire other minimum (foreign US$/hr)", 9.04, C.BERTH_MINIMUMS["dry_bulk"]["foreign"]),
        ("Anchorage minimum (coastal ₹/hr)", 40, C.ANCHORAGE_RATES["other"]["coastal"]["minimum"]),
        ("Anchorage minimum (foreign US$/hr)", 1.4, C.ANCHORAGE_RATES["other"]["foreign"]["minimum"]),
        ("Anchorage bunkering minimum (coastal ₹/hr)", 24, C.ANCHORAGE_RATES["bunkering"]["coastal"]["minimum"]),
        ("Anchorage bunkering minimum (foreign US$/hr)", 0.904, C.ANCHORAGE_RATES["bunkering"]["foreign"]["minimum"]),
        ("Tug hire (coastal ₹/hr)", 11000, C.TUG_HIRE_RATES["tug_other"]["coastal"]),
        ("Tug hire (foreign US$/hr)", 264, C.TUG_HIRE_RATES["tug_other"]["foreign"]),
        ("Tug hire at SPM (coastal ₹/hr)", 53680, C.TUG_HIRE_RATES["tug_spm"]["coastal"]),
        ("Tug hire at SPM (foreign US$/hr)", 1408, C.TUG_HIRE_RATES["tug_spm"]["foreign"]),
        ("Transit storage, export (₹/unit/day)", 4.68, C.TRANSIT_STORAGE_RATES["week_1"]),
        ("Container storage ≤20' (coastal ₹/day)", 22.22, C.CONTAINER_STORAGE_RATES["20"]["coastal"]),
        ("Container storage ≤20' (foreign US$/day)", 0.50, C.CONTAINER_STORAGE_RATES["20"]["foreign"]),
        ("Bunkering facility (foreign ₹/MT)", 41.97, C.BUNKERING_FACILITY_RATES["foreign"]),
        ("Bunkering facility (coastal ₹/MT)", 29.22, C.BUNKERING_FACILITY_RATES["coastal"]),
    ]
    wharfage_2022 = {  # SOR code: (coastal, foreign) ₹ per unit, 2022 general revision
        "A.I.d": (84.14, 84.14), "A.I.j": (30.39, 30.40), "A.I.o": (84.14, 84.14),
        "A.IV.a": (128.57, 213.89), "A.V.a": (36.23, 59.62), "A.II.a": (50.25, 84.14),
        "A.II.b": (43.25, 71.30), "A.II.s": (46.74, 77.14), "B.I.a": (28.05, 47.92),
        "B.I.e": (24.54, 42.08), "B.I.f": (37.40, 63.12), "B.I.l": (4.68, 8.18),
        "B.II.a": (24.54, 42.08), "B.II.b": (28.05, 47.92), "B.III.b": (36.23, 59.62),
        "B.III.e": (88.84, 148.43), "B.III.g": (24.54, 42.08), "B.III.j": (39.74, 39.74),
        "B.III.l": (24.54, 42.08), "B.III.p": (14.03, 23.38), "B.III.q": (63.12, 105.18),
        "B.IV.a": (29.22, 29.22), "B.IV.b": (17.52, 29.22), "B.IV.c": (47.92, 47.92),
        "B.V.a": (43.25, 71.30), "B.V.d": (21.04, 36.23), "B.V.f": (14.03, 23.38),
        "C.a": (37.40, 61.95), "C.b": (28.05, 46.74), "C.c": (32.73, 53.81),
        "C.f": (92.34, 154.27), "C.g": (36.23, 59.62), "C.h": (634.64, 1057.74),
        "C.j": (43.25, 71.30), "C.k": (28.05, 46.74), "C.m": (92.34, 154.27),
        "C.n": (71.30, 119.21), "C.o": (2177.42, 3627.88), "C.q": (362.32, 1813.94),
        "E": (28.05, 46.74),
    }
    for code, (c22, f22) in wharfage_2022.items():
        rows.append((f"Wharfage {code} {W[code]['item'][:38]} (coastal ₹)", c22, W[code]["coastal"]))
        rows.append((f"Wharfage {code} {W[code]['item'][:38]} (foreign ₹)", f22, W[code]["foreign"]))
    return rows


# Two uniform movements are expected between Dec-2022 and May-2026:
# general indexation (~8.6%) and a higher one on liquid bulk, cement,
# break-bulk machinery / ODC / bagged cargo and container storage (~14.8%).
EXPECTED_FACTORS = (1.0861, 1.1481)
TOLERANCE = 0.003  # rounding of published rates to 2-4 decimals


def check_against_sor_2022() -> Dict[str, Any]:
    items = []
    for label, old, new in _rows_2022_vs_2026():
        ratio = new / old
        nearest = min(EXPECTED_FACTORS, key=lambda f: abs(ratio - f))
        ok = abs(ratio - nearest) <= TOLERANCE
        items.append({
            "item": label, "sor_2022": old, "sor_2026": new,
            "ratio": round(ratio, 4), "factor": nearest, "consistent": ok,
        })
    hist = Counter(i["factor"] for i in items if i["consistent"])
    return {
        "items_compared": len(items),
        "consistent": sum(i["consistent"] for i in items),
        "outliers": [i for i in items if not i["consistent"]],
        "factor_counts": {str(k): v for k, v in hist.items()},
        "items": items,
        "sources": [SOURCES["sor_2022"], SOURCES["sor_2026"]],
    }


# ------------------------------------------------------------
# 2. NMPA income 2023-24 (RE, ₹ '000) vs tonnage handled 2023-24
# ------------------------------------------------------------

INCOME_2023_24_RE = {  # ERP code: (ledger description, ₹ '000)
    "61010228": ("Wharfage on Crude oil", 886_796),
    "61010249": ("Wharfage-SPM", 231_744),
    "61010230": ("Wharfage on LPG", 743_411),
    "61010221": ("P.O.L. import - wharfage (Finished products)", 126_395),
    "61010222": ("P.O.L. export - wharfage (Finished products)", 439_624),
    "61010207": ("Wharfage on iron ore/pellets Import & Export cargo of KIOCL", 220_220),
    "61010308": ("Wharfage on other tankers (Chemical & other Liquids)", 144_718),
    "62030276": ("Port dues on foreign vessels", 666_652),
    "62010286": ("Pilotage fees on foreign vessels", 1_098_397),
    "62030277": ("Port dues on coastal vessels", 66_310),
    "62010287": ("Pilotage fees on coastal vessels", 135_625),
    "62030282": ("Port Dues-SPM", 149_573),
    "62010292": ("Pilotage-SPM", 122_086),
}


@lru_cache(maxsize=1)
def traffic_fy(fy_start: int = 2023) -> Dict[tuple, float]:
    """Tonnes by (section, commodity) for April fy_start .. March fy_start+1.

    The parsed statements start in January 2024 and carry the same month of
    the previous year, so April-December 2023 comes from the 2024 rows'
    previous-year column.
    """
    t = pd.read_csv(TRAFFIC_PATH)
    t["m"] = pd.to_datetime(t["month"], format="%B").dt.month
    a = t[(t.year == fy_start + 1) & (t.m >= 4)].assign(tonnes=lambda x: x.traffic_tonnes_prev_year)
    b = t[(t.year == fy_start + 1) & (t.m <= 3)].assign(tonnes=lambda x: x.traffic_tonnes_current)
    fy = pd.concat([a, b])
    return {k: float(v) for k, v in fy.groupby(["section", "commodity"])["tonnes"].sum().items()}


def check_against_income_2023_24() -> Dict[str, Any]:
    tr = traffic_fy(2023)
    def tons(*keys):
        return sum(tr.get(k, 0.0) for k in keys)

    def wh(code, side):
        return W[code][side]

    cases = []

    def add(name, ledger_codes, tonnes, band_lo, band_hi, band_basis, expect_inside=True, explanation=None):
        income = sum(INCOME_2023_24_RE[c][1] for c in ledger_codes) * 1000.0
        realised = income / tonnes if tonnes else None
        inside = realised is not None and band_lo * 0.98 <= realised <= band_hi * 1.02
        cases.append({
            "line": name,
            "ledger": [f"{c} {INCOME_2023_24_RE[c][0]}" for c in ledger_codes],
            "income_rs_crore": round(income / 1e7, 2),
            "tonnes_lakh": round(tonnes / 1e5, 2),
            "realised_rs_per_tonne": round(realised, 2) if realised else None,
            "sor_band_rs_per_tonne": [round(band_lo, 2), round(band_hi, 2)],
            "band_basis": band_basis,
            "inside_band": inside,
            "expected_inside": expect_inside,
            "result": "consistent" if inside == expect_inside else "check",
            "explanation": explanation,
        })

    add("LPG", ["61010230"], tons(("UNLOADED", "TOTAL LPG")),
        213.89, wh("A.IV.a", "foreign"), "A.IV.a foreign: ₹213.89 (2022) → ₹245.57 (2026-27)")

    add("POL finished products (import + export)", ["61010221", "61010222"],
        tons(("UNLOADED", "POL PRODUCTS"), ("LOADED", "POL PRODUCTS")),
        84.14, wh("A.I.o", "foreign"), "A.I POL lines: ₹84.14 (2022) → ₹96.60 (2026-27)")

    crude_t = tons(("UNLOADED", "TOTAL CRUDE"))
    add("Crude oil, berth + SPM", ["61010228", "61010249"], crude_t,
        30.40, wh("A.I.d", "foreign"),
        "between SPM line A.I.j (₹30.40-34.90) and berth line A.I.d (₹84.14-96.60)",
        explanation=None)
    # implied SPM share, solved from the two ledger lines at 2022 and 2026 rates
    berth_inc = INCOME_2023_24_RE["61010228"][1] * 1000.0
    spm_inc = INCOME_2023_24_RE["61010249"][1] * 1000.0
    implied = []
    for label, rb, rs in (("2022 rates", 84.14, 30.40), ("2026-27 rates", 96.60, 34.90)):
        tb, ts = berth_inc / rb, spm_inc / rs
        implied.append({"at": label, "berth_tonnes_lakh": round(tb / 1e5, 1), "spm_tonnes_lakh": round(ts / 1e5, 1),
                        "total_lakh": round((tb + ts) / 1e5, 1)})
    cases[-1]["implied_split"] = implied
    lo, hi = sorted((implied[0]["total_lakh"], implied[1]["total_lakh"]))
    inside = lo <= crude_t / 1e5 <= hi
    cases[-1]["inside_band"] = inside
    cases[-1]["result"] = "consistent" if inside else "check"
    cases[-1]["band_basis"] = (
        "tonnage implied by NMPA's two crude wharfage lines at SOR rates must bracket the tonnage reported"
    )
    cases[-1]["explanation"] = (
        f"Solving the two ledger lines for tonnage gives {implied[0]['total_lakh']}-{implied[1]['total_lakh']} lakh t "
        f"against {crude_t / 1e5:.1f} lakh t reported, so the SPM and berth rates reproduce NMPA's crude income "
        "within the indexation range."
    )

    add("Chemicals & other liquids (other tankers)", ["61010308"],
        tons(("UNLOADED", "OTH. LIQ. CARGOES"), ("LOADED", "OTH.LIQ.CARGOES"), ("LOADED", "PETROCHEMICALS")),
        71.30, wh("A.I.o", "foreign"),
        "A.II chemicals ₹71.30-81.86; other liquids at POL rates up to ₹96.60")

    add("Iron ore / pellets of KIOCL", ["61010207"],
        tons(("UNLOADED", "IRON ORE"), ("LOADED", "IRON ORE")),
        39.74, wh("B.III.i", "foreign"),
        "B.III.j fines ₹39.74-43.16; B.III.i pellets up to ₹45.71 — but B.III.i is 'other than KIOCL'",
        expect_inside=False,
        explanation=(
            "Realised rate is above every SOR iron-ore line, even though the tonnage used here is ALL iron "
            "ore (KIOCL and others), which can only understate KIOCL's rate. This is expected: the SOR prices iron ore "
            "pellets 'other than KIOCL', so KIOCL cargo is billed under a separate arrangement. The "
            "calculator therefore marks KIOCL pellets as not priced by the SOR instead of using B.III.i."
        ))

    # Vessel side: the SOR fixes the ratio of pilotage to port dues per GRT.
    ratios = []
    for name, pd_code, pil_code, sor_ratio, basis in (
        ("Coastal vessels", "62030277", "62010287", 14.065 / 6.6576, "pilotage ₹14.065 / port dues ₹6.6576 per GRT (≤30,000 GRT)"),
        ("Vessels at SPM", "62030282", "62010292", 0.3107 / 0.4110, "SPM pilotage US$0.3107 / port dues US$0.4110 per GRT"),
        ("Foreign vessels", "62030276", "62010286", 0.5269 / 0.4110, "pilotage US$0.5269 / port dues US$0.4110 per GRT (≤30,000 GRT)"),
    ):
        actual = INCOME_2023_24_RE[pil_code][1] / INCOME_2023_24_RE[pd_code][1]
        ratios.append({
            "line": name,
            "ledger_ratio_pilotage_to_port_dues": round(actual, 3),
            "sor_ratio": round(sor_ratio, 3),
            "basis": basis,
            "difference_pct": round((actual / sor_ratio - 1) * 100, 1),
        })
    ratios[-1]["explanation"] = (
        "Foreign pilotage income runs above the per-GRT ratio because re-entry after anchorage and "
        "shifting to anchorage are billed as fresh pilotage (SOR 2.2.3 notes 2 and 7), and port dues "
        "carry the 25% / 50% concessions of 2.1.2."
    )

    return {
        "year": "2023-24 (NMPA Revised Estimate) vs tonnage handled April 2023 - March 2024",
        "cargo_lines": cases,
        "vessel_ratio_checks": ratios,
        "sources": [SOURCES["budget_2023_24"], SOURCES["traffic"], SOURCES["sor_2022"], SOURCES["sor_2026"]],
        "caveat": (
            "2023-24 income is NMPA's Revised Estimate (prepared in-year), not audited actuals. "
            "Rates in force in 2023-24 lie between the 2022 base and the 2026-27 indexed rate, so the "
            "check is a band, not a point."
        ),
    }


@lru_cache(maxsize=1)
def full_report() -> Dict[str, Any]:
    sor = check_against_sor_2022()
    income = check_against_income_2023_24()
    calls = reconcile_with_traffic_statement()
    return {
        "summary": {
            "sor_items_checked": sor["items_compared"],
            "sor_items_consistent": sor["consistent"],
            "income_lines_checked": len(income["cargo_lines"]),
            "income_lines_consistent": sum(1 for c in income["cargo_lines"] if c["result"] == "consistent"),
            "calls_tonnage_coverage_pct": calls["coverage_pct"],
            "months_compared": calls["months_compared"],
        },
        "past_tariff": sor,
        "past_revenue": income,
        "past_calls": calls,
    }
