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
import re
import zipfile
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_market as tmk
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


def _earlier_schemes(cargo: str) -> list[str]:
    """Earlier or current NMPA schemes for the same cargo (notices register), with the net-benefit verdict where judged."""
    try:
        n = pd.read_csv(tmk.ROOT / "data" / "nmpa_incentive_notices.csv", dtype=str).fillna("")
        key = cargo.split()[0].lower().replace("z", "s")                 # fertilizer = fertiliser
        verdicts = {}
        try:
            verdicts = {r["notice"]: r["verdict"] for r in net_benefit_review()["rows"]}
        except Exception:
            pass
        out = []
        for r in n.itertuples():
            if re.search(rf"\b{re.escape(key)}s?\b", f"{r.cargos} {r.type}".lower().replace("z", "s")):            # whole words: 'iron' not in 'environmental'
                period = f"{_d(r.valid_from) if r.valid_from else '?'} to {_d(r.valid_to) if r.valid_to else '?'}"
                v = next((vv for nn, vv in verdicts.items() if nn.split(",")[0] in r.notice), "")
                out.append(f"{r.notice} ({r.type}; {period}; {r.status})" + (f": {v.lower()}" if v and v not in ("Not yet",) else ""))
        return out[:5]
    except Exception:
        return []


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
    prev = _earlier_schemes(rec["cargo"])
    x.append(_para("Earlier NMPA schemes for this cargo: " + ("; ".join(prev) + "." if prev else "none found in NMPA's notices held.")))
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
    try:
        h_ref = float(cost_reference().get("suggested_rs_per_t") or 0)
    except Exception:
        h_ref = 0.0
    x.append(_para("4. Financial implications (estimates)", bold=True))
    x.append(_table([
        ("Rate per tonne", f"Rs {f['rate']:,.2f} today; Rs {f['discounted_rate']:,.2f} with the {rec['discount_pct']:g}% discount"),
        ("Expected cost", f"{_cr(f['cost'])} ({f['cost_basis']})"),
        ("Budget cap", _cr(rec.get("budget_cap_rs")) if rec.get("budget_cap_rs") else "To be set by the Board"),
        ("Break-even", ("From the first extra tonne: existing cargo keeps the full rate." if is_rebate else
                        f"Customers must bring {f['need_pct']:.1f}% more cargo a year for the discount to pay for itself.")),
    ] + ([("Kept per extra tonne", f"Rs {f['discounted_rate']:,.2f} after the discount; at least Rs "
                                    f"{f['discounted_rate'] - h_ref:,.2f} after NMPA's published average handling cost of Rs {h_ref:.2f} "
                                    "per tonne (an upper bound: it includes fixed costs)")] if h_ref else [])))
    x.append(_para("5. Safeguards and risks", bold=True))
    try:
        bc = berth_check(rec["cargo"], float(f.get("need_pct") or 0))
        if bc.get("available"):
            x.append(_para("Berth capacity: " + bc["plain"] + (" Where a berth is nearly full in its busiest month, the scheme should "
                                                                "aim at the quieter months." if any(r["peak_pct"] >= 90 for r in bc["rows"]) else "")))
    except Exception:
        pass
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
    try:
        ans = approval_route("Incentive scheme (concession on rates)").get("answer", {})
        x.append(_para("Approval route: " + (f"{ans['authority']} (confirmed by NMPA {ans.get('confirmed_on', '')})." if ans.get("authority") else
                                             "to be confirmed by NMPA. The Major Port Authorities Act 2021 (section 27) places the Scale of "
                                             "Rates with the Board; NMPA's current delegation orders apply."), italic=True))
    except Exception:
        pass
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


# ═══════════════════════════════════════════════════════════════════
# 4. Berth capacity check: is there room at this cargo's berths for the extra cargo a discount needs?
# ═══════════════════════════════════════════════════════════════════
ROOM_BELOW_PCT = 65.0        # rule of thumb for multi-user berths, until NMPA's own berth norms are held
BUSY_ABOVE_PCT = 80.0


def _verdict(pct: float) -> str:
    return "Room" if pct < ROOM_BELOW_PCT else "Some room" if pct <= BUSY_ABOVE_PCT else "Busy"


CAP_ROOM_BELOW_PCT = 85.0    # share of NMPA's own usable capacity (Berth Capacity as on 31-3-2025)
CAP_BUSY_ABOVE_PCT = 100.0
MIN_COVERED = 0.75           # estimate a berth's tonnes only where the cargos priced here are at least 75% of its ship-days


def _cap_verdict(pct: float | None) -> str | None:
    if pct is None:
        return None
    return "Room" if pct < CAP_ROOM_BELOW_PCT else "Some room" if pct <= CAP_BUSY_ABOVE_PCT else "Busy"


