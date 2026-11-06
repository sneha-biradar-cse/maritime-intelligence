from typing import Literal

from fastapi import Depends, APIRouter, Body, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from backend.app.services import auth
from backend.app.services import trade_benchmark as tb
from backend.app.services import trade_brief_pdf as tbp
from backend.app.services import trade_containers as tco
from backend.app.services import trade_feedback as tfb
from backend.app.services import trade_freshness as tfr
from backend.app.services import trade_customers as tcu
from backend.app.services import trade_forecast as tf
from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_lines as tln
from backend.app.services import trade_market as tmk
from backend.app.services import trade_lookahead as tla
from backend.app.services import trade_patterns as tpt
from backend.app.services import trade_performance as tp
from backend.app.services import trade_split as ts
from backend.app.services import trade_target as tt

router = APIRouter()

# Every endpoint below is computed from real NMPA data in data/. Nothing is simulated.

@router.get("/summary", summary="Real inbound vs outbound cargo summary (latest month, last 12 months, momentum)")
def get_trade_summary():
    return ti.get_trade_summary()


@router.get("/flows", summary="Real monthly inbound/outbound cargo series with EMA lines")
def get_trade_flows(months: int = Query(default=36, ge=3, le=120, description="How many months to return")):
    return ti.get_monthly_flows(months)


@router.get("/commodities", summary="Real per-cargo YoY, share and momentum signal")
def get_trade_commodities(
    direction: Literal["all", "inbound", "outbound"] = Query(default="all"),
):
    return ti.get_commodity_flows(direction)


@router.get("/alerts", summary="Real plain-language alerts (sharp falls, surges, irregular cargos)")
def get_trade_alerts():
    return ti.get_trade_alerts()


@router.get("/overseas-coastal", summary="Real overseas vs coastal cargo split for the whole port")
def get_trade_overseas_coastal():
    return ti.get_overseas_coastal()


@router.get("/forecast", summary="Honest 1-3 month forecast with a typical range, back-tested against a 12-month average")
def get_trade_forecast(horizon: int = Query(default=3, ge=1, le=3, description="Months ahead")):
    return tf.get_trade_forecast(horizon)


@router.get("/cargo-split", summary="ESTIMATE of foreign vs coastal ships per cargo, from NMPA daily vessel reports, checked against Ministry totals")
def get_trade_cargo_split():
    return ts.get_cargo_split()


@router.get("/brief", summary="Key findings in plain language, plus where each number comes from")
def get_trade_brief():
    return ti.get_trade_brief()


@router.get("/waiting", summary="Why ships wait: reasons, cargo, customers (real NMPA daily vessel reports)")
def get_trade_waiting():
    from backend.app.services import trade_waiting as tw
    return tw.get_waiting_analysis()


@router.get("/commodity", summary="Real monthly inbound/outbound series for one cargo")
def get_trade_commodity(
    name: str = Query(..., min_length=1, description="Cargo name, e.g. 'IRON ORE' or 'CONTAINER (JSW)'"),
    months: int = Query(default=36, ge=3, le=120),
):
    detail = ti.get_commodity_detail(name, months)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown cargo '{name}'. See /trade/commodities for valid names.")
    return detail


@router.get("/customers", summary="Customer watch: who brings the cargo, growing or shrinking, and the waiting they account for (NMPA daily vessel reports)")
def get_trade_customers():
    return tcu.get_customer_watch()


