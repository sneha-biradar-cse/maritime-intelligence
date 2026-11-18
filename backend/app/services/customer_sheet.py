"""
Customer call sheet: one page for a Traffic officer before calling a customer. Made only when asked; nothing is sent.

Facts from the engine (key customers, the daily vessel reports, NMPA's notices) and, at the end, suggested talking points
built from those facts. The suggestions are prompts for the officer, not decisions or promises to the customer.
"""
from __future__ import annotations

import datetime as _dt
import io
import re
from typing import Any

import pandas as pd

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_customers as tcu
from backend.app.services import trade_market as tmk


def _cr(v) -> str:
    return "-" if v is None else f"Rs {v / 1e7:,.2f} cr"


def sheet(customer: str) -> dict[str, Any]:
    kc = ie.get_key_customers()
    row = next((r for r in kc.get("rows", []) if r["customer"] == customer), None)
    b = tcu.build()
    v = b["voyages"]
    x = v[v["customer"] == customer]
    if row is None and x.empty:
        raise KeyError(customer)
    complete = list(b.get("complete") or sorted(v["month"].unique()))[-6:]
    monthly = [{"month": pd.Timestamp(m + "-01").strftime("%b %Y"), "tonnes": round(float(x.loc[x["month"] == m, "tonnes"].fillna(0).sum())),
                "ships": int(x.loc[x["month"] == m, "vessel"].nunique())} for m in complete]
    cargo_fams = sorted({str(f) for f in x["family"].dropna()})
    # waiting on the customer's side (last six months)
    ready = None
    try:
        from backend.app.services import incentive_scheme_review as sr
        rc = sr.readiness_condition()
        ready = next((r for r in rc.get("by_customer", []) if r["customer"] == customer), None)
        ready_window = rc.get("window")
    except Exception:
        ready_window = None
    # schemes in force that match the customer's cargo
    schemes = []
    try:
        n = pd.read_csv(tmk.ROOT / "data" / "nmpa_incentive_notices.csv", dtype=str).fillna("")
        generic = {"fuel", "other", "petroleum", "limestone"}                 # 'fuel' oil is not 'green fuels'
        keys = {f.split()[0].lower().replace("z", "s") for f in cargo_fams if f} - generic
        if row and row.get("main_cargo"):
            keys.add(row["main_cargo"].split()[0].lower().replace("z", "s"))
        keys -= generic
        for r in n[n["status"] == "In force"].itertuples():
            text = f"{r.cargos} {r.type}".lower().replace("z", "s")
            if any(re.search(rf"\b{re.escape(k)}s?\b", text) for k in keys):
                schemes.append({"notice": r.notice, "what": r.type, "benefit": r.benefit, "until": r.valid_to})
    except Exception:
        pass
    names = sorted(set(b.get("raw_by_customer", {}).get(customer, [])) - {customer})
    # suggested talking points
    pts = []
    status = (row or {}).get("status", "")
    if status in ("Falling", "Falling fast", "Stopped"):
        pts.append("Their wharfage fell last quarter: ask what changed (their plant, prices, shipping, or another port).")
    elif ((row or {}).get("change_q2_vs_q1_rs") or 0) < 0:
        pts.append("Their wharfage was a little lower last quarter (within normal ups and downs): ask how the coming months look.")
    elif status == "Rising":
        pts.append("Their cargo is rising: thank them, and ask about volumes and any new cargo planned for next year.")
    if ready and ready.get("ship_days_lost", 0) > 0:
        pts.append(f"Their ships waited {ready['ship_days_lost']:.0f} ship-days at anchorage because the cargo or documents "
                   f"were not ready ({ready_window}). Ask what would help them be ready earlier; this costs them and the port.")
    caution = {}
    try:
        for e in ie.iron_ore_rebate_monitor().get("exporters", []):
            if "own arrangement" in e.get("status", "").lower() or "confirm" in e.get("status", "").lower():
                for part in e["customer"].split(" + "):
                    caution[part.strip()] = e["status"]
    except Exception:
        pass
    for sch in schemes[:2]:
        txt = (f"Make sure they know about {sch['notice']} ({sch['what'].lower()}: {sch['benefit']}), valid until "
               f"{sch['until'] or 'notified'}, and how to claim it.")
        if "IOF" in sch["notice"] and customer in caution:
            txt = (f"Before mentioning {sch['notice']} (iron ore rebate), confirm their eligibility with Traffic: "
                   f"{caution[customer]}")
        pts.append(txt)
    if row and not row.get("owner"):
        pts.append("No account owner is recorded: agree who in Traffic follows up with them.")
    pts.append("Ask whether another port has offered them better terms, and what would keep their cargo at New Mangalore.")
    return {"customer": customer, "row": row, "monthly": monthly, "cargo": cargo_fams, "ready": ready, "ready_window": ready_window,
            "schemes": schemes, "names": names, "talking_points": pts, "period": kc.get("period"),
            "prepared_on": _dt.date.today().strftime("%d.%m.%Y"),
            "note": ("Facts from NMPA's daily vessel reports, monthly statements and notices; wharfage is estimated (tonnes x Scale of "
                     "Rates), not billed. Talking points are suggestions for the officer, not commitments to the customer.")}


