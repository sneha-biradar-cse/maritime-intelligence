"""
Decision aids for the Incentive Engine: three things that help NMPA decide, approve and renew schemes.

1. Growth check ("chance it pays for itself")
   A discount on all cargo pays for itself only if customers bring discount / (1 - discount) more cargo a year
   (10% -> 11.1%). This checks how often NMPA's cargo of that type has actually grown that much in a year, using every
   twelve-month period in NMPA's monthly statements. That growth happened WITHOUT this discount, so it shows how big
   the ask is, not what a discount would cause.

2. Schemes ending soon, with a review pack
   Every scheme in force (NMPA's notices) and every approved scheme in the register, with days left. For each: how it is
   doing against the other major ports (incentive_scheme_review), what it costs where that can be priced, and a
   renew / change / stop recommendation in plain words.

3. Board agenda note and trade notice, drafted from a scheme in the register
   Word files (.docx) built from the register's own figures: purpose, background, proposal, cost and break-even,
   safeguards, the legal basis (Section 27(1), Major Port Authorities Act 2021) and the resolution sought. Drafts only:
   every figure is an estimate from NMPA's published rates and statements, for Traffic and Finance to check.
   Written with the standard library (no extra package to install).
"""
from __future__ import annotations

import datetime as _dt
import io
import zipfile
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_intelligence as ti
from backend.app.services.forecasting import _ttl_cache

REVIEW_NOW_DAYS = 90         # a scheme ending within this many days needs its review now
PLAN_REVIEW_DAYS = 180       # within this many days, plan the review
LEGAL_BASIS = ("Section 27(1) of the Major Port Authorities Act, 2021, under which the Board frames the Scale of Rates and "
               "its conditions, read with the Tariff Policy for Major Port Authorities, 2021. The rates in the Scale of Rates "
               "are ceilings, so the Board may approve lower rates and rebates.")


def _d(iso: str) -> str:
    d = _dt.date.fromisoformat(str(iso)[:10])
    return f"{d.day} {d:%B %Y}"


def _data_version(dv: Any) -> str:
    """The register's data version, in words: which months of each source the figures use."""
    if not isinstance(dv, dict):
        return str(dv or "")
    month = lambda v: f"{pd.Timestamp(v + '-01'):%B %Y}" if len(str(v)) == 7 else _d(v)
    parts = [f"{lbl} to {month(dv[k])}" for k, lbl in (("nmpa_statements_through", "NMPA statements"),
                                                        ("ministry_reports_through", "Ministry reports"),
                                                        ("daily_reports_through", "daily vessel reports")) if dv.get(k)]
    return "; ".join(parts)


def _cr(rs: float | None) -> str:
    return "not priced" if rs is None else f"Rs {rs / 1e7:,.2f} crore"


# ═══════════════════════════════════════════════════════════════════
# 1. Growth check
# ═══════════════════════════════════════════════════════════════════

def _monthly_tonnes(cargo: str) -> pd.Series:
    wide = ti._prepared()["wide"]
    keys = ie.CARGO[cargo]["keys"]
    cols = [c for c in wide.columns if tuple(c) in {tuple(k) for k in keys}]
    s = wide[cols].sum(axis=1, min_count=1).sort_index() if cols else pd.Series(dtype=float)
    return s.asfreq("MS") if len(s) else s


