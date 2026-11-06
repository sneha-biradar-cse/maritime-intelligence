"""
NMPA Cost Engine

Calculates estimated port-related costs using the
NMPA Schedule of Rates (SOR) effective 01-05-2026 to 30-04-2027.

This first version covers:
- Wharfage
- Berth hire
- Transit storage
- Container composite box rate
- Container storage

It intentionally does NOT invent rates for tariff components
where the current SOR does not provide a numerical value.
"""

from typing import Dict, Any


# ============================================================
# NMPA SOR — 2026-27
# Effective: 01-05-2026 to 30-04-2027
# ============================================================

TARIFF_VERSION = "NMPA SOR 2026-27"
EFFECTIVE_FROM = "2026-05-01"
EFFECTIVE_TO = "2027-04-30"


# ------------------------------------------------------------
# WHARFAGE RATES — ₹ / MT
# ------------------------------------------------------------

WHARFAGE_RATES = {
    "pol_products": {
        "coastal": 96.60,
        "foreign": 96.60,
    },

    "crude_spm": {
        "coastal": 34.89,
        "foreign": 34.90,
    },

    "lpg_lng_gas": {
        "coastal": 147.61,
        "foreign": 245.57,
    },

    "edible_oil": {
        "coastal": 41.59,
        "foreign": 68.45,
    },

    "raw_cashew": {
        "coastal": 26.65,
        "foreign": 45.71,
    },

    "cashew_kernels": {
        "coastal": 40.62,
        "foreign": 68.55,
    },

    "fertilizer": {
        "coastal": 26.65,
        "foreign": 45.71,
    },

    "limestone": {
        "coastal": 26.65,
        "foreign": 45.71,
    },

    "iron_ore_pellets": {
        "coastal": 45.71,
        "foreign": 45.71,
    },

    "iron_ore_fines_lumps": {
        "coastal": 43.16,
        "foreign": 43.16,
    },

    "bentonite_clay": {
        "coastal": 15.24,
        "foreign": 25.39,
    },

    "thermal_coal": {
        "coastal": 31.73,
        "foreign": 31.73,
    },

    "coal_other": {
        "coastal": 19.02,
        "foreign": 31.73,
    },

    "pet_coke_bulk": {
        "coastal": 55.02,
        "foreign": 55.02,
    },

    "spices": {
        "coastal": 40.62,
        "foreign": 67.27,
    },

    "fish": {
        "coastal": 30.47,
        "foreign": 50.77,
    },

    "plant_machinery": {
        "coastal": 106.01,
        "foreign": 177.12,
    },

    "steel_plates_pipes": {
        "coastal": 39.35,
        "foreign": 64.75,
    },

    "bagged_cargo": {
        "coastal": 49.65,
        "foreign": 81.86,
    },

    "timber_logs": {
        "coastal": 30.47,
        "foreign": 50.76,
    },

    "personal_effects": {
        "coastal": 77.44,
        "foreign": 129.47,
    },

    "vehicles": {
        "coastal": 2364.82,
        "foreign": 3940.13,
    },
}


# ------------------------------------------------------------
# BERTH HIRE RATES
#
# ₹ / GRT / hour
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


# Minimum berth hire per hour
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
}


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
# CONTAINER STORAGE
#
# ₹ / container / day
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
# PORT DUES — SOR Chapter II, 2.1
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
# PILOTAGE — SOR Chapter II, 2.3
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
# ANCHORAGE FEES — SOR Chapter II, 2.5
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
# TUG HIRE CHARGES — SOR Chapter II, 2.4.1
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
# SHIFTING CHARGES — SOR Chapter II, 2.3 Note 4
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
) -> Dict[str, Any]:
    """
    Calculate wharfage for cargo.

    quantity_mt = cargo quantity in metric tonnes
    trade_type = coastal / foreign
    """

    cargo_type = cargo_type.lower().strip()
    trade_type = trade_type.lower().strip()

    if cargo_type not in WHARFAGE_RATES:
        return {
            "status": "rate_unavailable",
            "cargo_type": cargo_type,
            "message": (
                "No numerical wharfage rate is configured for "
                "this cargo type in the current cost engine."
            ),
            "amount": None,
        }

    rate = WHARFAGE_RATES[cargo_type][trade_type]
    amount = quantity_mt * rate

    return {
        "status": "calculated",
        "cargo_type": cargo_type,
        "quantity_mt": quantity_mt,
        "trade_type": trade_type,
        "rate_per_mt": rate,
        "amount": round(amount, 2),
    }


