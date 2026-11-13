"""
Finance check: our wharfage estimates against NMPA's bills.

NMPA Finance uploads a CSV of what was actually billed (month, cargo, charge, tonnes, amount). For each cargo and
month the engine's estimate is worked out with exactly the method of What we earn (incentive_engine.get_revenue):
statement tonnes x a blended rate (foreign / coastal split, SPM / berth split for crude, customers billed under their
own arrangement left out), at the Scale of Rates in force in that month where the engine holds it.

Two kinds of difference are shown separately, so Finance can see why an estimate is off:
  tonnes: NMPA's statement tonnes (what the engine uses) against the tonnes actually billed
  rate:   the engine's rate per tonne against the rate actually billed (amount / tonnes)
Accuracy = 1 - sum |estimate - billed| / sum billed, over the cargos and months uploaded.

The uploaded file stays on this computer (data/finance_billing.csv, kept out of GitHub by .gitignore).
"""
from __future__ import annotations

import io
from typing import Any

import pandas as pd

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_intelligence as ti
from backend.app.services.trade_market import ROOT

FILE = ROOT / "data" / "finance_billing.csv"
COLUMNS = ["month", "cargo", "charge", "tonnes", "amount_rs"]
CHARGES = ["wharfage", "port_dues", "pilotage", "berth_hire", "other"]
CURRENT_FROM = "2026-05"          # first month of the Scale of Rates in force today (from 1 May 2026)
SOR_2025_26_MONTHS = ("2025-05", "2026-04")


def template_csv() -> str:
    return ",".join(COLUMNS) + "\n"


def parse(text: str) -> tuple[pd.DataFrame | None, list[str]]:
    """Read and check an uploaded CSV. Returns (table, problems); nothing is saved if there is any problem."""
    problems: list[str] = []
    try:
        d = pd.read_csv(io.StringIO(text), dtype=str).fillna("")
    except Exception as e:                                   # not a CSV at all
        return None, [f"The file could not be read as CSV: {e}"]
    d.columns = [c.strip().lower() for c in d.columns]
    missing = [c for c in COLUMNS if c not in d.columns]
    if missing:
        return None, [f"Missing column(s): {', '.join(missing)}. The template has: {', '.join(COLUMNS)}."]
    if d.empty:
        return None, ["The file has no rows."]
    d = d[COLUMNS].copy()
    for c in COLUMNS:
        d[c] = d[c].astype(str).str.strip()
    d["charge"] = d["charge"].str.lower().str.replace(" ", "_")
    for i, r in d.iterrows():
        line = i + 2                                         # line number as seen in Excel (header is line 1)
        try:
            pd.Timestamp(r["month"] + "-01")
            if len(r["month"]) != 7:
                raise ValueError
        except Exception:
            problems.append(f"Line {line}: month '{r['month']}' must look like 2026-05.")
        if r["cargo"] not in ie.CARGO:
            problems.append(f"Line {line}: cargo '{r['cargo']}' is not one of: {', '.join(ie.CARGO)}.")
        if r["charge"] not in CHARGES:
            problems.append(f"Line {line}: charge '{r['charge']}' must be one of: {', '.join(CHARGES)}.")
        for c in ("tonnes", "amount_rs"):
            try:
                if float(str(r[c]).replace(",", "")) < 0:
                    raise ValueError
            except ValueError:
                problems.append(f"Line {line}: {c} '{r[c]}' must be a number, zero or more.")
    if problems:
        return None, problems[:20] + ([f"... and {len(problems) - 20} more."] if len(problems) > 20 else [])
    for c in ("tonnes", "amount_rs"):
        d[c] = d[c].str.replace(",", "").astype(float)
    return d, []


def save(text: str, by: str) -> dict[str, Any]:
    d, problems = parse(text)
    if problems:
        return {"saved": False, "problems": problems}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(FILE, index=False)
    (FILE.parent / "finance_billing_uploaded_by.txt").write_text(f"{by} {pd.Timestamp.now():%Y-%m-%d %H:%M}\n", encoding="utf-8")
    return {"saved": True, "rows": int(len(d)), "months": f"{d['month'].min()} to {d['month'].max()}"}


def _rates_for_month(cargo: str, month: str) -> tuple[dict, dict | None, str]:
    """(main rate, berth rate for crude, which Scale of Rates) for the month; falls back to today's rates, flagged."""
    c = ie.CARGO[cargo]
    main, berth = ie._rate(c["rate"]), (ie._rate(c["berth_rate"]) if c.get("berth_rate") else None)
    if month >= CURRENT_FROM:
        return main, berth, "in force"
    if SOR_2025_26_MONTHS[0] <= month <= SOR_2025_26_MONTHS[1]:
        old = ie.SOR_2025_26
        key_main = {"crude_spm": "crude_spm", "lpg_lng_gas": "lpg", "iron_ore_fines_lumps": "iron_ore"}.get(c["rate"])
        if key_main and key_main in old:
            m = {"foreign": old[key_main][0], "coastal": old[key_main][1]}
            b = {"foreign": old["crude_berth"][0], "coastal": old["crude_berth"][1]} if berth is not None else None
            return m, b, "in force"
    return main, berth, "today's rate (that year's not held)"


