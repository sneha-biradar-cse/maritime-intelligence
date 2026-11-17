"""
NMPA SOR 2026-27 — Wharfage on Cargo (Chapter III, Schedule 3.1.1)

Full commodity-wise wharfage table transcribed from
nmpa_public_data/tariff/SOR_extracted.txt (pages 39-42), plus a
commodity-name matching layer that maps free-text cargo names
(e.g. the names used in the NMPA commodity traffic statements)
onto a single SOR line item.

Matching order (first hit wins):
    1. Exact  — SOR code or a registered alias
    2. Alias  — a registered alias appears as whole words in the name
    3. Fuzzy  — token-overlap / difflib similarity against item text
    4. Fallback — "(E) Unremunerated goods" per SOR note 9(i),
                  always flagged needs_review

Charging rules applied (Notes to Schedule 3.1.1):
    - Note 3(b): fractions < 0.5 -> 0.5 unit, fractions >= 0.5 -> 1 unit
    - Note 4:   minimum wharfage is for one unit (1 MT)
    - 3.1.3:    goods free of wharfage are charged zero
    - B.V(a-c): cement rate chosen by annual volume band
"""

import difflib
import math
import re
from typing import Any, Dict, List, Optional


SCHEDULE_REFERENCE = "NMPA SOR 2026-27, Schedule 3.1.1 (Wharfage on cargo)"


# ============================================================
# WHARFAGE SCHEDULE — ₹ per unit
#
# code    : SOR section path  (group . sub-group . item)
# unit    : MT / CBM / UNIT   (UNIT = per vehicle / equipment)
# aliases : extra names used for matching; legacy cost-engine
#           keys (e.g. "pol_products") are registered here too
# ============================================================

def _row(code, group, item, unit, coastal, foreign, aliases=()):
    return {
        "code": code,
        "group": group,
        "item": item,
        "unit": unit,
        "coastal": coastal,
        "foreign": foreign,
        "aliases": list(aliases),
    }


_POL = "A-I Liquid bulk: POL products"
_CHEM = "A-II Liquid bulk: Chemicals & acids"
_RENEW = "A-III Liquid bulk: Renewable resources"
_GAS = "A-IV Liquid bulk: Gases"
_EDIBLE = "A-V Liquid bulk: Edible oil & other liquids"
_FOOD = "B-I Dry bulk: Food grains, food products, oil seeds"
_FERT = "B-II Dry bulk: Fertilizer & raw materials"
_ORE = "B-III Dry bulk: Metals, ores & minerals"
_COAL = "B-IV Dry bulk: Coal & coke"
_CONS = "B-V Dry bulk: Construction materials / cement"
_TIMBER = "B-VI Dry bulk: Timber & forest products"
_BB = "C Break bulk & general cargo (non-container)"
_PIPE = "D Pipeline transfer operation"
_UNREM = "E Unremunerated goods"