@_ttl_cache(seconds=300)
def growth_check(cargo: str, discount_pct: float) -> dict[str, Any]:
    if cargo not in ie.CARGO:
        raise KeyError(cargo)
    if not 0 < discount_pct < 100:
        raise ValueError("discount_pct must be between 0 and 100")
    d = discount_pct / 100
    need = d / (1 - d) * 100
    s = _monthly_tonnes(cargo)
    roll = s.rolling(12, min_periods=12).sum()
    g = ((roll / roll.shift(12) - 1) * 100).replace([np.inf, -np.inf], np.nan).dropna()
    if len(g) < 6:
        return {"available": False, "cargo": cargo, "need_pct": round(need, 1),
                "reason": "Fewer than six twelve-month periods are held for this cargo, so there is no history to compare with."}
    hits = int((g >= need).sum())
    share = hits / len(g) * 100
    lbl = lambda t: f"{t - pd.DateOffset(months=11):%b %Y} to {t:%b %Y}"
    span = f"the first ending {g.index[0]:%b %Y}, the latest ending {g.index[-1]:%b %Y}"
    if share < 20:
        reading = ("Rarely: a discount on all cargo would need more growth than this cargo usually achieves. A rebate on "
                   "extra cargo only is the safer design.")
    elif share < 50:
        reading = "Sometimes, but not usually: the discount is a real bet on customers responding."
    else:
        reading = ("Often: this cargo grows that much on its own in many years, so check that the growth would not have "
                   "come anyway; otherwise the discount gives money away.")
    plain = (f"A {discount_pct:g}% discount on all {cargo} pays for itself only if customers bring {need:.1f}% more a year. "
             f"In {hits} of the last {len(g)} twelve-month periods ({span}), NMPA's {cargo} "
             f"grew that much without this discount ({share:.0f}%). {reading}")
    return {
        "available": True, "cargo": cargo, "discount_pct": discount_pct, "need_pct": round(need, 1),
        "periods": int(len(g)), "hits": hits, "share_pct": round(share, 0),
        "typical_low_pct": round(float(np.percentile(g, 10)), 1), "typical_high_pct": round(float(np.percentile(g, 90)), 1),
        "median_pct": round(float(g.median()), 1), "latest_pct": round(float(g.iloc[-1]), 1),
        "latest_period": lbl(g.index[-1]), "reading": reading, "plain": plain,
        "series": [{"period_end": t.strftime("%Y-%m"), "growth_pct": round(float(v), 1)} for t, v in g.items()],
        "method": ("Each point compares twelve months of NMPA's tonnes with the twelve months before. Break-even growth for "
                   "a discount on all cargo = discount / (1 - discount). A rebate on extra cargo only breaks even from the "
                   "first extra tonne, because existing cargo keeps the full rate."),
        "source": "NMPA monthly commodity statements",
    }


# ═══════════════════════════════════════════════════════════════════
# 2. Schemes ending soon, with a review pack
# ═══════════════════════════════════════════════════════════════════

def _recommend(result: str, relief: bool, simple_check: bool = False) -> str:
    r = (result or "").lower()
    if simple_check and (r.startswith("worse") or r.startswith("better")):
        return ("Look closer before deciding: this is a broad check of the whole cargo group, not of the scheme's own "
                "calls. Ask for the scheme's ship calls (e.g. Berth 16 Cape-size calls and their sizes) to judge it properly.")
    if r.startswith("more cargo") or r.startswith("better"):
        return "Renew: the evidence so far supports it. Keep the design; check the cost against the budget."
    if relief and (r.startswith("less") or r.startswith("worse") or r.startswith("within")):
        return "Relief measure: judge it on whether the disruption has passed, not on extra cargo."
    if r.startswith("within") or r.startswith("in line"):
        return ("Change before renewing: no clear effect so far. Consider paying only on extra cargo, adding the "
                "customer-readiness condition, or narrowing it to the customers who responded.")
    if r.startswith("less") or r.startswith("worse"):
        return "Do not renew as it is: cargo did worse than at the other major ports during the scheme."
    if r.startswith("cannot be measured"):
        return "Ask Finance for billing by customer and cargo: public data cannot separate this cargo, so it cannot be judged yet."
    return ("Too early to judge: the Ministry publishes each month's figures 4 to 6 weeks later. Schedule the review "
            "after the scheme's months are published, or extend briefly while the evidence comes in.")