def calculate_berth_hire(
    vessel_type: str,
    vessel_grt: float,
    berth_hours: float,
    trade_type: str = "coastal",
) -> Dict[str, Any]:
    """
    Calculate berth hire.

    Formula:

        GRT × rate × hours

    Subject to minimum hourly berth hire.
    """

    vessel_type = vessel_type.lower().strip()
    trade_type = trade_type.lower().strip()

    if vessel_type not in BERTH_HIRE_RATES:
        vessel_type = "other"

    rate = BERTH_HIRE_RATES[vessel_type][trade_type]
    minimum = BERTH_MINIMUMS[vessel_type][trade_type]

    calculated_hourly = vessel_grt * rate
    hourly_charge = max(calculated_hourly, minimum)

    total = hourly_charge * berth_hours

    return {
        "status": "calculated",
        "vessel_type": vessel_type,
        "vessel_grt": vessel_grt,
        "berth_hours": berth_hours,
        "rate_per_grt_hour": rate,
        "minimum_hourly_charge": minimum,
        "effective_hourly_charge": round(hourly_charge, 2),
        "amount": round(total, 2),
    }
def get_free_storage_days(
    cargo_flow: str,
    cargo_category: str = "bulk",
) -> Dict[str, Any]:
    """
    Return the configured NMPA free-storage allowance.

    These are simplified application rules based on the
    current SOR wording. Working-day/calendar-day treatment
    must be handled separately when exact billing dates are used.
    """

    cargo_flow = cargo_flow.lower().strip()
    cargo_category = cargo_category.lower().strip()

    # Foreign import bulk / break bulk:
    # 7 working days after complete discharge.
    if cargo_flow == "import" and cargo_category in {
        "bulk",
        "break_bulk",
    }:
        return {
            "status": "configured",
            "cargo_flow": cargo_flow,
            "cargo_category": cargo_category,
            "free_storage_days": 7,
            "basis": "7 working days",
        }

    # Coastal bulk / break bulk:
    # 15 free days inclusive of customs/port holidays.
    if cargo_flow == "coastal" and cargo_category in {
        "bulk",
        "break_bulk",
    }:
        return {
            "status": "configured",
            "cargo_flow": cargo_flow,
            "cargo_category": cargo_category,
            "free_storage_days": 15,
            "basis": "15 calendar days including stated holidays",
        }

    # Export cargo:
    # 21 working days under the stated normal conditions.
    if cargo_flow == "export":
        return {
            "status": "configured",
            "cargo_flow": cargo_flow,
            "cargo_category": cargo_category,
            "free_storage_days": 21,
            "basis": "21 working days",
        }

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

def calculate_transit_storage(
    wharfage_units: float,
    actual_storage_days: float,
    free_storage_days: float = 0,
) -> Dict[str, Any]:
    """
    Calculate transit storage charges after the applicable
    free-storage period.

    Parameters
    ----------
    wharfage_units:
        Cargo quantity used as the chargeable wharfage unit.

    actual_storage_days:
        Total number of days cargo remains in storage.

    free_storage_days:
        Number of days allowed free of storage charges.

    The function calculates:

        chargeable days = actual storage days - free days

    Storage tariff:
        First 7 chargeable days     -> ₹5.083 / unit / day
        Next 7 chargeable days      -> ₹8.884 / unit / day
        Remaining chargeable days   -> ₹12.696 / unit / day
    """

    if actual_storage_days < 0:
        raise ValueError("actual_storage_days cannot be negative")

    if free_storage_days < 0:
        raise ValueError("free_storage_days cannot be negative")

    chargeable_days = max(
        0,
        actual_storage_days - free_storage_days
    )

    if chargeable_days == 0:
        return {
            "status": "calculated",
            "wharfage_units": wharfage_units,
            "actual_storage_days": actual_storage_days,
            "free_storage_days": free_storage_days,
            "chargeable_days": 0,
            "amount": 0.0,
        }

    remaining_days = chargeable_days
    amount = 0.0

    # First 7 chargeable days
    week_1_days = min(remaining_days, 7)

    amount += (
        week_1_days
        * TRANSIT_STORAGE_RATES["week_1"]
        * wharfage_units
    )

    remaining_days -= week_1_days

    # Next 7 chargeable days
    if remaining_days > 0:

        week_2_days = min(remaining_days, 7)

        amount += (
            week_2_days
            * TRANSIT_STORAGE_RATES["week_2"]
            * wharfage_units
        )

        remaining_days -= week_2_days

    # Beyond 14 chargeable days
    if remaining_days > 0:

        amount += (
            remaining_days
            * TRANSIT_STORAGE_RATES["after_week_2"]
            * wharfage_units
        )

    return {
        "status": "calculated",
        "wharfage_units": wharfage_units,
        "actual_storage_days": actual_storage_days,
        "free_storage_days": free_storage_days,
        "chargeable_days": chargeable_days,
        "amount": round(amount, 2),
    }