WHARFAGE_SCHEDULE: List[Dict[str, Any]] = [
    # (A) Liquid bulk — I POL products
    _row("A.I.a", _POL, "Motor spirit / motor gasoline (petrol) blended with ethanol", "MT", 96.60, 96.60,
         ["petrol", "motor spirit", "gasoline"]),
    _row("A.I.b", _POL, "Superior kerosene oil", "MT", 96.60, 96.60, ["kerosene", "sko"]),
    _row("A.I.c", _POL, "Diesel oil / HSD / HFHSD / automotive diesel fuel / LDO", "MT", 96.60, 96.60,
         ["diesel", "hsd", "ldo", "light diesel oil"]),
    _row("A.I.d", _POL, "Crude oil", "MT", 96.60, 96.60,
         ["crude", "crude oil", "total crude", "crude isprl"]),
    _row("A.I.e", _POL, "Naphtha", "MT", 96.60, 96.60, ["naphtha"]),
    _row("A.I.f", _POL, "Furnace oil", "MT", 96.60, 96.60, ["furnace oil"]),
    _row("A.I.g", _POL, "VLSFO / NFO / fuel oil / heavy fuel oil / marine fuel oil", "MT", 96.60, 96.60,
         ["vlsfo", "fuel oil", "heavy fuel oil", "hfo", "marine fuel oil", "mfo", "nfo"]),
    _row("A.I.h", _POL, "Grease", "MT", 88.56, 88.56, ["grease"]),
    _row("A.I.i", _POL, "Asphalt / coal tar / bitumen / liquid coal pitch tar (liquid bulk)", "MT", 88.56, 88.56,
         ["liquid bitumen", "coal tar", "liquid coal pitch"]),
    _row("A.I.j", _POL, "Crude oil through Single Point Mooring (SPM)", "MT", 34.89, 34.90,
         ["crude spm", "crude oil spm", "spm crude"]),
    _row("A.I.k", _POL, "Slop / sludge oil / waste oil / gas oil / reformate", "MT", 96.60, 96.60,
         ["slop", "sludge oil", "waste oil", "gas oil", "gasoil", "reformate"]),
    _row("A.I.l", _POL, "Aviation fuel", "MT", 96.60, 96.60, ["aviation fuel", "atf"]),
    _row("A.I.m", _POL, "Vacuum gas oil (VGO)", "MT", 96.60, 96.60, ["vgo", "vacuum gas oil"]),
    _row("A.I.n", _POL, "JET A1", "MT", 96.60, 96.60, ["jet a1", "jet fuel"]),
    _row("A.I.o", _POL, "POL products — others", "MT", 96.60, 96.60,
         ["pol", "pol products", "petroleum products"]),

    # (A) Liquid bulk — II Chemicals & acids
    _row("A.II.a", _CHEM, "Ammonia liquid or gas", "MT", 57.69, 96.60, ["ammonia", "liquid ammonia"]),
    _row("A.II.b", _CHEM, "Phosphoric acid and styrene monomer", "MT", 49.65, 81.86,
         ["phosphoric acid", "styrene monomer"]),
    _row("A.II.c", _CHEM, "Sulphuric acid", "MT", 49.65, 81.86, ["sulphuric acid", "sulfuric acid"]),
    _row("A.II.d", _CHEM, "Orthoxylene", "MT", 49.65, 81.86, ["orthoxylene", "ortho xylene"]),
    _row("A.II.e", _CHEM, "Ethylene dichloride (EDC)", "MT", 49.65, 81.86, ["ethylene dichloride", "edc"]),
    _row("A.II.f", _CHEM, "Cyclohexanone", "MT", 49.65, 81.86, ["cyclohexanone"]),
    _row("A.II.g", _CHEM, "Cumene", "MT", 49.65, 81.86, ["cumene"]),
    _row("A.II.h", _CHEM, "Methanol", "MT", 49.65, 81.86, ["methanol"]),
    _row("A.II.i", _CHEM, "Phenol", "MT", 49.65, 81.86, ["phenol"]),
    _row("A.II.j", _CHEM, "Caustic soda dye", "MT", 49.65, 81.86, ["caustic soda"]),
    _row("A.II.k", _CHEM, "Acids / acrylic acid / chemicals of all kinds not specified above", "MT", 49.65, 81.86,
         ["chemicals", "chemical", "acrylic acid", "acids", "petrochemicals", "petrochemical"]),
    _row("A.II.l", _CHEM, "Ethylhexyl acrylate", "MT", 49.65, 81.86, ["ethylhexyl acrylate"]),
    _row("A.II.m", _CHEM, "Butyl acrylate", "MT", 49.65, 81.86, ["butyl acrylate"]),
    _row("A.II.n", _CHEM, "2-ethyl acrylate", "MT", 49.65, 81.86, ["ethyl acrylate"]),
    _row("A.II.o", _CHEM, "Liquid crude glycerin", "MT", 49.65, 81.86, ["glycerin", "glycerine"]),
    _row("A.II.p", _CHEM, "Benzene", "MT", 49.65, 81.86, ["benzene"]),
    _row("A.II.q", _CHEM, "Mixed xylene", "MT", 49.65, 81.86, ["mixed xylene"]),
    _row("A.II.r", _CHEM, "Para xylene", "MT", 49.65, 81.86, ["para xylene", "paraxylene"]),
    _row("A.II.s", _CHEM, "Soda ash", "MT", 53.66, 88.56, ["soda ash"]),
    _row("A.II.t", _CHEM, "Sulphur", "MT", 49.65, 81.86, ["sulphur", "sulfur"]),
    _row("A.II.u", _CHEM, "Polypropylene granules", "MT", 49.65, 81.86,
         ["polypropylene", "poly propylene", "pp granules"]),
    _row("A.II.v", _CHEM, "Purified terephthalic acid (PTA)", "MT", 49.65, 81.86,
         ["pta", "purified terephthalic acid"]),
    _row("A.II.w", _CHEM, "Poly ethylene terephthalate (PET)", "MT", 49.65, 81.86,
         ["pet resin", "polyethylene terephthalate"]),
    _row("A.II.x", _CHEM, "Mono ethylene glycol (MEG)", "MT", 49.65, 81.86, ["meg", "mono ethylene glycol"]),

    # (A) Liquid bulk — III / IV / V
    _row("A.III.a", _RENEW, "Bio diesel / bio fuel / UCOME / FAME", "MT", 96.57, 96.60,
         ["bio diesel", "biodiesel", "bio fuel", "biofuel", "ucome", "fame"]),
    _row("A.IV.a", _GAS, "LPG / LNG or any gas in any other form", "MT", 147.61, 245.57,
         ["lpg", "lng", "gas", "total lpg", "lpg lng gas"]),
    _row("A.V.a", _EDIBLE,
         "Palm oil, vegetable oil, palm acid oil, RBDPO, CSFO, CPO, POME, FWO, UCO, RBD palm olein, soya bean oil",
         "MT", 41.59, 68.45,
         ["edible oil", "palm oil", "vegetable oil", "soya bean oil", "soybean oil", "sunflower oil",
          "crude palm oil", "cpo", "rbd palm olein", "used cooking oil", "fish oil"]),
    _row("A.V.b", _EDIBLE, "Cashew shell liquid", "MT", 30.47, 52.05, ["cashew shell liquid", "cnsl"]),

    # (B) Dry bulk — I Food grains, food products, oil seeds
    _row("B.I.a", _FOOD, "Rice, wheat, maize, pulses", "MT", 30.47, 52.04,
         ["rice", "wheat", "maize", "pulses", "food grains", "foodgrains", "grain"]),
    _row("B.I.b", _FOOD, "Sugar, sugar candy or cube", "MT", 30.47, 52.04, ["sugar", "sugar candy"]),
    _row("B.I.c", _FOOD, "Oil seeds", "MT", 41.60, 68.45, ["oil seeds", "oilseeds"]),
    _row("B.I.d", _FOOD, "Molasses", "MT", 41.60, 68.45, ["molasses"]),
    _row("B.I.e", _FOOD, "Raw cashew nuts", "MT", 26.65, 45.71,
         ["raw cashew", "raw cashew nuts", "rcn"]),
    _row("B.I.f", _FOOD, "Cashew kernels", "MT", 40.62, 68.55, ["cashew kernels", "cashew kernel"]),
    _row("B.I.g", _FOOD, "Rice bran", "MT", 22.86, 39.35, ["rice bran"]),
    _row("B.I.h", _FOOD, "Tapioca chips, flour starch, waste & tamarind seed powder in bags", "MT", 27.91, 46.97,
         ["tapioca", "tamarind seed powder"]),
    _row("B.I.i", _FOOD, "Onion", "MT", 22.86, 39.35, ["onion", "onions"]),
    _row("B.I.j", _FOOD, "Coir and coir products", "MT", 43.16, 71.09, ["coir"]),
    _row("B.I.k", _FOOD, "Oil cakes and fodder of all kinds", "MT", 22.86, 39.35,
         ["oil cake", "oil cakes", "fodder", "de oiled cake", "soyabean meal", "soybean meal"]),
    _row("B.I.l", _FOOD, "Salt", "MT", 5.09, 8.89, ["salt"]),

    # (B) Dry bulk — II Fertilizer & raw materials
    _row("B.II.a", _FERT,
         "MOP, SOP, urea, DAP, NPK, CAN, ammonium sulphate, MAP/SAP/UAP, other finished fertilizer / polysulphate",
         "MT", 26.65, 45.71,
         ["fertilizer", "fertiliser", "urea", "dap", "mop", "npk", "sop", "ammonium sulphate", "polysulphate"]),
    _row("B.II.b", _FERT, "Sulphate / rock phosphate", "MT", 30.47, 52.04,
         ["rock phosphate", "frm", "frm dry", "fertilizer raw material", "fertilizer raw materials"]),

    # (B) Dry bulk — III Metals, ores & minerals
    _row("B.III.a", _ORE, "Iron and steel scraps and drops / scraps", "MT", 30.47, 52.04,
         ["scrap", "steel scrap", "iron scrap"]),
    _row("B.III.b", _ORE, "Pig iron / sponge iron / hot rolled coils", "MT", 39.35, 64.75,
         ["pig iron", "sponge iron", "hot rolled coils", "hr coils", "hrc"]),
    _row("B.III.c", _ORE, "Alloy steel, stainless steel and metals n.o.s. — ingots and products", "MT", 106.63, 177.72,
         ["alloy steel", "stainless steel"]),
    _row("B.III.d", _ORE, "Copper concentrate", "MT", 30.47, 52.04, ["copper concentrate"]),
    _row("B.III.e", _ORE, "Copper cathode", "MT", 96.48, 161.20, ["copper cathode"]),
    _row("B.III.f", _ORE, "Copper wire, rods, cables, bars, blocks", "MT", 77.44, 129.47,
         ["copper wire", "copper rods"]),
    _row("B.III.g", _ORE, "Limestone", "MT", 26.65, 45.71, ["limestone", "lime stone"]),
    _row("B.III.h", _ORE, "Aluminium and tin", "MT", 85.06, 142.18, ["aluminium", "aluminum", "tin"]),
    _row("B.III.i", _ORE, "Iron ore pellets other than KIOCL", "MT", 45.71, 45.71,
         ["iron ore pellets", "pellets"]),
    _row("B.III.j", _ORE, "Iron ore fines / lumps", "MT", 43.16, 43.16,
         ["iron ore", "iron ore fines", "iron ore lumps", "iron ore fines lumps"]),
    _row("B.III.k", _ORE, "Slag", "MT", 26.65, 43.16, ["slag"]),
    _row("B.III.l", _ORE, "Bauxite", "MT", 26.65, 45.71, ["bauxite"]),
    _row("B.III.m", _ORE, "Manganese ore", "MT", 22.86, 39.35, ["manganese ore", "manganese"]),
    _row("B.III.n", _ORE, "Perlite ore", "MT", 22.86, 39.35, ["perlite"]),
    _row("B.III.o", _ORE, "Chromite ore", "MT", 22.86, 39.35, ["chromite"]),
    _row("B.III.p", _ORE, "Bentonite & ball clay, sand / clay of any class", "MT", 15.24, 25.39,
         ["bentonite", "ball clay", "bentonite clay", "bentonite powder", "bentonite lumps"]),
    _row("B.III.q", _ORE, "Zinc concentrate", "MT", 68.55, 114.23, ["zinc concentrate", "zinc"]),
    _row("B.III.r", _ORE, "Rock sand", "MT", 21.59, 35.54, ["rock sand"]),
    _row("B.III.s", _ORE, "Titaniferous magnetite ore", "MT", 45.70, 45.70, ["titaniferous magnetite", "magnetite"]),
    _row("B.III.t", _ORE, "Mill scale", "MT", 36.82, 60.92, ["mill scale"]),
    _row("B.III.u", _ORE, "Clay, chalk", "MT", 30.47, 50.76, ["clay", "chalk", "china clay", "calcite powder"]),
    _row("B.III.v", _ORE, "Granite in any form except granite boulder", "MT", 34.27, 58.39,
         ["granite", "granite slabs"]),
    _row("B.III.w", _ORE, "Ferro silicon", "MT", 30.47, 52.05, ["ferro silicon", "ferrosilicon"]),
    _row("B.III.x", _ORE, "Any other ore in bulk", "MT", 26.65, 45.71, ["ore", "other ore"]),

    # (B) Dry bulk — IV Coal & coke
    _row("B.IV.a", _COAL, "Thermal coal (other than UPCL)", "MT", 31.73, 31.73,
         ["thermal coal", "steam coal", "coal", "total coal"]),
    _row("B.IV.b", _COAL, "Coal (other than thermal coal) and coke", "MT", 19.02, 31.73,
         ["coking coal", "coke", "met coke", "coal other"]),
    _row("B.IV.c", _COAL, "Pet coke (in bulk)", "MT", 55.02, 55.02, ["pet coke", "petcoke", "pet coke bulk"]),

    # (B) Dry bulk — V Construction materials / cement
    # a/b/c are volume bands; resolved by _apply_cement_band().
    _row("B.V.a", _CONS, "Cement — up to 3.00 lakh tonnes per annum", "MT", 49.65, 81.86,
         ["cement", "total cement", "bulk cement"]),
    _row("B.V.b", _CONS, "Cement — above 3.00 and up to 4.00 lakh tonnes per annum", "MT", 41.60, 68.45),
    _row("B.V.c", _CONS, "Cement — above 4.00 lakh tonnes per annum", "MT", 32.20, 55.02),
    _row("B.V.d", _CONS, "Gypsum / clinker", "MT", 22.86, 39.35, ["gypsum", "clinker"]),
    _row("B.V.e", _CONS, "Dolomite", "MT", 22.86, 39.35, ["dolomite", "dolomite powder"]),
    _row("B.V.f", _CONS, "River sand, metal, sand, granule, jelly, marble, manufactured sand (M-sand)", "MT",
         15.24, 25.40, ["sand", "river sand", "m sand", "jelly", "marble", "granule"]),
    _row("B.V.g", _CONS, "Fly ash in bulk", "MT", 30.47, 50.76, ["fly ash", "flyash"]),
    _row("B.V.h", _CONS, "Granite boulders", "MT", 30.47, 50.76, ["granite boulders", "granite boulder"]),
    _row("B.V.i", _CONS, "Tetra pod", "MT", 30.47, 50.76, ["tetra pod", "tetrapod"]),

    # (B) Dry bulk — VI Timber & forest products
    _row("B.VI.a", _TIMBER, "Wood pulp and wood chips", "MT", 30.47, 50.76, ["wood pulp", "wood chips"]),
    _row("B.VI.b", _TIMBER, "Papers of all kinds including waste papers", "MT", 30.47, 50.76,
         ["paper", "waste paper", "news print", "newsprint"]),

    # (C) Break bulk & general cargo other than containers
    _row("C.a", _BB, "Spices (cardamom, ginger, turmeric, coriander seed, pepper, chillies, etc.)", "MT",
         40.62, 67.27, ["spices", "cardamom", "pepper", "turmeric", "chillies", "ginger"]),
    _row("C.b", _BB, "Fish — dried, fresh, salted, preserved or frozen; prawns, frog legs, lobsters", "MT",
         30.47, 50.77, ["fish", "seafood", "prawns", "frozen fish", "fish meal"]),
    _row("C.c", _BB, "Yarn, cotton and wool raw, waste or manufactured staple fibre", "CBM", 35.55, 58.44,
         ["yarn", "cotton", "wool", "staple fibre"]),
    _row("C.d", _BB,
         "Arecanuts, beedi leaves, coffee, tea, tobacco, sandal wood, monazite / rutile sand, coffee husk", "MT",
         39.35, 66.02, ["arecanut", "areca nut", "coffee", "tea", "tobacco", "beedi", "coffee husk", "cocoa beans"]),
    _row("C.e", _BB, "Asphalt, bitumen (break bulk)", "MT", 64.75, 106.63, ["bitumen", "asphalt"]),
    _row("C.f", _BB, "Plant & machinery (knock-down or otherwise)", "MT", 106.01, 177.12,
         ["plant machinery", "machinery", "plant and machinery"]),
    _row("C.g", _BB, "Iron & steel plates, pipes, tubes, steel wire coils", "MT", 39.35, 64.75,
         ["steel plates", "steel pipes", "pipes", "tubes", "steel wire coils", "steel plates pipes", "iron steel"]),
    _row("C.h", _BB, "Over dimensional cargo", "MT", 728.65, 1214.42, ["over dimensional cargo", "odc"]),
    _row("C.i", _BB, "Galvanized steel, ingots, tin plates, lead material of all types", "MT", 63.47, 106.63,
         ["galvanized steel", "ingots", "tin plates", "lead"]),
    _row("C.j", _BB,
         "Bagged cement / sugar / raw sugar / all bagged cargo / coal tar pitch in jumbo bags / dried RCN in shell",
         "MT", 49.65, 81.86, ["bagged cargo", "bagged cement", "bagged sugar", "jumbo bags", "break bulk"]),
    _row("C.k", _BB, "Timber of all kinds of logs including plywood", "CBM", 30.47, 50.76,
         ["timber", "timber logs", "logs", "plywood", "ply wood", "wood"]),
    _row("C.l", _BB, "Pet coke (in break bulk)", "MT", 55.02, 55.02, ["bagged pet coke"]),
    _row("C.m", _BB, "Defence stores equipment", "MT", 100.29, 167.55, ["defence stores", "defense stores", "drdo"]),
    _row("C.n", _BB, "Unaccompanied personal effects", "MT", 77.44, 129.47,
         ["personal effects", "unaccompanied baggage"]),
    _row("C.o", _BB, "Vehicles / equipment imported or exported through the port", "UNIT", 2364.82, 3940.13,
         ["vehicles", "vehicle", "cars", "equipment"]),
    _row("C.p", _BB, "Vehicles / equipment through Ro-Ro operation", "UNIT", 2364.82, 3940.13,
         ["roro vehicles", "ro ro vehicles"]),
    _row("C.q", _BB, "Vehicles / equipment with loaded merchandise through Ro-Ro operation", "UNIT", 393.50, 1970.06,
         ["roro trucks", "loaded trucks roro"]),
    _row("C.r", _BB, "Accompanied passenger / seamen baggage, military personnel effects", "MT", 0.0, 0.0,
         ["passenger baggage", "seamen baggage"]),

    # (D) Pipeline transfer, (E) unremunerated goods
    _row("D.a", _PIPE, "Pipeline transfer operation charges of POL products", "MT", 50.76, 50.76,
         ["pipeline transfer pol", "pol pipeline transfer"]),
    _row("D.b", _PIPE, "Pipeline transfer of edible oil from Berth 15 to Berth 5", "MT", 21.14, 21.14,
         ["edible oil pipeline transfer"]),
    _row("E", _UNREM, "Unremunerated goods other than the above specified", "MT", 30.47, 50.76,
         ["unremunerated", "unenumerated", "other cargo", "others", "general cargo", "miscellaneous"]),
]

