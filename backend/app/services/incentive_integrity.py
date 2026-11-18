"""
Is anyone gaming the discount?  Simple checks that flag the known tricks, each in plain words with its numbers.

Research on Busan and Gwangyang found shipping lines collected the full incentive just by managing when and where their
volumes were counted, without bringing more cargo. The tricks, and what is checked here:

  1. Holding back   - sending less cargo just before the scheme starts, so the "extra" afterwards looks bigger.
  2. Timing shift   - squeezing cargo into the last month of the scheme, then a drop after it ends.
  3. Related firms  - two related companies moving cargo between them to reach a higher slab.
  4. Relabelling    - cargo switched between coastal and foreign.
  5. Berth shift    - cargo moved from a private (PPP) berth onto an NMPA berth: new to the discount, not new to the port.
  6. Easy baseline  - a baseline period that was unusually weak, so beating it proves little.

A warning is a reason to look, not proof of wrongdoing. Customer data comes from NMPA's daily vessel reports (traced, not
billed); they start in Sep 2025, so some checks say "not enough data" for earlier periods.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.app.services import incentive_engine as ie
from backend.app.services import trade_customers as tc
from backend.app.services import trade_market as tmk
from backend.app.services import trade_split as ts

GROUPS_FILE = "data/customer_groups.csv"
PPP_BERTHS = {"14", "15", "16"}      # JSW container terminal, Adani Power (UPCL) captive jetty, JSW coal terminal
HOLD_BACK_RATIO = 0.70               # last 2 months at or below 70% of the customer's usual level
HOLD_BACK_GAP = 0.20                 # ... and at least 20 points worse than the cargo as a whole at NMPA
SPIKE_RATIO = 1.40                   # last scheme month 40% above the scheme's other months
DROP_RATIO = 0.70                    # first month after the scheme 30% below the scheme's average
SHARE_SHIFT_PTS = 25.0               # coastal share moved by 25 points or more
BERTH_SHIFT_PTS = 20.0               # PPP-berth share fell by 20 points or more
LOW_BASELINE_RATIO = 0.75            # baseline below 75% of the customer's usual level


def _months(start: str, end: str) -> list[str]:
    return [d.strftime("%Y-%m") for d in pd.date_range(pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1), freq="MS")]


def _fams(cargo: str) -> tuple[list[str], list[str]]:
    pairs = [k for k, v in ie.FAMILY_TO_CARGO.items() if v == cargo]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _voyages(customer: str | None, cargo: str) -> pd.DataFrame:
    v = tc.build()["voyages"]
    fams, dirs = _fams(cargo)
    v = v[v["family"].isin(fams) & v["direction"].isin(dirs) & v["tonnes"].notna()]
    return v if customer is None else v[v["customer"] == customer]


@lru_cache(maxsize=1)
def _berth_sightings() -> dict[str, list[tuple[str, str]]]:
    """vessel -> [(report date, berth)] from the 'berthed' table of every daily report held."""
    out: dict[str, list[tuple[str, str]]] = {}
    for p in sorted(ts.DAILY_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in d.get("berthed", []):
            b = str(r.get("berth_no") or "").strip().upper()
            if b:
                out.setdefault(ts._vessel_norm(r.get("vessel_name")), []).append((d.get("report_date", ""), b))
    return out


def _berth_of(vessel: str, first: str, last: str) -> str | None:
    seen = _berth_sightings().get(ts._vessel_norm(vessel), [])
    hits = [b for day, b in seen if str(first)[:10] <= day <= str(last)[:10]]
    return hits[-1] if hits else None


def _is_ppp(berth: str | None) -> bool | None:
    if not berth:
        return None
    nums = set(re.findall(r"\d+", berth))
    return bool(nums & PPP_BERTHS) if nums else False


def _monthly(customer: str, cargo: str) -> tuple[dict[str, float], list[str]]:
    from backend.app.services import incentive_proposal as ipr
    return ipr._customer_monthly(customer, cargo)


def _cargo_total(cargo: str, months: list[str]) -> float | None:
    wide = ie.ti._prepared()["wide"]
    keys = ie.CARGO[cargo]["keys"]
    tot = 0.0
    for m in months:
        d = pd.Timestamp(m + "-01")
        vals = [wide.loc[d, k] for k in keys if d in wide.index and k in wide.columns]
        if not vals or any(pd.isna(x) for x in vals):
            return None
        tot += float(sum(vals))
    return tot


def _fmt(ms) -> str:
    return ", ".join(pd.Timestamp(m + "-01").strftime("%b %Y") for m in ms)


def _res(check: str, status: str, plain: str, **numbers) -> dict:
    return {"check": check, "status": status, "plain": plain, "numbers": numbers}


def _periods(start: str, end: str, complete: list[str]) -> tuple[list[str], list[str], bool]:
    """(months before the scheme, months during the scheme held, started?). If nothing is held yet, 'during' is the
    last 3 complete months and 'before' the 3 before those, to show today's position."""
    sm = _months(start, end)
    during = [m for m in sm if m in complete]
    if during:
        before = [m for m in complete if m < sm[0]][-len(during):] or [m for m in complete if m < sm[0]][-3:]
        return before, during, True
    return complete[-6:-3], complete[-3:], False