def _berth_key(b: str) -> str:
    b = str(b).upper()
    return "SPM" if "SPM" in b else (re.match(r"\d+", b).group(0) if re.match(r"\d+", b) else b)


@_ttl_cache(seconds=600)
def berth_tonnes_12m() -> dict[str, Any]:
    """Estimated tonnes at each berth over the last 12 months: NMPA's official tonnes for each cargo the engine prices
    (monthly statements), spread across berths in the proportion of that cargo's ship-days at each berth (daily reports),
    then scaled up for the share of the berth's ship-days taken by other cargo."""
    occ = ie._berth_occupancy()
    wide = ti._prepared()["wide"]
    months = wide.dropna(how="all").index.sort_values()[-12:]
    covered_t, covered_days = {}, {}
    seen_fams = set()
    for c, spec in ie.CARGO.items():
        fam = spec.get("family")
        if not fam or tuple(fam) in seen_fams:
            continue
        cols = [k for k in wide.columns if tuple(k) in {tuple(x) for f2, sp2 in ie.CARGO.items()
                                                         if sp2.get("family") and tuple(sp2["family"]) == tuple(fam)
                                                         for x in sp2["keys"]}]
        seen_fams.add(tuple(fam))
        t = float(wide.loc[wide.index.isin(months), cols].sum(axis=1, min_count=1).sum()) if cols else 0.0
        fb = occ["fam_berths"].get(tuple(fam), {})
        n = sum(fb.values())
        for b, d in fb.items():
            k = _berth_key(b)
            covered_t[k] = covered_t.get(k, 0.0) + t * d / n if n else covered_t.get(k, 0.0)
            covered_days[k] = covered_days.get(k, 0) + d
    all_days = {}
    for fam, fb in occ["fam_berths"].items():
        for b, d in fb.items():
            all_days[_berth_key(b)] = all_days.get(_berth_key(b), 0) + d
    out = {}
    for k, t in covered_t.items():
        frac = covered_days.get(k, 0) / all_days[k] if all_days.get(k) else 0
        out[k] = {"tonnes": t / frac if frac >= MIN_COVERED else None, "covered_share": round(frac, 2)}
    return {"berths": out, "months": f"{months[0]:%b %Y} to {months[-1]:%b %Y}"}


def _capacity() -> dict[str, float]:
    from backend.app.services.trade_market import ROOT as _ROOT
    f = _ROOT / "data" / "nmpa_berth_capacity.csv"
    return {} if not f.exists() else {str(r.berth): float(r.usable_capacity_mt) for r in pd.read_csv(f, dtype={"berth": str}).itertuples()}