# ------------------------------------------------------------
# NMPA operational cargo codes
#
# Abbreviations exactly as they appear in NMPA's Daily Vessel
# Position reports (data/daily_vessel_position_parsed), e.g.
# "IOF(D)", "S.COAL", "CSFO", "AMSUL". Each one maps to the SOR
# 3.1.1 line that the full name falls under.
# ------------------------------------------------------------

NMPA_CARGO_CODES: Dict[str, List[str]] = {
    "A.I.a": ["ms", "mogas", "gasoline mogas"],
    "A.I.c": ["hfhsd", "hf hsd", "hsd hfsd"],
    "A.I.d": ["m crude", "mangala crude", "mangala crude oil", "murban crude", "mandji crude oil",
              "cruude"],
    "A.I.g": ["fo"],
    "A.I.k": ["slop discharge"],
    "A.I.n": ["jet a 1"],
    "A.II.b": ["phos acid", "ph acid", "sty mono", "sty monomer", "sty mon", "sm"],
    "A.II.c": ["sul acid", "sul aicd"],
    "A.II.k": ["2eha", "2 eha", "ba"],
    "A.II.r": ["paraxyene"],
    "A.II.t": ["cargo sulphar"],
    "A.V.a": ["csfo", "csfso", "rbdpo", "rbd", "prbd palm oil", "rbd cpo", "c palm oil", "fwo",
              "food waste oil", "uco", "pome", "rpome", "r pome"],
    "B.I.e": ["r cashew", "r cashew nuts", "r cashew neuts", "raw cahew nuts", "cashew"],
    "B.II.a": ["amsul", "ammonium sul", "granular urea", "prilled urea", "uread", "super phosphate",
               "ssp", "tsp"],
    "B.II.b": ["rock phos", "rock phosphate in bulk"],
    "B.III.b": ["pig iron"],
    "B.III.g": ["l stone", "limestone bulk"],
    "B.III.i": ["iop"],
    "B.III.j": ["iof", "iol", "iron ore fines"],
    "B.IV.a": ["s coal", "hard coal", "hard coal in bulk", "steam coal"],
    "B.IV.b": ["met coke", "coking coal"],
    "B.V.a": ["cemnt"],
    "C.f": ["project cargo", "plant euipment"],
    "C.g": ["s coil", "s coil plates", "steel coil", "steel coil plates"],
    "C.j": ["coal tar pitch in bags", "coal tar pitch in jumbo bags", "coal tar pitch in jumno bags",
            "bagged sugar", "bagged rice", "sop in j bags"],
}

