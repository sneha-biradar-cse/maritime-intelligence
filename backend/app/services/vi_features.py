"""
Vessel Intelligence — features served to the berth planner and the
Traffic Department. Built only on NMPA public data (Daily Vessel Position
archive, berths.csv, monthly Operational Performance reports).

    F1  port_call_board()      who is expected / waiting / alongside (as of a report)
    F2  arrival_outlook()      next-N-day arrivals with ETA reliability bands
        eta_accuracy()         declared-ETA error, backtested bias correction
    F3  berth_completion       when each berth frees up (balance ÷ handling rate)
        completion_backtest()  our forecast vs NMPA's own ETD column vs naive
    F4  berth_plan()           rule-based FIFO queue per berth → conflicts
    F5  wait_model()           P(pre-berthing wait > threshold), backtested
    F6  berthing_fit()         draft / LOA vs berth (and permissible-draft circulars)
    F8  performance()          DVP-derived KPIs reconciled to NMPA's official report
    F9  waiting_analytics()    waiting by month / reason / berth / receiver
        overview(), data_quality(), call_detail()

As-of discipline: every statistic used to predict something on report
day D is learned only from calls whose outcome was known before D, so
the backtests reproduce what the planner could actually have seen.
"""

from __future__ import annotations

import bisect
import math
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.app.services import vi_official_kpis as official
from backend.app.services import vi_port_calls as pc
from backend.app.services import vi_reference as ref

CARGO_ONLY = {"dry_bulk_conventional", "dry_bulk_mechanical", "break_bulk", "liquid_bulk", "container"}


# ──────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────

def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat(timespec="minutes")
    if isinstance(v, date):
        return v.isoformat()
    return v


def _r(v: Optional[float], n: int = 1) -> Optional[float]:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, n)


def _quantile(xs: List[float], q: float) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def as_of_report(as_of: Optional[date] = None) -> date:
    arch = pc.load_archive()
    if not arch.reports:
        raise ValueError("No Daily Vessel Position reports found in data/daily_vessel_position_parsed/")
    if as_of is None:
        return arch.last
    eligible = [d for d in arch.dates if d <= as_of]
    if not eligible:
        raise ValueError(f"No report on or before {as_of}; archive starts {arch.first}")
    return eligible[-1]


def report_dt(rd: date) -> datetime:
    return datetime.combine(rd, pc.report_reference_time())