@_ttl_cache(seconds=600)
def berth_check(cargo: str, extra_pct: float) -> dict[str, Any]:
    """The berths this cargo uses (daily reports), how often each had a ship in the last 12 months, and how busy they
    would be if this cargo grew by extra_pct (extra ship-days in proportion to this cargo's share of the berth's use)."""
    if cargo not in ie.CARGO:
        raise KeyError(cargo)
    occ = ie._berth_occupancy()
    family = ie.CARGO[cargo].get("family")
    fam = occ["fam_berths"].get(tuple(family), {}) if family else {}
    if not fam:
        return {"available": False, "cargo": cargo, "reason": "This cargo was not recorded at any berth in the daily reports."}
    months = sorted(occ["days"])[-12:]
    report_days = sum(occ["days"][m] for m in months)
    total_use = {}                                               # ship-records per berth, all cargos
    for f, berths in occ["fam_berths"].items():
        for b, n in berths.items():
            total_use[b] = total_use.get(b, 0) + n
    ranked = sorted(fam.items(), key=lambda kv: -kv[1])
    cover, main = 0, []
    for b, n in ranked:                                          # the berths carrying 80% of this cargo's ship-days
        main.append(b); cover += n
        if cover >= 0.8 * sum(fam.values()):
            break
    caps, bton = _capacity(), berth_tonnes_12m()
    wide = ti._prepared()["wide"]
    cols = [k for k in wide.columns if tuple(k) in {tuple(x) for x in ie.CARGO[cargo]["keys"]}]
    this_t = float(wide.loc[wide.dropna(how="all").index.sort_values()[-12:], cols].sum(axis=1, min_count=1).sum()) if cols else 0.0
    rows = []
    for b in main:
        busy_days = sum(occ["occ"].get((b, m), 0) for m in months)
        now = busy_days / report_days * 100 if report_days else 0.0
        peak_m = max(months, key=lambda m: occ["occ"].get((b, m), 0) / max(occ["days"][m], 1))
        peak = occ["occ"].get((b, peak_m), 0) / max(occ["days"][peak_m], 1) * 100
        share = fam[b] / total_use[b] if total_use.get(b) else 1.0
        after = min(100.0, now * (1 + share * extra_pct / 100))
        k = _berth_key(b)
        cap_mt = caps.get(k)
        bt = bton["berths"].get(k, {})
        used = (bt["tonnes"] / (cap_mt * 1e6) * 100) if (cap_mt and bt.get("tonnes")) else None
        used_after = (used + this_t * (fam[b] / sum(fam.values())) * extra_pct / 100 / (cap_mt * 1e6) * 100) if used is not None else None
        v_occ, v_cap = _verdict(after), _cap_verdict(used_after)
        order = {"Room": 0, "Some room": 1, "Busy": 2}
        rows.append({"berth": b, "cargo_share_pct": round(share * 100), "busy_now_pct": round(now, 1),
                     "busy_after_pct": round(after, 1), "peak_month": pd.Timestamp(peak_m + "-01").strftime("%b %Y"),
                     "peak_pct": round(peak, 1), "verdict_now": _verdict(now),
                     "usable_capacity_mt": cap_mt, "tonnes_12m_mt": round(bt["tonnes"] / 1e6, 2) if bt.get("tonnes") else None,
                     "capacity_used_pct": round(used, 1) if used is not None else None,
                     "capacity_used_after_pct": round(used_after, 1) if used_after is not None else None,
                     "verdict_capacity": v_cap,
                     "verdict_after": max([v for v in (v_occ, v_cap) if v], key=lambda v: order[v])})
    worst = max(rows, key=lambda r: r["busy_after_pct"])
    plain = (f"{cargo} uses berth(s) {', '.join(r['berth'] for r in rows)}. With {extra_pct:.1f}% more {cargo}, the busiest of them "
             f"(berth {worst['berth']}) would have a ship on about {worst['busy_after_pct']:.0f}% of days, against "
             f"{worst['busy_now_pct']:.0f}% now: {worst['verdict_after'].lower()}."
             + (f" Berth(s) with room: {', '.join(r['berth'] for r in rows if r['verdict_after'] == 'Room')}: route the extra "
                f"cargo there where possible." if any(r["verdict_after"] == "Room" for r in rows) and worst["verdict_after"] != "Room" else "")
             + (f" Berth {worst['berth']} would be beyond NMPA's usable capacity ({worst['capacity_used_after_pct']:.0f}%)."
                if (worst.get("capacity_used_after_pct") or 0) > CAP_BUSY_ABOVE_PCT else ""))
    return {
        "available": True, "cargo": cargo, "extra_pct": extra_pct, "rows": rows, "verdict": worst["verdict_after"],
        "plain": plain, "months": f"{pd.Timestamp(months[0] + '-01'):%b %Y} to {pd.Timestamp(months[-1] + '-01'):%b %Y}",
        "thresholds": {"room_below_pct": ROOM_BELOW_PCT, "busy_above_pct": BUSY_ABOVE_PCT},
        "method": ("Two checks, the stricter one decides. (1) Days with a ship: share of daily reports in the last 12 months on "
                   "which the berth had a ship; 'room' below 65%, 'busy' above 80% (rules of thumb for multi-user berths). "
                   "(2) Capacity: estimated tonnes at the berth (NMPA's official tonnes for each cargo, spread across berths by "
                   "ship-days in the daily reports) against NMPA's usable capacity (Berth Capacity as on 31-3-2025); 'room' "
                   "below 85%, 'busy' above 100%. Estimated only where the cargos priced here make up at least 75% of the "
                   "berth's ship-days; otherwise only the first check is used. Containers at Berth 14 are counted in boxes, "
                   "so its tonnes are not estimated."),
        "source": "NMPA daily vessel position reports (berths occupied each day)",
    }


# ═══════════════════════════════════════════════════════════════════
# 5. Shared budget pool (as at Incheon): a fixed amount shared among customers by their extra cargo
# ═══════════════════════════════════════════════════════════════════