for _code, _aliases in NMPA_CARGO_CODES.items():
    next(r for r in WHARFAGE_SCHEDULE if r["code"] == _code)["aliases"].extend(_aliases)


# Names that match more than one SOR line depending on how the cargo
# is presented. The match is kept but flagged needs_review with the
# alternative, because the Bill of Entry / Shipping Bill decides (SOR
# 3.1.1 note 2), not the short name in a vessel report.
AMBIGUOUS_ALIASES: Dict[str, Dict[str, str]] = {
    "coal tar pitch": {"alt": "C.j", "note": "Liquid coal tar pitch is A.I.i; in jumbo bags it is C.j."},
    "liquid coal tar pitch": {"alt": "C.j", "note": "A.I.i applies to liquid bulk; bagged pitch is C.j."},
    "bitumen": {"alt": "A.I.i", "note": "Break-bulk bitumen is C.e; liquid bitumen in a tanker is A.I.i."},
    "raw cashew": {"alt": "C.j", "note": "Raw cashew nuts are B.I.e, but 'dried raw cashew nuts in shell' is listed under C.j (bagged cargo)."},
    "raw cahew": {"alt": "C.j", "note": "Raw cashew nuts are B.I.e, but 'dried raw cashew nuts in shell' is listed under C.j (bagged cargo)."},
    "r cashew": {"alt": "C.j", "note": "Raw cashew nuts are B.I.e, but 'dried raw cashew nuts in shell' is listed under C.j (bagged cargo)."},
    "rcn": {"alt": "C.j", "note": "Raw cashew nuts are B.I.e, but 'dried raw cashew nuts in shell' is listed under C.j (bagged cargo)."},
    "fish meal": {"alt": "B.I.k", "note": "Fish meal is feed; it may be assessed as oil cakes & fodder (B.I.k) rather than fish (C.b)."},
    "coal": {"alt": "B.IV.b", "note": "Plain 'coal' is read as thermal coal (B.IV.a); coking coal is B.IV.b (lower coastal rate). UPCL coal is outside B.IV.a."},
    "bagged rice": {"alt": "B.I.a", "note": "Rice is B.I.a in bulk; 'all types of bagged cargo' is C.j."},
}


