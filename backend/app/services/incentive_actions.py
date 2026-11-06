"""
'Start here' for NMPA's team: this week's actions from the Incentive Engine's own findings, each with who should act, why
(the numbers) and where in the tool; a guide by role; a plain-word glossary; and a one-page brief PDF for management.
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_feedback as tfb

cr = ie.cr_text

ROLE_GUIDE = [
    {"role": "Traffic / Marketing officer", "use_for": "Who to call this week, and why",
     "where": "Start here (actions) \u2192 Customers & cargo (key customers, cargo lost) \u2192 Proposals & schemes (customer proposal)",
     "records": "Owner, reason, opportunity stage and follow-up date in Trade Intelligence, Customers, Update account"},
    {"role": "Finance", "use_for": "Checking every rupee: rates, reconciliation with the accounts, cost of any proposal",
     "where": "What we earn (estimated wharfage, 'Show the calculation', reconciliation) \u2192 Proposals & schemes (scenarios, scheme review)",
     "records": "Finance review step in the scheme register; billing figures when shared"},
    {"role": "Management", "use_for": "The picture in one page, and decisions on schemes",
     "where": "Start here (actions, KPIs) and the one-page Incentive brief (PDF)",
     "records": "Approval with an order / file reference in the scheme register"},
]
GLOSSARY = [
    ("Wharfage", "The port's charge on every tonne of cargo loaded or unloaded."),
    ("Scale of Rates (SOR)", "NMPA's official price list. Its rates are ceilings: the port may charge less or give rebates."),
    ("Foreign / coastal", "Cargo to or from another country / between two Indian ports."),
    ("Traced tonnes", "Cargo matched to a named customer in NMPA's daily vessel reports (about 85% of official tonnes)."),
    ("Baseline", "The cargo a customer would bring without any benefit; agreed and frozen before a scheme starts."),
    ("Rebate on extra volume", "Money back only on cargo above the baseline; existing cargo keeps the full rate."),
    ("Blanket discount", "A lower rate on every tonne, including cargo that would have come anyway."),
    ("Break-even", "The extra cargo needed for the port to earn the same as before the discount."),
    ("PPP berth", "A berth run by a private company (Berths 14, 15, 16); NMPA earns a royalty there, not wharfage."),
    ("Ship-days waiting (not ready)", "Days ships waited at anchor because the customer was not ready to receive or ship cargo."),
    ("Statistical gap", "Cargo New Mangalore would have handled had it kept last year's share; a reason to investigate, not proof of loss."),
]


def get_actions() -> dict[str, Any]:
    acts = []
    kc = ie.get_key_customers()
    for r in [r for r in kc["rows"] if r["risk"] == "High"][:3]:
        acts.append({"priority": 1, "who": "Traffic", "action": f"Call {r['customer']} and record the reason",
                     "why": "; ".join(r["signals"]) + f". {r['share_pct']:.0f}% of traced wharfage.",
                     "where": "Customers & cargo > Protect key customers", "next": r["next_step"]})
    if kc["no_owner_count"]:
        acts.append({"priority": 2, "who": "Management", "action": f"Assign an account owner to {kc['no_owner_count']} key customers",
                     "why": f"{len(kc['rows'])} customers make up {kc['key_share_pct']:.0f}% of traced wharfage; "
                            f"{kc['no_owner_count']} have no owner recorded.",
                     "where": "Trade Intelligence > Customers > Update account", "next": "One named officer per key customer."})
    opp = ie.get_opportunities()
    lost = sorted([o for o in opp["cargos"] if o.get("wharfage_at_stake_rs")], key=lambda o: -o["wharfage_at_stake_rs"])
    for o in lost[:1]:
        who = ", ".join(c["customer"] for c in o.get("customers", [])[:3]) or "the main customers"
        acts.append({"priority": 1, "who": "Traffic", "action": f"Find out why {o['cargo']} cargo is going to other ports",
                     "why": f"Share {o['share_prev_pct']:.1f}% -> {o['share_pct']:.1f}% of all major ports ({opp['period']}); about "
                            f"{o['tonnes_not_won'] / 1e3:,.0f} thousand t, {cr(o['wharfage_at_stake_rs'])} of wharfage (statistical gap).",
                     "where": "Customers & cargo > Cargo lost to other ports", "next": f"Talk to {who} before considering any benefit."})
    io = ie.iron_ore_rebate_monitor()
    if io["same_months_2025_t"] and io["fy2026_27_to_date_t"] < io["same_months_2025_t"]:
        gone = [e["customer"] for e in io["exporters"] if e["fy2026_27_to_date_t"] == 0 and e["sep2025_mar2026_t"] >= 100000]
        acts.append({"priority": 1, "who": "Traffic", "action": "Promote the 20% iron ore export rebate (in force to 31 Mar 2027)",
                     "why": f"Iron ore exports {io['months']}: {io['fy2026_27_to_date_t'] / 1e6:.2f} MMT against "
                            f"{io['same_months_2025_t'] / 1e6:.2f} MMT a year earlier"
                            + (f"; no 2026-27 shipments yet from {', '.join(gone)}" if gone else "") + ".",
                     "where": "Proposals & schemes > NMPA's own incentive schemes",
                     "next": "Tell exporters their 2025-26 base and what qualifies; record replies in Update account."})
    sw = ie.get_seasonal_windows(10)
    best = [r for r in sw["rows"] if r["regular"] and r["quiet_months"] and r.get("occupancy_quiet_pct") is not None
            and (r["occupancy_other_pct"] or 0) - (r["occupancy_quiet_pct"] or 0) >= 10]
    for r in best[:1]:
        acts.append({"priority": 3, "who": "Traffic + Marine", "action": f"Check a quiet-month offer for {r['cargo']}",
                     "why": f"Quiet in {', '.join(r['quiet_months'])}; its berths had a ship on {r['occupancy_quiet_pct']}% of days "
                            f"then against {r['occupancy_other_pct']}% otherwise. 10% in those months only: {cr(r['cost_quiet_months_rs'])} "
                            f"a year (vs {cr(r['cost_all_year_rs'])} all year).",
                     "where": "Customers & cargo > Seasonal windows", "next": "Marine / Operations to confirm capacity; customers to confirm demand."})
    for s in ie._load_schemes():
        if s["status"] in ("Traffic review", "Finance review"):
            acts.append({"priority": 2, "who": s["status"].split()[0], "action": f"Review scheme {s['id']} ({s['cargo']})",
                         "why": f"Waiting at {s['status']}.", "where": "Proposals & schemes > Scheme register", "next": "Move it on or send it back."})
        if s["status"] == "Active" and s["end"] <= (date.today() + timedelta(days=30)).isoformat():
            acts.append({"priority": 2, "who": "Traffic + Finance", "action": f"Evaluate scheme {s['id']} before it ends ({s['end']})",
                         "why": "Ends within 30 days.", "where": "Proposals & schemes > Scheme register", "next": "Compare with its target and stop rule."})
    for d in tfb.get_customer_notes().get("follow_ups_due", [])[:5]:
        acts.append({"priority": 2, "who": d.get("owner") or "Traffic", "action": f"Follow up with {d['customer']}",
                     "why": f"Follow-up date {d.get('follow_up')} has come.", "where": "Trade Intelligence > Customers", "next": "Record the outcome."})
    acts.append({"priority": 3, "who": "Finance", "action": "Share billed wharfage by cargo (latest year)",
                 "why": "Turns 'estimated' into checked figures; it is the main KPI still pending NMPA data.",
                 "where": "Start here > Baseline KPIs", "next": "A one-time extract is enough to start."})
    acts.sort(key=lambda a: a["priority"])
    return {"actions": acts, "role_guide": ROLE_GUIDE, "glossary": GLOSSARY, "prepared_on": date.today().isoformat(),
            "note": "Updated each time the page loads. Signals to act on, not conclusions."}


def brief_pdf() -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    asc = lambda x: str(x).replace("\u2212", "-").replace("\u20b9", "Rs ").replace("\u2192", "->").encode("ascii", "replace").decode()
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Heading2"], fontSize=11, spaceBefore=6, spaceAfter=2)
    b = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    sm = ParagraphStyle("s", parent=b, fontSize=7.5, textColor=colors.HexColor("#555555"))
    rv, kc, a = ie.get_revenue(), ie.get_key_customers(), get_actions()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title="NMPA Incentive brief")
    t = rv["total"]
    el = [Paragraph("New Mangalore Port: Incentive brief", ss["Title"]),
          Paragraph(asc(f"Prepared {a['prepared_on']}. Estimates from NMPA's published tonnes, daily reports and Scale of Rates; "
                        "not billing figures."), sm),
          Paragraph("1. The picture", h),
          Paragraph(asc(f"Estimated wharfage {rv['period']}: {cr(t['revenue_rs'])} on {t['tonnes'] / 1e6:.1f} MMT "
                        f"({(t['revenue_rs'] / t['revenue_prev_rs'] - 1) * 100:+.1f}% on the same months last year). "
                        f"{len(kc['rows'])} customers make up {kc['key_share_pct']:.0f}% of traced wharfage; {kc['at_risk_count']} show a "
                        f"warning sign (their wharfage fell {cr(-kc['at_risk_quarter_fall_rs'])} in {kc['q2_label']} against {kc['q1_label']})."), b),
          Paragraph("2. Actions this week", h)]
    rows = [["Who", "Action", "Why"]] + [[Paragraph(asc(x["who"]), b), Paragraph(asc(x["action"]), b), Paragraph(asc(x["why"]), b)]
                                         for x in a["actions"][:8]]
    tb = Table(rows, colWidths=[28 * mm, 55 * mm, 99 * mm])
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                            ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(tb)
    el.append(Paragraph("3. Key customers at risk", h))
    rows = [["Customer", "Share", "Risk", "Warning signs"]] + [[asc(r["customer"]), f"{r['share_pct']:.1f}%", r["risk"],
                                                                 Paragraph(asc("; ".join(r["signals"])), b)]
                                                                for r in kc["rows"] if r["risk"] != "None found"][:6]
    tb = Table(rows, colWidths=[42 * mm, 16 * mm, 16 * mm, 108 * mm])
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                            ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(tb)
    el.append(Paragraph(asc("Signals to act on, not conclusions. Any benefit needs the reason confirmed with the customer, Finance "
                            "review and approval (scheme register). Full detail: Incentive Engine in the YellowSense platform."), sm))
    doc.build(el)
    return buf.getvalue()
