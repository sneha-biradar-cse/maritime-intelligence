from fastapi import APIRouter, Query
from backend.app.services import ml_models as ml

router = APIRouter()

@router.get("/events")
def get_anomaly_events():
    return {"events": ml.detect_cargo_anomalies()}

@router.get("/history")
def get_anomaly_history(days: int = Query(default=30, ge=7, le=90)):
    return {"history": ml.get_cargo_anomaly_history(days)}
