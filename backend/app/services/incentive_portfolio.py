"""
All discounts together: one budget, one stacking rule, and a year-end settlement for each scheme.

  * Portfolio budget - what every approved or active scheme could cost, against what the port earns, with a Board-set cap.
    Spain's ports law is the model: an Authority's commercial bonuses in a year may not exceed 20% of its fee income, and
    bonuses on one fee for one traffic may not exceed 40% together. NMPA's Board sets its own numbers in
    data/incentive_policy.json; until it does, nothing is capped and the screen says so.
  * Stacking rule   - by default discounts cannot be combined (incentive_rules.COMBINATION_RULE). If the Board allows
    combination up to a ceiling, an overlap within the ceiling becomes a warning instead of a block.
  * Settlement      - like a loyalty card: the rebate is worked out at the end, against the volume the customer committed
    to; if the commitment is missed, part or all of the rebate is not paid (or is recovered). Rotterdam settles its volume
    discount after the year and Chennai's 2026-27 scheme asks for long-term commitments.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from backend.app.services import incentive_engine as ie
from backend.app.services import incentive_rules as ir
from backend.app.services import trade_market as tmk

POLICY_FILE = "data/incentive_policy.json"
DEFAULT_POLICY = {
    "portfolio_cap_pct_of_wharfage": None, "max_combined_benefit_pct": None, "allow_combination": False,
    "default_clawback_rule": "proportional", "set_by": "", "approval_reference": "",
    "note": ("To be set by NMPA's Board. Example from Spain's ports law: commercial bonuses in a year at most 20% of fee income, "
             "and at most 40% together on one fee for one traffic."),
}
CLAWBACK_RULES = {"proportional": "Rebate reduced in proportion to the shortfall",
                  "all_or_nothing": "No rebate if the commitment is missed"}


def policy() -> dict:
    f = tmk.ROOT / POLICY_FILE
    if not f.exists():
        return dict(DEFAULT_POLICY)
    try:
        return {**DEFAULT_POLICY, **json.loads(f.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULT_POLICY)


def save_policy(changes: dict, by: str = "") -> dict:
    allowed = {"portfolio_cap_pct_of_wharfage", "max_combined_benefit_pct", "allow_combination", "default_clawback_rule",
               "approval_reference", "note"}
    bad = set(changes) - allowed
    if bad:
        raise ValueError(f"unknown policy fields {sorted(bad)}")
    if changes.get("default_clawback_rule") not in (None, *CLAWBACK_RULES):
        raise ValueError(f"default_clawback_rule must be one of {list(CLAWBACK_RULES)}")
    for k in ("portfolio_cap_pct_of_wharfage", "max_combined_benefit_pct"):
        v = changes.get(k)
        if v is not None and not 0 < float(v) <= 100:
            raise ValueError(f"{k} must be between 0 and 100")
    p = {**policy(), **changes, "set_by": by, "set_on": date.today().isoformat()}
    (tmk.ROOT / POLICY_FILE).write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def annual_wharfage_rs() -> tuple[float, str]:
    rev = ie.get_revenue()
    months = len(ie._fy_months(ie.ti._prepared()["wide"].index.max())[0])
    tot = sum(r["revenue_rs"] for r in rev["cargos"])
    return tot / max(months, 1) * 12, f"wharfage on the cargos priced here, {rev.get('period', 'this year')}, scaled to 12 months"


def _projected_cost(res: dict) -> float | None:
    cost = res.get("estimated_discount_cost_rs")
    held, total = len(res.get("months_held") or []), res.get("months_total") or 0
    if cost is None or not held:
        return None
    return cost / held * total


def portfolio() -> dict[str, Any]:
    pol = policy()
    base, base_note = annual_wharfage_rs()
    rows, pipeline = [], []
    for rec in ie._load_schemes():
        if rec["status"] in ("Traffic review", "Finance review"):
            pipeline.append({"id": rec["id"], "cargo": rec["cargo"], "status": rec["status"], "budget_cap_rs": rec.get("budget_cap_rs") or 0})
        if rec["status"] not in ("Approved", "Active", "Completed"):
            continue
        res = ie.scheme_results(rec)
        proj = _projected_cost(res)
        cap = rec.get("budget_cap_rs") or 0
        exposure = max(cap, proj or 0)
        used = (res.get("extra_tonnes_vs_baseline") or 0) > 0
        rows.append({"id": rec["id"], "cargo": rec["cargo"], "customer": rec.get("customer") or "All users", "status": rec["status"],
                     "discount_pct": rec["discount_pct"], "budget_cap_rs": cap, "cost_to_date_rs": res.get("estimated_discount_cost_rs"),
                     "projected_cost_rs": None if proj is None else round(proj), "exposure_rs": round(exposure),
                     "months_held": len(res.get("months_held") or []), "months_total": res.get("months_total"),
                     "used": used if res.get("months_held") else None})
    exposure = sum(r["exposure_rs"] for r in rows if r["status"] != "Completed")
    pct = exposure / base * 100 if base else None
    cap = pol.get("portfolio_cap_pct_of_wharfage")
    started = [r for r in rows if r["used"] is not None]
    uptake = {"schemes_started": len(started), "schemes_earning_extra_cargo": sum(1 for r in started if r["used"]),
              "plain": ("No scheme has run long enough to measure." if not started else
                        f"{sum(1 for r in started if r['used'])} of {len(started)} running schemes have brought cargo above "
                        "their baseline so far.")}
    if cap is None:
        status = "No cap set"
        plain = (f"Approved and active schemes could cost up to \u20b9{exposure:,.0f} a year, {pct or 0:.1f}% of the port's "
                 f"estimated wharfage (\u20b9{base:,.0f}). The Board has not set a total cap yet "
                 "(data/incentive_policy.json).")
    else:
        status = "Over the cap" if pct and pct > cap else "Within the cap"
        plain = (f"Approved and active schemes could cost up to \u20b9{exposure:,.0f} a year: {pct or 0:.1f}% of estimated wharfage, "
                 f"against the Board's cap of {cap:g}%. {status}.")
    notices = [b for b in ir.KNOWN_BENEFIT_PERIODS
               if b["to"] >= date.today().isoformat()]
    return {"policy": pol, "annual_wharfage_rs": round(base), "base_note": base_note, "schemes": rows, "pipeline": pipeline,
            "exposure_rs": round(exposure), "exposure_pct": None if pct is None else round(pct, 2), "status": status,
            "plain": plain, "uptake": uptake,
            "nmpa_notices_in_force": [{"name": n["name"], "to": n["to"]} for n in notices],
            "limits": ["Exposure = the larger of each scheme's budget cap and its cost projected from the months held.",
                       "NMPA's own notices in force are listed but not costed here; ship-charge rebates are priced under "
                       "Ship charges, once ship sizes are known.",
                       "Wharfage only; ship charges are not in the base yet."]}


def combination_check(cargo: str, start: str, end: str, discount_pct: float | None, overlaps: list[dict]) -> dict:
    """Used by incentive_rules.check_eligibility when the Board allows combining discounts up to a ceiling."""
    pol = policy()
    if not pol.get("allow_combination") or pol.get("max_combined_benefit_pct") is None or discount_pct is None:
        return {"allowed": False}
    # the ceiling is per charge (as in Spain's law): only benefits on the same charge (wharfage) add up
    combined = discount_pct + sum(float(o.get("pct") or 0) for o in overlaps if o.get("charge", "wharfage") == "wharfage")
    ceiling = float(pol["max_combined_benefit_pct"])
    return {"allowed": combined <= ceiling, "combined_pct": combined, "ceiling_pct": ceiling,
            "plain": f"Together with overlapping discounts the benefit is {combined:g}% (Board ceiling {ceiling:g}%)."}


def settlement(rec: dict) -> dict[str, Any]:
    """Year-end settlement of one scheme: rebate earned, the customer's commitment, any shortfall and what is not paid
    (or recovered)."""
    res = ie.scheme_results(rec)
    held, total = res.get("months_held") or [], res.get("months_total") or 0
    cost = res.get("estimated_discount_cost_rs")
    actual = res.get("actual_tonnes")
    commit = rec.get("commitment_t")
    rule = rec.get("clawback_rule") or policy()["default_clawback_rule"]
    mode = rec.get("settlement") or ("After the period" if rec["scope"] == "Rebate on extra volume" else "At billing")
    out = {"id": rec["id"], "months_held": held, "months_total": total, "rebate_to_date_rs": cost,
           "projected_rebate_rs": None if _projected_cost(res) is None else round(_projected_cost(res)),
           "actual_tonnes": actual, "commitment_t": commit, "clawback_rule": rule, "clawback_rule_label": CLAWBACK_RULES.get(rule, rule),
           "settlement_mode": mode, "status_label": "Estimate from traced/statement tonnes; final figures need NMPA billing."}
    if not held or cost is None:
        out["plain"] = "Nothing to settle yet: no month of the scheme is in the data."
        return out
    if not commit:
        out["plain"] = (f"Rebate so far about \u20b9{cost:,.0f} ({len(held)} of {total} months). No volume commitment is recorded, "
                        "so nothing can be clawed back; record one when the scheme is agreed.")
        return out
    complete = len(held) >= total
    due_so_far = commit * len(held) / max(total, 1)
    if not complete:
        gap = (actual or 0) - due_so_far
        out.update({"commitment_to_date_t": round(due_so_far), "ahead_or_behind_t": round(gap)})
        out["plain"] = (f"{len(held)} of {total} months: {actual or 0:,.0f} t against {due_so_far:,.0f} t committed so far "
                        + ("(on track)." if gap >= 0 else f"(behind by {-gap:,.0f} t). Remind the customer before the period ends."))
        return out
    shortfall = max(commit - (actual or 0), 0.0)
    if shortfall == 0:
        claw = 0.0
    elif rule == "all_or_nothing":
        claw = cost
    else:
        claw = cost * shortfall / commit
    final = cost - claw
    out.update({"shortfall_t": round(shortfall), "clawback_rs": round(claw), "final_rebate_rs": round(final)})
    if shortfall == 0:
        out["plain"] = f"Commitment met ({actual:,.0f} t against {commit:,.0f} t). Rebate due: about \u20b9{final:,.0f}."
    elif mode == "At billing":
        out["plain"] = (f"Commitment missed by {shortfall:,.0f} t. The discount was given on each bill, so about \u20b9{claw:,.0f} "
                        f"is to be recovered from the customer ({CLAWBACK_RULES.get(rule, rule).lower()}).")
    else:
        out["plain"] = (f"Commitment missed by {shortfall:,.0f} t. Pay about \u20b9{final:,.0f} instead of \u20b9{cost:,.0f} "
                        f"({CLAWBACK_RULES.get(rule, rule).lower()}).")
    return out


def retention_option(baseline_t: float, rate: float, discount_pct: float, share_at_risk_pct: float = 100.0) -> dict:
    """'Please don't leave': a discount on ALL of a customer's cargo to keep it. Worth it only if the chance of losing the
    cargo without the discount is above the break-even chance."""
    d = discount_pct / 100
    cost = baseline_t * rate * d
    at_risk = baseline_t * share_at_risk_pct / 100 * rate * (1 - d)
    be = cost / at_risk * 100 if at_risk else None
    return {"option": f"Retention offer ({discount_pct:g}% on all of this cargo, to keep it)", "tariff_change": "Lower rate on every tonne",
            "cost_rs": round(cost), "revenue_at_risk_rs": round(baseline_t * share_at_risk_pct / 100 * rate),
            "break_even_chance_pct": None if be is None else round(be, 1),
            "notes": (f"Worth it only if, without the offer, the chance of losing {share_at_risk_pct:g}% of this cargo is above "
                      f"{be:.0f}% - and the offer actually keeps it. Every tonne that would have stayed anyway also gets the "
                      "discount (money given away)." if be is not None else "No baseline tonnes.")}