def estimate(cargo: str, month: str) -> dict[str, Any]:
    """The engine's wharfage estimate for one cargo and month, by the method of What we earn."""
    c = ie.CARGO[cargo]
    wide = ti._prepared()["wide"]
    ts = pd.Timestamp(month + "-01")
    if ts not in wide.index:
        return {"available": False}
    excl = ie._customer_share(c["family"], c["exclude_customer"]) if c.get("exclude_customer") else 0.0
    keep = 1.0 - (excl or 0.0)
    t = float(sum(wide.loc[ts, k] for k in c["keys"] if k in wide.columns and pd.notna(wide.loc[ts, k]))) * keep
    coastal = c.get("coastal_share", ie._coastal_shares().get(c["family"], 0.0) if c["family"] else 0.0)
    main, berth, basis = _rates_for_month(cargo, month)
    blend = lambda r_: (1 - coastal) * r_["foreign"] + coastal * r_["coastal"]
    spm = ie._crude_spm_share() if berth is not None else None
    rate = spm * blend(main) + (1 - spm) * blend(berth) if (berth is not None and spm is not None) else blend(main)
    return {"available": True, "tonnes": t, "rate": rate, "amount": t * rate, "rate_basis": basis}


def compare() -> dict[str, Any]:
    if not FILE.exists():
        return {"available": False, "uploaded": False, "template": template_csv(), "cargos": list(ie.CARGO), "charges": CHARGES}
    d = pd.read_csv(FILE)
    d["month"] = d["month"].astype(str)
    w = d[d["charge"] == "wharfage"].groupby(["cargo", "month"], as_index=False)[["tonnes", "amount_rs"]].sum()
    rows, months_rows = [], []
    for cargo, g in w.groupby("cargo"):
        est_t = est_rs = bill_t = bill_rs = 0.0
        bases, skipped = set(), []
        for _, r in g.iterrows():
            e = estimate(cargo, r["month"])
            if not e["available"]:
                skipped.append(r["month"])
                continue
            est_t, est_rs = est_t + e["tonnes"], est_rs + e["amount"]
            bill_t, bill_rs = bill_t + r["tonnes"], bill_rs + r["amount_rs"]
            bases.add(e["rate_basis"])
            months_rows.append({"cargo": cargo, "month": r["month"], "billed_t": r["tonnes"], "billed_rs": r["amount_rs"],
                                "statement_t": round(e["tonnes"]), "estimate_rs": round(e["amount"]),
                                "difference_pct": round((e["amount"] / r["amount_rs"] - 1) * 100, 1) if r["amount_rs"] else None})
        if not bill_rs:
            continue
        pct = lambda a, b: round((a / b - 1) * 100, 1) if b else None
        rows.append({"cargo": cargo, "months": int(len(g) - len(skipped)), "billed_t": round(bill_t), "billed_rs": round(bill_rs),
                     "statement_t": round(est_t), "estimate_rs": round(est_rs),
                     "tonnes_difference_pct": pct(est_t, bill_t),
                     "billed_rate": round(bill_rs / bill_t, 2) if bill_t else None,
                     "estimate_rate": round(est_rs / est_t, 2) if est_t else None,
                     "rate_difference_pct": pct(est_rs / est_t if est_t else 0, bill_rs / bill_t if bill_t else 0),
                     "amount_difference_pct": pct(est_rs, bill_rs),
                     "rate_basis": "; ".join(sorted(bases)), "months_not_held": skipped})
    total_bill = sum(r["billed_rs"] for r in rows)
    total_abs = sum(abs(r["estimate_rs"] - r["billed_rs"]) for r in rows)
    accuracy = round((1 - total_abs / total_bill) * 100, 1) if total_bill else None
    other = d[d["charge"] != "wharfage"].groupby("charge", as_index=False)["amount_rs"].sum().to_dict(orient="records")
    by = (FILE.parent / "finance_billing_uploaded_by.txt")
    return {"available": bool(rows), "uploaded": True, "rows": sorted(rows, key=lambda r: -r["billed_rs"]),
            "by_month": months_rows, "accuracy_pct": accuracy, "billed_total_rs": round(total_bill),
            "estimate_total_rs": round(sum(r["estimate_rs"] for r in rows)),
            "months": f"{d['month'].min()} to {d['month'].max()}", "other_charges": other,
            "uploaded_by": by.read_text(encoding="utf-8").strip() if by.exists() else "",
            "template": template_csv(), "cargos": list(ie.CARGO), "charges": CHARGES,
            "method": ("Estimate = NMPA's statement tonnes x the blended rate used in What we earn (foreign / coastal split; "
                       "SPM / berth split for crude), at the Scale of Rates in force in each month where the engine holds it. "
                       "Accuracy = 1 - total of |estimate - billed| / total billed. Other charges are listed but not yet compared.")}
