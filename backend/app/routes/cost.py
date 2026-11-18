from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services.cost_engine import (
    BERTH_HIRE_NOT_PUBLISHED,
    BERTH_HIRE_RATES,
    PER_VESSEL_BERTH_HIRE,
    TARIFF_VERSION,
    VALID_STORAGE_CATEGORIES,
    calculate_total_cost,
    coming_soon_components,
)
from backend.app.services.historical_calls import (
    build_calls,
    calculator_inputs,
    calls_summary,
    price_call_wharfage,
)
from backend.app.services.sor_wharfage import (
    FREE_OF_WHARFAGE,
    SCHEDULE_REFERENCE,
    match_commodity,
    schedule_table,
)
from backend.app.services.tariff_validation import full_report


router = APIRouter()


# ============================================================
# VALID VALUES
# ============================================================

VALID_TRADE_TYPES = {"coastal", "foreign"}

VALID_CARGO_FLOWS = {"import", "export", "coastal", "transhipment"}

VALID_VESSEL_TYPES = set(BERTH_HIRE_RATES) | set(PER_VESSEL_BERTH_HIRE) | set(BERTH_HIRE_NOT_PUBLISHED)


# ============================================================
# REQUEST MODEL
# ============================================================

class CostCalculationRequest(BaseModel):

    cargo_type: str = Field(
        ...,
        description=(
            "Commodity name or NMPA code as in the vessel reports (e.g. 'IOF(D)', "
            "'Iron ore fines'), legacy key (e.g. 'pol_products') or SOR code (e.g. 'B.III.j')"
        ),
    )
    cargo_quantity_mt: float = Field(0, ge=0, description="Cargo quantity in the SOR unit (MT for most cargo)")
    trade_type: str = Field(..., description="CARGO status: coastal or foreign (picks the wharfage rate)")
    vessel_trade_type: Optional[str] = Field(
        None, description="VESSEL status from Customs / DG Shipping: coastal or foreign. Defaults to trade_type."
    )
    cargo_flow: str = Field(..., description="import, export, coastal or transhipment")
    vessel_type: str = Field(..., description="Berth-hire class (SOR 2.3.1)")
    vessel_grt: Optional[float] = Field(
        None, ge=0, description="GRT from the International Tonnage Certificate. Needed for vessel related charges."
    )
    berth: Optional[str] = Field(None, description="Berth number, or 'SPM'")
    berth_hours: float = Field(0, ge=0, description="All fast to all lines cast off, in hours")
    storage_days: float = Field(0, ge=0, description="Days in transit storage, counted from the day after complete discharge")
    excluded_days_in_free_period: float = Field(
        0, ge=0, description="Customs holidays / port non-working days inside the free period (extend it)"
    )
    cargo_category: str = Field("bulk", description="bulk, break_bulk, salvaged or not_shipped")
    annual_volume_mt: Optional[float] = Field(None, ge=0, description="Annual volume, used only for the cement band")
    usd_inr_rate: Optional[float] = Field(
        None, gt=0, description="RBI reference USD/INR on the vessel's entry day (foreign vessel charges are in US$)"
    )
    receiver_shipper: Optional[str] = Field(None, description="Receiver / shipper, used for KIOCL and UPCL exceptions")
    include_vessel_related_charges: bool = True
    port_dues_reduction: str = Field("none", description="none, ballast_no_passengers or no_cargo_no_passenger")
    double_banked: bool = False
    anchorage_hours: float = Field(0, ge=0, description="Anchorage after sailing out from berth (pre-berthing is free)")
    tug_hire_hours: float = Field(0, ge=0, description="Tugs hired on request only; berthing tugs are inside pilotage")
    shifting_count: int = Field(0, ge=0, description="Shiftings at the vessel's own request")
    shifting_tug_used: bool = True
    bunker_quantity_mt: float = Field(0, ge=0, description="Bunkers supplied alongside berth / anchorage (SOR 3.7)")
    sor_code: Optional[str] = Field(None, description="Force a specific SOR wharfage line")


# ============================================================
# SOR REFERENCE DATA
# ============================================================

@router.get("/commodities")
def list_commodities():
    """Full SOR 3.1.1 wharfage schedule, one row per commodity line."""
    return {
        "tariff": TARIFF_VERSION,
        "reference": SCHEDULE_REFERENCE,
        "commodities": schedule_table(),
        "free_of_wharfage": FREE_OF_WHARFAGE,
    }


@router.get("/match")
def match_commodity_name(name: str):
    """Show which SOR wharfage line a commodity name maps to."""
    return match_commodity(name)


@router.get("/coming-soon")
def list_coming_soon():
    """SOR components without published numerical rates yet."""
    return {"tariff": TARIFF_VERSION, "components": coming_soon_components()}


# ============================================================
# REAL PAST CALLS (NMPA Daily Vessel Position reports)
# ============================================================

def _compact(call):
    return {
        "id": call["id"],
        "vessel": call["vessel"],
        "berthing_date": call["berthing_date"],
        "berth": call["berth"],
        "cargo_raw": call["cargo_raw"],
        "cargo_flow": call["cargo_flow"],
        "vessel_trade_type": call["vessel_trade_type"],
        "quantity": call["quantity"],
        "berth_hours": call["berth_hours"],
        "berth_hours_confidence": call["berth_hours_confidence"],
        "receiver_shipper": call["receiver_shipper"],
        "sor_code": call["sor_match"]["code"],
        "match_method": call["sor_match"]["method"],
    }


