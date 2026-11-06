from fastapi import APIRouter
from backend.app.services import synthetic_data as sd

router = APIRouter()

@router.get("/kpis")
def get_kpis():
    kpis = sd.generate_kpis()
    # Overlay real ML-model output where a real model exists (rest of the KPI
    # row has no backing dataset, so it stays synthetic/illustrative).
    try:
        from backend.app.services.ml_models import predict_congestion_risk
        from backend.app.services.forecasting import get_enhanced_cargo_forecast

        congestion = predict_congestion_risk()
        kpis["congestion_index"] = round(congestion["current_risk_score"] / 10.0, 2)
        kpis["congestion_index_is_ml"] = True

        forecast = get_enhanced_cargo_forecast(horizon_months=6)
        kpis["forecast_accuracy_pct"] = forecast["summary"]["model_accuracy_pct"]
        kpis["forecast_accuracy_is_ml"] = True
    except Exception:
        pass
    return kpis

@router.get("/events")
def get_port_events():
    return {"events": sd.generate_port_events()}

@router.get("/revenue-trend")
def get_revenue_trend():
    return sd.generate_revenue_trend(30)
