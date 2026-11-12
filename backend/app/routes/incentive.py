from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.app.services import auth
from backend.app.services import incentive_engine as ie
from backend.app.services import incentive_rules as ir
from backend.app.services import incentive_proposal as ipr
from fastapi.responses import Response

router = APIRouter()


# ── Evidence-based Incentive Engine (used by the dashboard) ─────────────────────
@router.get("/revenue", summary="Estimated wharfage per cargo (NMPA tonnes x Scale of Rates), and what the coastal concession costs")
def get_incentive_revenue():
    return ie.get_revenue()


@router.get("/evidence", summary="What followed real incentives (before/after, against all major ports)")
def get_incentive_evidence():
    return ie.get_evidence()


@router.get("/opportunities", summary="Cargos losing share, with the wharfage at stake")
def get_incentive_opportunities():
    return ie.get_opportunities()


@router.get("/scenario", summary="Blanket discount vs rebate on extra volume: scenarios, break-even, optional costs")
def get_scenario(cargo: str = Query(...), discount_pct: float = Query(..., ge=0, lt=100), cost_per_t: float = Query(0.0, ge=0),
                 fixed_cost: float = Query(0.0, ge=0), low_response_pct: float = Query(2.0, ge=0, le=100),
                 target_t: float | None = Query(None, ge=0)):
    try:
        return ie.scenario(cargo, discount_pct, cost_per_t, fixed_cost, low_response_pct, target_t)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown cargo '{cargo}'. See /incentive/revenue.")


@router.get("/ppp-royalty", summary="PPP berths: container royalty estimate (laden TEU x royalty per TEU); coal terminal basis")
def get_ppp_royalty():
    return ie.get_ppp_royalty()


@router.get("/customer-wharfage", summary="Estimated wharfage by customer (traced customer tonnes x cargo rate)")
def get_customer_wharfage():
    return ie.get_customer_wharfage()


@router.get("/accounts-check", summary="Income per tonne NMPA actually earned (its budget accounts) against the rates used here")
def get_accounts_check():
    return ie.get_accounts_check()


@router.get("/schemes", summary="Incentive scheme register: drafts, reviews, approvals, observed results, audit trail")
def get_schemes():
    return ie.list_schemes()


@router.post("/schemes", summary="Save a scenario as a DRAFT scheme with eligibility check, baseline and slabs (no offer, no billing change)")
def post_scheme(cargo: str = Body(...), scope: str = Body(...), discount_pct: float = Body(...), start: str = Body(...),
                end: str = Body(...), budget_cap_rs: float = Body(0.0), customers: str = Body(""), conditions: str = Body(""),
                by: str = Body(""), baseline_method: str = Body("same_months_last_year"), baseline_years: int = Body(3),
                contractual_t: float | None = Body(None), tiers: list[dict] | None = Body(None),
                success_target_t: float | None = Body(None), stop_rule: str = Body(""), customer: str = Body(""),
                baseline_tonnes: float | None = Body(None), baseline_label: str = Body(""), baseline_detail: str = Body(""),
                commitment_t: float | None = Body(None), clawback_rule: str = Body(""), settlement: str = Body(""),
                user: dict | None = Depends(auth.current_user)):
    auth.require(user, auth.ACTION_ROLES["create_scheme"], "create a draft scheme")
    by = auth.actor(user, by)
    try:
        return ie.create_scheme(cargo, scope, discount_pct, start, end, budget_cap_rs, customers, conditions, by,
                                baseline_method, baseline_years, contractual_t, tiers, success_target_t, stop_rule,
                                customer, baseline_tonnes, baseline_label, baseline_detail, commitment_t, clawback_rule,
                                settlement)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown cargo '{cargo}'")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/schemes/{sid}/baseline", summary="New baseline version for a DRAFT scheme (earlier versions kept)")
def post_rebaseline(sid: str, method: str = Body(...), years: int = Body(3), contractual_t: float | None = Body(None),
                    reason: str = Body(""), by: str = Body(""), user: dict | None = Depends(auth.current_user)):
    auth.require(user, auth.ACTION_ROLES["rebaseline"], "change a baseline")
    try:
        return ie.rebaseline(sid, method, years, contractual_t, reason, auth.actor(user, by))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown scheme '{sid}'")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/rules", summary="Tariff versions by date, who controls each charge, combination rule, baseline methods")
def get_rules():
    return {"tariff_versions": ir.TARIFF_VERSIONS, "charge_control": ir.CHARGE_CONTROL,
            "combination_rule": ir.COMBINATION_RULE, "known_benefits": ir.KNOWN_BENEFIT_PERIODS,
            "baseline_methods": ir.BASELINE_METHODS}


