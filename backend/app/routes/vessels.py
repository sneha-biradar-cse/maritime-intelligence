from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.services import ml_models as ml
from backend.app.services import nmpa_vessels as nmpa_v
from backend.app.services import vi_features as vi
from backend.app.services import vi_port_calls as vi_calls

router = APIRouter()

AS_OF = Query(default=None, description="Replay the tab as of an earlier report date (YYYY-MM-DD). Default: latest report.")


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Vessel Intelligence — real data (NMPA Daily Vessel Position archive +
# official monthly Operational Performance report). See
# PROJECT_DOCUMENTATION/27_VESSEL_INTELLIGENCE_IMPLEMENTATION.md
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/intel/overview", summary="Vessel Intelligence headline: board summary, alerts, model cards (real data)")
def intel_overview(as_of: Optional[date] = AS_OF):
    return _guard(vi.overview, as_of)


@router.get("/intel/board", summary="F1 Port Call Board — expected / waiting / alongside as of a Daily Vessel Position report")
def intel_board(as_of: Optional[date] = AS_OF):
    return _guard(vi.port_call_board, as_of)


@router.get("/intel/arrivals", summary="F2 Arrival outlook — next N days with ETA reliability bands")
def intel_arrivals(as_of: Optional[date] = AS_OF, days: int = Query(default=7, ge=1, le=14)):
    return _guard(vi.arrival_outlook, as_of, days)


@router.get("/intel/eta-accuracy", summary="F2 Declared-ETA accuracy and bias-correction backtest")
def intel_eta_accuracy(as_of: Optional[date] = AS_OF):
    return _guard(vi.eta_accuracy, as_of)


@router.get("/intel/departure-backtest", summary="F3 Departure-forecast backtest (NMPA ETD vs balance÷rate vs typical stay)")
def intel_departure_backtest(as_of: Optional[date] = AS_OF):
    return _guard(vi.completion_backtest, as_of)


@router.get("/intel/berth-plan", summary="F4 Berth plan — NMPA programme + rule-based queue forecast and conflicts")
def intel_berth_plan(as_of: Optional[date] = AS_OF, horizon_h: float = Query(default=72, ge=12, le=168)):
    return _guard(vi.berth_plan, as_of, horizon_h)


@router.get("/intel/wait-model", summary="F5 Pre-berthing wait model card (held-out backtest vs base rate)")
def intel_wait_model():
    return vi.wait_model()


@router.get("/intel/berthing-fit", summary="F6 Draft / LOA fit of expected vessels against their preferred berths")
def intel_berthing_fit(as_of: Optional[date] = AS_OF):
    return _guard(vi.berthing_fit, as_of)


@router.get("/intel/performance", summary="F8 DVP-derived KPIs reconciled with NMPA's official monthly Operational Performance report")
def intel_performance(as_of: Optional[date] = AS_OF):
    return _guard(vi.performance, as_of)


@router.get("/intel/waiting", summary="F9 Waiting analytics by month, reason, berth and receiver")
def intel_waiting(as_of: Optional[date] = AS_OF, months: int = Query(default=12, ge=1, le=60)):
    return _guard(vi.waiting_analytics, as_of, months)


@router.get("/intel/data-quality", summary="Archive coverage, linking quality, reason/cargo mapping checks")
def intel_data_quality():
    return vi.data_quality()


@router.get("/intel/calls", summary="Search stitched port calls (vessel, cargo or receiver text)")
def intel_calls(q: str = "", status: Optional[str] = None, limit: int = Query(default=50, ge=1, le=500)):
    return {"calls": vi.search_calls(q, status, limit)}


@router.get("/intel/calls/{call_id}", summary="One port call with every source row and movement used to build it")
def intel_call(call_id: str):
    c = vi.call_detail(call_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"No port call {call_id}")
    return c


@router.get("/intel/report-dates", summary="Report dates available for as-of replay")
def intel_report_dates():
    arch = vi_calls.load_archive()
    return {"dates": [d.isoformat() for d in arch.dates], "latest": arch.last.isoformat() if arch.last else None}


@router.post("/intel/refresh", summary="Drop caches so newly parsed reports / reference edits are picked up")
def intel_refresh():
    vi_calls.clear_caches()
    for fn in (vi._index, vi._rate_history, vi._stay_history, vi._completion_points, vi._offset, vi.method_ranking,
               vi._median_stay, vi._median_rate, vi._eta_accuracy, vi._wait_dataset, vi._wait_model, vi._programme_index):
        fn.cache_clear()
    from backend.app.services import vi_reference, vi_official_kpis
    vi_reference.reference.cache_clear()
    vi_reference._reason_rules.cache_clear()
    vi_reference.classify_cargo.cache_clear()
    vi_reference.permissible_drafts.cache_clear()
    vi_reference.tide_table.cache_clear()
    vi_official_kpis._load.cache_clear()
    return {"status": "caches cleared", "latest_report": vi_calls.load_archive().last}


# ──────────────────────────────────────────────────────────────────────────────
# Legacy endpoints (kept for the Executive tab and older clients)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/", summary="[DEMO] Illustrative fleet positions (no AIS) — use /vessels/intel/board for real data")
def get_vessels():
    vessels = nmpa_v.get_nmpa_vessels()
    return {
        "port": "New Mangalore Port Authority (NMPA)",
        "vessels": vessels,
        "count": len(vessels),
        "data_status": "DEMO — scripted fleet, not AIS. Real vessel data: GET /vessels/intel/board",
    }


@router.get("/eta", summary="[DEMO] Illustrative vessel ETAs — real ETAs: /vessels/intel/arrivals")
def get_eta_predictions():
    vessels = nmpa_v.get_nmpa_vessels()
    eta_data = sorted(vessels, key=lambda v: v["hours_to_arrival"])
    return {
        "eta_predictions": eta_data,
        "note": "Illustrative fleet positions, not a prediction. Real declared ETAs with reliability bands: GET /vessels/intel/arrivals.",
    }


@router.get("/congestion-alerts", summary="[DEMO] Scripted congestion alerts — real alerts: /vessels/intel/board")
def get_congestion_alerts():
    alerts = nmpa_v.get_nmpa_congestion_alerts()
    return {"alerts": alerts, "count": len(alerts),
            "data_status": "DEMO — real alerts (from NMPA anchorage reasons): GET /vessels/intel/board"}


@router.get("/forecast", summary="Real RandomForestRegressor forecast of monthly vessel call counts (not per-ship ETA)")
def get_vessel_call_forecast(
    horizon: int = Query(default=3, ge=1, le=12),
    commodity: str = Query(default="ALL"),
    section: str = Query(default="ALL"),
):
    return ml.forecast_vessel_calls(horizon_months=horizon, commodity=commodity, section=section)