def _cost_line(notice: str) -> str:
    try:
        from backend.app.services import vessel_charges as vc
        if notice.startswith("Comrc/DTM(C)"):
            return vc.container_rebate().get("plain", "")
        if "JSW" in notice:
            return vc.capesize_rebate().get("plain", "")
        if "IOF-Exp-Rebate" in notice:
            m = ie.iron_ore_rebate_monitor()
            return (f"Since the scheme began: {m['since_scheme_t']:,} t exported, against {m['since_scheme_prev_t']:,} t in the "
                    f"same days a year earlier. The rebate is Rs {m['rebate_per_extra_t_rs']:,.2f} per extra tonne, paid only "
                    f"on tonnes above each exporter's FY 2025-26 quantity, after verification.")
    except Exception:                                          # a cost that cannot be worked out is reported, not guessed
        return "Cost could not be worked out from the data held."
    return ""


def expiring_schemes(today: _dt.date | None = None) -> dict[str, Any]:
    from backend.app.services import incentive_scheme_review as sr
    today = today or _dt.date.today()
    from backend.app.services.trade_market import ROOT as _ROOT
    notices = pd.read_csv(_ROOT / "data" / "nmpa_incentive_notices.csv", dtype=str).fillna("")
    review = {r["notice"]: r for r in sr.get_scheme_review()["rows"]}
    relief = {s["notice"] for s in sr.SCHEMES if s.get("relief")}
    rows = []
    for _, n in notices.iterrows():
        if not n["status"].startswith("In force") or not n["valid_to"]:
            continue
        rows.append({"source": "NMPA notice", "notice": n["notice"], "what": n["type"] or n["benefit"],
                     "cargo": n["cargos"], "ends": n["valid_to"][:10]})
    for s in ie._load_schemes():
        if s.get("status") in ("Approved", "Active", "In force") and s.get("end"):
            rows.append({"source": "Scheme register", "notice": s.get("approval_reference") or s["id"],
                         "what": f"{s['scope']}, {s['discount_pct']}%", "cargo": s["cargo"], "ends": s["end"][:10]})
    out = []
    for r in rows:
        end = _dt.date.fromisoformat(r["ends"])
        days = (end - today).days
        if days < 0:
            continue
        rv = review.get(r["notice"], {})
        band = "Review now" if days <= REVIEW_NOW_DAYS else "Plan the review" if days <= PLAN_REVIEW_DAYS else "Running"
        out.append({**r, "days_left": days, "band": band,
                    "result": rv.get("result", "Not judged"), "evidence": rv.get("plain", ""),
                    "cost": _cost_line(r["notice"]),
                    "check": rv.get("check", ""),
                    "recommendation": _recommend(rv.get("result", ""), r["notice"] in relief, rv.get("check") == "Simple check")})
    out.sort(key=lambda x: x["days_left"])
    return {"available": True, "today": today.isoformat(), "rows": out,
            "review_now": sum(1 for x in out if x["band"] == "Review now"),
            "plan_review": sum(1 for x in out if x["band"] == "Plan the review"),
            "thresholds": {"review_now_days": REVIEW_NOW_DAYS, "plan_review_days": PLAN_REVIEW_DAYS},
            "source": "NMPA's incentive notices (data/nmpa_incentive_notices.csv) and the scheme register"}


# ═══════════════════════════════════════════════════════════════════
# 3. Board agenda note and trade notice (Word drafts)
# ═══════════════════════════════════════════════════════════════════

def _run(text: str, bold: bool = False, size: int | None = None, italic: bool = False) -> str:
    props = ("<w:b/>" if bold else "") + ("<w:i/>" if italic else "") + (f'<w:sz w:val="{size}"/>' if size else "")
    return f'<w:r>{"<w:rPr>" + props + "</w:rPr>" if props else ""}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(text: str = "", bold: bool = False, size: int | None = None, align: str | None = None,
          italic: bool = False, space_after: int = 120) -> str:
    jc = '<w:jc w:val="%s"/>' % align if align else ""
    ppr = f'<w:pPr>{jc}<w:spacing w:after="{space_after}"/></w:pPr>'
    return f"<w:p>{ppr}{_run(text, bold, size, italic) if text else ''}</w:p>"