@router.get("/past-calls")
def list_past_calls(
    q: str = Query("", description="Filter by vessel, cargo, berth or receiver"),
    cargo_only: bool = Query(True, description="Only calls with a cargo quantity and an SOR wharfage line"),
    limit: int = Query(300, ge=1, le=2000),
):
    """Real vessel calls at NMPA, newest first."""
    calls = build_calls()
    if cargo_only:
        calls = [c for c in calls if c["quantity"] and c["sor_match"]["code"]]
    if q:
        ql = q.lower()
        calls = [
            c for c in calls
            if ql in " ".join(str(c.get(k) or "") for k in ("vessel", "cargo_raw", "berth", "receiver_shipper", "berthing_date")).lower()
        ]
    return {
        "summary": calls_summary(),
        "count": len(calls),
        "calls": [_compact(c) for c in calls[:limit]],
        "source": "NMPA Daily Vessel Position reports (data/daily_vessel_position_parsed) + data/vessel_stays.json",
    }


@router.get("/past-calls/{call_id}")
def get_past_call(call_id: str):
    """One real call with the calculator inputs it implies and its wharfage at SOR 2026-27."""
    for call in build_calls():
        if call["id"] == call_id:
            return {
                "call": call,
                "calculator_inputs": calculator_inputs(call),
                "wharfage_at_sor_2026": price_call_wharfage(call),
                "missing": [
                    "vessel_grt — not published in NMPA's daily reports; take it from the vessel's "
                    "International Tonnage Certificate to price port dues, pilotage and berth hire",
                ],
            }
    raise HTTPException(status_code=404, detail={"error": "Unknown call id", "received": call_id})


# ============================================================
# VALIDATION AGAINST PAST DATA
# ============================================================

@router.get("/validation")
def tariff_validation():
    """SOR 2026-27 vs SOR 2022, vs NMPA's 2023-24 income, and per-call tonnage vs traffic statement."""
    return full_report()


# ============================================================
# COST CALCULATION
# ============================================================

def _bad(error, **extra):
    raise HTTPException(status_code=400, detail={"error": error, **extra})


@router.post("/calculate")
def calculate_cost(request: CostCalculationRequest):

    cargo_type = request.cargo_type.strip()
    trade_type = request.trade_type.lower().strip()
    vessel_trade_type = (request.vessel_trade_type or trade_type).lower().strip()
    cargo_flow = request.cargo_flow.lower().strip()
    vessel_type = request.vessel_type.lower().strip()
    cargo_category = request.cargo_category.lower().strip()

    if not cargo_type:
        _bad("cargo_type is required")

    cargo_match = match_commodity(cargo_type)
    if cargo_match["method"] in ("container", "aggregate"):
        _bad("cargo_type cannot be priced by wharfage", received=request.cargo_type, message=cargo_match["message"])

    if cargo_match["method"] != "non_cargo" and not request.cargo_quantity_mt:
        _bad("cargo_quantity_mt must be greater than 0 for cargo", received=request.cargo_quantity_mt)

    if cargo_category not in VALID_STORAGE_CATEGORIES:
        _bad("Invalid cargo_category", received=cargo_category, supported_values=sorted(VALID_STORAGE_CATEGORIES))

    for name, value in (("trade_type", trade_type), ("vessel_trade_type", vessel_trade_type)):
        if value not in VALID_TRADE_TYPES:
            _bad(f"Invalid {name}", received=value, supported_values=sorted(VALID_TRADE_TYPES))

    if cargo_flow not in VALID_CARGO_FLOWS:
        _bad("Invalid cargo_flow", received=cargo_flow, supported_values=sorted(VALID_CARGO_FLOWS))

    if vessel_type not in VALID_VESSEL_TYPES:
        _bad("Invalid vessel_type", received=vessel_type, supported_values=sorted(VALID_VESSEL_TYPES))

    if cargo_flow == "coastal" and trade_type != "coastal":
        _bad("Invalid trade/cargo-flow combination", message="A coastal cargo flow must use trade_type='coastal'.")

    if cargo_flow in {"import", "export"} and trade_type != "foreign":
        _bad("Invalid trade/cargo-flow combination", message="Import/export cargo flow must use trade_type='foreign'.")

    try:
        return calculate_total_cost(
            cargo_type=cargo_type,
            cargo_quantity_mt=request.cargo_quantity_mt,
            trade_type=trade_type,
            vessel_trade_type=vessel_trade_type,
            cargo_flow=cargo_flow,
            vessel_type=vessel_type,
            vessel_grt=request.vessel_grt,
            berth=request.berth,
            berth_hours=request.berth_hours,
            storage_days=request.storage_days,
            excluded_days_in_free_period=request.excluded_days_in_free_period,
            cargo_category=cargo_category,
            annual_volume_mt=request.annual_volume_mt,
            usd_inr_rate=request.usd_inr_rate,
            receiver_shipper=request.receiver_shipper,
            include_vessel_related_charges=request.include_vessel_related_charges,
            port_dues_reduction=request.port_dues_reduction,
            double_banked=request.double_banked,
            anchorage_hours=request.anchorage_hours,
            tug_hire_hours=request.tug_hire_hours,
            shifting_requested=request.shifting_count > 0,
            shifting_count=max(request.shifting_count, 1),
            shifting_tug_used=request.shifting_tug_used,
            bunker_quantity_mt=request.bunker_quantity_mt,
            sor_code=request.sor_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cost calculation failed: {exc}")