@router.get("/customer", summary="One customer: monthly calls and tonnes, cargo mix, recent ships, waiting, ships due")
def get_trade_customer(name: str = Query(..., min_length=1, description="Customer name as listed by /trade/customers, e.g. 'KIOCL'")):
    detail = tcu.get_customer_detail(name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown customer '{name}'. See /trade/customers for valid names.")
    return detail


@router.get("/target", summary="Annual cargo target tracker: done so far, monthly pace needed, year-end projections")
def get_trade_target():
    return tt.get_target_tracker()


@router.get("/benchmark", summary="New Mangalore against the other major ports (Ministry monthly report, Table-1)")
def get_trade_benchmark():
    return tb.get_benchmark()


@router.get("/performance", summary="NMPA official Traffic & Performance figures, and the customers behind liquid-bulk delay")
def get_trade_performance():
    return tp.get_official_performance()


@router.get("/containers", summary="Container cargo by commodity (NMPA Statement II): imports and exports in TEUs")
def get_trade_containers():
    return tco.get_container_trade()


@router.get("/next-7-days", summary="Ships due in the next 7 days, berth outlook, and ships waiting now (latest NMPA daily report)")
def get_trade_next_7_days():
    return tla.get_lookahead()


@router.get("/target-by-cargo", summary="This financial year so far against the same months last year, by cargo")
def get_trade_target_by_cargo():
    return tt.get_target_by_cargo()


@router.get("/freshness", summary="Latest month or day held for each trade data source")
def get_trade_freshness():
    return tfr.get_freshness()


@router.get("/customer-names.csv", summary="Customer spellings and how they are merged - for NMPA to confirm",
            response_class=PlainTextResponse)
def get_customer_names_csv():
    return PlainTextResponse(tfr.customer_names_csv(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=nmpa_customer_names_to_confirm.csv"})


@router.get("/brief.pdf", summary="One-page monthly trade brief (PDF)")
def get_trade_brief_pdf():
    return Response(tbp.build_monthly_brief_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=nmpa_trade_brief.pdf"})


@router.get("/seasonality", summary="Seasonal pattern of one cargo: each financial year month by month, and its seasonal index")
def get_trade_seasonality(name: str = Query(..., min_length=1)):
    r = tpt.get_seasonality(name)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Unknown cargo '{name}'. See /trade/commodities for names.")
    return r


@router.get("/cargo-mix", summary="Each cargo's tonnes and share of the port, financial year by financial year")
def get_trade_cargo_mix():
    return tpt.get_cargo_mix()


@router.get("/alert-feedback", summary="Responses the port team has recorded on Action-list items")
def get_alert_feedback():
    return tfb.get_feedback()


@router.post("/alert-feedback", summary="Record a response on an Action-list item (status + note)")
def post_alert_feedback(key: str = Body(...), status: str = Body(...), note: str = Body(""), by: str = Body(""),
                        user: dict | None = Depends(auth.current_user)):
    auth.require(user, auth.ACTION_ROLES["alert_feedback"], "record a response")
    try:
        return tfb.set_feedback(key, status, note, auth.actor(user, by) if user else by)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/market-share", summary="New Mangalore's share of each cargo at all major ports; gaining or losing ground")
def get_trade_market_share():
    return tmk.get_market_share()


@router.get("/container-lines", summary="Container lines / agents calling at New Mangalore, new and no longer seen")
def get_trade_container_lines():
    return tln.get_container_lines()


@router.get("/customer-notes", summary="Account owner, follow-up date and notes history for each customer")
def get_customer_notes():
    return tfb.get_customer_notes()


@router.post("/customer-notes", summary="Set a customer's owner or follow-up date, and/or add a note")
def post_customer_notes(customer: str = Body(...), owner: str | None = Body(None), follow_up: str | None = Body(None),
                        note: str = Body(""), by: str = Body(""), stage: str | None = Body(None),
                        reason: str | None = Body(None), action: str | None = Body(None),
                        user: dict | None = Depends(auth.current_user)):
    auth.require(user, auth.ACTION_ROLES["customer_notes"], "update a customer's account")
    try:
        return tfb.update_customer_notes(customer, owner, follow_up, note, auth.actor(user, by) if user else by, stage, reason, action)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/port-competition", summary="Each major port's tonnes by cargo, four financial years (Ministry annual report)")
def get_trade_port_competition():
    return tmk.get_port_competition()


@router.get("/data-status", summary="Status of every dataset and of each daily report")
def get_trade_data_status():
    return tfr.get_data_status()