def allocate_pool(extra_t: dict[str, float], pool_rs: float, cap_rs_per_t: float) -> dict[str, Any]:
    """Share pool_rs among customers in proportion to their extra tonnes (only growth counts), with no customer paid more
    than cap_rs_per_t per extra tonne. What is not paid stays with the port. Total paid never exceeds the pool."""
    extra = {c: max(0.0, float(t)) for c, t in extra_t.items()}
    total = sum(extra.values())
    rows = []
    for c, t in extra.items():
        share = t / total if total else 0.0
        pay = min(pool_rs * share, cap_rs_per_t * t)
        rows.append({"customer": c, "extra_t": round(t), "share_pct": round(share * 100, 1), "pay_rs": round(pay),
                     "pay_per_extra_t_rs": round(pay / t, 2) if t else 0.0, "capped": pool_rs * share > cap_rs_per_t * t + 0.5})
    rows.sort(key=lambda r: -r["pay_rs"])
    paid = sum(r["pay_rs"] for r in rows)
    return {"rows": rows, "pool_rs": round(pool_rs), "paid_rs": round(paid), "unspent_rs": round(pool_rs - paid),
            "extra_total_t": round(total), "customers_rewarded": sum(1 for r in rows if r["pay_rs"] > 0)}


def pool_simulation(cargo: str, pool_rs: float, cap_pct_of_rate: float = 50.0) -> dict[str, Any]:
    """If a pool for this cargo had run over the latest months that can be compared with a year earlier (daily reports),
    who would have received what."""
    from backend.app.services import trade_customers as tc
    if cargo not in ie.CARGO:
        raise KeyError(cargo)
    fam = ie.CARGO[cargo].get("family")
    if not fam:
        return {"available": False, "reason": "This cargo is not identified in the daily reports."}
    b = tc.build()
    complete = list(b.get("complete") or [])
    pairs = [(m, (pd.Timestamp(m + "-01") - pd.DateOffset(years=1)).strftime("%Y-%m")) for m in complete]
    pairs = [(m, p) for m, p in pairs if p in complete]
    if not pairs:
        return {"available": False, "reason": "No month in the daily reports can yet be compared with the same month a year earlier."}
    v = b["voyages"]
    v = v[(v["family"] == fam[0]) & (v["direction"] == fam[1]) & v["customer"].notna()]
    cur_m, prev_m = [m for m, _ in pairs], [p for _, p in pairs]
    cur = v[v["month"].isin(cur_m)].groupby("customer")["tonnes"].sum()
    prev = v[v["month"].isin(prev_m)].groupby("customer")["tonnes"].sum()
    custs = sorted(set(cur.index) | set(prev.index))
    extra = {c: float(cur.get(c, 0)) - float(prev.get(c, 0)) for c in custs}
    rate = ie.scenario(cargo, 10.0)["rate_rs_per_t"]
    cap = rate * cap_pct_of_rate / 100
    a = allocate_pool(extra, pool_rs, cap)
    for r in a["rows"]:
        r["prev_t"], r["cur_t"] = round(float(prev.get(r["customer"], 0))), round(float(cur.get(r["customer"], 0)))
    lbl = lambda ms: ", ".join(pd.Timestamp(x + "-01").strftime("%b %Y") for x in ms)
    return {"available": True, "cargo": cargo, **a, "rate_rs_per_t": rate, "cap_pct_of_rate": cap_pct_of_rate,
            "cap_rs_per_t": round(cap, 2), "period": lbl(cur_m), "compared_with": lbl(prev_m),
            "customers_falling": sum(1 for c in custs if extra[c] < 0),
            "method": ("Extra cargo = each customer's tonnes in the months shown minus the same months a year earlier (daily "
                       "reports); only growth counts. The pool is shared in proportion to extra tonnes, with no customer paid more "
                       f"than {cap_pct_of_rate:g}% of the wharfage rate per extra tonne. What is not paid stays with NMPA, so the "
                       "total paid can never exceed the pool. Modelled on Incheon Port's incentive programmes."),
            "source": "NMPA daily vessel position reports (customers and tonnes); NMPA Scale of Rates (wharfage rate)"}


# ═══════════════════════════════════════════════════════════════════
# 6. Public cost reference: NMPA's published cargo-handling cost per tonne
# ═══════════════════════════════════════════════════════════════════