# Vessel-report entries that are not cargo: the vessel is in port
# for SPM work, bunkering, dredging, crew change, repairs, trials,
# conversion and similar. Only vessel related charges apply.
NON_CARGO_PATTERNS = (
    r"\bspm op\b", r"\bbunker barge\b", r"\bbunkering\b", r"\bdredging\b", r"\bconversion\b",
    r"\bconverion\b", r"\breversion\b", r"\bsea trials?\b", r"\bcrew change\b", r"\bresearch\b",
    r"\bship repairs?\b", r"\bfor repair\b", r"\bport op\b", r"\bre ?flagging\b", r"\bbarge for clearance\b",
    r"\bloading barge\b", r"\bnew ?build vessel\b", r"\bbollard pull\b", r"\btowing\b",
    r"\bline flushing\b", r"\bcruise ship\b", r"\bpassenger\b", r"\bsupply stores\b", r"\bgac\b",
)


SCHEDULE_BY_CODE = {row["code"]: row for row in WHARFAGE_SCHEDULE}

FALLBACK_CODE = "E"

CEMENT_BAND_CODES = ("B.V.a", "B.V.b", "B.V.c")

# Names that are not wharfage cargo: containers pay the composite
# box rate (Chapter IV), which already includes wharfage.
CONTAINER_KEYWORDS = ("container", "containers", "teu", "reefer", "empty container", "boxes", "box")