def _table(rows: list[tuple[str, str]]) -> str:
    border = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="999999"/>' for s in
                     ("top", "left", "bottom", "right", "insideH", "insideV"))
    trs = "".join(
        f'<w:tr><w:tc><w:tcPr><w:tcW w:w="3200" w:type="dxa"/></w:tcPr>{_para(a, bold=True, space_after=40)}</w:tc>'
        f'<w:tc><w:tcPr><w:tcW w:w="6400" w:type="dxa"/></w:tcPr>{_para(b, space_after=40)}</w:tc></w:tr>' for a, b in rows)
    return (f'<w:tbl><w:tblPr><w:tblW w:w="9600" w:type="dxa"/><w:tblBorders>{border}</w:tblBorders></w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="3200"/><w:gridCol w:w="6400"/></w:tblGrid>{trs}</w:tbl>{_para()}')


def _docx(body_xml: str) -> bytes:
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           f'{body_xml}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/>'
           '</w:sectPr></w:body></w:document>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" '
              'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def _scheme(sid: str) -> dict:
    rec = next((s for s in ie._load_schemes() if s["id"] == sid), None)
    if rec is None:
        raise KeyError(sid)
    return rec


def _figures(rec: dict) -> dict[str, Any]:
    d = rec["discount_pct"] / 100
    rate = rec.get("rate_rs_per_t") or ie.scenario(rec["cargo"], rec["discount_pct"])["rate_rs_per_t"]
    base = rec.get("baseline_tonnes") or 0
    n_months = max(1, len(rec.get("months") or []))
    if rec["scope"] == "Blanket discount":
        cost = rate * d * base
        cost_basis = "rate x discount x baseline tonnes (the discount given on cargo that comes anyway)"
    else:
        tgt = rec.get("success_target_t")
        cost = rate * d * tgt if tgt else None
        cost_basis = "rate x rebate x target extra tonnes (paid only on cargo above the baseline)"
    return {"rate": rate, "discounted_rate": rate * (1 - d), "baseline": base, "months": n_months, "cost": cost,
            "cost_basis": cost_basis, "need_pct": d / (1 - d) * 100}