def cost_reference() -> dict[str, Any]:
    """Average cargo handling & storage expenditure per tonne from NMPA's budget documents (data/nmpa_cost_reference.csv).
    It includes fixed costs (salaries), so the true cost of an extra tonne is lower: a cautious upper bound."""
    from backend.app.services.trade_market import ROOT as _ROOT
    f = _ROOT / "data" / "nmpa_cost_reference.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f)
    d = d[d["traffic_lakh_t"].notna() & d["cargo_handling_expenditure_cr"].notna()]
    if d.empty:
        return {"available": False}
    rows = []
    for r in d.itertuples():
        t = r.traffic_lakh_t * 1e5
        rows.append({"year": r.year, "basis": r.basis,
                     "handling_cost_per_t_rs": round(r.cargo_handling_expenditure_cr * 1e7 / t, 2),
                     "handling_income_per_t_rs": round(r.cargo_handling_income_cr * 1e7 / t, 2) if pd.notna(r.cargo_handling_income_cr) else None,
                     "operating_cost_per_t_rs": round(r.operating_expenditure_cr * 1e7 / t, 2) if pd.notna(r.operating_expenditure_cr) else None,
                     "source": r.source, "url": r.url})
    pick = next((x for x in reversed(rows) if x["basis"] == "Actual"), None)
    rev = next((x for x in reversed(rows) if x["basis"] == "Revised Estimate"), None)
    use = rev or pick
    return {"available": True, "rows": rows, "suggested_rs_per_t": use["handling_cost_per_t_rs"],
            "suggested_basis": f"{use['basis']} {use['year']}",
            "plain": (f"NMPA's published cargo handling & storage expenditure works out at about \u20b9{use['handling_cost_per_t_rs']:.2f} "
                      f"per tonne ({use['basis']} {use['year']}). It includes fixed costs such as salaries, so the real cost of an "
                      f"extra tonne is lower: use it as a cautious upper bound."),
            "source": use["source"], "url": use["url"]}


# ═══════════════════════════════════════════════════════════════════
# 7. Turnaround benchmark: New Mangalore against the other major ports (Ministry figures)
# ═══════════════════════════════════════════════════════════════════

def turnaround_benchmark() -> dict[str, Any]:
    """Average turnaround time of each major port by year (Ministry, Parliament reply), with New Mangalore's rank, and
    NMPA's own latest year-to-date figure (operational performance statements) for the current year."""
    from backend.app.services.trade_market import ROOT as _ROOT
    f = _ROOT / "data" / "major_ports_turnaround.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f)
    years = [c for c in d.columns if re.fullmatch(r"20\d{2}-\d{2}", c)]
    last = years[-1]
    ports = d[d["port"] != "All Major Ports"].sort_values(last).reset_index(drop=True)
    avg = float(d.loc[d["port"] == "All Major Ports", last].iloc[0]) if (d["port"] == "All Major Ports").any() else None
    nm = int(ports.index[ports["port"] == "New Mangalore Port"][0])
    nm_val = float(ports.loc[nm, last])
    ytd = None
    p = _ROOT / "data" / "nmpa_performance_monthly.csv"
    if p.exists():
        perf = pd.read_csv(p)
        x = perf[(perf.metric == "turn_round_time_hrs") & (perf.basis == "pilot") & (perf.category == "overall")
                 & (perf.period == "ytd") & (perf.year == "current")].sort_values("report_month")
        if not x.empty:
            ytd = {"hours": round(float(x.value.iloc[-1]), 2), "through": pd.Timestamp(x.report_month.iloc[-1] + "-01").strftime("%b %Y")}
    rank_now = None
    if ytd:
        others = ports[ports["port"] != "New Mangalore Port"]
        rank_now = int((others[last] < ytd["hours"]).sum()) + 1                 # ports faster than this year's level, plus one
    plain = (f"In {last} New Mangalore's average turnaround was {nm_val:.2f} hours: {nm + 1} of {len(ports)} major ports"
             + (f", against an all-ports average of {avg:.2f}" if avg else "") + ".")
    if ytd:
        plain += (f" This year so far (to {ytd['through']}) it is {ytd['hours']:.2f} hours"
                  + (f": at that level it would rank about {rank_now} of {len(ports)} on last year's figures." if rank_now else "."))
    return {"available": True, "year": last, "years": years,
            "ports": [{"port": r["port"], "hours": float(r[last]), "series": [float(r[y]) for y in years]}
                      for _, r in ports.iterrows()],
            "all_ports_avg": avg, "nmpa_rank": nm + 1, "nmpa_hours": nm_val, "nmpa_ytd": ytd, "rank_at_ytd": rank_now,
            "plain": plain,
            "source": ("Ministry of Ports, Shipping and Waterways, written reply in the Lok Sabha (Annexure I, Aug 2026); "
                       "New Mangalore's current year from NMPA's operational performance statements")}


# ═══════════════════════════════════════════════════════════════════
# 8. Approval route: who approves what. References only until NMPA confirms; nothing unconfirmed is enforced
# ═══════════════════════════════════════════════════════════════════