# Summary rows in traffic statements ("GRAND TOTAL", "a) Dry Bulk (Total)")
# are sums over many commodities and cannot be priced as one item.
AGGREGATE_PATTERNS = (
    r"\bgrand total\b",
    r"^[abcd] (dry bulk|break bulk|liquid bulk|containers?)\b",
    r"^(dry bulk|break bulk|liquid bulk)( total)?$",
)


# ------------------------------------------------------------
# 3.1.3 Goods free of wharfage
# ------------------------------------------------------------

FREE_OF_WHARFAGE = [
    "Cargo consigned to or by the Port",
    "Bunkers for govt anti-smuggling launches; ship's dunnage, fittings, packing materials not manifested as cargo",
    "Postal articles, diplomatic mail, bona fide crew luggage, military personnel baggage on duty",
    "Sand ballast",
    "Bona fide passengers' and seamen's baggage and personal effects",
    "Bona fide ship's fittings of the same vessel",
    "Cargo sweepings collected on shore",
]


# ============================================================
# MATCHING LAYER
# ============================================================

_STOPWORDS = {
    "total", "oth", "other", "and", "of", "the", "in", "all", "kinds", "kind",
    "any", "form", "bulk", "bags", "dry", "etc", "or", "products", "product",
}

FUZZY_ACCEPT = 0.60     # below this -> fallback to unremunerated goods
FUZZY_CONFIDENT = 0.85  # below this -> needs_review
TOKEN_MATCH = 0.85      # per-word similarity that counts as the same word (typos)


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/brackets/underscores, collapse spaces."""
    text = name.lower().replace("_", " ").replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Join dotted abbreviations: "f r m dry" -> "frm dry"
    return re.sub(
        r"\b(?:[a-z] ){2,}[a-z]\b",
        lambda m: m.group(0).replace(" ", ""),
        text,
    )


def _tokens(text: str) -> set:
    tokens = set()
    for tok in normalize_name(text).split():
        if tok in _STOPWORDS or len(tok) < 2:
            continue
        # crude singularisation: "pellets" -> "pellet", but keep "gas"/"glass"
        if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
            tok = tok[:-1]
        tokens.add(tok)
    return tokens


_CODE_INDEX = {row["code"].lower(): row["code"] for row in WHARFAGE_SCHEDULE}


def _build_alias_index() -> Dict[str, str]:
    index = {}
    for row in WHARFAGE_SCHEDULE:
        for alias in row["aliases"]:
            index[normalize_name(alias)] = row["code"]
    return index


ALIAS_INDEX = _build_alias_index()

# Longest aliases first so "iron ore pellets" beats "iron ore".
_ALIASES_BY_LENGTH = sorted(ALIAS_INDEX.items(), key=lambda kv: -len(kv[0]))


def _similarity(query: str, candidate: str) -> float:
    """
    Share of the query's words found in the candidate text. A word
    counts when spelled within TOKEN_MATCH similarity, so typos like
    "limestne" still match but "beer" does not match "beedi".
    """
    q_tokens, c_tokens = _tokens(query), _tokens(candidate)
    if not q_tokens or not c_tokens:
        return 0.0
    matched = 0.0
    for q in q_tokens:
        best = max(difflib.SequenceMatcher(None, q, c).ratio() for c in c_tokens)
        if best >= TOKEN_MATCH:
            matched += best
    return matched / len(q_tokens)


def match_commodity(name: str, top_n: int = 3) -> Dict[str, Any]:
    """
    Map a free-text commodity name to one SOR wharfage line item.

    Returns code, method (exact / alias / fuzzy / fallback / container /
    aggregate / non_cargo),
    score (0-1), needs_review, and the top alternative candidates.
    """
    raw = name or ""
    norm = normalize_name(strip_flow_markers(raw))

    if not norm:
        return _match_result(raw, FALLBACK_CODE, "fallback", 0.0, True, [])

    if any(re.search(pat, norm) for pat in NON_CARGO_PATTERNS):
        return {
            "query": raw,
            "code": None,
            "method": "non_cargo",
            "score": 1.0,
            "needs_review": False,
            "message": (
                "Not cargo (SPM work, bunkering, dredging, crew change, repairs, "
                "trials or similar). No wharfage; only vessel related charges apply."
            ),
            "candidates": [],
        }

    if any(re.search(pat, norm) for pat in AGGREGATE_PATTERNS):
        return {
            "query": raw,
            "code": None,
            "method": "aggregate",
            "score": 1.0,
            "needs_review": False,
            "message": (
                "This is a summary row covering several commodities; "
                "price each commodity separately."
            ),
            "candidates": [],
        }

    if any(re.search(rf"\b{kw}\b", norm) for kw in CONTAINER_KEYWORDS):
        return {
            "query": raw,
            "code": None,
            "method": "container",
            "score": 1.0,
            "needs_review": False,
            "message": (
                "Containerised cargo is charged the composite box rate "
                "(SOR Chapter IV), which already includes wharfage."
            ),
            "candidates": [],
        }

    # 1. Exact code / alias
    code_key = raw.strip().lower()
    if code_key in _CODE_INDEX:
        return _match_result(raw, _CODE_INDEX[code_key], "exact", 1.0, False, [])
    if norm in ALIAS_INDEX:
        return _match_result(raw, ALIAS_INDEX[norm], "exact", 1.0, False, [], norm)

    # 2. Alias contained as whole words
    for alias, code in _ALIASES_BY_LENGTH:
        if re.search(rf"\b{re.escape(alias)}\b", norm):
            return _match_result(raw, code, "alias", 0.95, False, [], alias)

    # 3. Fuzzy against item text + aliases
    scored = []
    for row in WHARFAGE_SCHEDULE:
        texts = [row["item"]] + row["aliases"]
        best = max(_similarity(norm, t) for t in texts)
        scored.append((best, row["code"]))
    scored.sort(reverse=True)
    candidates = [
        {"code": code, "item": SCHEDULE_BY_CODE[code]["item"], "score": round(score, 3)}
        for score, code in scored[:top_n]
    ]

    best_score, best_code = scored[0]
    if best_score >= FUZZY_ACCEPT:
        return _match_result(
            raw, best_code, "fuzzy", best_score,
            best_score < FUZZY_CONFIDENT, candidates,
        )

    # 4. Fallback — SOR note 9(i): unenumerated goods
    return _match_result(raw, FALLBACK_CODE, "fallback", best_score, True, candidates)


def _match_result(query, code, method, score, needs_review, candidates, matched_alias=None):
    row = SCHEDULE_BY_CODE[code]
    result = {
        "query": query,
        "code": code,
        "item": row["item"],
        "group": row["group"],
        "method": method,
        "score": round(score, 3),
        "needs_review": needs_review,
        "candidates": candidates,
    }
    ambiguity = None
    probe = normalize_name(strip_flow_markers(query)) if query else ""
    for key in sorted(AMBIGUOUS_ALIASES, key=len, reverse=True):
        if key == matched_alias or re.search(rf"\b{re.escape(key)}\b", probe):
            # A longer, more specific alias ("coal tar pitch in bags") settles it.
            if not (matched_alias and len(matched_alias) > len(key) and key in matched_alias):
                ambiguity = AMBIGUOUS_ALIASES[key]
            break
    if ambiguity and ambiguity["alt"] == code:
        ambiguity = {**ambiguity, "alt": _AMBIGUITY_PRIMARY.get(code, code)}
    if ambiguity and ambiguity["alt"] != code and method != "code":
        alt = SCHEDULE_BY_CODE[ambiguity["alt"]]
        result["needs_review"] = True
        result["ambiguity"] = ambiguity["note"]
        result["candidates"] = [
            {"code": code, "item": row["item"], "score": round(score, 3)},
            {"code": alt["code"], "item": alt["item"], "score": None},
        ]
    return result


# When the matched line is itself the "alternative", point back at the other one.
_AMBIGUITY_PRIMARY = {"C.j": "A.I.i", "A.I.i": "C.j", "B.I.a": "C.j", "A.II.m": "A.II.k"}

_FLOW_MARKER_RE = re.compile(r"\(\s*(?:d|l|e|i|d\s*/\s*l|l\s*/\s*d)\s*\)", re.IGNORECASE)


def strip_flow_markers(name: str) -> str:
    """Drop NMPA's '(D)' discharge / '(L)' load markers: 'IOF(D)' -> 'IOF'."""
    text = _FLOW_MARKER_RE.sub(" ", name or "")
    # A marker whose opening bracket was lost in PDF extraction: "COALD)"
    return re.sub(r"(?<=[A-Za-z])[DL]\)\s*$", " ", text)