def _hold_back(customer, cargo, start, monthly, complete) -> dict:
    first = _months(start, start)[0]
    pre = [m for m in complete if m < first]
    if len(pre) < 5:
        return _res("Holding back before the start", "Not enough data",
                    f"Fewer than 5 complete months of this customer's cargo before {_fmt([first])} (daily reports start in Sep 2025).")
    last2, ref = pre[-2:], pre[-8:-2]
    avg = lambda ms: sum(monthly.get(m, 0.0) for m in ms) / len(ms)
    if avg(ref) <= 0:
        return _res("Holding back before the start", "Not enough data", "No cargo from this customer in the reference months.")
    ratio = avg(last2) / avg(ref)
    c2, cr = _cargo_total(cargo, last2), _cargo_total(cargo, ref)
    cargo_ratio = (c2 / len(last2)) / (cr / len(ref)) if c2 is not None and cr else None
    flag = ratio <= HOLD_BACK_RATIO and (cargo_ratio is None or ratio <= cargo_ratio - HOLD_BACK_GAP)
    txt = (f"In {_fmt(last2)} the customer sent {ratio * 100:.0f}% of its usual monthly cargo"
           + (f", while this cargo as a whole at NMPA was at {cargo_ratio * 100:.0f}% of usual" if cargo_ratio else "") + ". ")
    txt += ("Possible holding back: a dip just before a scheme makes the 'extra' afterwards look bigger. Use a longer baseline."
            if flag else "No sign of holding back.")
    return _res("Holding back before the start", "Warning" if flag else "OK", txt,
                customer_ratio_pct=round(ratio * 100), cargo_ratio_pct=None if cargo_ratio is None else round(cargo_ratio * 100),
                months=last2, reference_months=ref)


def _timing(start, end, monthly, complete) -> dict:
    sm = _months(start, end)
    held = [m for m in sm if m in complete]
    if len(held) < 3:
        return _res("Squeezing cargo into the last month", "Not checked yet",
                    "Needs at least 3 months of the scheme in the data.")
    last, others = held[-1], held[:-1]
    avg_o = sum(monthly.get(m, 0.0) for m in others) / len(others)
    spike = avg_o > 0 and monthly.get(last, 0.0) >= SPIKE_RATIO * avg_o
    after = [m for m in complete if m > sm[-1]][:1]
    drop = None
    if after:
        avg_s = sum(monthly.get(m, 0.0) for m in held) / len(held)
        drop = avg_s > 0 and monthly.get(after[0], 0.0) <= DROP_RATIO * avg_s
    if spike and drop:
        return _res("Squeezing cargo into the last month", "Warning",
                    f"Cargo jumped in {_fmt([last])} (the scheme's last month) and fell in {_fmt(after)}, just after it ended: cargo may "
                    "have been moved in time to earn the rebate rather than added.", last_month=last, month_after=after[0])
    if spike and not after:
        return _res("Squeezing cargo into the last month", "Watch",
                    f"Cargo jumped in {_fmt([last])}; check the month after the scheme ends for a matching drop.", last_month=last)
    return _res("Squeezing cargo into the last month", "OK", "No end-of-scheme jump followed by a drop.")


