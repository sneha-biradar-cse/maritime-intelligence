from fastapi import APIRouter, Query
from backend.app.services import nmpa_vessels as nmpa_v
from backend.app.services import ml_models as ml

router = APIRouter()

@router.get("/", summary="Get live vessel positions centered at New Mangalore Port (NMPA)")
def get_vessels():
    vessels = nmpa_v.get_nmpa_vessels()
    return {
        "port": "New Mangalore Port Authority (NMPA)",
        "vessels": vessels,
        "count": len(vessels)
    }

@router.get("/eta", summary="Illustrative vessel ETAs (not a real prediction — see /vessels/forecast for the real model)")
def get_eta_predictions():
    vessels = nmpa_v.get_nmpa_vessels()
    eta_data = sorted(vessels, key=lambda v: v["hours_to_arrival"])
    return {
        "eta_predictions": eta_data,
        "note": (
            "These are illustrative fleet positions, not a real prediction — no AIS/vessel-tracking "
            "data exists in this project. For a real, backtested forecast (monthly vessel call counts "
            "per commodity, not per-ship arrival time), see GET /vessels/forecast."
        ),
    }

@router.get("/congestion-alerts", summary="Get NMPA congestion alerts")
def get_congestion_alerts():
    alerts = nmpa_v.get_nmpa_congestion_alerts()
    return {"alerts": alerts, "count": len(alerts)}

@router.get("/forecast", summary="Real RandomForestRegressor forecast of monthly vessel call counts (not per-ship ETA)")
def get_vessel_call_forecast(
    horizon: int = Query(default=3, ge=1, le=12),
    commodity: str = Query(default="ALL"),
    section: str = Query(default="ALL"),
):
    return ml.forecast_vessel_calls(horizon_months=horizon, commodity=commodity, section=section)