def calculate_container_cost(
    container_size: str,
    container_status: str,
    number_of_containers: int,
    trade_type: str = "coastal",
    storage_days: float = 0,
) -> Dict[str, Any]:
    """
    Calculate container composite box cost + storage.

    IMPORTANT:
    The composite box rate already includes wharfage and
    basic container handling services.
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

    total = box_cost + storage_cost

    return {
        "status": "calculated",
        "container_size": container_size,
        "container_status": container_status,
        "number_of_containers": number_of_containers,
        "trade_type": trade_type,
        "box_rate": box_rate,
        "box_cost": round(box_cost, 2),
        "storage_rate_per_container_day": storage_rate,
        "storage_days": storage_days,
        "storage_cost": round(storage_cost, 2),
        "total": round(total, 2),
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
        "ballast_no_passengers"   -> 75% of the rate (SOR 2.1 Note 1)
        "no_cargo_no_passenger"   -> 50% of the rate (SOR 2.1 Note 2)
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
    """Tiered ship/steamer pilotage per SOR 2.3(i)."""

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
        "ship_steamer" -> tiered by GRT band (SOR 2.3(i))
        "spm"          -> flat rate per GRT (SOR 2.3(i)(d))
        "barge_small"  -> flat per-vessel rate, GRT < 200 (SOR 2.3(ii)(a))
        "barge_large"  -> flat per-vessel rate, GRT >= 200 (SOR 2.3(ii)(b))
        "bunker_barge" -> flat per-vessel rate, first entry only (SOR 2.3(iii)(a))
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
    Anchorage fees (SOR 2.5).

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
    amount = hourly_charge * anchorage_hours

    return {
        "status": "calculated",
        "category": category,
        "vessel_grt": vessel_grt,
        "anchorage_hours": anchorage_hours,
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
    Tug / harbour craft hire charges (SOR 2.4.1).

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
    amount = rate * hire_hours

    return {
        "status": "calculated",
        "craft_type": craft_type,
        "hire_hours": hire_hours,
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
    at the vessel's own request (SOR 2.3 Note 4). A 50% concession
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
    """Tiered ship/steamer shifting charge per SOR 2.3 Note 4(i)."""

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
# MAIN COST CALCULATOR
# ============================================================

def calculate_total_cost(
    cargo_type: str,
    cargo_quantity_mt: float,
    trade_type: str,
    cargo_flow: str,
    vessel_type: str,
    vessel_grt: float,
    berth_hours: float,
    storage_days: float = 0,
    free_storage_days: float = 0,
    include_vessel_related_charges: bool = False,
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
) -> Dict[str, Any]:

    """
    Main NMPA port cost calculation.

    Cargo-side components (always calculated):

        Wharfage
        + Berth Hire
        + Transit Storage

    Vessel-related charges (SOR Chapter II) are calculated only
    when include_vessel_related_charges=True, since they depend
    on vessel-visit details (port dues category, pilotage,
    anchorage time, shifting) that a pure cargo costing request
    may not have. Passing anchorage_hours > 0 or
    shifting_requested=True adds those components even if
    include_vessel_related_charges is left False:

        + Port Dues
        + Pilotage
        + Anchorage Fees   (only if anchorage_hours > 0)
        + Tug Hire         (only if tug_hire_hours > 0)
        + Shifting         (only if shifting_requested=True)

    Some SOR components are intentionally excluded where
    numerical rates are not available in the current SOR.
    """

    wharfage = calculate_wharfage(
        cargo_type=cargo_type,
        quantity_mt=cargo_quantity_mt,
        trade_type=trade_type,
    )

    berth_hire = calculate_berth_hire(
        vessel_type=vessel_type,
        vessel_grt=vessel_grt,
        berth_hours=berth_hours,
        trade_type=trade_type,
    )

    storage_rule = get_free_storage_days(
    cargo_flow=cargo_flow,
    cargo_category="bulk",

)

    if storage_rule["status"] == "configured":
        automatic_free_storage_days = storage_rule["free_storage_days"]
    else:
        automatic_free_storage_days = free_storage_days

    storage = calculate_transit_storage(
        wharfage_units=cargo_quantity_mt,
        actual_storage_days=storage_days,
        free_storage_days=automatic_free_storage_days,
)

    known_components = []
    breakdown = {
        "wharfage": wharfage,
        "berth_hire": berth_hire,
        "transit_storage": storage,
    }

    if wharfage["status"] == "calculated":
        known_components.append(wharfage["amount"])

    if berth_hire["status"] == "calculated":
        known_components.append(berth_hire["amount"])

    if storage["status"] == "calculated":
        known_components.append(storage["amount"])

    # --------------------------------------------------------
    # Vessel-related charges (SOR Chapter II) — optional
    # --------------------------------------------------------

    if include_vessel_related_charges:
        port_dues = calculate_port_dues(
            vessel_category=port_dues_vessel_category,
            vessel_grt=vessel_grt,
            trade_type=trade_type,
            reduction=port_dues_reduction,
        )
        breakdown["port_dues"] = port_dues
        if port_dues["status"] == "calculated":
            known_components.append(port_dues["amount"])

        pilotage = calculate_pilotage(
            vessel_grt=vessel_grt,
            trade_type=trade_type,
            vessel_category=pilotage_vessel_category,
        )
        breakdown["pilotage"] = pilotage
        if pilotage["status"] == "calculated":
            known_components.append(pilotage["amount"])

    if anchorage_hours > 0:
        anchorage = calculate_anchorage(
            vessel_grt=vessel_grt,
            anchorage_hours=anchorage_hours,
            trade_type=trade_type,
            category=anchorage_category,
        )
        breakdown["anchorage"] = anchorage
        if anchorage["status"] == "calculated":
            known_components.append(anchorage["amount"])

    if tug_hire_hours > 0:
        tug_hire = calculate_tug_hire(
            hire_hours=tug_hire_hours,
            trade_type=trade_type,
            craft_type=tug_hire_craft_type,
        )
        breakdown["tug_hire"] = tug_hire
        if tug_hire["status"] == "calculated":
            known_components.append(tug_hire["amount"])

    if shifting_requested:
        shifting = calculate_shifting(
            vessel_grt=vessel_grt,
            trade_type=trade_type,
            vessel_category=shifting_vessel_category,
            tug_used=shifting_tug_used,
        )
        breakdown["shifting"] = shifting
        if shifting["status"] == "calculated":
            known_components.append(shifting["amount"])

    total_known_cost = sum(known_components)

    return {
        "status": "success",

        "tariff": {
            "name": TARIFF_VERSION,
            "effective_from": EFFECTIVE_FROM,
            "effective_to": EFFECTIVE_TO,
        },

        "inputs": {
            "cargo_type": cargo_type,
            "cargo_quantity_mt": cargo_quantity_mt,
            "trade_type": trade_type,
            "cargo_flow": cargo_flow,
            "vessel_type": vessel_type,
            "vessel_grt": vessel_grt,
            "berth_hours": berth_hours,
            "storage_days": storage_days,
            "free_storage_days": automatic_free_storage_days,
        },

        "breakdown": breakdown,

        "total_known_cost": round(total_known_cost, 2),

        "currency": "INR",

        "important_note": (
            "This is an estimated cost based on configured "
            "NMPA SOR components. It is not a complete final invoice. "
            "Components without numerical rates in the current SOR "
            "are not invented or included."
        ),
    }