def board_note_docx(sid: str) -> bytes:
    rec = _scheme(sid)
    f = _figures(rec)
    try:
        gc = growth_check(rec["cargo"], rec["discount_pct"])
    except Exception:
        gc = {"available": False}
    el = rec.get("eligibility") or {}
    import re as _re
    _dates = lambda t: _re.sub(r"\b(20\d\d-\d\d-\d\d)\b", lambda m: _d(m.group(1)), t)
    blocks = [_dates(b.get("message", str(b)) if isinstance(b, dict) else str(b)) for b in el.get("blocks", [])]
    warns = [_dates(w.get("message", str(w)) if isinstance(w, dict) else str(w)) for w in el.get("warnings", [])]
    today = _dt.date.today().strftime("%d.%m.%Y")
    period = f"{_d(rec['start'])} to {_d(rec['end'])}"
    is_rebate = rec["scope"] != "Blanket discount"
    x = []
    x.append(_para("DRAFT FOR DISCUSSION", bold=True, size=18, align="right", italic=True))
    x.append(_para("NEW MANGALORE PORT AUTHORITY", bold=True, size=28, align="center", space_after=40))
    x.append(_para("AGENDA NOTE FOR THE MEETING OF THE BOARD", bold=True, size=24, align="center"))
    x.append(_para(f"Subject: Proposal for a {rec['scope'].lower()} of {rec['discount_pct']:g}% on {rec['cargo']} "
                   f"({rec['id']}), {period}", bold=True))
    x.append(_para("1. Purpose", bold=True))
    x.append(_para(f"To seek the Board's approval for a {rec['scope'].lower()} of {rec['discount_pct']:g}% on the wharfage for "
                   f"{rec['cargo']}, from {_d(rec['start'])} to {_d(rec['end'])}, to "
                   + ("attract cargo above the agreed baseline." if is_rebate else "retain and attract cargo.")))
    x.append(_para("2. Background", bold=True))
    x.append(_para(f"The baseline for this scheme is {f['baseline']:,.0f} tonnes ({rec.get('baseline_basis', '')}). "
                   f"Wharfage is charged at Rs {f['rate']:,.2f} per tonne under the Scale of Rates ({rec.get('tariff_version', '')})."))
    if gc.get("available") and not is_rebate:
        x.append(_para(gc["plain"]))
    x.append(_para("3. Proposal", bold=True))
    x.append(_table([
        ("Scheme", f"{rec['scope']}, {rec['discount_pct']:g}% on wharfage"),
        ("Cargo", rec["cargo"]),
        ("Period", period),
        ("Eligible customers", rec.get("customers") or "All users handling this cargo"),
        ("Baseline", f"{f['baseline']:,.0f} t: {rec.get('baseline_basis', '')}"),
        ("Slabs", "; ".join(f"up to {t['up_to_pct_above_baseline']}% above baseline: {t['rebate_pct']}%"
                            if t.get("up_to_pct_above_baseline") else f"all extra cargo: {t['rebate_pct']}%"
                            for t in rec.get("tiers", [])) or "Not applicable"),
        ("Conditions", rec.get("conditions") or "None beyond the standard conditions of the Scale of Rates"),
        ("Customer commitment", f"{rec['commitment_t']:,.0f} t" if rec.get("commitment_t") else "None"),
        ("Clawback if the commitment is missed", {"proportional": "Rebate reduced in proportion to the shortfall",
                                                  "all_or_nothing": "No rebate if the commitment is missed"}.get(rec.get("clawback_rule", ""), "Not specified")),
        ("Settlement", rec.get("settlement") or "At billing" if not is_rebate else rec.get("settlement") or "After the period, on verification"),
        ("Success target", f"{rec['success_target_t']:,.0f} t extra" if rec.get("success_target_t") else "To be set"),
        ("Stop rule", rec.get("stop_rule") or "To be set"),
    ]))
    x.append(_para("4. Financial implications (estimates)", bold=True))
    x.append(_table([
        ("Rate per tonne", f"Rs {f['rate']:,.2f} today; Rs {f['discounted_rate']:,.2f} with the {rec['discount_pct']:g}% discount"),
        ("Expected cost", f"{_cr(f['cost'])} ({f['cost_basis']})"),
        ("Budget cap", _cr(rec.get("budget_cap_rs")) if rec.get("budget_cap_rs") else "To be set by the Board"),
        ("Break-even", ("From the first extra tonne: existing cargo keeps the full rate." if is_rebate else
                        f"Customers must bring {f['need_pct']:.1f}% more cargo a year for the discount to pay for itself.")),
    ]))
    x.append(_para("5. Safeguards and risks", bold=True))
    x.append(_para("Overlap with schemes in force: " + ("none found." if not blocks else "BLOCKED: " + "; ".join(blocks))))
    if warns:
        x.append(_para("Points to note: " + "; ".join(warns)))
    x.append(_para("The scheme will be reviewed against the other major ports' trend for the same cargo (Ministry of Ports "
                   "monthly data), so that only growth beyond the market is credited to it, and checked for known ways of "
                   "gaming a discount (holding cargo back before the start, timing shifts, related firms, berth shifts)."))
    x.append(_para("6. Legal basis", bold=True))
    x.append(_para(LEGAL_BASIS + " On approval, the scheme will be notified to the trade by a Trade Notice."))
    x.append(_para("7. Resolution sought", bold=True))
    x.append(_para(f"The Board may consider and approve the {rec['scope'].lower()} of {rec['discount_pct']:g}% on {rec['cargo']} "
                   f"for the period {period}, on the terms set out in paragraph 3, within a budget of "
                   f"{_cr(rec.get('budget_cap_rs')) if rec.get('budget_cap_rs') else '[amount]'}, and authorise the Traffic "
                   "Department to issue the Trade Notice."))
    x.append(_para())
    x.append(_para(f"Draft prepared on {today} with the YellowSense Incentive Engine (scheme {rec['id']}; data used: "
                   f"{_data_version(rec.get('data_version'))}). All figures are estimates from NMPA's published Scale of Rates and monthly "
                   "statements, for the Traffic and Finance Departments to verify before the meeting.", italic=True, size=18))
    return _docx("".join(x))


