"""
NMPA Cost Engine

Calculates estimated port-related costs using the
NMPA Schedule of Rates (SOR) effective 01-05-2026 to 30-04-2027.

This version covers:
- Wharfage (full commodity schedule 3.1.1, via sor_wharfage)
- Berth hire
- Cargo storage: free days + transit storage (3.2.1)
- Container composite box rate
- Container storage
- Vessel-related charges (port dues, pilotage, anchorage, tugs, shifting)

It intentionally does NOT invent rates for tariff components
where the current SOR does not provide a numerical value; those
are reported as "Coming soon" (see COMING_SOON_COMPONENTS).
"""

import math
from typing import Dict, Any, Optional

from backend.app.services.sor_wharfage import calculate_commodity_wharfage


# ============================================================
# NMPA SOR — 2026-27
# Effective: 01-05-2026 to 30-04-2027
# ============================================================

TARIFF_VERSION = "NMPA SOR 2026-27"
EFFECTIVE_FROM = "2026-05-01"
EFFECTIVE_TO = "2027-04-30"


# ------------------------------------------------------------
# WHARFAGE — SOR Chapter III, Schedule 3.1.1
#
# The full commodity-wise table (~116 line items) and the
# commodity-name matching layer live in sor_wharfage.py.
# ------------------------------------------------------------


# ------------------------------------------------------------
# BERTH HIRE RATES — SOR Chapter II, 2.3.1
#
# Per GRT / hour: coastal in ₹, foreign in US$
# ------------------------------------------------------------

BERTH_HIRE_RATES = {
    "liquid": {
        "coastal": 0.10861,
        "foreign": 0.004019,
    },

    "dry_bulk": {
        "coastal": 0.07602,
        "foreign": 0.002824,
    },

    "container": {
        "coastal": 0.07602,
        "foreign": 0.002824,
    },

    "roro": {
        "coastal": 0.07602,
        "foreign": 0.002824,
    },

    "general_cargo": {
        "coastal": 0.07602,
        "foreign": 0.002824,
    },

    "hazardous": {
        "coastal": 0.10861,
        "foreign": 0.004019,
    },

    "other": {
        "coastal": 0.07602,
        "foreign": 0.002824,
    },
}


# SOR 2.3.1 (vii): vessels calling exclusively for bunkering at berth.
# The foreign rate is printed as USD 0.0040 here (0.004019 for tankers).
BERTH_HIRE_RATES["bunkering_at_berth"] = {"coastal": 0.10861, "foreign": 0.0040}


# SOR 2.3.1 item 11 and (ii)-(vi): small craft pay a flat rate per
# vessel per hour, not per GRT. Coastal in ₹, foreign in US$.
PER_VESSEL_BERTH_HIRE = {
    "barge_tug_craft": {"coastal": 136.063, "foreign": 5.0937},
    "bunker_barge": {"coastal": 136.063, "foreign": 5.0937},
    "fishing_service_boat": {"coastal": 21.786, "foreign": 0.8146},
    "wooden_rowing_boat": {"coastal": 10.698, "foreign": 0.3909},
}

# Passenger vessels: "Guided by separate notification of rates" (**).
BERTH_HIRE_NOT_PUBLISHED = {"passenger"}


# Minimum berth hire per hour: coastal in ₹, foreign in US$
BERTH_MINIMUMS = {
    "liquid": {
        "coastal": 216.52,
        "foreign": 8.10,
    },

    "dry_bulk": {
        "coastal": 262.83,
        "foreign": 9.82,
    },

    "container": {
        "coastal": 262.83,
        "foreign": 9.82,
    },

    "roro": {
        "coastal": 262.83,
        "foreign": 9.82,
    },

    "general_cargo": {
        "coastal": 262.83,
        "foreign": 9.82,
    },

    "hazardous": {
        "coastal": 216.52,
        "foreign": 8.10,
    },

    "other": {
        "coastal": 262.83,
        "foreign": 9.82,
    },

    "bunkering_at_berth": {
        "coastal": 216.52,
        "foreign": 8.10,
    },
}


def chargeable_hours(hours: float) -> int:
    """'Per hour or part thereof' (SOR 2.3.1, 2.5.2, 2.2.5): round up."""
    if hours <= 0:
        return 0
    return math.ceil(round(hours, 6))


# ------------------------------------------------------------
# CONTAINER COMPOSITE BOX RATE
#
# ₹ / container
# Includes wharfage + basic container handling services.
# ------------------------------------------------------------

CONTAINER_BOX_RATES = {
    "loaded_20": {
        "coastal": 315.36,
        "foreign": 524.69,
    },

    "loaded_40": {
        "coastal": 472.36,
        "foreign": 787.69,
    },

    "loaded_above_40": {
        "coastal": 630.69,
        "foreign": 1050.72,
    },

    "empty_20": {
        "coastal": 150.30,
        "foreign": 250.94,
    },

    "empty_40": {
        "coastal": 225.45,
        "foreign": 375.72,
    },

    "empty_above_40": {
        "coastal": 300.59,
        "foreign": 500.52,
    },
}


# ------------------------------------------------------------
# CONTAINER STORAGE — SOR 4.1(c)
#
# Per container / day: coastal in ₹, foreign in US$
# ------------------------------------------------------------

CONTAINER_STORAGE_RATES = {
    "20": {
        "coastal": 25.50,
        "foreign": 0.574,
    },

    "40": {
        "coastal": 50.98,
        "foreign": 1.15,
    },

    "above_40": {
        "coastal": 76.48,
        "foreign": 1.72,
    },
}


# ------------------------------------------------------------
# TRANSIT STORAGE
#
# ₹ / wharfage unit / day
# ------------------------------------------------------------

TRANSIT_STORAGE_RATES = {
    "week_1": 5.083,
    "week_2": 8.884,
    "after_week_2": 12.696,
}


# ------------------------------------------------------------
# PORT DUES — SOR Chapter II, 2.1.1 / 2.1.3 (SPM: 2.6)
#
# ₹ or US$ / GRT, levied each entry (bunker barge: once on
# first entry; bunkering-at-anchorage: nil).
# ------------------------------------------------------------

PORT_DUES_RATES = {
    "ship_steamer_spm": {
        "foreign": 0.4110,
        "coastal": 6.6576,
    },
    "tug_launch_sailing_barge": {
        "foreign": 0.0657,
        "coastal": 3.0735,
    },
    "bunker_barge": {
        "foreign": 0.0657,
        "coastal": 3.0735,
    },
    "bunkering_at_berth": {
        "foreign": 0.4110,
        "coastal": 6.6576,
    },
    "bunkering_at_anchorage": {
        "foreign": 0.0,
        "coastal": 0.0,
    },
}


