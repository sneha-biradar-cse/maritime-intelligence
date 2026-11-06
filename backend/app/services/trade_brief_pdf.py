"""
One-page monthly trade brief (PDF) for NMPA - the Trade Intelligence summary in a form that can be forwarded.
Every figure comes from the same services as the dashboard; nothing is computed differently here.
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.app.services import trade_benchmark as tb
from backend.app.services import trade_customers as tcu
from backend.app.services import trade_feedback as tfb
from backend.app.services import trade_freshness as tfr
from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_market as tmk
from backend.app.services import trade_target as tt

INK, MUTED, RULE = colors.HexColor("#1C1917"), colors.HexColor("#57534E"), colors.HexColor("#D6D3D1")
NICE = {"TOTAL CRUDE": "Crude oil", "TOTAL COAL": "Coal", "IRON ORE": "Iron ore", "TOTAL LPG": "LPG",
        "POL PRODUCTS": "POL products", "CONTAINER (JSW)": "Containers (JSW)", "EDIBLE OIL": "Edible oil",
        "OTH. LIQ. CARGOES": "Other liquid cargo", "OTHER CARGO": "Other cargo", "CRUDE - ISPRL": "Crude (ISPRL)",
        "TOTAL CEMENT": "Cement", "F.R.M. (DRY)": "F.R.M. (dry)"}


def _mmt(v):
    return "-" if v is None else f"{v / 1e6:.2f} MMT"


def _pct(v):
    return "n/a" if v is None else f"{v:+.1f}%"


def _ascii(s: str) -> str:
    return (str(s).replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
            .replace("\u2019", "'").replace("\u20b9", "Rs "))


def build_monthly_brief_pdf() -> bytes:
    s = ti.get_trade_summary()
    tg = tt.get_target_tracker()
    cw = tcu.get_customer_watch()
    bm = tb.get_benchmark()
    gc = tt.get_target_by_cargo()
    fr = tfr.get_freshness()["sources"]
    month = pd.Timestamp(s["as_of"] + "-01").strftime("%B %Y")

    st = {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK),
        "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=MUTED),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=12.5, textColor=INK, spaceBefore=5, spaceAfter=2),
        "p": ParagraphStyle("p", fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=INK, alignment=TA_LEFT),
        "li": ParagraphStyle("li", fontName="Helvetica", fontSize=8.6, leading=11, textColor=INK, leftIndent=8, bulletIndent=0),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, textColor=INK),
        "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=INK),
        "big": ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK),
    }
    P = lambda t, k="p": Paragraph(_ascii(t), st[k])
    story = [P(f"New Mangalore Port - Trade brief, {month}", "h1"),
             P(f"Trade Intelligence module. Sources: NMPA monthly statements (to {fr['nmpa_commodity_statements']}), "
               f"Ministry of Ports reports (to {fr['ministry_major_ports']}), NMPA daily vessel reports (to {fr['nmpa_daily_reports']}). "
               f"Generated {date.today():%d %b %Y}.", "sub"), Spacer(1, 6)]

    lm, tot = s["latest_month"], s["total"]
    kp = [[P("Cargo handled, " + pd.Timestamp(s["as_of"] + "-01").strftime("%b %Y"), "sub"),
           P(f"{tg['financial_year']} so far" if tg.get("available") else "Year so far", "sub"),
           P("Needed per month for target", "sub"), P("Last 12 months", "sub")],
          [P(_mmt(lm["total_tonnes"]), "big"), P(_mmt(tg.get("done_tonnes")), "big"),
           P(_mmt(tg.get("needed_per_month_tonnes")), "big"), P(_mmt(tot["last_12_months_tonnes"]), "big")],
          [P(f"{_pct(tot['yoy_pct_latest_month'])} on a year earlier", "sub"),
           P(f"{tg.get('done_share_of_target_pct', 0):.0f}% of the {tg.get('target_tonnes', 0) / 1e6:.0f} MMT target; {_pct(tg.get('growth_so_far_pct'))} on last year", "sub"),
           P(f"{_pct(tg.get('growth_needed_on_last_year_pct'))} on the same months last year", "sub"),
           P(f"{_pct(tot['yoy_pct_last_12_months'])} on the 12 months before", "sub")]]
    t = Table(kp, colWidths=[44 * mm] * 4)
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.2, INK), ("LINEBELOW", (0, -1), (-1, -1), 0.5, RULE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    story += [t, Spacer(1, 4)]
    if tg.get("available"):
        story.append(P(tg["verdict"]))
        mo = tg["monthly"]
        d = Drawing(182 * mm, 31 * mm)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 10 * mm, 5 * mm, 168 * mm, 21 * mm
        bc.data = [[(m["last_year_tonnes"] or 0) / 1e6 for m in mo], [(m["this_year_tonnes"] or 0) / 1e6 for m in mo]]
        bc.categoryAxis.categoryNames = [pd.Timestamp(m["month"] + "-01").strftime("%b") for m in mo]
        bc.categoryAxis.labels.fontSize, bc.categoryAxis.labels.fontName = 6.5, "Helvetica"
        bc.valueAxis.labels.fontName = "Helvetica"
        bc.valueAxis.valueMin, bc.valueAxis.labels.fontSize = 0, 6.5
        bc.valueAxis.labelTextFormat = "%.0f"
        bc.bars[0].fillColor, bc.bars[1].fillColor = colors.HexColor("#D6D3D1"), colors.HexColor("#1D4E89")
        bc.bars.strokeColor = None
        bc.groupSpacing, bc.barSpacing = 3, 0.5
        d.add(bc)
        d.add(String(10 * mm, 28 * mm, "Cargo handled per month, MMT: grey = last year, blue = this year", fontSize=7, fontName="Helvetica", fillColor=MUTED))
        story += [Spacer(1, 2), d]

    story.append(P("Action list", "h2"))
    handled = {k for k, v in tfb.get_feedback()["items"].items() if v.get("status") in ("Explained", "Not relevant")}
    items = []
    for a in ti.get_trade_alerts()["alerts"]:
        d = a.get("yoy_pct_last_3_months")
        if d is not None and d < 0 and f"cargo|{a['commodity']}|{a['direction']}" not in handled:
            items.append((0, -a["share_of_direction_pct"], f"{NICE.get(a['commodity'], a['commodity'].title())} ({a['direction']}): "
                          f"down {abs(d):.0f}% on the same 3 months last year ({a['share_of_direction_pct']:.1f}% of {a['direction']} cargo)."))
    if cw.get("available"):
        for a in cw["alerts"]:
            if a["severity"] in ("high", "medium") and a["type"] != "rising" and f"customer|{a['customer']}" not in handled:
                items.append((1 if a["severity"] == "high" else 2, -(a["share_pct"] or 0), a["message"]))
    for _, _, text in sorted(items)[:6]:
        story.append(Paragraph(_ascii(text), st["li"], bulletText="-"))

    story.append(P("This year so far by cargo, against the same months last year", "h2"))
    cg = gc["cargos"]
    behind = [r for r in cg if r["change_tonnes"] < 0][:4]
    ahead = sorted([r for r in cg if r["change_tonnes"] > 0], key=lambda r: -r["change_tonnes"])[:4]
    rows = [[P("Cargo", "cellb"), P("Direction", "cellb"), P("This year (t)", "cellb"), P("Last year (t)", "cellb"),
             P("Change (t)", "cellb"), P("Change", "cellb")]]
    group_rows = []
    for label, part in (("Behind last year", behind), ("Ahead of last year", ahead)):
        if not part:
            continue
        group_rows.append(len(rows))
        rows.append([P(label, "cellb"), "", "", "", "", ""])
        for r in part:
            rows.append([P(NICE.get(r["cargo"], r["cargo"].title()), "cell"), P(r["direction"], "cell"),
                         P(f"{r['this_year_tonnes']:,}", "cell"), P(f"{r['same_months_last_year_tonnes']:,}", "cell"),
                         P(f"{r['change_tonnes']:+,}", "cell"), P(_pct(r["change_pct"]) if r["same_months_last_year_tonnes"] else "new", "cell")])
    t = Table(rows, colWidths=[44 * mm, 20 * mm, 30 * mm, 30 * mm, 30 * mm, 22 * mm])
    style = [("LINEBELOW", (0, 0), (-1, 0), 0.6, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
             ("LEFTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]
    for g in group_rows:
        style += [("SPAN", (0, g), (-1, g)), ("BACKGROUND", (0, g), (-1, g), colors.HexColor("#F2EFEA"))]
    t.setStyle(TableStyle(style))
    story.append(t)

    if cw.get("available"):
        story.append(P(f"Largest customers ({cw['period']['recent_label']} against {cw['period']['previous_label']})", "h2"))
        rows = [[P(h, "cellb") for h in ("Customer", "Main cargo", "Share of tonnes", "Change", "Status", "Days since last ship")]]
        for r in cw["customers"][:6]:
            rows.append([P(r["customer"], "cell"), P(r["main_cargo"], "cell"), P(f"{r['share_of_traced_tonnes_pct'] or 0:.1f}%", "cell"),
                         P(_pct(r["change_pct"]) if r["change_pct"] is not None else "-", "cell"), P(r["status"], "cell"),
                         P(str(r["days_since_last_call"]), "cell")])
        t = Table(rows, colWidths=[50 * mm, 38 * mm, 24 * mm, 20 * mm, 24 * mm, 20 * mm])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, INK), ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
                               ("LEFTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        story.append(t)

    ms = tmk.get_market_share()
    if bm.get("available") or ms.get("available"):
        story.append(P("Against the other major ports", "h2"))
    if bm.get("available"):
        h = bm["home"]
        story.append(P(f"New Mangalore grew {_pct(h['ytd_growth_pct'])} from {bm['period_label']}, against {_pct(bm['all_ports_ytd_growth_pct'])} "
                       f"for all major ports: {h['rank_by_growth']}th of 12 for growth and {h['rank_by_tonnes']}th for tonnes. Overseas cargo "
                       f"{_pct(h['overseas_growth_pct'])}, coastal cargo {_pct(h['coastal_growth_pct'])}."))
    if ms.get("available"):
        story.append(P(f"Market share ({ms['period_label']}): New Mangalore handles {ms['nmpa_share_of_all_major_ports_pct']:.1f}% of all major-port "
                       f"cargo. Compared with the other 11 major ports, it is gaining share in {', '.join(ms['gaining']) or 'none'}, and "
                       f"losing share in {', '.join(ms['losing']) or 'none'}."
                       + (f" Growing at other ports but not here: {', '.join(o['cargo'] for o in ms['opportunities'])}." if ms["opportunities"] else "")))
    story += [Spacer(1, 6), P("Customer tonnes are traced from NMPA daily vessel reports (about 85% of official tonnes) and are for "
                               "ranking and trends, not billing. Customer names are merged by spelling and need NMPA confirmation. Cargo and port "
                               "figures are checked against NMPA's and the Ministry's original reports.", "sub")]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=10 * mm, bottomMargin=9 * mm,
                      title=f"NMPA trade brief {month}", author="Trade Intelligence").build(story)
    return buf.getvalue()