def approval_route(decision: str | None = None, amount_rs: float | None = None) -> dict[str, Any]:
    """The approval route NMPA has confirmed (data/approval_matrix.csv, rows with confirmed_by_nmpa = yes), and the
    reference documents. Rows NMPA has not confirmed are shown as 'to confirm' and are never used to allow or block anything.
    For a decision and an amount, the confirmed authority is the one with the lowest limit that covers the amount."""
    from backend.app.services.trade_market import ROOT as _ROOT
    mx = pd.read_csv(_ROOT / "data" / "approval_matrix.csv", dtype=str).fillna("")
    refs = pd.read_csv(_ROOT / "data" / "approval_references.csv", dtype=str).fillna("")
    mx["confirmed"] = mx["confirmed_by_nmpa"].str.strip().str.lower().isin(["yes", "y", "true"])
    out = {"rows": mx.drop(columns=["confirmed_by_nmpa"]).to_dict("records"), "references": refs.to_dict("records"),
           "confirmed_rows": int(mx["confirmed"].sum()),
           "rule": ("Approval limits are used only after NMPA confirms them (approval_matrix.csv: confirmed_by_nmpa = yes, with "
                    "the date). Older delegation documents are references, not current rules; general financial powers do not by "
                    "themselves establish who approves incentive claims.")}
    if decision:
        m = mx[(mx["decision"] == decision) & mx["confirmed"]].copy()
        if m.empty:
            out["answer"] = {"confirmed": False, "authority": None,
                             "message": f"Approval authority for '{decision}' is not yet confirmed by NMPA."}
        else:
            m["limit"] = pd.to_numeric(m["up_to_rs"], errors="coerce")
            ok = m[m["limit"].isna() | (m["limit"] >= (amount_rs or 0))].sort_values("limit", na_position="last")
            out["answer"] = ({"confirmed": True, "authority": ok.iloc[0]["authority"], "basis": ok.iloc[0]["basis"],
                              "confirmed_on": ok.iloc[0]["confirmed_on"]} if not ok.empty else
                             {"confirmed": True, "authority": None,
                              "message": "No confirmed authority covers this amount: refer upwards (e.g. the Board)."})
    return out


def charter_standards() -> dict[str, Any]:
    """NMPA's Citizen's Charter service standards, with NMPA's actual output per ship berth-day for comparison."""
    from backend.app.services.trade_market import ROOT as _ROOT
    f = _ROOT / "data" / "nmpa_citizen_charter_standards.csv"
    if not f.exists():
        return {"available": False}
    d = pd.read_csv(f)
    out = {"available": True, "standards": d.to_dict("records"), "source": "NMPA Citizen's Charter 2024-25"}
    p = _ROOT / "data" / "nmpa_performance_monthly.csv"
    if p.exists():
        perf = pd.read_csv(p)
        x = perf[(perf.metric == "output_per_berth_day_t") & (perf.category == "overall") & (perf.period == "ytd")
                 & (perf.year == "current")].sort_values("report_month")
        if not x.empty:
            out["actual_output_per_berth_day_t"] = round(float(x.value.iloc[-1]))
            out["actual_through"] = pd.Timestamp(x.report_month.iloc[-1] + "-01").strftime("%b %Y")
    return out


def cargo_at_risk() -> dict[str, Any]:
    """Cargos where New Mangalore lost share of all major ports (Ministry data), and the tonnes it would have handled at
    last year's share."""
    m = tmk.get_market_share()
    rows = []
    for c in m.get("cargos", []):
        if c["cargo"] in m.get("losing", []):
            gap = c["all_ports_tonnes"] * (c["share_prev_pct"] - c["share_pct"]) / 100
            rows.append({"cargo": c["cargo"], "share_prev_pct": c["share_prev_pct"], "share_pct": c["share_pct"], "tonnes_at_stake": round(gap)})
    rows.sort(key=lambda r: -r["tonnes_at_stake"])
    return {"rows": rows, "total_t": sum(r["tonnes_at_stake"] for r in rows), "period": m.get("period_label"),
            "compared_with": m.get("previous_period_label")}


def busy_berths() -> list[dict]:
    """Berths whose estimated tonnes in the last 12 months are at or beyond NMPA's usable capacity (where estimated)."""
    caps, bt = _capacity(), berth_tonnes_12m()["berths"]
    out = []
    for k, v in bt.items():
        if v.get("tonnes") and caps.get(k):
            pct = v["tonnes"] / (caps[k] * 1e6) * 100
            if pct >= CAP_ROOM_BELOW_PCT:
                out.append({"berth": k, "used_pct": round(pct), "tonnes_mt": round(v["tonnes"] / 1e6, 2), "usable_mt": caps[k]})
    return sorted(out, key=lambda r: -r["used_pct"])