# ------------------------------------------------------------
# PILOTAGE — SOR Chapter II, 2.2.1 / 2.2.2 (SPM: 2.6)
#
# Composite inward + outward pilotage. Ships/steamers are
# tiered by GRT band; SPM and small craft use flat rates.
# ------------------------------------------------------------

PILOTAGE_SPM_RATE = {
    "foreign": 0.3107,
    "coastal": 11.84,
}

PILOTAGE_FLAT_RATES = {
    "barge_small": {
        "foreign": 117.078,
        "coastal": 3136.02,
    },
    "barge_large": {
        "foreign": 175.61,
        "coastal": 4702.24,
    },
    "bunker_barge": {
        "foreign": 117.078,
        "coastal": 3136.02,
    },
}


# ------------------------------------------------------------
# ANCHORAGE FEES — SOR Chapter II, 2.5.2
#
# ₹ or US$ / GRT / hour, subject to a minimum hourly charge.
# Pre-berthing anchorage while loading/unloading is free.
# ------------------------------------------------------------

ANCHORAGE_RATES = {
    "post_sailing": {
        "foreign": {"rate": 0.00075, "minimum": 1.52},
        "coastal": {"rate": 0.021, "minimum": 43.44},
    },
    "other": {
        "foreign": {"rate": 0.00075, "minimum": 1.52},
        "coastal": {"rate": 0.021, "minimum": 43.44},
    },
    "bunkering": {
        "foreign": {"rate": 0.00027, "minimum": 0.981},
        "coastal": {"rate": 0.0075, "minimum": 26.06},
    },
}


# ------------------------------------------------------------
# TUG HIRE CHARGES — SOR Chapter II, 2.2.5 (SPM tugs: 2.6)
#
# ₹ or US$ / tug (or craft) hour or part thereof.
# ------------------------------------------------------------

TUG_HIRE_RATES = {
    "tug_spm": {
        "foreign": 1529.18,
        "coastal": 58300.13,
    },
    "tug_other": {
        "foreign": 286.72,
        "coastal": 11947.16,
    },
    "pilot_launch": {
        "foreign": 82.53,
        "coastal": 3452.97,
    },
    "mooring_launch": {
        "foreign": 68.10,
        "coastal": 2854.95,
    },
}


# ------------------------------------------------------------
# SHIFTING CHARGES — SOR Chapter II, 2.2.3
#
# Movement of a vessel within the dock basin at the vessel's
# own request. Ships/steamers are tiered by GRT band; small
# craft use flat per-vessel rates. Bunker barges: nil.
# 50% concession applies when tugs are not used for the shift.
# ------------------------------------------------------------

SHIFTING_FLAT_RATES = {
    "barge_small": {
        "foreign": 29.346,
        "coastal": 783.71,
    },
    "barge_large": {
        "foreign": 43.985,
        "coastal": 1175.56,
    },
    "bunker_barge": {
        "foreign": 0.0,
        "coastal": 0.0,
    },
}


# ============================================================
# CALCULATORS
# ============================================================

