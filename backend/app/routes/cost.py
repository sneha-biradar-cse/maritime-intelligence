from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.cost_engine import (
    calculate_total_cost,
    WHARFAGE_RATES,
    BERTH_HIRE_RATES,
)


router = APIRouter()


# ============================================================
# VALID VALUES
# ============================================================

VALID_TRADE_TYPES = {
    "coastal",
    "foreign",
}

VALID_CARGO_FLOWS = {
    "import",
    "export",
    "coastal",
}

VALID_VESSEL_TYPES = set(BERTH_HIRE_RATES.keys())


# ============================================================
# REQUEST MODEL
# ============================================================

class CostCalculationRequest(BaseModel):

    cargo_type: str = Field(
        ...,
        description="Cargo type configured in NMPA tariff"
    )

    cargo_quantity_mt: float = Field(
        ...,
        gt=0,
        description="Cargo quantity in metric tonnes"
    )

    trade_type: str = Field(
        ...,
        description="Trade type: coastal or foreign"
    )

    cargo_flow: str = Field(
        ...,
        description="Cargo flow: import, export, or coastal"
    )

    vessel_type: str = Field(
        ...,
        description="Vessel category"
    )

    vessel_grt: float = Field(
        ...,
        gt=0,
        description="Vessel Gross Registered Tonnage"
    )

    berth_hours: float = Field(
        ...,
        gt=0,
        description="Vessel berth occupation time in hours"
    )

    storage_days: float = Field(
        0,
        ge=0,
        description="Total cargo storage duration in days"
    )


# ============================================================
# COST CALCULATION
# ============================================================

@router.post("/calculate")
def calculate_cost(request: CostCalculationRequest):

    # --------------------------------------------------------
    # Normalize text inputs
    # --------------------------------------------------------

    cargo_type = request.cargo_type.lower().strip()
    trade_type = request.trade_type.lower().strip()
    cargo_flow = request.cargo_flow.lower().strip()
    vessel_type = request.vessel_type.lower().strip()


    # --------------------------------------------------------
    # Validate cargo type
    # --------------------------------------------------------

    if cargo_type not in WHARFAGE_RATES:

        supported_cargo = sorted(WHARFAGE_RATES.keys())

        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid cargo_type",
                "received": cargo_type,
                "supported_values": supported_cargo,
            },
        )


    # --------------------------------------------------------
    # Validate trade type
    # --------------------------------------------------------

    if trade_type not in VALID_TRADE_TYPES:

        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid trade_type",
                "received": trade_type,
                "supported_values": sorted(VALID_TRADE_TYPES),
            },
        )


    # --------------------------------------------------------
    # Validate cargo flow
    # --------------------------------------------------------

    if cargo_flow not in VALID_CARGO_FLOWS:

        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid cargo_flow",
                "received": cargo_flow,
                "supported_values": sorted(VALID_CARGO_FLOWS),
            },
        )


    # --------------------------------------------------------
    # Validate vessel type
    # --------------------------------------------------------

    if vessel_type not in VALID_VESSEL_TYPES:

        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid vessel_type",
                "received": vessel_type,
                "supported_values": sorted(VALID_VESSEL_TYPES),
            },
        )


    # --------------------------------------------------------
    # Validate trade-flow combination
    # --------------------------------------------------------

    if cargo_flow == "coastal" and trade_type != "coastal":

        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid trade/cargo-flow combination",
                "message": (
                    "A coastal cargo flow must use trade_type='coastal'."
                ),
            },
        )


    if cargo_flow in {"import", "export"} and trade_type != "foreign":

        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid trade/cargo-flow combination",
                "message": (
                    "Import/export cargo flow must use "
                    "trade_type='foreign'."
                ),
            },
        )


    # --------------------------------------------------------
    # Calculate cost
    # --------------------------------------------------------

    try:

        result = calculate_total_cost(
            cargo_type=cargo_type,
            cargo_quantity_mt=request.cargo_quantity_mt,
            trade_type=trade_type,
            cargo_flow=cargo_flow,
            vessel_type=vessel_type,
            vessel_grt=request.vessel_grt,
            berth_hours=request.berth_hours,
            storage_days=request.storage_days,
        )

        return result


    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )


    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Cost calculation failed: {str(exc)}"
        )