def sheet_pdf(customer: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    s = sheet(customer)
    asc = lambda t: str(t).replace("\u20b9", "Rs ").encode("latin-1", "replace").decode("latin-1")
    st = getSampleStyleSheet()
    h, b, sm = st["Heading3"], st["BodyText"], st["Italic"]
    b.fontSize, b.leading, sm.fontSize = 9.5, 12.5, 8
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    el = [Paragraph(asc(f"Customer call sheet: {s['customer']}"), st["Title"]),
          Paragraph(asc(f"Prepared {s['prepared_on']} on request, for the Traffic officer. {s['note']}"), sm), Spacer(1, 4)]
    r = s["row"] or {}
    el.append(Paragraph("1. At a glance", h))
    el.append(Paragraph(asc(
        f"Main cargo: {r.get('main_cargo') or ', '.join(s['cargo']) or 'not stated'}. "
        + (f"Share of traced wharfage: {r['share_pct']:.1f}%; estimated wharfage {_cr(r['wharfage_rs'])} ({s['period']}). "
           f"Last quarter {_cr(r['wharfage_q2_rs'])} against {_cr(r['wharfage_q1_rs'])} the quarter before: {r['status'].lower()}. "
           f"Risk: {r['risk']}." if r else "Not among the customers making up most of NMPA's traced wharfage.")), b))
    el.append(Paragraph("2. Cargo month by month (daily vessel reports)", h))
    tb = Table([["Month", "Tonnes", "Ships"]] + [[m["month"], f"{m['tonnes']:,}", str(m["ships"])] for m in s["monthly"]],
               colWidths=[40 * mm, 35 * mm, 20 * mm])
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    el.append(tb)
    el.append(Paragraph("3. Waiting on their side", h))
    rd = s["ready"]
    el.append(Paragraph(asc(
        f"{s['ready_window']}: {rd['calls']} calls; the customer was ready on {rd['qualifying']} ({rd['qualifying_pct']:.0f}%). "
        f"Ship-days lost at anchorage because their cargo or documents were not ready: {rd['ship_days_lost']:.0f}."
        if rd else "No waiting on the customer's side recorded in the last six months."), b))
    el.append(Paragraph("4. NMPA schemes they can use now", h))
    el.append(Paragraph(asc("; ".join(f"{x['notice']}: {x['what']} ({x['benefit']}), until {x['until'] or 'notified'}" for x in s["schemes"])
                            or "None in force for their cargo."), b))
    el.append(Paragraph("5. Names they appear under in the daily reports", h))
    el.append(Paragraph(asc(", ".join(s["names"]) or "Only one spelling found."), b))
    el.append(Paragraph("6. Follow-up so far (recorded by Traffic)", h))
    el.append(Paragraph(asc(", ".join(f"{k}: {r[k]}" for k in ("owner", "stage", "reason", "follow_up") if r.get(k)) or "Nothing recorded yet."), b))
    el.append(Paragraph("7. Suggested talking points", h))
    for p in s["talking_points"]:
        el.append(Paragraph(asc("- " + p), b))
    doc.build(el)
    return buf.getvalue()