# ═══════════════════════════════════════════════════════════════════
# 9. Did it pay for itself? Net benefit of each NMPA scheme judged so far
# ═══════════════════════════════════════════════════════════════════
# What each scheme gave up and what an extra tonne earns. Costs are taken only from figures the engine already holds;
# where a cost cannot be worked out it is said so, never guessed.
NET_SPECS = {
    "NMPA/TM/Fertiliser/2025-26": {"rate_cargo": "Fertilizer (finished)", "kind": "no_money",
                                   "cost_note": "Priority berthing: no charge was given up."},
    "NMPA/TM/2025-26/Gen.2, amended by Gen.3": {"rate_cargo": "Crude oil", "kind": "relief", "cost": "waiver"},
    "NMPA/TM/IOF-Exp-Rebate/26-27": {"rate_cargo": "Iron ore exports", "kind": "incremental", "rebate_pct": 20.0},
    "12/1/2021-22/ATM Gr.I (Com)/JSW": {"kind": "ship_charges",
                                       "cost_note": "Not priced: needs the GRT of each Cape-size call (on NMPA's bills)."},
    "NMPA/TM/Trade Notice/2026 (corrigendum)": {"kind": "relief",
                                                "cost_note": "Not priced: the ground rent waived per container is not in the data held."},
    "Comrc/DTM(C)/2026-27/01": {"kind": "ship_charges",
                                "cost_note": "Not priced: needs the GRT of each container call (on NMPA's bills)."},
}


def net_benefit_review() -> dict[str, Any]:
    from backend.app.services import incentive_scheme_review as sr
    rv = sr.get_scheme_review()
    h_hi = (cost_reference() or {}).get("suggested_rs_per_t") or 0.0          # NMPA's average handling cost: a cautious upper bound
    out = []
    for r in rv.get("rows", []):
        spec = NET_SPECS.get(r["notice"], {})
        row = {"short": r["short"], "notice": r["notice"], "result": r.get("result"), "extra_t": r.get("extra_t"),
               "kind": spec.get("kind"), "cost_rs": None, "earned_low_rs": None, "earned_high_rs": None,
               "net_low_rs": None, "net_high_rs": None, "verdict": "", "why": ""}
        rate = ie._rate(ie.CARGO[spec["rate_cargo"]]["rate"])["foreign"] if spec.get("rate_cargo") else None
        # what the scheme gave up
        if spec.get("kind") == "no_money":
            row["cost_rs"] = 0.0
        elif spec.get("cost") == "waiver":
            try:
                row["cost_rs"] = float(ie.waiver_cost()["total_rs"])
                row["cost_basis"] = "Wharfage waived on the ships that could have qualified (an upper estimate)"
            except Exception:
                row["cost_rs"] = None
        elif spec.get("kind") == "incremental" and rate and r.get("extra_t") is not None:
            row["cost_rs"] = max(0.0, r["extra_t"]) * rate * spec["rebate_pct"] / 100
        # what extra cargo earned (only cargo above what the market would explain counts; none if it fell)
        if r.get("extra_t") is not None and rate:
            keep = rate * (1 - spec.get("rebate_pct", 0) / 100)
            et = max(0.0, r["extra_t"])
            row["earned_high_rs"], row["earned_low_rs"] = et * keep, et * (keep - h_hi)
        if r.get("extra_t") is None or not r.get("available", True):
            row["verdict"], row["why"] = "Not yet", r.get("result") or "Not judged yet"
        elif row["cost_rs"] is None:
            row["verdict"], row["why"] = "Cost not priced", spec.get("cost_note", "The cost could not be worked out from the data held.")
        elif row["earned_high_rs"] is None:
            row["verdict"], row["why"] = "Earnings not priced", "No wharfage rate held for this cargo group."
        else:
            row["net_low_rs"], row["net_high_rs"] = row["earned_low_rs"] - row["cost_rs"], row["earned_high_rs"] - row["cost_rs"]
            firm = not any(w in (r.get("result") or "").lower() for w in ("too few", "information", "not enough"))
            if not firm:
                row["verdict"] = "Indicative only"
            elif row["net_low_rs"] > 0:
                row["verdict"] = "Paid for itself (so far)"
            elif row["net_high_rs"] < 0:
                row["verdict"] = "Did not pay for itself (so far)"
            else:
                row["verdict"] = "Close to break-even"
            row["why"] = (("No extra cargo above the market was measured, so nothing was earned from it. " if (r["extra_t"] or 0) <= 0 else "")
                          + ("A relief measure: judge it on keeping cargo and goodwill in a crisis, not on profit. " if spec.get("kind") == "relief" else "")
                          + ("Not yet a firm result: " + r["result"].lower() + "." if "too few" in (r.get("result") or "").lower() else ""))
        out.append(row)
    return {"rows": out, "handling_cost_rs_per_t": h_hi,
            "method": ("Earned = extra tonnes above what the market explains (the scheme review) x the wharfage NMPA keeps per tonne; "
                       f"shown with no handling cost and with NMPA's published average of Rs {h_hi:.2f} per tonne (an upper bound). "
                       "Cost = what the scheme gave up, only where the engine can work it out. Net = earned - cost. Results follow the "
                       "review: a scheme the review cannot judge yet is not judged here either."),
            "source": "Scheme review; NMPA Scale of Rates; NMPA budget document (handling cost); daily vessel reports (waiver cost)"}