# ============================================================
# CHARGING RULES
# ============================================================

def chargeable_units(quantity: float) -> float:
    """
    SOR note 3(b) rounding + note 4 minimum of one unit.

    Fractions below 0.5 are taken as 0.5 unit; fractions of 0.5 and
    above are taken as one unit.
    """
    if quantity <= 0:
        return 0.0
    whole = math.floor(quantity)
    fraction = quantity - whole
    if fraction == 0:
        units = float(whole)
    elif fraction < 0.5:
        units = whole + 0.5
    else:
        units = whole + 1.0
    return max(units, 1.0)


def _apply_cement_band(code: str, annual_volume_mt: Optional[float]) -> Dict[str, Any]:
    """Pick the cement band (B.V.a/b/c) from the user's annual volume."""
    if code not in CEMENT_BAND_CODES:
        return {"code": code, "note": None}

    if annual_volume_mt is None:
        return {
            "code": "B.V.a",
            "note": (
                "Annual cement volume not supplied; the up-to-3-lakh-tonne "
                "band (B.V.a) was applied."
            ),
        }
    if annual_volume_mt <= 300_000:
        band = "B.V.a"
    elif annual_volume_mt <= 400_000:
        band = "B.V.b"
    else:
        band = "B.V.c"
    return {
        "code": band,
        "note": f"Cement band chosen from annual volume {annual_volume_mt:,.0f} MT.",
    }