def lineage(rd: Optional[date], method: str, status: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    arch = pc.load_archive()
    out = {
        "status": status,
        "method": method,
        "source": "NMPA Daily Vessel Position reports (newmangaloreport.gov.in), parsed",
        "as_of_report": _iso(rd),
        "report_reference_time": pc.report_reference_time().strftime("%H:%M") + " IST (estimated from NMPA's own waiting clock)",
        "archive": {"first": _iso(arch.first), "last": _iso(arch.last), "reports": len(arch.reports)},
        "coverage": pc.coverage(arch),
        "data_age_days": (date.today() - arch.last).days if arch.last else None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if extra:
        out.update(extra)
    return out


@lru_cache(maxsize=2)
def _index(fp: Tuple[int, float]) -> Dict[str, Any]:
    calls = pc._calls_cached(fp)
    by_id = {c["call_id"]: c for c in calls}
    obs_call: Dict[Tuple[str, date, str], str] = {}
    for c in calls:
        for o in c.get("_rows", []):
            obs_call[(o["vessel"], o["report_date"], o["section"])] = c["call_id"]
    return {"calls": calls, "by_id": by_id, "obs_call": obs_call}


def _idx() -> Dict[str, Any]:
    return _index(pc.archive_fingerprint())


def call_for(o: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cid = _idx()["obs_call"].get((o["vessel"], o["report_date"], o["section"]))
    return _idx()["by_id"].get(cid) if cid else None


def _report_obs(rd: date) -> List[Dict[str, Any]]:
    arch = pc.load_archive()
    return pc.observations_for_report(rd, arch.reports[rd])


def _moves_upto(vessel: str, until: datetime) -> List[Dict[str, Any]]:
    return [m for m in pc.movements() if m["vessel"] == vessel and m["dt"] <= until]


@lru_cache(maxsize=2)
def _programme_index(fp: Tuple[int, float]) -> Dict[date, List[Dict[str, Any]]]:
    """NMPA's berthing programme as printed in each report: the planned
    berths / shifts / sails from report time onwards."""
    arch = pc._load_archive(fp)
    ref_t = pc._report_reference_time(fp)
    out: Dict[date, List[Dict[str, Any]]] = {}
    for rd in arch.dates:
        now = datetime.combine(rd, ref_t)
        out[rd] = [m for m in pc.movements_for_report(rd, arch.reports[rd])
                   if m["source"] == "programme" and m["dt"] >= now - timedelta(hours=2)]
    return out


def programme(rd: date) -> List[Dict[str, Any]]:
    return _programme_index(pc.archive_fingerprint()).get(rd, [])


def programmed(rd: date, vessel: str, event: str) -> Optional[Dict[str, Any]]:
    evs = [m for m in programme(rd) if m["vessel"] == vessel and m["event"] == event]
    return min(evs, key=lambda m: m["dt"]) if evs else None


# ──────────────────────────────────────────────────────────────────────
# F2 — ETA reliability (declared ETA vs actual arrival)
# ──────────────────────────────────────────────────────────────────────

def _eta_history(before: Optional[date]) -> List[Dict[str, Any]]:
    out = []
    for c in _idx()["calls"]:
        if c.get("eta_error_h") is None or c["arrival_dt"] is None:
            continue
        if before is not None and c["arrival_dt"].date() >= before:
            continue
        if abs(c["eta_error_h"]) > 24 * 20:
            continue
        out.append(c)
    return out


def eta_error_profile(trade: Optional[str], cargo_class: Optional[str], before: Optional[date], min_n: int = 15) -> Dict[str, Any]:
    """Empirical (actual − declared) arrival error in hours, most specific
    group with ≥ min_n history: trade+class → class → trade → all."""
    hist = _eta_history(before)
    groups = [
        ("trade+class", lambda c: c["trade"] == trade and c["cargo_class"] == cargo_class),
        ("cargo class", lambda c: c["cargo_class"] == cargo_class),
        ("trade", lambda c: c["trade"] == trade),
        ("all calls", lambda c: True),
    ]
    for label, fn in groups:
        errs = [c["eta_error_h"] for c in hist if fn(c)]
        if len(errs) >= min_n:
            return {
                "basis": label, "n": len(errs), "errors": errs,
                "p10_h": _quantile(errs, 0.1), "p50_h": _quantile(errs, 0.5), "p90_h": _quantile(errs, 0.9),
            }
    return {"basis": "insufficient history", "n": len(hist), "errors": [], "p10_h": None, "p50_h": None, "p90_h": None}


def eta_accuracy(as_of: Optional[date] = None) -> Dict[str, Any]:
    return _eta_accuracy(as_of_report(as_of), pc.archive_fingerprint())


@lru_cache(maxsize=16)
def _eta_accuracy(rd: date, fp: Tuple[int, float]) -> Dict[str, Any]:
    hist = _eta_history(rd + timedelta(days=1))
    rows = []
    for c in sorted(hist, key=lambda c: c["arrival_dt"]):
        prior = eta_error_profile(c["trade"], c["cargo_class"], c["declared_eta_reported_on"])
        corr = prior["p50_h"] if prior["p50_h"] is not None else 0.0
        rows.append({"err_declared": c["eta_error_h"], "err_corrected": c["eta_error_h"] - corr, "c": c})

    def stats(errs: List[float]) -> Dict[str, Any]:
        if not errs:
            return {"n": 0}
        a = [abs(e) for e in errs]
        return {
            "n": len(errs), "mae_h": _r(mean(a)), "median_abs_h": _r(median(a)), "bias_h": _r(median(errs)),
            "within_12h_pct": _r(100 * sum(x <= 12 for x in a) / len(a)),
            "within_24h_pct": _r(100 * sum(x <= 24 for x in a) / len(a)),
        }

    decl = stats([r["err_declared"] for r in rows])
    corr = stats([r["err_corrected"] for r in rows])
    by_class = {}
    for cls in sorted({r["c"]["cargo_class"] for r in rows}):
        sel = [r for r in rows if r["c"]["cargo_class"] == cls]
        by_class[cls] = {"declared": stats([r["err_declared"] for r in sel]), "corrected": stats([r["err_corrected"] for r in sel])}
    by_agent = []
    agents = Counter(r["c"]["agent"] for r in rows if r["c"]["agent"])
    for ag, n in agents.most_common():
        if n < 5:
            continue
        s = stats([r["err_declared"] for r in rows if r["c"]["agent"] == ag])
        by_agent.append({"agent": ag, **s})
    by_agent.sort(key=lambda x: x["mae_h"])
    hist_bins = Counter(max(-5, min(5, round(r["err_declared"] / 24))) for r in rows)
    # adopt the correction only if it helps on every headline measure
    better = (corr.get("mae_h") is not None and decl.get("mae_h") is not None
              and corr["mae_h"] < decl["mae_h"]
              and corr["within_24h_pct"] >= decl["within_24h_pct"]
              and corr["median_abs_h"] <= decl["median_abs_h"] + 0.5)
    matched = [c for c in _idx()["calls"] if c["declared_eta"] and c["declared_eta_reported_on"] and c["declared_eta_reported_on"] <= rd]
    arrived = [c for c in matched if c["arrival_dt"]]
    return {
        "declared_eta": decl,
        "bias_corrected_eta": corr,
        "use_correction": better,
        "verdict": ("Bias-corrected ETA beats the declared ETA on a rolling backtest — used for the arrival outlook."
                    if better else "NMPA's declared ETA is already as good as any correction we can learn — the outlook uses it unchanged "
                                   "and only widens it into a reliability band."),
        "by_cargo_class": by_class,
        "by_agent": by_agent,
        "error_histogram_days": [{"days": k, "calls": hist_bins.get(k, 0)} for k in range(-5, 6)],
        "expected_lists_matched_to_an_arrival_pct": _r(100 * len(arrived) / len(matched)) if matched else None,
        "lineage": lineage(rd, "Declared ETA = first ETA printed in 'Vessels Expected'. Actual = arrival (DOA + time) in the anchorage/berthed list. "
                               "Correction = median historical error of the same trade/cargo class, learned only from calls that arrived before the ETA was published (rolling origin).",
                           "REAL (derived, backtested)"),
    }


def arrival_outlook(as_of: Optional[date] = None, days: int = 7) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    now = report_dt(rd)
    use_corr = eta_accuracy(rd)["use_correction"]
    obs = [o for o in _report_obs(rd) if o["section"] == "expected"]
    horizon = [rd + timedelta(days=i) for i in range(days)]
    per_day = {d: Counter() for d in horizon}
    vessels = []
    seen = set()
    for o in obs:
        if o["vessel"] in seen or not o.get("eta_date"):
            continue
        seen.add(o["vessel"])
        eta = datetime.combine(o["eta_date"], o["eta_time"] or pc.MIDDAY)
        prof = eta_error_profile(ref_trade(o["run"]), o["cargo_class"], rd)
        shift = (prof["p50_h"] or 0.0) if use_corr else 0.0
        pred = eta + timedelta(hours=shift)
        errs = prof["errors"] or [0.0]
        for e in errs:
            arr = eta + timedelta(hours=e)
            if arr.date() in per_day:
                per_day[arr.date()][o["cargo_class"]] += 1.0 / len(errs)
        vessels.append({
            "vessel": o["vessel"], "cargo": o["cargo"], "cargo_class": o["cargo_class"],
            "trade": ref_trade(o["run"]), "qty_t": o.get("qty"), "boxes": o.get("boxes"),
            "declared_eta": _iso(eta), "eta_precision": o.get("eta_precision"),
            "predicted_eta": _iso(pred),
            "eta_band": {"p10": _iso(eta + timedelta(hours=prof["p10_h"])) if prof["p10_h"] is not None else None,
                         "p90": _iso(eta + timedelta(hours=prof["p90_h"])) if prof["p90_h"] is not None else None,
                         "basis": prof["basis"], "n": prof["n"]},
            "hours_from_now": _r((pred - now).total_seconds() / 3600),
            "berth_prefs": o.get("berth_prefs"), "draft_m": o.get("draft_m"), "loa_m": o.get("loa_m"),
            "agent": o["agent"], "receiver": o["receiver"],
        })
    vessels.sort(key=lambda v: v["predicted_eta"])
    days_out = []
    for d in horizon:
        cnt = per_day[d]
        days_out.append({"date": d.isoformat(), "expected_arrivals": _r(sum(cnt.values()), 2),
                         "by_cargo_class": {k: _r(v, 2) for k, v in cnt.items()}})
    return {
        "as_of_report": rd.isoformat(), "days": days_out, "vessels": vessels,
        "lineage": lineage(rd, "Each expected vessel's arrival is spread over days using the empirical distribution of past declared-ETA errors "
                               "for its trade/cargo class; daily figures are expected counts (sum of probabilities).",
                           "REAL (derived, backtested)"),
    }


def ref_trade(run: Optional[str]) -> Optional[str]:
    if not run:
        return None
    return "foreign" if run.startswith("F") else ("coastal" if run.startswith("C") else None)


# ──────────────────────────────────────────────────────────────────────
# F3 — berth completion / departure forecast
# ──────────────────────────────────────────────────────────────────────
#
# Three candidate estimates for "when will this vessel sail?", each
# backtested on every vessel-day of the archive:
#   etd   NMPA's own ETD column (a date) + a calibrated time-of-day offset
#   rate  remaining balance ÷ handling rate (full days only)
#   stay  typical stay for the cargo class & berth − time already alongside
# The forecast uses the first available estimate in the order that the
# backtest ranks best (it is not assumed — see completion_backtest()).

def _full_day_rate(o: Dict[str, Any]) -> bool:
    bd = o.get("berthing_date")
    return bool(o.get("qty_day") and o["qty_day"] > 0 and bd and (o["report_date"] - bd).days >= 2)


@lru_cache(maxsize=2)
def _rate_history(fp: Tuple[int, float]) -> Dict[Tuple[str, Optional[str]], List[Tuple[date, float]]]:
    """Full-day handling rates (t/day) from the berthed list, by (class, berth) and (class, None)."""
    out: Dict[Tuple[str, Optional[str]], List[Tuple[date, float]]] = defaultdict(list)
    for o in pc._observations(fp)[0]:
        if o["section"] == "berthed" and o["cargo_class"] in CARGO_ONLY and _full_day_rate(o):
            out[(o["cargo_class"], o["berth"])].append((o["report_date"], o["qty_day"]))
            out[(o["cargo_class"], None)].append((o["report_date"], o["qty_day"]))
    for v in out.values():
        v.sort()
    return out


@lru_cache(maxsize=8192)
def _median_rate(cargo_class: str, berth: Optional[str], before: date, window_days: int = 180) -> Tuple[Optional[float], str]:
    hist = _rate_history(pc.archive_fingerprint())
    for key, label in (((cargo_class, berth), f"{ref.CARGO_CLASS_LABELS.get(cargo_class, cargo_class)} at berth {berth}"),
                       ((cargo_class, None), ref.CARGO_CLASS_LABELS.get(cargo_class, cargo_class))):
        series = hist.get(key, [])
        lo = bisect.bisect_left(series, (before - timedelta(days=window_days), -1))
        hi = bisect.bisect_left(series, (before, -1))
        vals = [v for _, v in series[lo:hi]]
        if len(vals) >= 5:
            return median(vals), f"median full-day rate, {label}, last {window_days} d (n={len(vals)})"
    return None, "no rate history"


@lru_cache(maxsize=2)
def _stay_history(fp: Tuple[int, float]) -> List[Tuple[date, str, Optional[str], float]]:
    out = []
    for c in pc._calls_cached(fp):
        if c["at_berth_h"] is not None and c["depart_dt"] and c["cargo_class"] in CARGO_ONLY \
                and c["first_berth_precision"] and c["at_berth_h"] < 24 * 30:
            out.append((c["depart_dt"].date(), c["cargo_class"], c["primary_berth"], c["at_berth_h"]))
    return sorted(out, key=lambda h: h[0])


def median_stay(cargo_class: str, berth: Optional[str], before: date) -> Tuple[Optional[float], str, int]:
    return _median_stay(cargo_class, berth, before, pc.archive_fingerprint())


@lru_cache(maxsize=8192)
def _median_stay(cargo_class: str, berth: Optional[str], before: date, fp: Tuple[int, float]) -> Tuple[Optional[float], str, int]:
    hist = [h for h in _stay_history(fp) if h[0] < before]
    for sel, label in (([h[3] for h in hist if h[1] == cargo_class and h[2] == berth], "same cargo class & berth"),
                       ([h[3] for h in hist if h[1] == cargo_class], "same cargo class"),
                       ([h[3] for h in hist], "all cargo calls")):
        if len(sel) >= 5:
            return median(sel), label, len(sel)
    return None, "no history", 0


def _call_rows_upto(call: Optional[Dict[str, Any]], rd: date) -> List[Dict[str, Any]]:
    if not call:
        return []
    return sorted([o for o in call.get("_rows", []) if o["section"] == "berthed" and o["report_date"] <= rd],
                  key=lambda o: o["report_date"])


def _raw_estimates(o: Dict[str, Any], rd: date) -> Dict[str, Any]:
    """Uncalibrated hours-to-departure from each method (None if unavailable)."""
    now = report_dt(rd)
    call = call_for(o)
    berthing = None
    if call and call.get("first_berth_dt") and call["first_berth_dt"] <= now:
        berthing = call["first_berth_dt"]
    elif o.get("berthing_date"):
        berthing = datetime.combine(o["berthing_date"], pc.MIDDAY)
    alongside = (now - berthing).total_seconds() / 3600 if berthing else None

    etd_h = None
    if o.get("etd_date") and o["etd_date"] >= rd:
        etd_h = (datetime.combine(o["etd_date"], time(0, 0)) - now).total_seconds() / 3600

    rate_h, rate_basis, rate = None, None, None
    bal = o.get("qty_balance")
    if bal is not None and bal > 0:
        recent = [r["qty_day"] for r in _call_rows_upto(call, rd) if _full_day_rate(r)][-3:]
        med, med_basis = _median_rate(o["cargo_class"], o["berth"], rd)
        if recent:
            rate, rate_basis = mean(recent), f"this call's last {len(recent)} full-day handling figure(s)"
            if med and rate < 0.5 * med:
                rate, rate_basis = med, med_basis + " (call's own rate implausibly low)"
        else:
            rate, rate_basis = med, med_basis
        if rate and rate > 0:
            rate_h = min(bal / rate * 24, 24 * 20)
    elif bal is not None and bal <= 0:
        rate_h, rate_basis = 0.0, "balance 0 — operations complete"

    prog = programmed(rd, o["vessel"], "sails")
    prog_h = (prog["dt"] - now).total_seconds() / 3600 if prog else None

    stay_h, stay_basis = None, None
    stay, basis, n = median_stay(o["cargo_class"], o["berth"], rd)
    if stay is not None and alongside is not None:
        stay_h, stay_basis = max(stay - alongside, 0.0), f"typical stay ({basis}, n={n}, median {stay:.0f} h)"

    return {"now": now, "alongside_h": alongside, "etd_h": etd_h, "programme_h": prog_h,
            "programme_basis": f"sailing at {prog['dt'].strftime('%d/%m %H:%M')} in this report's berthing programme" if prog else None,
            "rate_h": rate_h, "rate": rate,
            "rate_basis": rate_basis, "stay_h": stay_h, "stay_basis": stay_basis, "balance": bal}


@lru_cache(maxsize=2)
def _completion_points(fp: Tuple[int, float]) -> List[Dict[str, Any]]:
    pts = []
    for o in pc._observations(fp)[0]:
        if o["section"] != "berthed" or o["cargo_class"] not in CARGO_ONLY:
            continue
        call = call_for(o)
        if not call or call["depart_dt"] is None or call["depart_precision"] != "exact":
            continue
        now = report_dt(o["report_date"])
        if call["depart_dt"] <= now:
            continue
        actual = (call["depart_dt"] - now).total_seconds() / 3600
        if actual > 24 * 20:
            continue
        e = _raw_estimates(o, o["report_date"])
        # The 'actual' sailing time is itself NMPA's last programme revision before
        # the sailing. If that revision is THIS report's programme, scoring the
        # programme against it would be circular — drop it for that method.
        circular = call.get("depart_reported_in") == o["report_date"]
        pts.append({"d": o["report_date"], "cls": o["cargo_class"], "actual": actual,
                    "programme": None if circular else e["programme_h"], "programme_circular": circular and e["programme_h"] is not None, "etd": e["etd_h"], "rate": e["rate_h"], "stay": e["stay_h"]})
    return sorted(pts, key=lambda p: p["d"])


@lru_cache(maxsize=4096)
def _offset(method: str, cargo_class: str, before: date) -> float:
    """Median (actual − estimate) hours for a method, learned from earlier days."""
    pts = [p for p in _completion_points(pc.archive_fingerprint()) if p["d"] < before and p[method] is not None]
    cls_pts = [p for p in pts if p["cls"] == cargo_class]
    use = cls_pts if len(cls_pts) >= 20 else pts
    if len(use) < 20:
        return 12.0 if method == "etd" else 0.0
    if method == "programme":
        return 0.0  # a programme time is already a clock time — never shifted
    return median(p["actual"] - p[method] for p in use)


METHOD_LABELS = {
    "programme": "NMPA berthing programme (planned sailing time in today's report)",
    "etd": "NMPA's ETD (date) + calibrated time-of-day offset",
    "rate": "remaining balance ÷ handling rate + calibrated offset",
    "stay": "typical stay for this cargo class & berth − time already alongside",
}


@lru_cache(maxsize=16)
def method_ranking(before: date) -> List[str]:
    """Methods ordered by backtested MAE on points before `before`."""
    pts = [p for p in _completion_points(pc.archive_fingerprint()) if p["d"] < before]
    scores = {}
    # The programme is shown alongside but not ranked: it cannot be scored
    # independently (see completion_backtest note).
    for m in ("etd", "rate", "stay"):
        errs = [abs(p["actual"] - (p[m] + _offset(m, p["cls"], p["d"]))) for p in pts if p[m] is not None]
        scores[m] = mean(errs) if len(errs) >= 30 else float("inf")
    order = sorted(scores, key=lambda m: scores[m])
    return order if scores[order[0]] < float("inf") else ["etd", "rate", "stay"]


def completion_forecast(o: Dict[str, Any], rd: date) -> Dict[str, Any]:
    """Predicted departure for a vessel alongside on report rd."""
    e = _raw_estimates(o, rd)
    out: Dict[str, Any] = {"hours_alongside": _r(e["alongside_h"]), "balance_t": e["balance"],
                           "rate_t_per_day": _r(e["rate"], 0), "nmpa_etd": None,
                           "estimates": {}}
    if o.get("etd_date"):
        out["nmpa_etd"] = o["etd_date"].isoformat()
    if o["cargo_class"] not in CARGO_ONLY:
        out.update({"method": "non-cargo call — not forecast", "predicted_departure": None})
        return out
    for m in ("programme", "etd", "rate", "stay"):
        raw = e[f"{m}_h"]
        if raw is not None:
            h = max(raw + _offset(m, o["cargo_class"], rd), 1.0)
            out["estimates"][m] = {"hours": _r(h), "at": _iso(e["now"] + timedelta(hours=h)),
                                   "basis": METHOD_LABELS[m] + (f" [{e[m + '_basis']}]" if e.get(m + "_basis") else "")}
    for m in method_ranking(rd):
        if m in out["estimates"]:
            est = out["estimates"][m]
            out.update({"method": est["basis"], "method_key": m, "remaining_h": est["hours"], "predicted_departure": est["at"]})
            return out
    out.update({"method": "insufficient data", "predicted_departure": None})
    return out


def completion_backtest(as_of: Optional[date] = None) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    pts = [p for p in _completion_points(pc.archive_fingerprint()) if p["d"] <= rd]
    for p in pts:
        for m in ("programme", "etd", "rate", "stay"):
            p[m + "_c"] = p[m] + _offset(m, p["cls"], p["d"]) if p[m] is not None else None
        p["etd_noon"] = p["etd"] + 12 if p["etd"] is not None else None
        rank = method_ranking(p["d"])
        p["chosen"] = next((p[m + "_c"] for m in rank if p[m + "_c"] is not None), None)

    def mae(key: str, sel: List[Dict[str, Any]]) -> Dict[str, Any]:
        errs = [abs(p["actual"] - p[key]) for p in sel if p.get(key) is not None]
        return {"n": len(errs), "mae_h": _r(mean(errs)) if errs else None,
                "within_12h_pct": _r(100 * sum(x <= 12 for x in errs) / len(errs)) if errs else None}

    keys = {"chosen": "Forecast shown on the board (best available method)",
            "etd_noon": "NMPA ETD as printed (date, read as 12:00)",
            "programme_c": METHOD_LABELS["programme"],
            "etd_c": METHOD_LABELS["etd"], "rate_c": METHOD_LABELS["rate"], "stay_c": METHOD_LABELS["stay"]}
    same = [p for p in pts if all(p.get(k) is not None for k in keys if k != "programme_c")]
    same_prog = [p for p in pts if all(p.get(k) is not None for k in keys)]
    by_class = {}
    for cls in sorted({p["cls"] for p in same}):
        sel = [p for p in same if p["cls"] == cls]
        by_class[cls] = {k: mae(k, sel) for k in keys}
    return {
        "methods": keys,
        "ranking_now": [METHOD_LABELS[m] for m in method_ranking(rd + timedelta(days=1))],
        "same_points": {k: mae(k, same) for k in keys if k != "programme_c"},
        "same_points_with_programme": {k: mae(k, same_prog) for k in keys},
        "all_points": {k: mae(k, pts) for k in keys},
        "by_cargo_class": by_class,
        "programme_points_excluded_as_circular": sum(1 for p in pts if p.get("programme_circular")),
        "note": "Error = |predicted − actual sailing time| (hours), on every day a cargo vessel was alongside and later sailed with a "
                "recorded time. Offsets and the method ranking are learned only from earlier days. 'Same points' compares all "
                "methods on identical vessel-days. Caveat: NMPA publishes no actual sailing log, so the 'actual' time is the last "
                "programme revision printed before the sailing (or a post-operation change). The programme method is therefore "
                "scored only where a LATER report revised/confirmed the time; points where today's programme is itself the "
                "'actual' are excluded as circular.",
        "lineage": lineage(rd, "Rolling backtest over the DVP archive.", "REAL (derived, backtested)"),
    }


# ──────────────────────────────────────────────────────────────────────
# F6 — berthing fit (draft / LOA vs berth)
# ──────────────────────────────────────────────────────────────────────

def fit_check(berth_id: str, draft_m: Optional[float], loa_m: Optional[float], on: date) -> Dict[str, Any]:
    b = ref.berths().get(berth_id)
    if not b:
        return {"berth": berth_id, "status": "unknown_berth"}
    max_draft, draft_src = ref.max_draft_for(berth_id, on)
    issues, status = [], "ok"
    if draft_m is not None and max_draft:
        margin = max_draft - draft_m
        if margin < 0:
            status = "exceeds"
            issues.append(f"draft {draft_m:.1f} m > {max_draft:.1f} m allowed (needs tide window or another berth)")
        elif margin < 0.5:
            status = "tight"
            issues.append(f"draft {draft_m:.1f} m within {margin:.1f} m of {max_draft:.1f} m limit")
    if loa_m is not None and b.get("quay_length_m"):
        if loa_m > b["quay_length_m"] * 1.15:
            status = "exceeds"
            issues.append(f"LOA {loa_m:.0f} m vs quay {b['quay_length_m']:.0f} m")
        elif loa_m > b["quay_length_m"] and status == "ok":
            status = "tight"
            issues.append(f"LOA {loa_m:.0f} m overhangs {b['quay_length_m']:.0f} m quay")
    if draft_m is None and status == "ok":
        status = "draft_not_declared"
    return {"berth": berth_id, "status": status, "issues": issues,
            "max_draft_m": max_draft, "draft_limit_source": draft_src, "quay_length_m": b.get("quay_length_m")}


def berthing_fit(as_of: Optional[date] = None) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    rows, seen = [], set()
    for o in _report_obs(rd):
        if o["section"] != "expected" or o["vessel"] in seen:
            continue
        seen.add(o["vessel"])
        on = o.get("eta_date") or rd
        checks = [fit_check(b, o.get("draft_m"), o.get("loa_m"), on) for b in (o.get("berth_prefs") or [])]
        worst = "ok"
        order = ["ok", "draft_not_declared", "tight", "exceeds"]
        for c in checks:
            if c["status"] in order and order.index(c["status"]) > order.index(worst):
                worst = c["status"]
        best = next((c["berth"] for c in checks if c["status"] in ("ok", "draft_not_declared")), None)
        rows.append({"vessel": o["vessel"], "cargo": o["cargo"], "eta": _iso(o.get("eta_date")),
                     "draft_m": o.get("draft_m"), "loa_m": o.get("loa_m"), "berth_prefs": o.get("berth_prefs"),
                     "checks": checks, "worst": worst, "first_fitting_preference": best})
    tide_loaded = bool(ref.tide_table())
    pd_loaded = bool(ref.permissible_drafts())
    return {
        "as_of_report": rd.isoformat(), "vessels": rows,
        "limits_used": "Permissible-draft circulars" if pd_loaded else
        "berths.csv design draught — load NMPA's latest Permissible Draft circular into data/reference/permissible_draft.csv for real limits",
        "tide_table_loaded": tide_loaded,
        "lineage": lineage(rd, "Rule check: declared draft / LOA from 'Vessels Expected' vs berth limits.", "RULE-BASED (real inputs)"),
    }


# ──────────────────────────────────────────────────────────────────────
# F5 — pre-berthing wait model
# ──────────────────────────────────────────────────────────────────────

WAIT_FEATURES = ["is_foreign", "loa_m", "log_qty", "month_sin", "month_cos",
                 "q_waiting_total", "q_waiting_port", "q_for_pref", "pref_occupied",
                 "cls_dry_bulk_conventional", "cls_dry_bulk_mechanical", "cls_break_bulk", "cls_liquid_bulk", "cls_container"]


def _queue_state(rd: date, prefs: List[str]) -> Dict[str, float]:
    obs = _report_obs(rd)
    waiting = [o for o in obs if o["section"] in ("anchorage", "tankers_scheduled") and o["cargo_class"] in CARGO_ONLY]
    q_port = [o for o in waiting if o.get("account") == "port"]
    q_pref = [o for o in waiting if (o.get("berth") in prefs) or (o.get("wob_target") in prefs)]
    occ = {o["berth"] for o in obs if o["section"] == "berthed" and o["cargo_class"] in CARGO_ONLY}
    return {"q_waiting_total": len(waiting), "q_waiting_port": len(q_port), "q_for_pref": len(q_pref),
            "pref_occupied": sum(1 for p in prefs if p in occ) / len(prefs) if prefs else float("nan")}


def _wait_features(cargo_class: str, trade: Optional[str], loa: Optional[float], qty: Optional[float],
                   when: date, prefs: List[str], state_day: date) -> Dict[str, float]:
    f = {"is_foreign": 1.0 if trade == "foreign" else 0.0,
         "loa_m": loa if loa else float("nan"),
         "log_qty": math.log1p(qty) if qty else float("nan"),
         "month_sin": math.sin(2 * math.pi * when.month / 12), "month_cos": math.cos(2 * math.pi * when.month / 12)}
    f.update(_queue_state(state_day, prefs))
    for c in sorted(CARGO_ONLY):
        f[f"cls_{c}"] = 1.0 if cargo_class == c else 0.0
    return f


def _report_on_or_before(d: date) -> Optional[date]:
    ds = pc.load_archive().dates
    i = bisect.bisect_right(ds, d) - 1
    return ds[i] if i >= 0 else None


@lru_cache(maxsize=2)
def _wait_dataset(fp: Tuple[int, float]) -> List[Dict[str, Any]]:
    rows = []
    for c in pc._calls_cached(fp):
        if c["cargo_class"] not in CARGO_ONLY or c["wait_h"] is None or c["arrival_dt"] is None or c["stage"] != "berthed":
            continue
        if c["wait_h"] > 24 * 30:
            continue
        prefs = c["berth_prefs"] or ([c["primary_berth"]] if c["primary_berth"] else [])
        state_day = _report_on_or_before(c["arrival_dt"].date() - timedelta(days=0 if c["arrival_dt"].time() >= pc.report_reference_time() else 1))
        if state_day is None:
            continue
        x = _wait_features(c["cargo_class"], c["trade"], c["loa_m"], c["qty_t"], c["arrival_dt"].date(), prefs, state_day)
        rows.append({"x": x, "wait_h": c["wait_h"], "wait_port_h": c["wait_port_h"], "d": c["arrival_dt"].date(),
                     "cls": c["cargo_class"], "call_id": c["call_id"]})
    return sorted(rows, key=lambda r: r["d"])


@lru_cache(maxsize=4)
def _wait_model(fp: Tuple[int, float], threshold_h: float) -> Dict[str, Any]:
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import brier_score_loss, roc_auc_score

    data = _wait_dataset(fp)
    if len(data) < 150:
        return {"status": "insufficient_data", "n": len(data)}
    X = np.array([[r["x"][k] for k in WAIT_FEATURES] for r in data], dtype=float)
    y = np.array([1 if r["wait_h"] > threshold_h else 0 for r in data])
    cut = int(len(data) * 0.7)
    Xtr, Xte, ytr, yte = X[:cut], X[cut:], y[:cut], y[cut:]
    model = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, l2_regularization=1.0,
                                           min_samples_leaf=20, random_state=7)
    model.fit(Xtr, ytr)
    p_model = model.predict_proba(Xte)[:, 1]
    # baseline: historical rate per cargo class in the training window
    rates = {}
    for c in CARGO_ONLY:
        sel = [r for r, yy in zip(data[:cut], ytr) if r["cls"] == c]
        rates[c] = (sum(1 for r in sel if r["wait_h"] > threshold_h) + 1) / (len(sel) + 2)
    p_base = np.array([rates[r["cls"]] for r in data[cut:]])
    try:
        auc_m, auc_b = roc_auc_score(yte, p_model), roc_auc_score(yte, p_base)
    except ValueError:
        auc_m = auc_b = float("nan")
    brier_m, brier_b = brier_score_loss(yte, p_model), brier_score_loss(yte, p_base)
    use_model = brier_m < brier_b and auc_m > auc_b
    final = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, l2_regularization=1.0,
                                           min_samples_leaf=20, random_state=7).fit(X, y) if use_model else None
    all_rates = {}
    for c in CARGO_ONLY:
        sel = [r for r in data if r["cls"] == c]
        all_rates[c] = (sum(1 for r in sel if r["wait_h"] > threshold_h) + 1) / (len(sel) + 2)
    return {
        "status": "ok", "threshold_h": threshold_h, "n_train": cut, "n_test": len(data) - cut,
        "train_period": [data[0]["d"].isoformat(), data[cut - 1]["d"].isoformat()],
        "test_period": [data[cut]["d"].isoformat(), data[-1]["d"].isoformat()],
        "positive_rate_test": float(yte.mean()),
        "model": {"auc": _r(auc_m, 3), "brier": _r(brier_m, 4)},
        "baseline": {"auc": _r(auc_b, 3), "brier": _r(brier_b, 4), "what": "historical share of calls of the same cargo class that waited longer than the threshold"},
        "use_model": use_model,
        "_final": final, "_rates": all_rates,
    }


def wait_model(threshold_h: Optional[float] = None) -> Dict[str, Any]:
    th = threshold_h or ref.standard("port_account_wait_alert_hours")
    m = _wait_model(pc.archive_fingerprint(), th)
    out = {k: v for k, v in m.items() if not k.startswith("_")}
    if m.get("status") == "ok":
        gain = (m["baseline"]["brier"] - m["model"]["brier"]) / m["baseline"]["brier"] if m["baseline"]["brier"] else 0
        strength = "clearly" if gain > 0.03 else "only marginally"
        out["verdict"] = (f"Gradient-boosted model {strength} beats the cargo-class base rate on the held-out period "
                          f"(AUC {m['model']['auc']} vs {m['baseline']['auc']}, Brier {m['model']['brier']} vs {m['baseline']['brier']}) — used for predictions."
                          if m["use_model"] else
                          f"The model does NOT beat the simple cargo-class base rate on the held-out period "
                          f"(AUC {m['model']['auc']} vs {m['baseline']['auc']}, Brier {m['model']['brier']} vs {m['baseline']['brier']}) — "
                          f"predictions use the base rate instead.")
        out["features"] = WAIT_FEATURES
    out["lineage"] = lineage(as_of_report(), "Target: pre-berthing wait (arrival → first berthing) above threshold. Features known before arrival: cargo class, "
                                             "trade, LOA, quantity, season, and the anchorage/berth situation in the last report before arrival. "
                                             "Chronological 70/30 split.", "REAL (ML, backtested)")
    return out


def predict_wait_probability(cargo_class: str, trade: Optional[str], loa: Optional[float], qty: Optional[float],
                             when: date, prefs: List[str], state_day: date) -> Dict[str, Any]:
    th = ref.standard("port_account_wait_alert_hours")
    m = _wait_model(pc.archive_fingerprint(), th)
    if m.get("status") != "ok" or cargo_class not in CARGO_ONLY:
        return {"p_wait_over_threshold": None, "threshold_h": th, "basis": "no model"}
    if m["use_model"]:
        import numpy as np
        x = _wait_features(cargo_class, trade, loa, qty, when, prefs, state_day)
        p = float(m["_final"].predict_proba(np.array([[x[k] for k in WAIT_FEATURES]], dtype=float))[0, 1])
        return {"p_wait_over_threshold": _r(p, 3), "threshold_h": th, "basis": "gradient-boosted model (backtested)"}
    return {"p_wait_over_threshold": _r(m["_rates"][cargo_class], 3), "threshold_h": th,
            "basis": "historical rate for this cargo class (model did not beat it)"}


def remaining_wait(elapsed_h: float, account: Optional[str], cargo_class: str, before: date) -> Dict[str, Any]:
    """Empirical: of past calls that had already waited this long for the same
    kind of reason, how much longer did they wait?"""
    hist = [c for c in _idx()["calls"] if c["wait_h"] is not None and c["arrival_dt"] and c["first_berth_dt"]
            and c["first_berth_dt"].date() < before and c["wait_h"] > elapsed_h and c["cargo_class"] in CARGO_ONLY]

    def acc_of(c: Dict[str, Any]) -> str:
        a = c["wait_accounts"]
        return max(("port", "non_port"), key=lambda k: a.get(k, 0)) if (a.get("port") or a.get("non_port")) else "unknown"

    for sel, label in (([c for c in hist if acc_of(c) == account and c["cargo_class"] == cargo_class], "same reason type & cargo class"),
                       ([c for c in hist if acc_of(c) == account], "same reason type"),
                       (hist, "all waits")):
        if len(sel) >= 8:
            rem = [c["wait_h"] - elapsed_h for c in sel]
            return {"median_more_h": _r(median(rem)), "p80_more_h": _r(_quantile(rem, 0.8)), "basis": label, "n": len(sel)}
    return {"median_more_h": None, "p80_more_h": None, "basis": "insufficient history", "n": len(hist)}


# ──────────────────────────────────────────────────────────────────────
# F1 — Port Call Board
# ──────────────────────────────────────────────────────────────────────

def _waiting_hours(o: Dict[str, Any], now: datetime) -> Tuple[Optional[float], str]:
    if o.get("nmpa_wait_days") is not None:
        return _r(o["nmpa_wait_days"] * 24), "NMPA's own waiting clock"
    if o.get("arrival_date"):
        arr = datetime.combine(o["arrival_date"], o.get("arrival_time") or pc.MIDDAY)
        return _r(max((now - arr).total_seconds() / 3600, 0)), "report time − arrival (DOA)"
    return None, "unknown"


def _imo(o: Dict[str, Any]) -> Dict[str, Any]:
    """IMO number for a board row (name + LOA match against the curated lookup)."""
    vi = ref.vessel_identity(o["vessel"], o.get("loa_m"))
    return {"imo": vi["imo"], "imo_match": vi["imo_match"], "imo_confidence": vi["imo_confidence"]}


def port_call_board(as_of: Optional[date] = None) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    now = report_dt(rd)
    obs = _report_obs(rd)
    th_port = ref.standard("port_account_wait_alert_hours")
    th_any = ref.standard("long_wait_any_reason_hours")
    alerts: List[Dict[str, Any]] = []

    alongside = []
    for o in [o for o in obs if o["section"] == "berthed"]:
        fc = completion_forecast(o, rd)
        call = call_for(o)
        alongside.append({
            "vessel": o["vessel"], **_imo(o), "berth": o["berth"], "cargo": o["cargo"], "cargo_class": o["cargo_class"],
            "trade": ref_trade(o["run"]), "loa_m": o["loa_m"], "agent": o["agent"], "receiver": o["receiver"],
            "arrival_date": _iso(o.get("arrival_date")), "berthing_date": _iso(o.get("berthing_date")),
            "qty_day_t": o.get("qty_day"), "qty_handled_t": o.get("qty_total"), "qty_balance_t": o.get("qty_balance"),
            "boxes_handled": o.get("boxes_total"),
            "hours_alongside": fc.get("hours_alongside"), "nmpa_etd": fc.get("nmpa_etd"),
            "programme_sailing": _iso(p["dt"]) if (p := programmed(rd, o["vessel"], "sails")) else None,
            "predicted_departure": fc.get("predicted_departure"), "remaining_h": fc.get("remaining_h"),
            "forecast_method": fc.get("method"), "call_id": call["call_id"] if call else None,
        })
    alongside.sort(key=lambda a: (a["berth"] is None, ref.berth_order().index(a["berth"]) if a["berth"] in ref.berth_order() else 99))

    waiting = []
    for o in [o for o in obs if o["section"] in ("anchorage", "tankers_scheduled")]:
        hrs, basis = _waiting_hours(o, now)
        call = call_for(o)
        prefs = (call or {}).get("berth_prefs") or []
        target = o.get("berth") or o.get("wob_target") or (prefs[0] if prefs else None)
        rem = remaining_wait(hrs or 0.0, o.get("account"), o["cargo_class"], rd) if o["cargo_class"] in CARGO_ONLY else {}
        item = {
            "vessel": o["vessel"], **_imo(o), "list": "Tankers scheduled" if o["section"] == "tankers_scheduled" else "Anchorage",
            "cargo": o["cargo"], "cargo_class": o["cargo_class"], "trade": ref_trade(o["run"]),
            "loa_m": o["loa_m"], "qty_t": o.get("qty"), "agent": o["agent"], "receiver": o["receiver"],
            "arrival": _iso(datetime.combine(o["arrival_date"], o.get("arrival_time") or pc.MIDDAY)) if o.get("arrival_date") else None,
            "waiting_h": hrs, "waiting_basis": basis,
            "reason": o.get("reason"), "reason_raw": o.get("reason_raw"), "account": o.get("account"),
            "target_berth": target,
            "programme_berthing": ({"at": _iso(pb["dt"]), "berth": pb["berth"]} if (pb := programmed(rd, o["vessel"], "berths")) else None),
            "expected_more_wait_h": rem.get("median_more_h"), "expected_more_wait_p80_h": rem.get("p80_more_h"),
            "expected_more_wait_basis": f"{rem.get('basis')} (n={rem.get('n')})" if rem else None,
            "call_id": call["call_id"] if call else None,
        }
        waiting.append(item)
        if o.get("account") == "port" and hrs is not None and hrs > th_port:
            alerts.append({"severity": "high", "type": "port_account_wait", "vessel": o["vessel"],
                           "message": f"{o['vessel']} waiting {hrs:.0f} h for {o.get('reason', '').lower()}"
                                      f"{' (berth ' + target + ')' if target else ''} — over the {th_port:.0f} h alert level."})
        elif hrs is not None and hrs > th_any and o.get("account") != "excluded":
            alerts.append({"severity": "medium", "type": "long_wait", "vessel": o["vessel"],
                           "message": f"{o['vessel']} at anchorage {hrs / 24:.1f} days — {o.get('reason') or 'no reason stated'}."})
    waiting.sort(key=lambda w: -(w["waiting_h"] or 0))

    expected = []
    seen = set()
    state_day = rd
    for o in [o for o in obs if o["section"] == "expected"]:
        if o["vessel"] in seen:
            continue
        seen.add(o["vessel"])
        eta = datetime.combine(o["eta_date"], o["eta_time"] or pc.MIDDAY) if o.get("eta_date") else None
        prof = eta_error_profile(ref_trade(o["run"]), o["cargo_class"], rd)
        prefs = o.get("berth_prefs") or []
        checks = [fit_check(b, o.get("draft_m"), o.get("loa_m"), o.get("eta_date") or rd) for b in prefs]
        fit = "exceeds" if any(c["status"] == "exceeds" for c in checks) else (
            "tight" if any(c["status"] == "tight" for c in checks) else (
                "draft_not_declared" if any(c["status"] == "draft_not_declared" for c in checks) else ("ok" if checks else "no_berth_preference")))
        pw = predict_wait_probability(o["cargo_class"], ref_trade(o["run"]), o.get("loa_m"), o.get("qty"),
                                      o.get("eta_date") or rd, prefs, state_day)
        expected.append({
            "vessel": o["vessel"], **_imo(o), "cargo": o["cargo"], "cargo_class": o["cargo_class"], "trade": ref_trade(o["run"]),
            "declared_eta": _iso(eta), "eta_precision": o.get("eta_precision"),
            "eta_p10": _iso(eta + timedelta(hours=prof["p10_h"])) if eta and prof["p10_h"] is not None else None,
            "eta_p90": _iso(eta + timedelta(hours=prof["p90_h"])) if eta and prof["p90_h"] is not None else None,
            "hours_to_eta": _r((eta - now).total_seconds() / 3600) if eta else None,
            "draft_m": o.get("draft_m"), "loa_m": o.get("loa_m"), "qty_t": o.get("qty"), "boxes": o.get("boxes"),
            "berth_prefs": prefs, "berthing_fit": fit,
            "programme_berthing": ({"at": _iso(pb["dt"]), "berth": pb["berth"]} if (pb := programmed(rd, o["vessel"], "berths")) else None), "fit_issues": [i for c in checks for i in c["issues"]],
            "p_wait_over_threshold": pw["p_wait_over_threshold"], "wait_threshold_h": pw["threshold_h"], "wait_basis": pw["basis"],
            "agent": o["agent"], "receiver": o["receiver"],
        })
        if fit == "exceeds":
            alerts.append({"severity": "medium", "type": "berthing_fit", "vessel": o["vessel"],
                           "message": f"{o['vessel']}: " + "; ".join(i for c in checks for i in c["issues"])})
    expected.sort(key=lambda e: e["declared_eta"] or "9999")

    cargo_berths = [b for b in ref.berth_order()]
    occupied = sorted({a["berth"] for a in alongside if a["berth"] and a["cargo_class"] in CARGO_ONLY},
                      key=lambda b: cargo_berths.index(b) if b in cargo_berths else 99)
    stale_days = (date.today() - rd).days
    if as_of is None and stale_days > 2:
        alerts.insert(0, {"severity": "info", "type": "data_freshness", "vessel": None,
                          "message": f"Latest Daily Vessel Position report loaded is {rd.isoformat()} ({stale_days} days old). "
                                     f"Run scripts/update_vessel_intel_data.py to fetch newer reports."})
    sev_order = {"info": 0, "high": 1, "medium": 2}
    alerts.sort(key=lambda a: sev_order.get(a["severity"], 9))
    port_waiting = [w for w in waiting if w["account"] == "port"]
    return {
        "as_of_report": rd.isoformat(), "report_time": _iso(now),
        "summary": {
            "alongside_cargo": sum(1 for a in alongside if a["cargo_class"] in CARGO_ONLY),
            "alongside_other": sum(1 for a in alongside if a["cargo_class"] not in CARGO_ONLY),
            "berths_occupied_cargo": len(occupied), "berths_total": len(cargo_berths),
            "occupied_berths": occupied,
            "waiting_total": len(waiting),
            "waiting_port_account": len(port_waiting),
            "waiting_non_port_account": sum(1 for w in waiting if w["account"] == "non_port"),
            "longest_port_account_wait_h": max((w["waiting_h"] or 0 for w in port_waiting), default=0),
            "expected_total": len(expected),
            "expected_next_72h": sum(1 for e in expected if e["hours_to_eta"] is not None and e["hours_to_eta"] <= 72),
            "programmed_berthings": sum(1 for m in programme(rd) if m["event"] in ("berths", "re_berthed")),
            "programmed_sailings": sum(1 for m in programme(rd) if m["event"] == "sails"),
            "alerts": len([a for a in alerts if a["severity"] != "info"]),
        },
        "alerts": alerts, "alongside": alongside, "waiting": waiting, "expected": expected,
        "programme": [{"at": _iso(m["dt"]), "event": m["event"], "vessel": m["vessel"], "berth": m["berth"]}
                      for m in sorted(programme(rd), key=lambda m: m["dt"])],
        "lineage": lineage(rd, "Each list is the NMPA Daily Vessel Position report of this date, normalised; forecasts are added per row "
                               "(departure: F3, more-wait: empirical, ETA band: F2, wait probability: F5, fit: F6).", "REAL (derived)"),
    }


# ──────────────────────────────────────────────────────────────────────
# F4 — berth plan / queue forecast (rule-based)
# ──────────────────────────────────────────────────────────────────────

def berth_plan(as_of: Optional[date] = None, horizon_h: Optional[float] = None) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    now = report_dt(rd)
    horizon_h = horizon_h or ref.standard("berth_conflict_window_hours")
    end = now + timedelta(hours=horizon_h)
    board = port_call_board(rd)
    berths = ref.berth_order()
    free_at: Dict[str, datetime] = {b: now for b in berths}
    timeline: Dict[str, List[Dict[str, Any]]] = {b: [] for b in berths}

    for a in board["alongside"]:
        b = a["berth"]
        if b not in timeline:
            continue
        dep = datetime.fromisoformat(a["predicted_departure"]) if a.get("predicted_departure") else None
        if a["cargo_class"] in CARGO_ONLY:
            free_at[b] = max(free_at[b], dep or now + timedelta(hours=24))
        timeline[b].append({"vessel": a["vessel"], "kind": "alongside", "cargo_class": a["cargo_class"],
                            "start": _iso(now - timedelta(hours=a["hours_alongside"] or 0)), "end": _iso(dep) if dep else None,
                            "note": a.get("forecast_method")})

    demand = []
    for w in board["waiting"]:
        if w["cargo_class"] not in CARGO_ONLY:
            continue
        prefs = [w["target_berth"]] if w["target_berth"] else []
        call = _idx()["by_id"].get(w["call_id"]) if w["call_id"] else None
        for p in (call or {}).get("berth_prefs") or []:
            if p not in prefs:
                prefs.append(p)
        ready = now if w["account"] in ("port", "unknown") or w["list"] == "Tankers scheduled" else None
        demand.append({"vessel": w["vessel"], "kind": "waiting", "cargo_class": w["cargo_class"], "prefs": prefs,
                       "ready": ready, "loa_m": w["loa_m"], "draft_m": None, "reason": w["reason"], "account": w["account"]})
    for e in board["expected"]:
        if e["cargo_class"] not in CARGO_ONLY or not e["declared_eta"]:
            continue
        eta = datetime.fromisoformat(e["declared_eta"])
        if eta > end:
            continue
        demand.append({"vessel": e["vessel"], "kind": "expected", "cargo_class": e["cargo_class"], "prefs": e["berth_prefs"],
                       "ready": max(eta, now), "loa_m": e["loa_m"], "draft_m": e["draft_m"], "reason": None, "account": None})

    prog_berth = {m["vessel"]: m for m in programme(rd) if m["event"] in ("berths", "re_berthed") and m["berth"]}
    for d in demand:
        pm = prog_berth.get(d["vessel"])
        if pm and pm["berth"] in free_at:
            d["prefs"] = [pm["berth"]] + [b for b in d["prefs"] if b != pm["berth"]]
            d["ready"] = max(pm["dt"], now)
            d["programme"] = True
    sequenced, unsequenced = [], []
    for d in sorted([d for d in demand if d["ready"]], key=lambda d: (not d.get("programme"), d["ready"], d["kind"] != "waiting")):
        options = []
        for b in d["prefs"]:
            if b not in free_at:
                continue
            fit = fit_check(b, d["draft_m"], d["loa_m"], d["ready"].date())
            if fit["status"] == "exceeds":
                continue
            start = max(d["ready"], free_at[b])
            options.append((start, b))
            if d.get("programme"):
                break  # NMPA has already allotted this berth
        if not options:
            unsequenced.append({**d, "why": "no berth preference that fits" if d["prefs"] else "no berth preference stated"})
            continue
        start, b = min(options)
        mismatch = None
        if d.get("programme"):
            if free_at[b] > d["ready"] + timedelta(hours=2):
                mismatch = (f"NMPA programmes berth {b} at {d['ready'].strftime('%d/%m %H:%M')}, but our departure forecast for the "
                            f"current occupant frees it only at {free_at[b].strftime('%d/%m %H:%M')} — programme taken as authoritative")
            start = d["ready"]
        stay, basis, n = median_stay(d["cargo_class"], b, rd)
        stay = stay or 36.0
        free_at[b] = start + timedelta(hours=stay)
        wait = (start - d["ready"]).total_seconds() / 3600
        item = {"vessel": d["vessel"], "kind": d["kind"], "cargo_class": d["cargo_class"], "berth": b,
                "ready": _iso(d["ready"]), "start": _iso(start), "end": _iso(start + timedelta(hours=stay)),
                "predicted_wait_h": _r(wait), "service_h": _r(stay), "service_basis": f"median stay, {basis} (n={n})",
                "slot_basis": "NMPA berthing programme" if d.get("programme") else "FIFO over stated berth preferences",
                "note": mismatch,
                "alternatives": [x for x in d["prefs"] if x != b]}
        sequenced.append(item)
        timeline[b].append({"vessel": d["vessel"], "kind": f"planned ({d['kind']})", "cargo_class": d["cargo_class"],
                            "start": item["start"], "end": item["end"], "note": f"wait {wait:.0f} h"})
    for d in demand:
        if not d["ready"]:
            unsequenced.append({**d, "why": f"waiting for a non-port reason ({d['reason']}) — berths when cargo/receiver is ready"})

    th = ref.standard("port_account_wait_alert_hours")
    conflicts = []
    for b in berths:
        items = [s for s in sequenced if s["berth"] == b]
        late = [s for s in items if (s["predicted_wait_h"] or 0) > th]
        queued = [s for s in items if (s["predicted_wait_h"] or 0) > 6]
        if late or queued:
            conflicts.append({"berth": b, "vessels_needing_berth": len(items),
                              "max_predicted_wait_h": max((s["predicted_wait_h"] or 0 for s in items), default=0),
                              "severity": "high" if late else "watch",
                              "message": (f"Berth {b}: {len(items)} vessel(s) need it in the next {horizon_h:.0f} h; "
                                          f"longest predicted wait {max((s['predicted_wait_h'] or 0 for s in items), default=0):.0f} h"
                                          + (f" — consider alternatives: {', '.join(sorted({a for s in late for a in s['alternatives']}))}"
                                             if any(s['alternatives'] for s in late) else ""))})
    conflicts.sort(key=lambda c: (c["severity"] != "high", -c["max_predicted_wait_h"]))
    for d in unsequenced:
        d.pop("ready", None)
    return {
        "as_of_report": rd.isoformat(), "horizon_h": horizon_h, "report_time": _iso(now),
        "berths": [{"berth": b, "label": ref.berths()[b]["label"], "type": ref.berths()[b]["type"],
                    "free_at": _iso(free_at[b]), "timeline": timeline[b]} for b in berths],
        "sequenced": sequenced, "not_sequenced": unsequenced, "conflicts": conflicts,
        "lineage": lineage(rd, "Berthings already in NMPA's programme (today's report) are placed first at the programmed berth/time; "
                               "everything else follows a rule-based first-come-first-served simulation: each vessel takes the earliest-free berth among its "
                               "stated preferences that fits its draft/LOA; service time = historical median stay for the cargo class at "
                               "that berth. Ignores priority-berthing policy, tide windows and pilot/tug availability — a planning aid, "
                               "not NMPA's berth plan.", "RULE-BASED (real inputs)"),
    }


# ──────────────────────────────────────────────────────────────────────
# F9 — waiting analytics
# ──────────────────────────────────────────────────────────────────────

def waiting_analytics(as_of: Optional[date] = None, months: int = 12) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    start = (rd.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    calls = [c for c in _idx()["calls"] if c["cargo_class"] in CARGO_ONLY and c["wait_h"] is not None
             and c["first_berth_dt"] and start <= c["first_berth_dt"].date() <= rd]
    by_month = defaultdict(list)
    for c in calls:
        by_month[c["first_berth_dt"].strftime("%Y-%m")].append(c)
    monthly = []
    for m in sorted(by_month):
        cs = by_month[m]
        tot = [c["wait_h"] for c in cs]
        port = [c["wait_port_h"] for c in cs if c["wait_port_h"] is not None]
        oth = [c["wait_non_port_h"] for c in cs if c["wait_non_port_h"] is not None]
        monthly.append({"month": m, "calls": len(cs),
                        "avg_wait_days": _r(mean(tot) / 24, 2), "avg_port_account_days": _r(mean(port) / 24, 2) if port else None,
                        "avg_other_days": _r(mean(oth) / 24, 2) if oth else None,
                        "share_waited_over_24h_pct": _r(100 * sum(t > 24 for t in tot) / len(tot))})
    reason_hours = Counter()
    for c in calls:
        tot_obs = sum(c["wait_reasons"].values())
        for reason, n in c["wait_reasons"].items():
            reason_hours[reason] += c["wait_h"] * n / tot_obs if tot_obs else 0
    by_reason = [{"reason": r, "vessel_days": _r(h / 24, 1)} for r, h in reason_hours.most_common()]
    wob = Counter()
    wob_calls = Counter()
    for c in calls:
        if c["wait_port_h"] and c["wait_port_h"] > 0:
            b = c["wob_target"] or c["primary_berth"] or "unknown"
            wob[b] += c["wait_port_h"]
            wob_calls[b] += 1
    by_berth = [{"berth": b, "port_account_vessel_days": _r(h / 24, 1), "calls": wob_calls[b]} for b, h in wob.most_common()]
    rec = Counter()
    rec_calls = Counter()
    for c in calls:
        if c["wait_non_port_h"] and c["receiver"]:
            rec[c["receiver"]] += c["wait_non_port_h"]
            rec_calls[c["receiver"]] += 1
    by_receiver = [{"receiver_shipper": r, "non_port_vessel_days": _r(h / 24, 1), "calls": rec_calls[r]} for r, h in rec.most_common(12)]
    by_class = []
    for cls in sorted(CARGO_ONLY):
        cs = [c for c in calls if c["cargo_class"] == cls]
        if cs:
            by_class.append({"cargo_class": cls, "calls": len(cs),
                             "median_wait_h": _r(median(c["wait_h"] for c in cs)),
                             "avg_wait_days": _r(mean(c["wait_h"] for c in cs) / 24, 2),
                             "share_port_account_pct": _r(100 * sum(c["wait_port_h"] or 0 for c in cs) / max(sum(c["wait_h"] for c in cs), 1e-9))})
    return {
        "as_of_report": rd.isoformat(), "period": [start.isoformat(), rd.isoformat()], "calls": len(calls),
        "monthly": monthly, "by_reason": by_reason, "by_cargo_class": by_class,
        "want_of_berth_by_berth": by_berth,
        "non_port_waiting_by_receiver": by_receiver,
        "receiver_note": "Commercially sensitive — for NMPA internal use only.",
        "lineage": lineage(rd, "Pre-berthing wait = arrival (DOA + time) → first berthing (movement log, else berthing date). Split into "
                               "Port Account / Other in proportion to the days each anchorage reason was printed, mirroring NMPA's "
                               "monthly report. Reason → account rules in data/reference/vessel_intel_reference.json.", "REAL (derived)"),
    }


# ──────────────────────────────────────────────────────────────────────
# F8 — performance: DVP-derived KPIs vs NMPA's official monthly report
# ──────────────────────────────────────────────────────────────────────

OFFICIAL_CLASSES = ["dry_bulk_conventional", "dry_bulk_mechanical", "dry_bulk_total", "break_bulk", "liquid_bulk", "container", "overall"]


def _dvp_month_kpis(month: str) -> Dict[str, Dict[str, Any]]:
    """KPIs per official cargo class for calls that sailed in `month` (NMPA counts vessels sailed)."""
    sailed = []
    for c in _idx()["calls"]:
        if c["cargo_class"] not in CARGO_ONLY or c["stage"] != "berthed":
            continue
        if c["depart_dt"] is not None:
            m = c["depart_dt"].strftime("%Y-%m")
        elif c["status"] == "departed_unrecorded":
            m = c["last_report"].strftime("%Y-%m")
        else:
            continue
        if m == month:
            sailed.append(c)
    groups = {cls: [c for c in sailed if c["cargo_class"] == cls] for cls in CARGO_ONLY}
    groups["dry_bulk_total"] = groups["dry_bulk_conventional"] + groups["dry_bulk_mechanical"]
    groups["overall"] = sailed
    out = {}
    for cls, cs in groups.items():
        w = [c for c in cs if c["wait_h"] is not None]
        wp = [c for c in cs if c["wait_port_h"] is not None]
        ab = [c["at_berth_h"] for c in cs if c["at_berth_h"] is not None]
        out[cls] = {
            "vessels_handled": len(cs),
            "pre_berthing_days|total": _r(mean(c["wait_h"] for c in w) / 24, 2) if w else None,
            "pre_berthing_days|port_account": _r(mean(c["wait_port_h"] for c in wp) / 24, 2) if wp else None,
            "pre_berthing_days|other_than_port_account": _r(mean(c["wait_non_port_h"] for c in wp) / 24, 2) if wp else None,
            "turnaround_hours": _r(mean(ab), 1) if ab else None,
            "n_with_wait": len(w), "n_with_stay": len(ab),
        }
    return out


def _verdict(metric: str, official_v: Optional[float], dvp_v: Optional[float]) -> str:
    if official_v is None or dvp_v is None:
        return "n/a"
    if metric == "vessels_handled":
        r = dvp_v / official_v if official_v else 0
        return "matches" if 0.9 <= r <= 1.1 else ("under-detected" if r < 0.9 else "over-counted")
    diff = abs(dvp_v - official_v)
    scale = max(abs(official_v), 0.25 if "days" in metric else 4.0)
    return "close" if diff / scale <= 0.25 else "differs"


def performance(as_of: Optional[date] = None) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    arch = pc.load_archive()
    off = official.load()
    off_months = official.months_available()
    recon = []
    for m in off_months:
        y, mo = map(int, m.split("-"))
        first = date(y, mo, 1)
        last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        cov = pc.coverage(arch, first, last)
        if not arch.first or last < arch.first or first > arch.last or cov["coverage_pct"] < 50:
            continue
        dvp = _dvp_month_kpis(m)
        rows = []
        for cls in OFFICIAL_CLASSES:
            for metric, comp, label in (("vessels_handled", "total", "Vessels handled (sailed)"),
                                        ("pre_berthing_days", "total", "Pre-berthing detention, total (days)"),
                                        ("pre_berthing_days", "port_account", "Pre-berthing, Port Account (days)"),
                                        ("pre_berthing_days", "other_than_port_account", "Pre-berthing, other than Port A/c (days)"),
                                        ("turnaround_hours", "total", "Turn-round time (h) — DVP proxy = time at berth")):
                ov = official.value(m, metric, cls, comp)
                key = metric if metric in ("vessels_handled", "turnaround_hours") else f"{metric}|{comp}"
                dv = dvp.get(cls, {}).get(key)
                rows.append({"cargo_class": cls, "metric": label, "metric_key": f"{metric}|{comp}",
                             "official": ov, "dvp_derived": dv,
                             "difference": _r(dv - ov, 2) if (dv is not None and ov is not None) else None,
                             "verdict": _verdict(metric, ov, dv)})
        recon.append({"month": m, "dvp_coverage_pct": cov["coverage_pct"], "rows": rows})

    series = defaultdict(dict)
    for r in off["rows"]:
        if r["period"] != "month":
            continue
        if r["metric"] == "pre_berthing_days" and r["cargo_class"] == "overall":
            series[r["month"]][f"pre_berthing_{r['component']}_days"] = r["value"]
        elif r["metric"] in ("turnaround_hours", "idle_time_pct", "output_per_berthday_t", "traffic_t") and r["cargo_class"] == "overall":
            series[r["month"]][r["metric"]] = r["value"]
        elif r["metric"] == "vessels_handled":
            series[r["month"]][f"vessels_{r['cargo_class']}"] = r["value"]
    official_series = [{"month": m, **v} for m, v in sorted(series.items())]

    dvp_series = []
    if arch.first:
        m = arch.first.replace(day=1)
        while m <= rd:
            key = m.strftime("%Y-%m")
            k = _dvp_month_kpis(key)["overall"]
            nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
            cov = pc.coverage(arch, m, nxt - timedelta(days=1))
            dvp_series.append({"month": key, "vessels_handled": k["vessels_handled"],
                               "pre_berthing_total_days": k["pre_berthing_days|total"],
                               "pre_berthing_port_account_days": k["pre_berthing_days|port_account"],
                               "pre_berthing_other_than_port_account_days": k["pre_berthing_days|other_than_port_account"],
                               "time_at_berth_h": k["turnaround_hours"], "coverage_pct": cov["coverage_pct"],
                               "partial_month": nxt - timedelta(days=1) > rd})
            m = nxt
    return {
        "as_of_report": rd.isoformat(),
        "official_files": off["files"],
        "official_months_loaded": off_months,
        "reconciliation": recon,
        "official_series": official_series,
        "dvp_series": dvp_series,
        "how_to_read": ("Official = NMPA monthly Operational Performance report (vessels counted when they sail; TRT measured pilot "
                        "boarding → de-boarding). DVP-derived = the same KPI rebuilt from the daily reports. Daily snapshots taken "
                        "around 10:00 miss calls shorter than a day (most container calls), so counts can be under-detected; "
                        "'time at berth' is our closest proxy for NMPA's turn-round time."),
        "lineage": lineage(rd, "Reconciliation of DVP-derived KPIs against NMPA's official monthly report.", "REAL (official + derived)"),
    }


# ──────────────────────────────────────────────────────────────────────
# Overview, data quality, call detail
# ──────────────────────────────────────────────────────────────────────

def overview(as_of: Optional[date] = None) -> Dict[str, Any]:
    rd = as_of_report(as_of)
    board = port_call_board(rd)
    eta = eta_accuracy(rd)
    comp = completion_backtest(rd)
    wm = wait_model()
    last30 = [c for c in _idx()["calls"] if c["cargo_class"] in CARGO_ONLY and c["first_berth_dt"]
              and rd - timedelta(days=30) <= c["first_berth_dt"].date() <= rd and c["wait_h"] is not None]
    perf = performance(rd)
    recon_summary = None
    if perf["reconciliation"]:
        last = perf["reconciliation"][-1]
        pick = {r["metric_key"]: r for r in last["rows"] if r["cargo_class"] == "overall"}
        recon_summary = {"month": last["month"],
                         "pre_berthing_total": pick.get("pre_berthing_days|total"),
                         "pre_berthing_port_account": pick.get("pre_berthing_days|port_account"),
                         "vessels_handled": pick.get("vessels_handled|total")}
    return {
        "as_of_report": rd.isoformat(),
        "board_summary": board["summary"],
        "alerts": board["alerts"][:8],
        "last_30_days": {
            "cargo_calls_berthed": len(last30),
            "avg_pre_berthing_days": _r(mean(c["wait_h"] for c in last30) / 24, 2) if last30 else None,
            "avg_port_account_days": _r(mean(c["wait_port_h"] or 0 for c in last30) / 24, 2) if last30 else None,
            "share_waiting_over_24h_pct": _r(100 * sum(c["wait_h"] > 24 for c in last30) / len(last30)) if last30 else None,
        },
        "model_cards": [
            {"feature": "ETA reliability (F2)", "status": "REAL (derived, backtested)",
             "headline": f"Declared ETA within ±24 h for {eta['declared_eta'].get('within_24h_pct')}% of {eta['declared_eta'].get('n')} arrivals",
             "verdict": eta["verdict"]},
            {"feature": "Departure forecast (F3)", "status": "REAL (derived, backtested)",
             "headline": f"Mean error {comp['all_points']['chosen']['mae_h']} h (NMPA ETD as printed: {comp['all_points']['etd_noon']['mae_h']} h)",
             "verdict": "Uses NMPA's own ETD with a learned time-of-day offset; falls back to balance ÷ handling rate, then typical stay."},
            {"feature": "Wait-probability model (F5)", "status": "REAL (ML, backtested)" if wm.get("use_model") else "REAL (base rate)",
             "headline": f"Held-out AUC {wm.get('model', {}).get('auc')} vs base rate {wm.get('baseline', {}).get('auc')}",
             "verdict": wm.get("verdict")},
            {"feature": "KPI reconciliation (F8)", "status": "REAL (official + derived)",
             "headline": (f"{recon_summary['month']}: pre-berthing {recon_summary['pre_berthing_total']['dvp_derived']} d (DVP) vs "
                          f"{recon_summary['pre_berthing_total']['official']} d (NMPA official)") if recon_summary and recon_summary.get("pre_berthing_total") else
                         "Load NMPA monthly Operational Performance PDFs to reconcile",
             "verdict": "Validates the whole call-stitching pipeline against NMPA's own published numbers."},
            {"feature": "Berth plan (F4)", "status": "RULE-BASED (real inputs)",
             "headline": "FIFO simulation over stated berth preferences", "verdict": "Planning aid — ignores priority policy and tide windows."},
        ],
        "lineage": lineage(rd, "Summary of the Vessel Intelligence features.", "REAL (derived)"),
    }


def data_quality() -> Dict[str, Any]:
    arch = pc.load_archive()
    cal = pc.report_calendar(arch)
    missing_workdays = [r["date"] for r in cal if not r["published"] and r["weekday"] != "Sun"]
    calls = _idx()["calls"]
    flags = Counter(f.split(" ")[0] for c in calls for f in c["flags"])
    cls = Counter(c["cargo_class"] for c in calls if c["stage"] != "expected")
    status = Counter(c["status"] for c in calls)
    exp = [c for c in calls if c["declared_eta"]]
    import json as _json
    review = []
    rp = ref.DATA_DIR / "vessel_name_review_candidates.json"
    if rp.exists():
        try:
            review = _json.loads(rp.read_text())
        except ValueError:
            review = []
    prec = Counter(c["wait_precision"] for c in calls if c["wait_h"] is not None)
    obs = pc.observations()
    reasons = Counter((o.get("reason"), o.get("account")) for o in obs if o["section"] in ("anchorage", "tankers_scheduled"))
    unknown_cargo = Counter(o["cargo"] for o in obs if o["cargo_class"] == "unknown" and o["section"] != "expected")
    return {
        "archive": pc.coverage(arch),
        "imo_coverage": _imo_coverage(calls),
        "missing_working_days": {"count": len(missing_workdays), "most_recent": missing_workdays[-15:]},
        "unparsed_rows": sum(r["unparsed_rows"] or 0 for r in cal if r["published"]),
        "port_calls": {"total": len(calls), "by_status": dict(status), "by_cargo_class": dict(cls),
                       "flags": dict(flags)},
        "linking": {
            "expected_episodes": len(exp),
            "matched_to_arrival_pct": _r(100 * sum(1 for c in exp if c["arrival_dt"]) / len(exp)) if exp else None,
            "wait_precision": dict(prec),
        },
        "waiting_reason_mapping": [{"reason": r, "account": a, "rows": n} for (r, a), n in reasons.most_common()],
        "unclassified_cargo_texts": [{"cargo": k, "rows": v} for k, v in unknown_cargo.most_common(15)],
        "vessel_name_review_queue": len(review),
        "reference_version": ref.reference().get("_version"),
        "report_reference_time": pc.report_reference_time().strftime("%H:%M"),
        "lineage": lineage(arch.last, "Data-quality checks on the DVP archive and the call-stitching step.", "REAL (derived)"),
    }


def _imo_coverage(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How much of the traffic the curated IMO lookup already identifies."""
    cargo = [c for c in calls if c["cargo_class"] in CARGO_ONLY]
    with_imo = [c for c in cargo if c.get("imo")]
    match = Counter(c.get("imo_match") for c in cargo)
    unmatched = Counter(c["vessel"] for c in cargo if not c.get("imo"))
    return {
        "ships_in_lookup": sum(len(v) for v in ref.imo_lookup().values()),
        "cargo_calls": len(cargo), "cargo_calls_with_imo": len(with_imo),
        "share_pct": round(100 * len(with_imo) / len(cargo), 1) if cargo else None,
        "distinct_ships_with_imo": len({c["imo"] for c in with_imo}),
        "by_match": dict(match),
        "needs_review": sorted({c["vessel"] for c in cargo if c.get("imo_match") in ("ambiguous", "loa_mismatch")}),
        "next_to_look_up": [{"vessel": v, "calls": n} for v, n in unmatched.most_common(25)],
        "file": "data/reference/vessel_imo_lookup.csv",
    }


def call_detail(call_id: str) -> Optional[Dict[str, Any]]:
    c = _idx()["by_id"].get(call_id)
    if not c:
        return None
    out = {k: _iso(v) if isinstance(v, (date, datetime)) else v for k, v in c.items() if not k.startswith("_")}
    out["observations"] = [{k: (_iso(v) if isinstance(v, (date, datetime)) else (v.strftime("%H:%M") if isinstance(v, time) else v))
                            for k, v in o.items()} for o in sorted(c.get("_rows", []), key=lambda o: (o["report_date"], o["section"]))]
    lo = (c["arrival_dt"] or datetime.combine(c["first_report"], time(0))) - timedelta(days=1)
    hi = datetime.combine(c["last_report"], time(23, 59)) + timedelta(days=3)
    out["movements"] = [{"event": m["event"], "berth": m["berth"], "at": _iso(m["dt"]), "precision": m["precision"],
                         "first_reported_in": _iso(m["reported_in"])}
                        for m in pc.movements() if m["vessel"] == c["vessel"] and lo <= m["dt"] <= hi]
    return out


def search_calls(q: str = "", status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    ql = q.upper().strip()
    out = []
    for c in reversed(_idx()["calls"]):
        if ql and ql not in c["vessel"] and ql not in (c["cargo"] or "") and ql not in (c["receiver"] or "").upper() \
                and ql != (c.get("imo") or ""):
            continue
        if status and c["status"] != status:
            continue
        out.append({"call_id": c["call_id"], "vessel": c["vessel"], "imo": c.get("imo"), "status": c["status"], "cargo": c["cargo"],
                    "cargo_class": c["cargo_class"], "arrival": _iso(c["arrival_dt"]), "berths": c["berths"],
                    "wait_h": c["wait_h"], "at_berth_h": c["at_berth_h"]})
        if len(out) >= limit:
            break
    return out


def warm_up() -> None:
    """Build every cache once (called in a background thread at API start-up)."""
    try:
        overview()
        arrival_outlook()
        berth_plan()
        waiting_analytics()
        data_quality()
    except Exception as exc:  # never crash the API because of a warm-up
        print(f"[vessel-intel] warm-up failed: {exc}")
