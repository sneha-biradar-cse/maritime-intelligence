"""
Deal desk: a DRAFT commercial proposal for one customer and one cargo, for internal discussion.

It brings together the evidence (the customer's history, trend, waiting, notes), a stated baseline, four options
(no incentive, non-price action, rebate on extra volume with marginal slabs, blanket discount) with their arithmetic,
the eligibility check, the data gaps and the approval route. It is not an offer: nothing is sent to the customer and no
billing changes. Customer tonnes come from NMPA's daily vessel reports (traced, not billed) and are labelled as such.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any

import pandas as pd

from backend.app.services import incentive_engine as ie
from backend.app.services import incentive_rules as ir
from backend.app.services import trade_customers as tc
from backend.app.services import trade_feedback as tfb

STATUS = "Draft for internal discussion - not an offer to the customer"
APPROVAL_ROUTE = ["Traffic review (reason confirmed with the customer)", "Finance review (rate, budget, billing treatment)",
                  "Approval by the competent authority (order / file reference)",
                  "Recorded in the scheme register before any communication to the customer"]
BASELINE_CHOICES = {"same_months_last_year": "Same months last year (customer's tonnes in NMPA daily reports)",
                    "recent_run_rate": "Recent run-rate: average of the last 3 complete months x months in the proposal",
                    "contractual": "Contractual commitment (entered from the agreement)"}


def priced_cargos_for(customer: str) -> list[dict]:
    """The customer's cargos that have an NMPA wharfage rate (and are not own-arrangement / PPP), largest first."""
    v = tc.build()["voyages"]
    v = v[(v["customer"] == customer) & v["tonnes"].notna()]
    rev = {r["cargo"] for r in ie.get_revenue()["cargos"]}
    out = {}
    for fam, d, t in zip(v["family"], v["direction"], v["tonnes"]):
        k = ie.FAMILY_TO_CARGO.get((fam, d))
        if k in rev and (customer, fam) not in ie.NOT_PRICED_CUSTOMERS:
            out[k] = out.get(k, 0.0) + float(t)
    return [{"cargo": k, "traced_tonnes": round(t)} for k, t in sorted(out.items(), key=lambda x: -x[1])]


def _customer_monthly(customer: str, cargo: str) -> tuple[dict[str, float], list[str]]:
    """Traced tonnes per month for this customer and cargo, and the list of complete months held."""
    b = tc.build()
    v = b["voyages"]
    fams = [f for (f, d), k in ie.FAMILY_TO_CARGO.items() if k == cargo]
    dirs = [d for (f, d), k in ie.FAMILY_TO_CARGO.items() if k == cargo]
    v = v[(v["customer"] == customer) & v["family"].isin(fams) & v["direction"].isin(dirs)]
    by = v.groupby("month")["tonnes"].sum().to_dict()
    detail = tc.get_customer_detail(customer)
    complete = [m["month"] for m in detail.get("monthly", []) if m.get("complete")]
    return {m: float(by.get(m, 0.0)) for m in complete}, complete


def _baseline(customer: str, cargo: str, months: list[str], method: str, contractual_t: float | None) -> dict:
    monthly, complete = _customer_monthly(customer, cargo)
    if method == "contractual":
        if not contractual_t:
            return {"method": method, "label": BASELINE_CHOICES[method], "tonnes": None, "blocked": "Enter the committed tonnes."}
        return {"method": method, "label": BASELINE_CHOICES[method], "tonnes": round(contractual_t), "blocked": None,
                "detail": "Entered from the agreement", "status": "As entered"}
    if method == "same_months_last_year":
        back = [(pd.Timestamp(m + "-01") - pd.DateOffset(years=1)).strftime("%Y-%m") for m in months]
        missing = [m for m in back if m not in monthly]
        if missing:
            return {"method": method, "label": BASELINE_CHOICES[method], "tonnes": None,
                    "blocked": "Daily reports do not cover " + ", ".join(missing) + " (they start in Sep 2025). Use another method."}
        t = sum(monthly[m] for m in back)
        return {"method": method, "label": BASELINE_CHOICES[method], "tonnes": round(t), "blocked": None,
                "detail": "; ".join(f"{m}: {monthly[m]:,.0f} t" for m in back), "status": "Estimated (traced tonnes)"}
    last3 = complete[-3:]
    if len(last3) < 3:
        return {"method": method, "label": BASELINE_CHOICES[method], "tonnes": None, "blocked": "Fewer than 3 complete months held."}
    avg = sum(monthly[m] for m in last3) / 3
    return {"method": method, "label": BASELINE_CHOICES[method], "tonnes": round(avg * len(months)), "blocked": None,
            "detail": f"average of {', '.join(last3)} = {avg:,.0f} t a month", "status": "Estimated (traced tonnes)"}