def _groups() -> pd.DataFrame:
    f = tmk.ROOT / GROUPS_FILE
    if not f.exists():
        return pd.DataFrame(columns=["group", "member", "evidence", "source"])
    return pd.read_csv(f, comment="#", dtype=str).fillna("")


def _related(customer, cargo, start, end, complete) -> dict:
    g = _groups()
    grp = g[g["member"].str.upper() == customer.upper()]
    v_all = _voyages(None, cargo)
    joint = sorted({c for c in v_all["customer"].unique() if " + " in c and customer.upper() in [p.strip().upper() for p in c.split(" + ")]})
    if grp.empty and not joint:
        return _res("Related companies", "OK", "No related company recorded in data/customer_groups.csv and no joint entries "
                    "with others for this cargo.")
    others = sorted(set(g[g["group"].isin(grp["group"])]["member"]) - {customer})
    before, during, started = _periods(start, end, complete)
    by = v_all.groupby(["customer", "month"])["tonnes"].sum()
    t = lambda c, ms: float(sum(by.get((c, m), 0.0) for m in ms))
    rows = [{"member": c, "before_t": round(t(c, before)), "during_t": round(t(c, during))} for c in [customer] + others + joint]
    me = rows[0]
    moved = [r for r in rows[1:] if r["before_t"] > 0 and r["during_t"] < r["before_t"] * 0.7]
    plain = []
    if others:
        plain.append(f"Related companies: {', '.join(others)} ({grp['evidence'].iloc[0]}). Count them together in the baseline "
                     "and the slabs, otherwise cargo can be moved between them to reach a higher slab.")
    if joint:
        plain.append(f"Also appears in joint entries with other firms: {', '.join(joint)}. Agree how joint cargo is counted.")
    flag = bool(me["during_t"] > me["before_t"] and moved)
    if flag:
        plain.append("Warning: this customer's cargo rose while a related company's fell ("
                     + ", ".join(f"{r['member']}: {r['before_t']:,} t to {r['during_t']:,} t" for r in moved) + ").")
    period = "during the scheme vs before" if started else "last 3 months vs the 3 before"
    return _res("Related companies", "Warning" if flag else "Note", " ".join(plain), period=period, members=rows,
                before_months=before, during_months=during)


def _share_shift(customer, cargo, start, end, complete) -> dict:
    v = _voyages(customer, cargo)
    before, during, started = _periods(start, end, complete)

    def coastal(ms):
        x = v[v["month"].isin(ms)]
        tot = x["tonnes"].sum()
        return None if not tot else float(x.loc[x["run"].str.upper().str.startswith("C"), "tonnes"].sum() / tot * 100)
    a, b = coastal(before), coastal(during)
    if a is None or b is None:
        return _res("Coastal / foreign relabelling", "Not enough data", "No cargo in one of the two periods.")
    flag = abs(b - a) >= SHARE_SHIFT_PTS
    return _res("Coastal / foreign relabelling", "Warning" if flag else "OK",
                f"Coastal share {a:.0f}% before, {b:.0f}% " + ("during the scheme" if started else "recently") + ". "
                + ("A big switch: check the cargo was genuinely coastal/foreign (the rates differ)." if flag else "No big switch."),
                coastal_before_pct=round(a), coastal_during_pct=round(b))