@router.get("/eligibility", summary="Check a proposed benefit before saving it: tariff version, charge control, identity, combination")
def get_eligibility(cargo: str = Query(...), start: str = Query(...), end: str = Query(...), customers: str = Query(""),
                    discount_pct: float | None = Query(None, ge=0, le=100)):
    custs = [c.strip() for c in customers.replace(";", ",").split(",") if c.strip()]
    return ir.check_eligibility(cargo, start, end, custs, ie._load_schemes(), [r["cargo"] for r in ie.get_revenue()["cargos"]],
                                discount_pct=discount_pct)


@router.get("/baseline", summary="Baseline tonnes for a cargo and months by a stated method (missing months block it)")
def get_baseline(cargo: str = Query(...), start: str = Query(...), end: str = Query(...),
                 method: str = Query("same_months_last_year"), years: int = Query(3), contractual_t: float | None = Query(None)):
    import pandas as pd
    if cargo not in ie.CARGO:
        raise HTTPException(status_code=404, detail=f"Unknown cargo '{cargo}'")
    months = [m.strftime("%Y-%m") for m in pd.date_range(pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1), freq="MS")]
    try:
        return ir.baseline(ie.CARGO[cargo]["keys"], months, method, years, contractual_t)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/schemes/{sid}", summary="Move a scheme to its next status, record an approval reference, or add a note")
def post_scheme_update(sid: str, status: str | None = Body(None), approval_reference: str | None = Body(None),
                       note: str = Body(""), by: str = Body(""), user: dict | None = Depends(auth.current_user)):
    if status:
        auth.require(user, auth.STATUS_ROLES.get(status, set()), f"move a scheme to '{status}'")
    else:
        auth.require(user, auth.ACTION_ROLES["scheme_note"], "add a note or approval reference")
    if approval_reference:
        auth.require(user, {"approver"}, "record an approval reference")
    try:
        return ie.update_scheme(sid, status, approval_reference, note, auth.actor(user, by))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown scheme '{sid}'")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/tariff-comparison", summary="Published wharfage lines: NMPA vs Cochin (page references)")
def get_tariff_comparison():
    return ie.get_tariff_comparison()


@router.get("/cochin-schemes", summary="Cochin Port's incentive and concession notices, as design examples")
def get_cochin_schemes():
    return ie.get_cochin_schemes()


@router.get("/published-accounts", summary="NMPA's actual income by activity, 2023-24 and 2024-25 (Administration Report)")
def get_published_accounts():
    return ie.get_published_accounts()


def _proposal_args(customer, cargo, start, end, discount_pct, low_response_pct, target_extra_t, budget_cap_rs, baseline_method,
                   contractual_t, tier1_upto, tier1_pct, tier2_pct):
    tiers = [{"up_to_pct_above_baseline": tier1_upto, "rebate_pct": tier1_pct}, {"up_to_pct_above_baseline": None, "rebate_pct": tier2_pct}]
    return dict(customer=customer, cargo=cargo or None, start=start, end=end, discount_pct=discount_pct, tiers=tiers,
                low_response_pct=low_response_pct, target_extra_t=target_extra_t or None, budget_cap_rs=budget_cap_rs or None,
                baseline_method=baseline_method, contractual_t=contractual_t or None)


@router.get("/proposal/cargos", summary="A customer's cargos that have an NMPA wharfage rate")
def get_proposal_cargos(customer: str = Query(...)):
    return {"customer": customer, "cargos": ipr.priced_cargos_for(customer)}


@router.get("/proposal", summary="Deal desk: draft proposal for one customer and cargo (not an offer)")
def get_proposal(customer: str = Query(...), cargo: str = Query(""), start: str = Query("2026-12-01"), end: str = Query("2027-02-28"),
                 discount_pct: float = Query(10.0, ge=0, lt=100), low_response_pct: float = Query(5.0, ge=0),
                 target_extra_t: float = Query(0.0, ge=0), budget_cap_rs: float = Query(0.0, ge=0),
                 baseline_method: str = Query("same_months_last_year"), contractual_t: float = Query(0.0, ge=0),
                 tier1_upto: float = Query(10.0, gt=0), tier1_pct: float = Query(5.0, ge=0), tier2_pct: float = Query(10.0, ge=0)):
    try:
        return ipr.build_proposal(**_proposal_args(customer, cargo, start, end, discount_pct, low_response_pct, target_extra_t,
                                                   budget_cap_rs, baseline_method, contractual_t, tier1_upto, tier1_pct, tier2_pct))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown customer '{customer}'")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/proposal.pdf", summary="Deal desk proposal as a one-page PDF")