def _non_price_actions(s: dict) -> list[str]:
    out = []
    if (s.get("not_ready_ship_days") or 0) >= 10:
        out.append(f"Receiver/shipper readiness coordination: the customer's ships waited {s['not_ready_ship_days']:.0f} ship-days "
                   "because the customer was not ready (daily reports).")
    if s.get("trend") == "Falling":
        out.append(f"Commercial follow-up: tonnes {s.get('change_pct'):+.0f}% on the previous 3 months; confirm the reason with "
                   "the customer before any tariff benefit.")
    if s.get("status") == "Gone quiet":
        out.append(f"Commercial follow-up: no ship for {s.get('days_since_last_call')} days against a usual gap of "
                   f"{s.get('usual_gap_days')} days.")
    out.append("Confirm with Marine / Operations that berth, equipment, storage and evacuation can take extra cargo.")
    return out


def build_proposal(customer: str, cargo: str | None = None, start: str = "2026-12-01", end: str = "2027-02-28",
                   discount_pct: float = 10.0, tiers: list[dict] | None = None, low_response_pct: float = 5.0,
                   target_extra_t: float | None = None, budget_cap_rs: float | None = None,
                   baseline_method: str = "same_months_last_year", contractual_t: float | None = None) -> dict[str, Any]:
    detail = tc.get_customer_detail(customer)
    if not detail or not detail.get("summary"):
        raise KeyError(customer)
    s = detail["summary"]
    cargos = priced_cargos_for(customer)
    if not cargos:
        raise ValueError(f"'{customer}' has no cargo with an NMPA wharfage rate (PPP berth, own arrangement or mixed rates).")
    cargo = cargo or cargos[0]["cargo"]
    if cargo not in [c["cargo"] for c in cargos]:
        raise ValueError(f"'{customer}' has no traced '{cargo}' cargo.")
    if baseline_method not in BASELINE_CHOICES:
        raise ValueError(f"baseline_method must be one of {list(BASELINE_CHOICES)}")
    months = [m.strftime("%Y-%m") for m in pd.date_range(pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1), freq="MS")]
    rate = next(r["avg_rate_rs_per_t"] for r in ie.get_revenue()["cargos"] if r["cargo"] == cargo)
    d = discount_pct / 100
    tiers = tiers or [{"up_to_pct_above_baseline": 10, "rebate_pct": discount_pct / 2}, {"up_to_pct_above_baseline": None, "rebate_pct": discount_pct}]
    bl = _baseline(customer, cargo, months, baseline_method, contractual_t)
    notes = tfb.get_customer_notes()["customers"].get(customer, {})
    elig = ir.check_eligibility(cargo, start, end, [customer], ie._load_schemes(), [r["cargo"] for r in ie.get_revenue()["cargos"]])

    options = [{"option": "No incentive (monitor)", "tariff_change": "None", "cost_rs": 0, "notes": "Baseline cargo at the full rate."},
               {"option": "Non-price action", "tariff_change": "None", "cost_rs": 0, "notes": " ".join(_non_price_actions(s))}]
    scenarios = []
    if bl["tonnes"]:
        q0 = bl["tonnes"]
        low = q0 * low_response_pct / 100
        given_up = q0 * rate * d
        be_blanket = given_up / (rate * (1 - d)) if d < 1 else None
        for name, extra in (("No response", 0.0), (f"Low response ({low_response_pct:g}% more)", low),
                            *([("Commercial target", float(target_extra_t))] if target_extra_t else [])):
            mr = ir.marginal_rebate(q0 + extra, q0, rate, tiers, budget_cap_rs)
            scenarios.append({"scenario": name, "extra_tonnes": round(extra), "extra_wharfage_rs": round(extra * rate),
                              "rebate_rs": mr["rebate_rs"], "rebate_net_rs": round(extra * rate - mr["rebate_rs"]),
                              "rebate_capped": mr["capped"],
                              "blanket_net_rs": round(extra * rate * (1 - d) - given_up)})
        options.append({"option": "Rebate on extra volume (marginal slabs)", "tariff_change": "Rebate above the agreed baseline",
                        "cost_rs": None, "notes": "Existing cargo keeps the full rate; the rebate is paid only on tonnes above the baseline."})
        options.append({"option": f"Blanket discount ({discount_pct:g}% on all of this cargo)", "tariff_change": "Lower rate on every tonne",
                        "cost_rs": round(given_up), "notes": f"Needs {be_blanket:,.0f} t more ({be_blanket / q0 * 100:.1f}%) just to break even."})
        from backend.app.services import incentive_portfolio as ipf
        ret = ipf.retention_option(q0, rate, discount_pct)
        options.append({k: ret[k] for k in ("option", "tariff_change", "cost_rs", "notes")})
    try:
        from backend.app.services import incentive_integrity as iig
        integrity = iig.check(cargo, start, end, customer, bl.get("tonnes"))
    except Exception as e:                           # the proposal must still be produced
        integrity = {"checks": [], "warnings": 0, "summary": f"Gaming checks not available: {e}"}
    gaps = [
        "Customer tonnes are traced from NMPA daily reports (about 85% of official tonnes); NMPA billing figures not provided.",
        ie.daily_report_note(),
        "Costs of handling extra cargo are not known: results are wharfage receipts, not profit.",
        "Operational capacity is not checked: Marine / Operations to confirm.",
    ]
    if any("identity" in b for b in elig["blocks"]):
        gaps.insert(0, "Customer identity not confirmed by NMPA.")
    if not notes.get("stage") or notes.get("stage", "").startswith("Statistical"):
        gaps.append("The reason for the change has not been confirmed with the customer (opportunity stage: statistical gap).")
    return {
        "status": STATUS, "prepared_on": date.today().isoformat(), "customer": customer, "cargo": cargo, "cargos_available": cargos,
        "period": {"start": start, "end": end, "months": months},
        "evidence": {"trend": s.get("trend"), "change_pct": s.get("change_pct"), "recent_tonnes": s.get("recent_tonnes"),
                     "previous_tonnes": s.get("previous_tonnes"), "calls": s.get("calls"), "share_pct": s.get("share_of_traced_tonnes_pct"),
                     "not_ready_ship_days": s.get("not_ready_ship_days"), "days_since_last_call": s.get("days_since_last_call"),
                     "usual_gap_days": s.get("usual_gap_days"), "status": s.get("status"),
                     "owner": notes.get("owner"), "stage": notes.get("stage"), "reason": notes.get("reason"),
                     "proposed_action": notes.get("action")},
        "rate_rs_per_t": rate, "discount_pct": discount_pct, "tiers": tiers, "budget_cap_rs": budget_cap_rs,
        "baseline": bl, "options": options, "scenarios": scenarios, "eligibility": elig, "integrity": integrity, "data_gaps": gaps,
        "approval_route": APPROVAL_ROUTE, "tariff_version": ie.TARIFF_VERSION,
        "sources": ["NMPA daily vessel reports (customer tonnes, waiting)", "NMPA Scale of Rates (rate)",
                    "NMPA monthly statements (cargo totals)", "Customer notes recorded in Trade Intelligence"],
    }