def _berth_shift(customer, cargo, start, end, complete) -> dict:
    v = _voyages(customer, cargo).copy()
    v["ppp"] = [_is_ppp(_berth_of(r.vessel, r.first_seen, r.last_seen)) for r in v.itertuples()]
    before, during, started = _periods(start, end, complete)

    def share(ms):
        x = v[v["month"].isin(ms) & v["ppp"].notna()]
        tot = x["tonnes"].sum()
        return None if not tot else float(x.loc[x["ppp"].astype(bool), "tonnes"].sum() / tot * 100)
    a, b = share(before), share(during)
    if a is None or b is None:
        return _res("Moved from a private berth", "Not enough data", "Berth not found in the daily reports for one of the periods.")
    flag = a - b >= BERTH_SHIFT_PTS
    return _res("Moved from a private berth", "Warning" if flag else "OK",
                f"Share of this customer's cargo at PPP berths (14, 15, 16): {a:.0f}% before, {b:.0f}% "
                + ("during the scheme" if started else "recently") + ". "
                + ("Cargo has moved onto NMPA berths: that is new to the discount, not new to the port. Exclude it from 'extra'."
                   if flag else "No shift from private berths."),
                ppp_share_before_pct=round(a), ppp_share_during_pct=round(b))


def _easy_baseline(start, baseline_t, n_months, monthly, complete) -> dict:
    if not baseline_t:
        return _res("Easy baseline", "Not checked", "No baseline given.")
    first = _months(start, start)[0]
    pre = [m for m in complete if m < first]
    if len(pre) < 3:
        return _res("Easy baseline", "Not enough data", "Fewer than 3 complete months before the scheme.")
    usual = sum(monthly.get(m, 0.0) for m in pre) / len(pre)
    per_month = baseline_t / max(n_months, 1)
    if usual <= 0:
        return _res("Easy baseline", "Not enough data", "No cargo from this customer before the scheme.")
    ratio = per_month / usual
    flag = ratio < LOW_BASELINE_RATIO
    return _res("Easy baseline", "Warning" if flag else "OK",
                f"The baseline is {per_month:,.0f} t a month against the customer's usual {usual:,.0f} t ({ratio * 100:.0f}%). "
                + ("It looks easy to beat: an average over more months (or the contract volume) is safer." if flag
                   else "It is in line with the customer's usual level."),
                baseline_per_month_t=round(per_month), usual_per_month_t=round(usual))


def check(cargo: str, start: str, end: str, customer: str | None = None, baseline_t: float | None = None) -> dict[str, Any]:
    if cargo not in ie.CARGO:
        raise KeyError(cargo)
    if not customer:
        return {"cargo": cargo, "customer": None, "checks": [],
                "summary": "These checks work customer by customer. For a scheme open to every user, run them for its largest "
                           "customers (see Customers & cargo).",
                "source": "NMPA daily vessel reports"}
    monthly, complete = _monthly(customer, cargo)
    n = len(_months(start, end))
    checks = [_hold_back(customer, cargo, start, monthly, complete), _timing(start, end, monthly, complete),
              _related(customer, cargo, start, end, complete), _share_shift(customer, cargo, start, end, complete),
              _berth_shift(customer, cargo, start, end, complete), _easy_baseline(start, baseline_t, n, monthly, complete)]
    warn = [c["check"] for c in checks if c["status"] == "Warning"]
    notes = [c["check"] for c in checks if c["status"] in ("Note", "Watch")]
    return {"cargo": cargo, "customer": customer, "period": {"start": start, "end": end}, "checks": checks,
            "warnings": len(warn),
            "summary": (("No sign of gaming found." if not warn else f"{len(warn)} thing(s) to look at: " + "; ".join(warn) + ".")
                        + (f" To keep in mind: {'; '.join(notes)}." if notes else "")),
            "note": "A warning is a reason to look, not proof. Customer tonnes are traced from NMPA daily reports (from Sep 2025).",
            "source": "NMPA daily vessel reports; NMPA monthly statements; data/customer_groups.csv"}