def trade_notice_docx(sid: str) -> bytes:
    rec = _scheme(sid)
    f = _figures(rec)
    is_rebate = rec["scope"] != "Blanket discount"
    today = _dt.date.today().strftime("%d.%m.%Y")
    x = []
    x.append(_para("DRAFT", bold=True, size=18, align="right", italic=True))
    x.append(_para("NEW MANGALORE PORT AUTHORITY", bold=True, size=28, align="center", space_after=40))
    x.append(_para("Traffic Department", align="center", space_after=40))
    x.append(_para("Panambur, Mangaluru - 575 010", align="center"))
    x.append(_para("No.: [to be assigned]                                                    Date: [dd.mm.yyyy]"))
    x.append(_para("TRADE NOTICE", bold=True, size=26, align="center"))
    x.append(_para(f"Sub: {rec['scope']} of {rec['discount_pct']:g}% on wharfage for {rec['cargo']}, "
                   f"{_d(rec['start'])} to {_d(rec['end'])} - reg.", bold=True))
    x.append(_para("The trade and all port users are hereby informed that the Board of New Mangalore Port Authority, vide "
                   "Board Resolution No. [ ] dated [ ], under Section 27(1) of the Major Port Authorities Act, 2021, has "
                   f"approved a {rec['scope'].lower()} on wharfage for {rec['cargo']} on the following terms:"))
    terms = [
        f"Benefit: {rec['discount_pct']:g}% " + ("on the wharfage for cargo above the baseline" if is_rebate
                                                else "on the wharfage") + f" (Rs {f['discounted_rate']:,.2f} per tonne instead of Rs {f['rate']:,.2f}).",
        f"Period: from {_d(rec['start'])} to {_d(rec['end'])}, both days inclusive.",
        f"Eligibility: {rec.get('customers') or 'all users handling ' + rec['cargo'] + ' at NMPA berths'}.",
    ]
    if is_rebate:
        terms.append(f"Baseline: {f['baseline']:,.0f} tonnes ({rec.get('baseline_basis', '')}). The rebate applies only to "
                     "tonnes handled above the baseline during the period.")
    if rec.get("conditions"):
        terms.append(f"Conditions: {rec['conditions']}")
    if rec.get("commitment_t"):
        terms.append(f"Commitment: {rec['commitment_t']:,.0f} tonnes during the period. "
                     + {"proportional": "If the commitment is not met, the rebate will be reduced in proportion to the shortfall.",
                        "all_or_nothing": "If the commitment is not met, no rebate will be payable."}.get(rec.get("clawback_rule", ""), ""))
    terms.append("Settlement: " + (rec.get("settlement") or ("after the end of the period, on verification of the quantities "
                                                             "handled" if is_rebate else "at the time of billing")) + ".")
    terms.append("This benefit cannot be combined with any other rebate or concession on the same charge for the same cargo.")
    terms.append("The Port reserves the right to verify the quantities and to modify or withdraw the scheme.")
    for i, t in enumerate(terms, 1):
        x.append(_para(f"{i}. {t}"))
    x.append(_para("All port users are requested to take note."))
    x.append(_para())
    x.append(_para("Traffic Manager", bold=True, align="right", space_after=40))
    x.append(_para("New Mangalore Port Authority", align="right"))
    x.append(_para())
    x.append(_para(f"Draft prepared on {today} from scheme {rec['id']} in the YellowSense Incentive Engine; to be issued only "
                   "after the Board's approval, with the Board Resolution number and date filled in.", italic=True, size=18))
    return _docx("".join(x))