def proposal_pdf(p: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    asc = lambda x: str(x).replace("\u2212", "-").replace("\u20b9", "Rs ").encode("ascii", "replace").decode()
    cr = lambda v: "-" if v is None else (("-" if v < 0 else "") + (f"Rs {abs(v) / 1e7:,.2f} cr" if abs(v) >= 1e6 else f"Rs {abs(v) / 1e5:,.1f} lakh"))
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Heading2"], fontSize=11, spaceBefore=6, spaceAfter=2)
    b = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle("s", parent=b, fontSize=7.5, textColor=colors.HexColor("#555555"))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Draft proposal - {asc(p['customer'])}")
    e, bl = p["evidence"], p["baseline"]
    el = []
    el.append(Paragraph(f"<b>Draft commercial proposal: {asc(p['customer'])} - {asc(p['cargo'])}</b>", ss["Title"]))
    el.append(Paragraph(f"<b>{asc(p['status'])}</b>. Prepared {p['prepared_on']}. Period {p['period']['start']} to {p['period']['end']}. "
                        f"Tariff: {asc(p['tariff_version'])}.", small))
    el.append(Paragraph("1. Evidence", h))
    el.append(Paragraph(asc(
        f"Trend: {e['trend']} ({e['change_pct']:+.0f}% on the previous 3 months: {e['recent_tonnes'] or 0:,.0f} t against "
        f"{e['previous_tonnes'] or 0:,.0f} t). Share of traced cargo: {e['share_pct']}%. Calls since Sep 2025: {e['calls']}. "
        f"Ship-days waiting because the customer was not ready: {e['not_ready_ship_days'] or 0:.1f}. "
        f"Account owner: {e['owner'] or 'not set'}. Opportunity stage: {e['stage'] or 'statistical gap'}. Reason: {e['reason'] or 'not recorded'}."
        if e.get("change_pct") is not None else
        f"Status: {e['status']}. Calls since Sep 2025: {e['calls']}. Account owner: {e['owner'] or 'not set'}."), b))
    el.append(Paragraph("2. Baseline (tonnes expected without a benefit)", h))
    el.append(Paragraph(asc(f"{bl['label']}: " + (f"{bl['tonnes']:,} t ({bl.get('detail', '')}). Status: {bl.get('status', '')}."
                                                   if bl.get("tonnes") is not None else f"cannot be set - {bl.get('blocked')}")), b))
    el.append(Paragraph("3. Options", h))
    rows = [["Option", "Tariff change", "Cost / notes"]] + [[Paragraph(asc(o["option"]), b), Paragraph(asc(o["tariff_change"]), b),
                                                             Paragraph(asc((cr(o["cost_rs"]) + " over the proposal period. " if o.get("cost_rs") else "") + o["notes"]), b)]
                                                            for o in p["options"]]
    t = Table(rows, colWidths=[45 * mm, 38 * mm, 99 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                           ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(t)
    if p["scenarios"]:
        el.append(Paragraph(asc(f"4. Scenarios (rate Rs {p['rate_rs_per_t']:.2f}/t; extra tonnes are assumptions, not predictions)"), h))
        rows = [["Scenario", "Extra t", "Extra wharfage", "Rebate (slabs)", "Rebate: net", "Blanket: net"]] + [
            [asc(s["scenario"]), f"{s['extra_tonnes']:,}", cr(s["extra_wharfage_rs"]), cr(s["rebate_rs"]) + (" (capped)" if s["rebate_capped"] else ""),
             cr(s["rebate_net_rs"]), cr(s["blanket_net_rs"])] for s in p["scenarios"]]
        t = Table(rows, colWidths=[40 * mm, 22 * mm, 30 * mm, 32 * mm, 28 * mm, 30 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                               ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        el.append(t)
        el.append(Paragraph(asc("Slabs (marginal): " + "; ".join(
            (f"up to {x['up_to_pct_above_baseline']:g}% above baseline: {x['rebate_pct']:g}%" if x.get("up_to_pct_above_baseline") is not None
             else f"beyond: {x['rebate_pct']:g}%") for x in p["tiers"]) + (f". Budget cap {cr(p['budget_cap_rs'])}." if p.get("budget_cap_rs") else ".")), small))
    el.append(Paragraph("5. Eligibility", h))
    el.append(Paragraph(asc("Blocked: " + " | ".join(p["eligibility"]["blocks"]) if p["eligibility"]["blocks"] else "No blocking issue found by the tool."), b))
    ig = p.get("integrity") or {}
    if ig.get("checks"):
        el.append(Paragraph("5b. Checks for gaming (a warning is a reason to look, not proof)", h))
        el.append(Paragraph(asc(ig.get("summary", "")), b))
        for c in ig["checks"]:
            if c["status"] in ("Warning", "Watch", "Note"):
                el.append(Paragraph(asc(f"- {c['check']} ({c['status']}): {c['plain']}"), b))
    el.append(Paragraph("6. Data gaps and assumptions", h))
    for g in p["data_gaps"]:
        el.append(Paragraph(asc("- " + g), b))
    el.append(Paragraph("7. Approval route", h))
    el.append(Paragraph(asc(" -> ".join(p["approval_route"])), b))
    el.append(Spacer(1, 4))
    el.append(Paragraph(asc("Sources: " + "; ".join(p["sources"]) + ". Estimates for discussion; not billing figures."), small))
    doc.build(el)
    return buf.getvalue()