# ═══════════════════════════════════════════════════════════════════
# 10. Compare scheme designs side by side (the officer chooses; nothing is decided here)
# ═══════════════════════════════════════════════════════════════════

def compare_designs(cargo: str, discount_pct: float, extra_pct: float, pool_crore: float | None = None) -> dict[str, Any]:
    """For one cargo, one discount and one assumption of extra cargo, what each scheme design would cost NMPA in a year and
    what it would earn back. Estimates from NMPA's tonnes and Scale of Rates; handling cost = NMPA's published average
    (an upper bound)."""
    if cargo not in ie.CARGO:
        raise KeyError(cargo)
    from backend.app.services import incentive_scheme_review as sr
    h = float(cost_reference().get("suggested_rs_per_t") or 0)
    sc = ie.scenario(cargo, discount_pct, cost_per_t=h)                # break-even on the same basis as the net figures
    r, d, base = sc["rate_rs_per_t"], discount_pct / 100, sc["baseline_tonnes_per_year"]
    e = base * extra_pct / 100                                      # extra tonnes assumed
    keep_extra = r - h                                              # what an extra tonne earns before any discount
    try:
        q = sr.readiness_condition()["qualifying_tonnes_pct"] / 100
    except Exception:
        q = None
    pool = (pool_crore * 1e7) if pool_crore else e * r * d          # default pool = what the rebate on extra would cost
    rows = []
    # A. discount on all cargo
    cost_a = base * r * d + e * r * d
    rows.append({"design": "Discount on all cargo", "cost_rs": cost_a, "net_rs": e * keep_extra - cost_a,
                 "pays_when": f"{sc['break_even_extra_pct_blanket']:.1f}% more cargo a year" if not sc["never_breaks_even"] else "never",
                 "customers_must": "nothing: every tonne gets the discount",
                 "main_risk": "pays on all the cargo that would have come anyway"})
    # B. rebate on extra cargo only
    cost_b = e * r * d
    rows.append({"design": "Rebate on extra cargo only", "cost_rs": cost_b, "net_rs": e * keep_extra - cost_b,
                 "pays_when": "from the first extra tonne" if r * (1 - d) > h else "never (handling cost is higher)",
                 "customers_must": "bring more than last year",
                 "main_risk": "growth that would have come anyway is rewarded; set the baseline carefully"})
    # C. shared budget pool
    spent = min(pool, cost_b) if e > 0 else 0.0
    rows.append({"design": "Shared budget pool", "cost_rs": spent, "net_rs": e * keep_extra - spent,
                 "pays_when": f"total paid can never exceed {pool / 1e7:,.2f} crore",
                 "customers_must": "bring more than last year; share the pool by extra tonnes",
                 "main_risk": "a small pool may be too little to change a large customer's decision"})
    # D. pay only when the customer is ready (rebate on extra, only for calls where the customer was ready)
    if q is not None:
        cost_d = e * r * d * q
        rows.append({"design": "Rebate only when the customer is ready", "cost_rs": cost_d, "net_rs": e * keep_extra - cost_d,
                     "pays_when": "from the first extra tonne",
                     "customers_must": "bring more cargo and have cargo and documents ready (no waiting on their side)",
                     "main_risk": "needs NMPA to confirm readiness per call; customers may find it strict"})
    for x in rows:
        x["cost_rs"], x["net_rs"] = round(x["cost_rs"]), round(x["net_rs"])
    return {"cargo": cargo, "discount_pct": discount_pct, "extra_pct": extra_pct, "extra_t": round(e), "baseline_t": base,
            "rate_rs_per_t": r, "handling_rs_per_t": h, "readiness_share_pct": round(q * 100, 1) if q is not None else None,
            "rows": rows,
            "note": ("Assumes the extra cargo comes in all designs; whether it does depends on the design and the customer. "
                     "Handling cost uses NMPA's published average (an upper bound). The readiness share is for all cargo "
                     "(calls in the last six months where the customer was ready). The officer chooses; nothing is decided here."),
            "source": "NMPA monthly statements and Scale of Rates; NMPA budget document; NMPA daily vessel reports"}