def calculate_commodity_wharfage(
    commodity: str,
    quantity: float,
    trade_type: str = "foreign",
    annual_volume_mt: Optional[float] = None,
    sor_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wharfage for any commodity name.

    quantity is in the SOR unit of the matched line item (MT for most
    items, CBM for yarn/cotton and timber/plywood, number of units for
    vehicles). Pass sor_code to bypass matching.
    """
    trade_type = trade_type.lower().strip()
    if trade_type not in ("coastal", "foreign"):
        raise ValueError("trade_type must be 'coastal' or 'foreign'")
    if quantity < 0:
        raise ValueError("quantity cannot be negative")

    if sor_code:
        if sor_code not in SCHEDULE_BY_CODE:
            raise ValueError(f"Unknown SOR wharfage code: {sor_code}")
        match = _match_result(commodity or sor_code, sor_code, "code", 1.0, False, [])
    else:
        match = match_commodity(commodity)

    if match["method"] in ("container", "aggregate", "non_cargo"):
        return {
            "status": "not_applicable",
            "commodity": commodity,
            "match": match,
            "amount": None,
            "message": match["message"],
        }

    band = _apply_cement_band(match["code"], annual_volume_mt)
    row = SCHEDULE_BY_CODE[band["code"]]
    rate = row[trade_type]
    units = chargeable_units(quantity)
    amount = units * rate

    notes = []
    if band["note"]:
        notes.append(band["note"])
    if row["unit"] != "MT":
        notes.append(
            f"This item is charged per {row['unit']}; the quantity was "
            f"read as {row['unit']}, not MT."
        )
    if match["needs_review"]:
        notes.append(
            "Commodity match is low-confidence; confirm the SOR line item "
            "against the Bill of Entry / Shipping Bill description."
        )

    return {
        "status": "calculated",
        "commodity": commodity,
        "match": match,
        "sor_code": row["code"],
        "sor_item": row["item"],
        "unit": row["unit"],
        "trade_type": trade_type,
        "quantity": quantity,
        "chargeable_units": units,
        "rate_per_unit": rate,
        "amount": round(amount, 2),
        "notes": notes,
        "reference": SCHEDULE_REFERENCE,
    }


def schedule_table() -> List[Dict[str, Any]]:
    """The schedule without aliases, for display / export."""
    return [
        {k: row[k] for k in ("code", "group", "item", "unit", "coastal", "foreign")}
        for row in WHARFAGE_SCHEDULE
    ]