def calculate_wharfage(
    cargo_type: str,
    quantity_mt: float,
    trade_type: str = "foreign",
    annual_volume_mt: Optional[float] = None,
    sor_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate wharfage for cargo.

    cargo_type may be any commodity name ("Iron ore fines", "TOTAL COAL"),
    a legacy cost-engine key ("pol_products") or an SOR code ("B.III.j").
    It is matched to one line of Schedule 3.1.1 by sor_wharfage.

    quantity_mt = cargo quantity in the SOR unit of the matched item
                  (MT for most cargo)
    trade_type = coastal / foreign
    """

    result = calculate_commodity_wharfage(
        commodity=cargo_type,
        quantity=quantity_mt,
        trade_type=trade_type,
        annual_volume_mt=annual_volume_mt,
        sor_code=sor_code,
    )

    if result["status"] != "calculated":
        return {
            "status": result["status"],
            "cargo_type": cargo_type,
            "message": result["message"],
            "match": result["match"],
            "amount": None,
        }

    return {
        "status": "calculated",
        "cargo_type": cargo_type,
        "sor_code": result["sor_code"],
        "sor_item": result["sor_item"],
        "unit": result["unit"],
        "quantity_mt": quantity_mt,
        "chargeable_units": result["chargeable_units"],
        "trade_type": result["trade_type"],
        "rate_per_mt": result["rate_per_unit"],
        "amount": result["amount"],
        "match": result["match"],
        "notes": result["notes"],
    }


def calculate_berth_hire(
    vessel_type: str,
    vessel_grt: Optional[float],
    berth_hours: float,
    trade_type: str = "coastal",
    double_banked: bool = False,
) -> Dict[str, Any]:
    """
    Berth hire, SOR 2.3.1.

        GRT × rate per GRT per hour, subject to a minimum per hour,
        × chargeable hours ("per hour or part thereof", so rounded up)

    Small craft (barges, tugs, bunker barges, fishing / service boats)
    pay a flat rate per vessel per hour instead. A double-banked
    vessel pays 50% (2.3.1 item 12). trade_type here is the VESSEL's
    status (coastal / foreign-going), which decides the currency.
    """

    vessel_type = vessel_type.lower().strip()
    trade_type = trade_type.lower().strip()
    hours = chargeable_hours(berth_hours)

    if vessel_type in BERTH_HIRE_NOT_PUBLISHED:
        return {
            "status": "rate_unavailable",
            "vessel_type": vessel_type,
            "message": "Passenger vessel berth hire is set by separate notification (SOR 2.3.1 item 8).",
            "amount": None,
        }

    if vessel_type in PER_VESSEL_BERTH_HIRE:
        hourly_charge = PER_VESSEL_BERTH_HIRE[vessel_type][trade_type]
        basis = "per vessel per hour"
        rate = None
        minimum = None
    else:
        if vessel_type not in BERTH_HIRE_RATES:
            vessel_type = "other"
        if not vessel_grt:
            return {
                "status": "needs_grt",
                "vessel_type": vessel_type,
                "berth_hours": berth_hours,
                "chargeable_hours": hours,
                "message": "Enter the vessel's GRT (International Tonnage Certificate) to price berth hire.",
                "amount": None,
            }
        rate = BERTH_HIRE_RATES[vessel_type][trade_type]
        minimum = BERTH_MINIMUMS[vessel_type][trade_type]
        hourly_charge = max(vessel_grt * rate, minimum)
        basis = "per GRT per hour"

    if double_banked:
        hourly_charge *= 0.5

    total = hourly_charge * hours

    return {
        "status": "calculated",
        "vessel_type": vessel_type,
        "vessel_grt": vessel_grt,
        "berth_hours": berth_hours,
        "chargeable_hours": hours,
        "basis": basis,
        "rate_per_grt_hour": rate,
        "minimum_hourly_charge": minimum,
        "double_banked": double_banked,
        "effective_hourly_charge": round(hourly_charge, 4),
        "amount": round(total, 2),
        "sor_reference": "2.3.1",
    }


# ------------------------------------------------------------
# CARGO STORAGE — SOR Chapter III, 3.2.1(a) / 3.2.1(b)
#
# Free days by cargo flow and category, then transit storage
# charged per wharfage unit per day.
# ------------------------------------------------------------

STORAGE_FREE_DAYS = {
    # (cargo_flow, cargo_category): (days, basis, SOR reference)
    ("import", "bulk"): (7, "7 working days after complete discharge", "3.2.1(a) note 1(ii)"),
    ("import", "break_bulk"): (7, "7 working days after complete discharge", "3.2.1(a) note 1(ii)"),
    ("coastal", "bulk"): (15, "15 days inclusive of Customs / Port holidays", "3.2.1(a) note 1(vi)"),
    ("coastal", "break_bulk"): (15, "15 days inclusive of Customs / Port holidays", "3.2.1(a) note 1(vi)"),
    ("export", "bulk"): (21, "21 working days from receipt in transit area", "3.2.1(b) note 1(ii)"),
    ("export", "break_bulk"): (21, "21 working days from receipt in transit area", "3.2.1(b) note 1(ii)"),
    ("export", "salvaged"): (3, "3 working days from date of salvage", "3.2.1(b) note 1(iii)"),
    ("export", "not_shipped"): (7, "7 working days for export cargo not actually shipped", "3.2.1(b) note 2(iii)"),
    ("transhipment", "bulk"): (28, "28 working days from receipt", "3.2.1(b) note 5"),
    ("transhipment", "break_bulk"): (28, "28 working days from receipt", "3.2.1(b) note 5"),
}

VALID_STORAGE_CATEGORIES = {"bulk", "break_bulk", "salvaged", "not_shipped"}


def get_free_storage_days(
    cargo_flow: str,
    cargo_category: str = "bulk",
) -> Dict[str, Any]:
    """
    Return the NMPA free-storage allowance (SOR 3.2.1).

    Day counts are returned as plain numbers; excluding Customs
    holidays and port non-working days must be handled separately
    when exact billing dates are used.
    """

    cargo_flow = cargo_flow.lower().strip()
    cargo_category = cargo_category.lower().strip()

    rule = STORAGE_FREE_DAYS.get((cargo_flow, cargo_category))

    if rule is None:
        return {
            "status": "manual_required",
            "cargo_flow": cargo_flow,
            "cargo_category": cargo_category,
            "free_storage_days": None,
            "basis": (
                "No automatic rule configured. "
                "Manual tariff interpretation required."
            ),
        }

    days, basis, reference = rule
    return {
        "status": "configured",
        "cargo_flow": cargo_flow,
        "cargo_category": cargo_category,
        "free_storage_days": days,
        "basis": basis,
        "sor_reference": reference,
    }


def calculate_transit_storage(
    wharfage_units: float,
    actual_storage_days: float,
    free_storage_days: float = 0,
    cargo_flow: str = "import",
) -> Dict[str, Any]:
    """
    Calculate transit storage charges after the applicable
    free-storage period.

        chargeable days = actual storage days - free days

    Import / coastal / transhipment cargo — SOR 3.2.1(a):
        First 7 chargeable days     -> ₹5.083 / unit / day
        Next 7 chargeable days      -> ₹8.884 / unit / day
        Remaining chargeable days   -> ₹12.696 / unit / day

    Export cargo — SOR 3.2.1(b):
        All chargeable days         -> ₹5.083 / unit / day
    """

    if actual_storage_days < 0:
        raise ValueError("actual_storage_days cannot be negative")

    if free_storage_days < 0:
        raise ValueError("free_storage_days cannot be negative")

    cargo_flow = cargo_flow.lower().strip()

    chargeable_days = max(
        0,
        actual_storage_days - free_storage_days
    )

    slabs = []

    if cargo_flow == "export":
        if chargeable_days > 0:
            slabs.append(("all_days", chargeable_days, TRANSIT_STORAGE_RATES["week_1"]))
    else:
        remaining_days = chargeable_days
        for slab, limit in (("week_1", 7), ("week_2", 7), ("after_week_2", None)):
            if remaining_days <= 0:
                break
            days = remaining_days if limit is None else min(remaining_days, limit)
            slabs.append((slab, days, TRANSIT_STORAGE_RATES[slab]))
            remaining_days -= days

    slab_rows = [
        {
            "slab": slab,
            "days": days,
            "rate_per_unit_day": rate,
            "amount": round(days * rate * wharfage_units, 2),
        }
        for slab, days, rate in slabs
    ]
    amount = sum(days * rate * wharfage_units for _, days, rate in slabs)

    return {
        "status": "calculated",
        "cargo_flow": cargo_flow,
        "wharfage_units": wharfage_units,
        "actual_storage_days": actual_storage_days,
        "free_storage_days": free_storage_days,
        "chargeable_days": chargeable_days,
        "slabs": slab_rows,
        "amount": round(amount, 2),
        "sor_reference": "3.2.1(b)" if cargo_flow == "export" else "3.2.1(a)",
    }


# ------------------------------------------------------------
# COMING SOON — SOR components with no numerical rate yet
#
# The 2026-27 SOR prints these as "*" ("as and when applicable")
# or "as per Estate SOR". They are reported, never invented.
# ------------------------------------------------------------

COMING_SOON_MESSAGE = "Coming soon"

COMING_SOON_COMPONENTS = [
    {
        "component": "demurrage",
        "label": "Demurrage schedule (open / covered space)",
        "sor_reference": "3.2.2",
        "reason": (
            "Rates printed as '*'. The calculator applies the week-2 and succeeding transit "
            "rates of 3.2.1(a), which NMPA treats as demurrage (3.2.1(a) note 1(iv))."
        ),
    },
    {
        "component": "hazardous_demurrage_surcharge",
        "label": "Hazardous cargo demurrage (+50%)",
        "sor_reference": "3.2.2 note 3",
        "reason": "Depends on the demurrage schedule, which has no rates yet.",
    },
    {
        "component": "licence_fee_storage",
        "label": "Storage licence fee (allotted space)",
        "sor_reference": "3.3.1 / 3.3.2",
        "reason": "Charged as per Estate SOR, not published in this SOR.",
    },
    {
        "component": "wharf_evacuation_penalty",
        "label": "Penal charges for cargo not evacuated from wharf",
        "sor_reference": "3.1.1 note 10",
        "reason": "Hour bands and rates printed as '*'.",
    },
    {
        "component": "shut_out_back_to_town",
        "label": "Shut-out / back-to-town cargo surcharge",
        "sor_reference": "3.1.2",
        "reason": "Percentage printed as '*' (as and when applicable).",
    },
    {
        "component": "container_free_dwell",
        "label": "Container free dwell time and demurrage",
        "sor_reference": "4.9",
        "reason": "Free days and slabs printed as blanks; container storage 4.1(c) is per day from day one.",
    },
    {
        "component": "berth_hire_ppp_terminals",
        "label": "Terminal tariff at PPP Berths 14 and 16",
        "sor_reference": "—",
        "reason": "Billed by the PPP operator under its own tariff; not part of the NMPA SOR.",
    },
    {
        "component": "volume_discount",
        "label": "Volume / quantum discount on wharfage",
        "sor_reference": "3.1.4",
        "reason": "Section is blank in the 2026-27 SOR.",
    },
    {
        "component": "labour_charges",
        "label": "Supply of labour / staff",
        "sor_reference": "3.4.1",
        "reason": "Rates printed as '*'.",
    },
]


def coming_soon_components() -> list:
    """Components shown to the user as 'Coming soon'."""
    return [
        {**item, "status": "coming_soon", "message": COMING_SOON_MESSAGE}
        for item in COMING_SOON_COMPONENTS
    ]


# ------------------------------------------------------------
# CURRENCY — SOR Chapter I, General terms (iii) and (iv)
#
# Foreign-going vessel rates (Chapter II) and foreign container
# storage (4.1(c)) are denominated in US$. They are billed in
# INR at the RBI reference rate on the day the vessel enters
# port limits, so the rate is an input, never a constant here.
# ------------------------------------------------------------

USD_DENOMINATED_COMPONENTS = {
    "berth_hire",
    "port_dues",
    "pilotage",
    "anchorage",
    "tug_hire",
    "shifting",
}


def component_currency(component_key: str, trade_type: str) -> str:
    """SOR currency of a cost component for the given trade type."""

    if trade_type == "foreign" and component_key in USD_DENOMINATED_COMPONENTS:
        return "USD"
    return "INR"


def apply_sor_currency(
    result: Dict[str, Any],
    currency: str,
    usd_inr_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Tag a calculated component with its SOR currency and make
    "amount" the INR value.

    Rates inside the result stay in the SOR currency. For a US$
    component the original figure is kept in "amount_usd"; without
    an exchange rate "amount" becomes None and the status becomes
    "needs_exchange_rate", so it is never added to an INR total.
    """

    if result.get("status") != "calculated":
        return result

    result["currency"] = currency

    if currency == "INR":
        return result

    amount_usd = round(result["amount"], 2)
    result["amount_usd"] = amount_usd

    if usd_inr_rate:
        result["usd_inr_rate"] = usd_inr_rate
        result["amount"] = round(amount_usd * usd_inr_rate, 2)
    else:
        result["amount"] = None
        result["status"] = "needs_exchange_rate"
        result["message"] = (
            "SOR rate is in US$ for foreign-going vessels. Enter the RBI "
            "reference USD/INR rate for the vessel's entry day to convert."
        )

    return result


def calculate_container_cost(
    container_size: str,
    container_status: str,
    number_of_containers: int,
    trade_type: str = "coastal",
    storage_days: float = 0,
    usd_inr_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate container composite box cost + storage.

    IMPORTANT:
    The composite box rate already includes wharfage and
    basic container handling services.

    Box rates are in INR for both trades; foreign container
    storage (SOR 4.1(c)) is in US$ and needs usd_inr_rate.
    """

    container_size = container_size.lower().strip()
    container_status = container_status.lower().strip()
    trade_type = trade_type.lower().strip()

    if container_size == "20":
        size_key = "20"
    elif container_size == "40":
        size_key = "40"
    else:
        size_key = "above_40"

    if container_status == "loaded":
        rate_key = f"loaded_{size_key}"
    else:
        rate_key = f"empty_{size_key}"

    box_rate = CONTAINER_BOX_RATES[rate_key][trade_type]

    box_cost = box_rate * number_of_containers

    storage_rate = CONTAINER_STORAGE_RATES[size_key][trade_type]
    storage_cost = (
        storage_rate
        * number_of_containers
        * storage_days
    )

    storage = apply_sor_currency(
        {"status": "calculated", "amount": storage_cost},
        currency="USD" if trade_type == "foreign" else "INR",
        usd_inr_rate=usd_inr_rate,
    )

    storage_cost_inr = storage["amount"]
    total = (
        box_cost + storage_cost_inr
        if storage_cost_inr is not None
        else None
    )

    return {
        "status": storage["status"],
        "container_size": container_size,
        "container_status": container_status,
        "number_of_containers": number_of_containers,
        "trade_type": trade_type,
        "box_rate": box_rate,
        "box_cost": round(box_cost, 2),
        "storage_rate_per_container_day": storage_rate,
        "storage_rate_currency": storage["currency"],
        "storage_days": storage_days,
        "storage_cost": (
            round(storage_cost_inr, 2)
            if storage_cost_inr is not None
            else None
        ),
        "storage_cost_usd": storage.get("amount_usd"),
        "usd_inr_rate": usd_inr_rate,
        "total": round(total, 2) if total is not None else None,
    }


def calculate_port_dues(
    vessel_category: str,
    vessel_grt: float,
    trade_type: str = "coastal",
    reduction: str = "none",
) -> Dict[str, Any]:
    """
    Calculate port dues for a single vessel entry.

    reduction:
        "none"                    -> full rate
        "ballast_no_passengers"   -> 75% of the rate (SOR 2.1.2 item 1: 25% concession)
        "no_cargo_no_passenger"   -> 50% of the rate (SOR 2.1.2 item 2: 50% concession)
    """

    vessel_category = vessel_category.lower().strip()
    trade_type = trade_type.lower().strip()
    reduction = reduction.lower().strip()

    if vessel_category not in PORT_DUES_RATES:
        return {
            "status": "rate_unavailable",
            "vessel_category": vessel_category,
            "message": (
                "No port dues rate is configured for this vessel category."
            ),
            "amount": None,
        }

    rate = PORT_DUES_RATES[vessel_category][trade_type]
    amount = vessel_grt * rate

    if reduction == "ballast_no_passengers":
        amount *= 0.75
    elif reduction == "no_cargo_no_passenger":
        amount *= 0.50

    return {
        "status": "calculated",
        "vessel_category": vessel_category,
        "vessel_grt": vessel_grt,
        "trade_type": trade_type,
        "reduction": reduction,
        "rate_per_grt": rate,
        "amount": round(amount, 2),
    }


def _pilotage_tiered_amount(vessel_grt: float, trade_type: str) -> float:
    """Tiered ship/steamer pilotage per SOR 2.2.1."""

    if trade_type == "foreign":
        if vessel_grt <= 30000:
            return max(vessel_grt * 0.5269, 1580.7)
        if vessel_grt <= 60000:
            return 15807 + (vessel_grt - 30000) * 0.4217
        return 28458 + (vessel_grt - 60000) * 0.3692

    # coastal
    if vessel_grt <= 30000:
        return max(vessel_grt * 14.065, 42194.00)
    if vessel_grt <= 60000:
        return 421950 + (vessel_grt - 30000) * 11.251
    return 759480 + (vessel_grt - 60000) * 9.840


def calculate_pilotage(
    vessel_grt: float,
    trade_type: str = "coastal",
    vessel_category: str = "ship_steamer",
) -> Dict[str, Any]:
    """
    Composite inward + outward pilotage.

    vessel_category:
        "ship_steamer" -> tiered by GRT band (SOR 2.2.1)
        "spm"          -> flat rate per GRT (SOR 2.6 item 2)
        "barge_small"  -> flat per-vessel rate, GRT up to 199 (SOR 2.2.2 item 9)
        "barge_large"  -> flat per-vessel rate, GRT 200 and above (SOR 2.2.2 item 10)
        "bunker_barge" -> flat per-vessel rate, first entry only (SOR 2.2.2 item 11)
    """

    trade_type = trade_type.lower().strip()
    vessel_category = vessel_category.lower().strip()

    if vessel_category == "ship_steamer":
        amount = _pilotage_tiered_amount(vessel_grt, trade_type)
    elif vessel_category == "spm":
        amount = vessel_grt * PILOTAGE_SPM_RATE[trade_type]
    elif vessel_category in PILOTAGE_FLAT_RATES:
        amount = PILOTAGE_FLAT_RATES[vessel_category][trade_type]
    else:
        return {
            "status": "rate_unavailable",
            "vessel_category": vessel_category,
            "message": "No pilotage rate is configured for this vessel category.",
            "amount": None,
        }

    return {
        "status": "calculated",
        "vessel_category": vessel_category,
        "vessel_grt": vessel_grt,
        "trade_type": trade_type,
        "amount": round(amount, 2),
    }


def calculate_anchorage(
    vessel_grt: float,
    anchorage_hours: float,
    trade_type: str = "coastal",
    category: str = "post_sailing",
) -> Dict[str, Any]:
    """
    Anchorage fees (SOR 2.5.2), per GRT per hour or part thereof.

    category:
        "pre_berthing" -> free, while loading/unloading
        "post_sailing" -> vessel at anchorage after sailing out from berth
        "other"        -> vessels other than those specifically listed
        "bunkering"    -> vessels called exclusively to anchorage for bunkering
    """

    trade_type = trade_type.lower().strip()
    category = category.lower().strip()

    if category == "pre_berthing":
        return {
            "status": "calculated",
            "category": category,
            "amount": 0.0,
            "note": (
                "Pre-berthing anchorage for vessels loading/unloading "
                "cargo at the port is free under SOR 2.5."
            ),
        }

    if category not in ANCHORAGE_RATES:
        return {
            "status": "rate_unavailable",
            "category": category,
            "message": "No anchorage rate is configured for this category.",
            "amount": None,
        }

    spec = ANCHORAGE_RATES[category][trade_type]
    hourly_charge = max(vessel_grt * spec["rate"], spec["minimum"])
    hours = chargeable_hours(anchorage_hours)
    amount = hourly_charge * hours

    return {
        "status": "calculated",
        "category": category,
        "vessel_grt": vessel_grt,
        "anchorage_hours": anchorage_hours,
        "chargeable_hours": hours,
        "trade_type": trade_type,
        "rate_per_grt_hour": spec["rate"],
        "minimum_hourly_charge": spec["minimum"],
        "effective_hourly_charge": round(hourly_charge, 2),
        "amount": round(amount, 2),
    }


def calculate_tug_hire(
    hire_hours: float,
    trade_type: str = "coastal",
    craft_type: str = "tug_other",
) -> Dict[str, Any]:
    """
    Tug / harbour craft hire charges (SOR 2.2.5; SPM tugs 2.6).

    Tugs used for berthing, unberthing and shifting are part of the
    pilotage / shifting service and are NOT charged separately
    (2.2.5 note 6); this is only for tugs hired on request.

    craft_type:
        "tug_spm"        -> tug hire for SPM operations
        "tug_other"      -> tug hire for other than SPM operations
        "pilot_launch"   -> pilot launch hire
        "mooring_launch" -> mooring launch hire
    """

    trade_type = trade_type.lower().strip()
    craft_type = craft_type.lower().strip()

    if craft_type not in TUG_HIRE_RATES:
        return {
            "status": "rate_unavailable",
            "craft_type": craft_type,
            "message": "No tug/craft hire rate is configured for this craft type.",
            "amount": None,
        }

    rate = TUG_HIRE_RATES[craft_type][trade_type]
    hours = chargeable_hours(hire_hours)
    if craft_type == "tug_spm":
        hours = max(hours, 2)  # SOR 2.6 item 6: minimum of 2 hours
    amount = rate * hours

    return {
        "status": "calculated",
        "craft_type": craft_type,
        "hire_hours": hire_hours,
        "chargeable_hours": hours,
        "trade_type": trade_type,
        "rate_per_hour": rate,
        "amount": round(amount, 2),
    }


def calculate_shifting(
    vessel_grt: float,
    trade_type: str = "coastal",
    vessel_category: str = "ship_steamer",
    tug_used: bool = True,
) -> Dict[str, Any]:
    """
    Shifting charges for movement of a vessel within the dock basin
    at the vessel's own request (SOR 2.2.3). A 50% concession
    applies when tugs are not used for the shift (Note 4(ii)).
    """

    trade_type = trade_type.lower().strip()
    vessel_category = vessel_category.lower().strip()

    if vessel_category == "ship_steamer":
        amount = _shifting_tiered_amount(vessel_grt, trade_type)
    elif vessel_category in SHIFTING_FLAT_RATES:
        amount = SHIFTING_FLAT_RATES[vessel_category][trade_type]
    else:
        return {
            "status": "rate_unavailable",
            "vessel_category": vessel_category,
            "message": "No shifting rate is configured for this vessel category.",
            "amount": None,
        }

    if not tug_used:
        amount *= 0.5

    return {
        "status": "calculated",
        "vessel_category": vessel_category,
        "vessel_grt": vessel_grt,
        "trade_type": trade_type,
        "tug_used": tug_used,
        "amount": round(amount, 2),
    }


def _shifting_tiered_amount(vessel_grt: float, trade_type: str) -> float:
    """Tiered ship/steamer shifting charge per SOR 2.2.3."""

    if trade_type == "foreign":
        if vessel_grt <= 30000:
            return max(vessel_grt * 0.1314, 394.15)
        if vessel_grt <= 60000:
            return 3942.26 + (vessel_grt - 30000) * 0.1051
        return 7095.26 + (vessel_grt - 60000) * 0.09198

    # coastal
    if vessel_grt <= 30000:
        return max(vessel_grt * 3.5189, 10556.78)
    if vessel_grt <= 60000:
        return 105568 + (vessel_grt - 30000) * 2.8237
    return 190280 + (vessel_grt - 60000) * 2.4653


# ============================================================
# BUNKERING FACILITY — SOR 3.7
# ₹ per MT of bunkers supplied alongside berth / anchorage.
# ============================================================

BUNKERING_FACILITY_RATES = {"foreign": 45.58, "coastal": 31.73}


def calculate_bunkering_facility(quantity_mt: float, trade_type: str) -> Dict[str, Any]:
    rate = BUNKERING_FACILITY_RATES[trade_type]
    return {
        "status": "calculated",
        "quantity_mt": quantity_mt,
        "rate_per_mt": rate,
        "trade_type": trade_type,
        "amount": round(quantity_mt * rate, 2),
        "sor_reference": "3.7",
    }


# ============================================================
# BERTH / CARGO CONTEXT — where the NMPA SOR does not apply
#
# Taken from NMPA's own books (Revised Estimate 2023-24, operating
# income schedule): Berth 14 (containers) and Berth 16 (coal) are
# PPP terminals that earn NMPA a royalty, UPCL coal is booked as
# "Wharfage (Royalty)", and the SOR wharfage line for pellets reads
# "Iron Ore Pellets other than KIOCL". For those, the user pays the
# terminal operator's / agreement tariff, which is not in the SOR.
# ============================================================

PPP_BERTHS = {"14": "Berth 14 container terminal (PPP)", "16": "Berth 16 coal / bulk terminal (PPP)"}
SPM_BERTHS = {"SPM", "SBM"}


def normalise_berth(berth: Optional[str]) -> Optional[str]:
    if not berth:
        return None
    b = str(berth).upper().strip()
    if b.startswith("SPM") or b.startswith("SBM"):
        return "SPM"
    m = __import__("re").match(r"(\d+)", b)
    return m.group(1) if m else b


def cargo_exceptions(
    sor_code: Optional[str],
    berth: Optional[str],
    receiver_shipper: Optional[str],
) -> list:
    """Reasons the SOR wharfage / berth hire should NOT be billed for this call."""

    reasons = []
    b = normalise_berth(berth)
    party = (receiver_shipper or "").upper()

    if b in PPP_BERTHS:
        reasons.append({
            "scope": "cargo_and_berth",
            "code": "ppp_terminal",
            "message": (
                f"{PPP_BERTHS[b]}: cargo handling, wharfage and berth hire are billed by the "
                "terminal operator under its own tariff; NMPA earns a royalty. The NMPA SOR "
                "amount is shown for reference only and is not added to the total."
            ),
        })
    if sor_code == "B.III.i" and "KIOCL" in party:
        reasons.append({
            "scope": "cargo",
            "code": "kiocl_pellets",
            "message": (
                "SOR line B.III.i is 'Iron Ore Pellets other than KIOCL'. KIOCL pellets are "
                "charged under a separate arrangement that is not in the SOR."
            ),
        })
    if sor_code == "B.III.j" and "KIOCL" in party:
        reasons.append({
            "scope": "note",
            "code": "kiocl_iron_ore",
            "message": (
                "Check with NMPA: its books book KIOCL iron ore separately, and in 2023-24 it "
                "realised about ₹49/t on KIOCL cargo against the SOR fines rate of ₹39.74-43.16. "
                "The SOR rate is used here."
            ),
        })
    if sor_code in ("B.IV.a", "B.IV.b") and "UPCL" in party:
        reasons.append({
            "scope": "cargo",
            "code": "upcl_coal",
            "message": (
                "SOR line B.IV.a is 'Thermal Coal (other than UPCL)'. UPCL coal is booked by "
                "NMPA as wharfage royalty under a separate arrangement."
            ),
        })
    return reasons


# Working-day free periods are extended by Customs holidays and port
# non-working days inside them (SOR 1.1(xii), 3.2.1 note 1). Coastal
# bulk / break bulk gets 15 days INCLUSIVE of holidays, so no extension.
WORKING_DAY_RULES = {
    ("import", "bulk"), ("import", "break_bulk"),
    ("export", "bulk"), ("export", "break_bulk"),
    ("export", "salvaged"), ("export", "not_shipped"),
    ("transhipment", "bulk"), ("transhipment", "break_bulk"),
}


# ============================================================
# MAIN COST CALCULATOR
# ============================================================

VESSEL_COMPONENTS = ("port_dues", "pilotage", "berth_hire", "anchorage", "tug_hire", "shifting")


def calculate_total_cost(
    cargo_type: str,
    cargo_quantity_mt: float,
    trade_type: str,
    cargo_flow: str,
    vessel_type: str,
    vessel_grt: Optional[float],
    berth_hours: float,
    storage_days: float = 0,
    free_storage_days: float = 0,
    include_vessel_related_charges: bool = True,
    port_dues_vessel_category: str = "ship_steamer_spm",
    port_dues_reduction: str = "none",
    pilotage_vessel_category: str = "ship_steamer",
    anchorage_hours: float = 0,
    anchorage_category: str = "post_sailing",
    tug_hire_hours: float = 0,
    tug_hire_craft_type: str = "tug_other",
    shifting_requested: bool = False,
    shifting_vessel_category: str = "ship_steamer",
    shifting_tug_used: bool = True,
    cargo_category: str = "bulk",
    annual_volume_mt: Optional[float] = None,
    usd_inr_rate: Optional[float] = None,
    vessel_trade_type: Optional[str] = None,
    berth: Optional[str] = None,
    receiver_shipper: Optional[str] = None,
    double_banked: bool = False,
    excluded_days_in_free_period: float = 0,
    bunker_quantity_mt: float = 0,
    shifting_count: int = 1,
    sor_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main NMPA port cost calculation for one vessel call.

    Two different "trade types" exist in the SOR:
      * trade_type        — the CARGO's status (coastal / foreign), which
                            picks the wharfage rate (Chapter III).
      * vessel_trade_type — the VESSEL's status from Customs / DG Shipping
                            (SOR 1.2(i)), which picks coastal ₹ or foreign
                            US$ vessel related charges (Chapter II).
                            Defaults to trade_type.

    Cargo related:  wharfage (3.1.1) + transit storage (3.2.1)
    Vessel related: port dues (2.1.1), pilotage (2.2.1), berth hire
                    (2.3.1), and on request anchorage (2.5.2), tug hire
                    (2.2.5), shifting (2.2.3); bunkering facility (3.7).

    Vessel related charges need the vessel's GRT. Without it they are
    returned as "needs_grt" and left out of the total, never guessed.
    At an SPM the SPM tariff (2.6) is used and crude takes the SPM
    wharfage line A.I.j. At PPP berths the terminal operator bills
    cargo and berth charges, so those are shown but not totalled.
    """

    trade_type = trade_type.lower().strip()
    vessel_trade_type = (vessel_trade_type or trade_type).lower().strip()
    cargo_flow = cargo_flow.lower().strip()
    b = normalise_berth(berth)
    at_spm = b in SPM_BERTHS
    grt = vessel_grt if vessel_grt and vessel_grt > 0 else None
    notes = []

    # Small craft use their own port dues / pilotage / shifting lines.
    vt = vessel_type.lower().strip()
    if vt in PER_VESSEL_BERTH_HIRE:
        port_dues_vessel_category = "bunker_barge" if vt == "bunker_barge" else "tug_launch_sailing_barge"
        if vt == "bunker_barge":
            pilotage_vessel_category = shifting_vessel_category = "bunker_barge"
        elif grt:
            small = grt < 200
            pilotage_vessel_category = shifting_vessel_category = "barge_small" if small else "barge_large"

    # ---------------- cargo related ----------------
    if at_spm and not sor_code:
        probe = calculate_wharfage(cargo_type, 1, trade_type)
        if probe.get("sor_code") == "A.I.d":
            sor_code = "A.I.j"
            notes.append("Crude discharged at the SPM takes the SPM wharfage line A.I.j.")

    wharfage = calculate_wharfage(
        cargo_type=cargo_type,
        quantity_mt=cargo_quantity_mt,
        trade_type=trade_type,
        annual_volume_mt=annual_volume_mt,
        sor_code=sor_code,
    )
    wharfage["sor_reference"] = "3.1.1"

    storage_rule = get_free_storage_days(cargo_flow=cargo_flow, cargo_category=cargo_category)
    if storage_rule["status"] == "configured":
        free_days = storage_rule["free_storage_days"]
        if (cargo_flow, cargo_category) in WORKING_DAY_RULES and excluded_days_in_free_period > 0:
            free_days += excluded_days_in_free_period
            storage_rule["extended_by_non_working_days"] = excluded_days_in_free_period
    else:
        free_days = free_storage_days

    if wharfage["status"] == "not_applicable":
        storage = {"status": "not_applicable", "amount": None, "message": wharfage.get("message")}
    else:
        storage = calculate_transit_storage(
            wharfage_units=wharfage.get("chargeable_units") or cargo_quantity_mt,
            actual_storage_days=math.ceil(storage_days) if storage_days > 0 else 0,
            free_storage_days=free_days,
            cargo_flow=cargo_flow,
        )
    storage["free_days_rule"] = storage_rule

    breakdown = {"wharfage": wharfage, "transit_storage": storage}

    # ---------------- vessel related ----------------
    def needs_grt(label):
        return {
            "status": "needs_grt",
            "amount": None,
            "message": f"Enter the vessel's GRT to price {label}.",
        }

    if include_vessel_related_charges:
        if at_spm:
            breakdown["port_dues"] = (
                calculate_port_dues("ship_steamer_spm", grt, vessel_trade_type, port_dues_reduction)
                if grt else needs_grt("port dues")
            )
            breakdown["pilotage"] = (
                calculate_pilotage(grt, vessel_trade_type, "spm") if grt else needs_grt("SPM pilotage")
            )
            breakdown["port_dues"]["sor_reference"] = "2.6 item 1"
            breakdown["pilotage"]["sor_reference"] = "2.6 item 2"
            breakdown["berth_hire"] = {
                "status": "rate_unavailable",
                "amount": None,
                "message": "SBM/SPM stay charges are 'as per applicability' in SOR 2.6 item 9 — not published.",
                "sor_reference": "2.6 item 9",
            }
        else:
            breakdown["port_dues"] = (
                calculate_port_dues(port_dues_vessel_category, grt, vessel_trade_type, port_dues_reduction)
                if grt else needs_grt("port dues")
            )
            breakdown["port_dues"]["sor_reference"] = "2.1.1"
            breakdown["pilotage"] = (
                calculate_pilotage(grt, vessel_trade_type, pilotage_vessel_category)
                if grt or pilotage_vessel_category in PILOTAGE_FLAT_RATES else needs_grt("pilotage")
            )
            breakdown["pilotage"]["sor_reference"] = "2.2.1"
            if grt and grt <= 200 and pilotage_vessel_category == "ship_steamer":
                breakdown["pilotage"] = {
                    "status": "calculated", "amount": 0.0, "sor_reference": "2.2.1 note 3(i)",
                    "note": "Vessels up to 200 GRT are not provided pilotage and pay no pilotage fee.",
                }
            breakdown["berth_hire"] = calculate_berth_hire(
                vessel_type=vessel_type,
                vessel_grt=grt,
                berth_hours=berth_hours,
                trade_type=vessel_trade_type,
                double_banked=double_banked,
            )

        if anchorage_hours > 0:
            breakdown["anchorage"] = (
                calculate_anchorage(grt, anchorage_hours, vessel_trade_type, anchorage_category)
                if grt else needs_grt("anchorage")
            )
            breakdown["anchorage"]["sor_reference"] = "2.5.2"

        if tug_hire_hours > 0:
            breakdown["tug_hire"] = calculate_tug_hire(
                tug_hire_hours, vessel_trade_type, "tug_spm" if at_spm else tug_hire_craft_type,
            )
            breakdown["tug_hire"]["sor_reference"] = "2.6 item 7" if at_spm else "2.2.5"

        if shifting_requested:
            if grt or shifting_vessel_category in SHIFTING_FLAT_RATES:
                one = calculate_shifting(grt or 0, vessel_trade_type, shifting_vessel_category, shifting_tug_used)
                if one["status"] == "calculated" and shifting_count > 1:
                    one["amount"] = round(one["amount"] * shifting_count, 2)
                    one["shiftings"] = shifting_count
                breakdown["shifting"] = one
            else:
                breakdown["shifting"] = needs_grt("shifting")
            breakdown["shifting"]["sor_reference"] = "2.2.3"

    if bunker_quantity_mt > 0:
        breakdown["bunkering_facility"] = calculate_bunkering_facility(bunker_quantity_mt, vessel_trade_type)

    # ---------------- exceptions (PPP / KIOCL / UPCL) ----------------
    exceptions = cargo_exceptions(wharfage.get("sor_code"), berth, receiver_shipper)
    excluded = set()
    for ex in exceptions:
        if ex["scope"] in ("cargo", "cargo_and_berth"):
            excluded.update({"wharfage", "transit_storage"})
        if ex["scope"] == "cargo_and_berth":
            excluded.add("berth_hire")
    for key in excluded:
        comp = breakdown.get(key)
        if comp and comp.get("status") == "calculated":
            comp["status"] = "not_billed_by_nmpa"
            comp["reference_amount"] = comp.get("amount")
            comp["reference_currency"] = component_currency(
                key, vessel_trade_type if key in VESSEL_COMPONENTS else trade_type
            )

    # ---------------- currency ----------------
    for key, component in breakdown.items():
        component.setdefault("sor_reference", None)
        if component.get("status") == "calculated":
            apply_sor_currency(
                component,
                currency=component_currency(key, vessel_trade_type if key in VESSEL_COMPONENTS else trade_type),
                usd_inr_rate=usd_inr_rate,
            )
        elif component.get("status") == "not_billed_by_nmpa":
            component["amount"] = None

    total_known_cost = sum(
        c["amount"] for c in breakdown.values() if c.get("status") == "calculated" and c.get("amount") is not None
    )
    unconverted_usd = [k for k, c in breakdown.items() if c.get("status") == "needs_exchange_rate"]
    missing_grt = [k for k, c in breakdown.items() if c.get("status") == "needs_grt"]
    unpublished = [k for k, c in breakdown.items() if c.get("status") == "rate_unavailable"]

    complete = not (unconverted_usd or missing_grt)

    return {
        "status": "success",
        "tariff": {
            "name": TARIFF_VERSION,
            "effective_from": EFFECTIVE_FROM,
            "effective_to": EFFECTIVE_TO,
            "source": "nmpa_public_data/tariff/Indexed SOR wef 01.05.2026 (0.65).pdf",
        },
        "inputs": {
            "cargo_type": cargo_type,
            "cargo_quantity_mt": cargo_quantity_mt,
            "trade_type": trade_type,
            "vessel_trade_type": vessel_trade_type,
            "cargo_flow": cargo_flow,
            "vessel_type": vessel_type,
            "vessel_grt": grt,
            "berth": berth,
            "berth_hours": berth_hours,
            "storage_days": storage_days,
            "free_storage_days": free_days,
            "cargo_category": cargo_category,
            "annual_volume_mt": annual_volume_mt,
            "usd_inr_rate": usd_inr_rate,
            "receiver_shipper": receiver_shipper,
        },
        "breakdown": breakdown,
        "exceptions": exceptions,
        "notes": notes,
        "total_known_cost": round(total_known_cost, 2),
        # SOR 1.2(ix): grand total of each bill is rounded to the next higher rupee.
        "bill_total_rounded": math.ceil(round(total_known_cost, 2)) if total_known_cost else 0,
        "currency": "INR",
        "is_complete": complete,
        "unconverted_usd_components": unconverted_usd,
        "unconverted_usd_total": round(sum(breakdown[k]["amount_usd"] for k in unconverted_usd), 2),
        "missing_grt_components": missing_grt,
        "unpublished_components": unpublished,
        "coming_soon": coming_soon_components(),
        "important_note": (
            "Estimate from the NMPA SOR 2026-27 for the components listed. Taxes (GST) are "
            "extra (SOR 1.2(v)). Charges the SOR prints as '*' are not invented; they are "
            "listed as coming soon."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# Compatibility for the Incentive Engine: wharfage per tonne by its cargo keys, taken from the SOR 3.1.1 schedule above
# (sor_wharfage), so both engines read ONE transcription of the Scale of Rates. Each key names its SOR line code.
# ═══════════════════════════════════════════════════════════════════
WHARFAGE_SOR_CODES = {
    "pol_products": "A.I.o", "crude_spm": "A.I.j", "lpg_lng_gas": "A.IV.a", "edible_oil": "A.V.a",
    "raw_cashew": "B.I.e", "cashew_kernels": "B.I.f", "fertilizer": "B.II.a", "limestone": "B.III.g",
    "iron_ore_pellets": "B.III.i", "iron_ore_fines_lumps": "B.III.j", "bentonite_clay": "B.III.p",
    "thermal_coal": "B.IV.a", "coal_other": "B.IV.b", "pet_coke_bulk": "B.IV.c", "spices": "C.a", "fish": "C.b",
    "plant_machinery": "C.f", "steel_plates_pipes": "C.g", "bagged_cargo": "C.j", "timber_logs": "C.k",
    "personal_effects": "C.n", "vehicles": "C.o",
}


def _wharfage_rates_by_key() -> Dict[str, Dict[str, float]]:
    from backend.app.services.sor_wharfage import schedule_table
    by_code = {r["code"]: r for r in schedule_table()}
    return {k: {"coastal": float(by_code[c]["coastal"]), "foreign": float(by_code[c]["foreign"])}
            for k, c in WHARFAGE_SOR_CODES.items()}


WHARFAGE_RATES = _wharfage_rates_by_key()