def get_proposal_pdf(customer: str = Query(...), cargo: str = Query(""), start: str = Query("2026-12-01"), end: str = Query("2027-02-28"),
                     discount_pct: float = Query(10.0, ge=0, lt=100), low_response_pct: float = Query(5.0, ge=0),
                     target_extra_t: float = Query(0.0, ge=0), budget_cap_rs: float = Query(0.0, ge=0),
                     baseline_method: str = Query("same_months_last_year"), contractual_t: float = Query(0.0, ge=0),
                     tier1_upto: float = Query(10.0, gt=0), tier1_pct: float = Query(5.0, ge=0), tier2_pct: float = Query(10.0, ge=0)):
    try:
        p = ipr.build_proposal(**_proposal_args(customer, cargo, start, end, discount_pct, low_response_pct, target_extra_t,
                                                budget_cap_rs, baseline_method, contractual_t, tier1_upto, tier1_pct, tier2_pct))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown customer '{customer}'")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    name = "".join(ch if ch.isalnum() else "_" for ch in customer)[:40]
    return Response(ipr.proposal_pdf(p), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="NMPA_draft_proposal_{name}.pdf"'})


@router.get("/kpis", summary="Baseline KPIs for the Incentive Engine (measured / pending NMPA data / estimated)")
def get_kpis():
    from backend.app.services import incentive_kpis as ik
    return ik.get_module_kpis()


@router.get("/seasonal-windows", summary="Quiet months per cargo: cost of a benefit in quiet months only vs all year; berth occupancy")
def get_seasonal_windows(discount_pct: float = Query(10.0, gt=0, lt=100)):
    return ie.get_seasonal_windows(discount_pct)


@router.get("/key-customers", summary="Protect key customers: wharfage at risk, warning signs, follow-up status")
def get_key_customers():
    return ie.get_key_customers()


@router.get("/actions", summary="Start here: this week's actions, role guide and glossary for NMPA's team")
def get_actions():
    from backend.app.services import incentive_actions as ia
    return ia.get_actions()


@router.get("/brief.pdf", summary="One-page Incentive brief for management")
def get_brief_pdf():
    from backend.app.services import incentive_actions as ia
    return Response(ia.brief_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="NMPA_incentive_brief.pdf"'})


@router.post("/schemes/{sid}/amend", summary="Amend an Approved / Active scheme: old terms kept, back to Traffic review for re-approval")
def post_amend(sid: str, changes: dict = Body(...), reason: str = Body(""), by: str = Body(""),
               user: dict | None = Depends(auth.current_user)):
    auth.require(user, auth.ACTION_ROLES["amend"], "amend a scheme")
    try:
        return ie.amend_scheme(sid, changes, reason, auth.actor(user, by))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown scheme '{sid}'")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/data-current", summary="What the Incentive Engine's figures rest on: latest month or date of each source")
def get_data_current():
    return ie.data_version()


@router.get("/waiver-coverage", summary="Ships and tonnes covered by the March 2026 crude/LPG waiver (daily reports)")
def get_waiver_coverage():
    return ie.get_waiver_coverage()


@router.get("/waiver-cost", summary="Wharfage waived under the March 2026 waiver, at the 2025-26 rates (upper estimate)")
def get_waiver_cost():
    return ie.waiver_cost()


@router.get("/iron-ore-rebate", summary="The iron ore export rebate in force: what public data shows, and its limits")
def get_iron_ore_rebate():
    return ie.iron_ore_rebate_monitor()


@router.get("/other-ports", summary="How other major ports design incentive schemes, by kind, against NMPA's own notices")
def get_other_ports():
    return ie.get_other_ports_schemes()


@router.get("/nmpa-notices", summary="NMPA's incentive notices held: scheme, terms, period, status")
def get_nmpa_notices():
    import pandas as pd
    d = pd.read_csv(ie.tmk.ROOT / "data" / "nmpa_incentive_notices.csv")
    return {"notices": d.astype(object).where(pd.notna(d), None).to_dict(orient="records")}


@router.get("/tariff-comparison-voc", summary="Published wharfage: NMPA vs VOC (Tuticorin), same year 2025-26")
def get_tariff_comparison_voc():
    return ie.get_tariff_comparison_voc()


# ── Improvements (Nov 2026): did it work, is it gamed, ship charges, one budget, settlement ─────────────────────
from backend.app.services import incentive_evaluation as iev      # noqa: E402
from backend.app.services import incentive_integrity as iig       # noqa: E402
from backend.app.services import incentive_portfolio as ipf       # noqa: E402
from backend.app.services import vessel_charges as vch            # noqa: E402


@router.get("/evaluate", summary="Did a discount work? NMPA against the other major ports over the same months")
def get_evaluate(cargo: str = Query(...), start: str = Query(...), end: str = Query(...),
                 rebate_cost_rs: float | None = Query(None, ge=0)):
    try:
        return iev.evaluate(cargo, start, end, rebate_cost_rs)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No peer-port comparison for '{cargo}'. Cargos: {sorted(iev.CARGO_GROUP)}")


@router.get("/integrity", summary="Checks for gaming: holding back, timing, related companies, relabelling, berth shift, easy baseline")
def get_integrity(cargo: str = Query(...), start: str = Query(...), end: str = Query(...), customer: str = Query(""),
                  baseline_t: float | None = Query(None, ge=0)):
    try:
        return iig.check(cargo, start, end, customer or None, baseline_t)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown cargo '{cargo}'")


@router.get("/vessel-charges", summary="Ship charges (port dues, pilotage, berth hire): inputs held and NMPA's ship-charge rebates priced")
def get_vessel_charges(usd_inr: float | None = Query(None, gt=0)):
    return vch.summary(usd_inr)


@router.get("/vessel-charges/call", summary="Ship charges for one call, from the Scale of Rates")
def get_vessel_call(grt: float = Query(..., gt=0), coastal: bool = Query(False), kind: str = Query("dry"),
                    hours: float = Query(24, ge=0), usd_inr: float | None = Query(None, gt=0), ballast: bool = Query(False)):
    try:
        return vch.call_cost(grt, coastal, kind, hours, usd_inr, ballast)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/portfolio", summary="All discounts together: total exposure against the port's income and the Board's cap; uptake")
def get_portfolio():
    return ipf.portfolio()


@router.get("/policy", summary="Board policy for discounts: total cap, stacking ceiling, clawback rule")
def get_policy():
    return {**ipf.policy(), "clawback_rules": ipf.CLAWBACK_RULES}


@router.post("/policy", summary="Set the Board policy (approver only)")
def post_policy(changes: dict = Body(...), user: dict | None = Depends(auth.current_user)):
    auth.require(user, auth.ACTION_ROLES["set_policy"], "set the incentive policy")
    try:
        return ipf.save_policy(changes, auth.actor(user, ""))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/schemes/{sid}/settlement", summary="Year-end settlement: rebate earned, commitment, shortfall, clawback")
def get_settlement(sid: str):
    rec = next((r for r in ie._load_schemes() if r["id"] == sid), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Unknown scheme '{sid}'")
    return ipf.settlement(rec)


@router.get("/scheme-review", summary="Every NMPA scheme judged so far against the other major ports")
def get_scheme_review():
    from backend.app.services import incentive_scheme_review as sr
    return sr.get_scheme_review()


@router.get("/readiness-condition", summary="Calls that would qualify for a rebate tied to customer readiness")
def readiness_condition(customer: str | None = None, months: int = 6, max_wait_days: float = 0.0):
    from backend.app.services import incentive_scheme_review as sr
    return sr.readiness_condition(customer=customer or None, months=months, max_wait_days=max_wait_days)


# ---- Decision aids: growth check, schemes ending soon, Board note and trade notice drafts
@router.get("/growth-check", summary="How often NMPA's cargo grew enough in a year for a discount on all cargo to pay for itself")
def get_growth_check(cargo: str, discount_pct: float):
    from backend.app.services import incentive_decision_aids as da
    try:
        return da.growth_check(cargo, discount_pct)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/expiring", summary="Schemes in force and approved schemes, with days left and a review pack")
def get_expiring():
    from backend.app.services import incentive_decision_aids as da
    return da.expiring_schemes()


_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/schemes/{sid}/board-note.docx", summary="Draft Board agenda note (Word) for a scheme in the register")
def get_board_note(sid: str):
    from fastapi import Response
    from backend.app.services import incentive_decision_aids as da
    try:
        data = da.board_note_docx(sid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No scheme {sid}")
    return Response(data, media_type=_DOCX, headers={"Content-Disposition": f'attachment; filename="{sid}_Board_agenda_note_DRAFT.docx"'})


@router.get("/schemes/{sid}/trade-notice.docx", summary="Draft trade notice (Word) for a scheme in the register")
def get_trade_notice(sid: str):
    from fastapi import Response
    from backend.app.services import incentive_decision_aids as da
    try:
        data = da.trade_notice_docx(sid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No scheme {sid}")
    return Response(data, media_type=_DOCX, headers={"Content-Disposition": f'attachment; filename="{sid}_Trade_notice_DRAFT.docx"'})
