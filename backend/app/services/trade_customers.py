"""
Customer Watch - who brings cargo to New Mangalore Port, whether they are growing or shrinking,
and how much ship waiting they account for.

Data (all real, all in this repository):
  * data/daily_vessel_position_parsed/   NMPA Daily Vessel Positions. Every berthed ship with its cargo,
                                         receiver/shipper, quantities and run flag; ships at anchorage with the
                                         written reason for waiting; ships expected in the coming days.
  * data/customer_aliases.csv            Spelling variants -> one customer name (reviewable by the port team).
  * data/port_cargo_monthly.csv          NMPA monthly statements, used only to check how much of the official
                                         tonnage the daily reports account for.

Rules (each one is stated in the API response too):
1. One CALL = one ship + cargo + stay (trade_split.build_voyages). A call belongs to the month it was last seen.
2. TONNES = the ship's cargo parcel: "handled so far" + "balance" written in the daily sheet. Container calls are
   counted as calls only (their quantities are box counts, not tonnes).
3. CUSTOMER = receiver/shipper as written, cleaned with customer_aliases.csv. Joint entries ("HP/IOC/BPC") stay a
   joint customer ("BPCL + HPCL + IOCL") because the sheet does not say how the parcel is split.
4. Only COMPLETE months (at least MIN_REPORT_DAYS_FOR_FULL_MONTH daily reports) are used for trends.
5. Trend = last TREND_MONTHS complete months against the TREND_MONTHS before them. No seasonal adjustment and no
   year-on-year comparison yet, because the daily reports only start in September 2025.
6. Waiting = trade_waiting.build_waiting_events (ships that waited, reason as written by port staff).

Nothing here is simulated. Where the data cannot answer a question the response says so.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_split as ts
from backend.app.services import trade_waiting as tw
from backend.app.services.forecasting import _ttl_cache

ROOT = Path(__file__).resolve().parents[3]
ALIAS_FILE = ROOT / "data" / "customer_aliases.csv"

NOT_STATED = "Not stated"
# Waiting reasons as written by port staff, split so the customer's own share is exact:
CUSTOMER_NR = "Customer not ready (receiver / shipper / cargo)"
SHIP_NR = "Ship not ready"
ALIAS_NOT_STATED = "NOT_STATED"

# ─── Settings (all can be changed; each is reported back in the response) ─────
MIN_REPORT_DAYS_FOR_FULL_MONTH = 15   # months with fewer daily reports are "partial"
TREND_MONTHS = 3                      # compare the last 3 complete months with the 3 before
TREND_ALERT_PCT = 30.0                # change in tonnes (or calls, for container customers) to raise an alert
MIN_SHARE_FOR_TREND_ALERT_PCT = 1.0   # customers below this share of traced tonnes are not alerted on
LARGE_CHANGE_PCT = 5.0               # ... or at least this % AND at least LARGE_CHANGE_T tonnes (large customers)
LARGE_CHANGE_T = 100_000
MIN_CALLS_FOR_TREND = 4               # calls in both windows together, else "Too few calls"
QUIET_MIN_DAYS = 30                   # "gone quiet" needs at least this many days without a call ...
QUIET_GAP_MULTIPLE = 3.0              # ... and at least this multiple of the customer's usual gap
QUIET_MIN_CALLS = 5                   # only for customers with a track record
NEW_CUSTOMER_DAYS = 90                # first call within this many days of the latest report = new
NOT_READY_ALERT_SHARE_PCT = 10.0      # share of all "not ready" waiting days in the trend window
AGENT_NAME_MIN_USES = 20              # a name used this often in the AGENT column is flagged as an agent name


# ═══════════════════════════════════════════════════════════════════
# Customer names
# ═══════════════════════════════════════════════════════════════════

def _key(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def load_aliases(path: Path | None = None) -> dict[str, str]:
    """{spelling key: customer}. Lines starting with '#' are comments."""
    p = path or ALIAS_FILE
    if not p.exists():
        return {}
    a = pd.read_csv(p, comment="#", dtype=str).fillna("")
    a = a[(a["variant"].str.strip() != "") & (a["customer"].str.strip() != "")]
    return {_key(v): c.strip().upper() for v, c in zip(a["variant"], a["customer"])}


_COUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*\(\s*[A-Z ]+\s*\)")     # '574(I)', '450(PASSENGER)'
_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Z0-9.])\d+(?:\.\d+)?(?![A-Z0-9])")   # 'MRPL 40000', 'UF 2'


def _strip_counts(s: str) -> str:
    s = _COUNT_RE.sub(" ", s)
    s = _NUMBER_TOKEN_RE.sub(" ", s)
    s = re.sub(r"\s*\+\s*", " ", s)
    return re.sub(r"\s+", " ", s).strip(" /&,-")


def canonical_customer(raw: Any, aliases: dict[str, str]) -> str:
    """Receiver/shipper text as written in the daily sheet -> one customer name (or NOT_STATED)."""
    s = re.sub(r"\s+", " ", str(raw or "").upper()).strip()
    if not s:
        return NOT_STATED
    hit = aliases.get(_key(s))                      # whole string first ('AEGIS C/O SEALORD', 'NFL A/C IPL')
    if hit:
        return NOT_STATED if hit == ALIAS_NOT_STATED else hit
    s = _strip_counts(s)
    s = re.sub(r"\([^)]*\)", " ", s)              # notes in brackets, e.g. '(TERMINAL : AEGIS)'
    s = re.sub(r"[()]", " ", s).strip()
    if not re.search(r"[A-Z]{2}", s):               # only numbers / box counts / a single letter
        return NOT_STATED
    hit = aliases.get(_key(s))
    if hit:
        return NOT_STATED if hit == ALIAS_NOT_STATED else hit
    names: set[str] = set()
    for part in re.split(r"[/&,]", s):
        part = re.sub(r"\s+", " ", part).strip(" .-")
        if not part:
            continue
        mapped = aliases.get(_key(part), part)
        if mapped != ALIAS_NOT_STATED:
            names.add(mapped)
    if not names:
        return NOT_STATED
    return " + ".join(sorted(names))


# ═══════════════════════════════════════════════════════════════════
# Load
# ═══════════════════════════════════════════════════════════════════

def _read_days(folder: Path) -> list[dict]:
    days = []
    for path in sorted(folder.glob("*.json")):
        try:
            days.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted((d for d in days if d.get("report_date")), key=lambda d: d["report_date"])


def _agent_names(days: list[dict]) -> set[str]:
    counts: dict[str, int] = {}
    for d in days:
        for sec in ("berthed", "anchorage", "tankers_scheduled", "expected"):
            for r in d.get(sec, []):
                k = _key(r.get("agent") or "")
                if k:
                    counts[k] = counts.get(k, 0) + 1
    return {k for k, n in counts.items() if n >= AGENT_NAME_MIN_USES}


def _month_label(m: str) -> str:
    return pd.Timestamp(m + "-01").strftime("%b %Y")


def _window_label(months: list[str]) -> str:
    if not months:
        return ""
    return f"{_month_label(months[0])} to {_month_label(months[-1])}" if len(months) > 1 else _month_label(months[0])


def _num(x: Any, nd: int = 1) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


def _pct(cur: float, prev: float) -> float | None:
    return round((cur / prev - 1) * 100, 1) if prev and prev > 0 else None


def _official_non_container_by_month() -> dict[str, float]:
    """NMPA monthly statements: all cargo except container lines, for months where every cargo is reported."""
    p = ti._prepared()
    wide, totals = p["wide"], p["totals"]
    cont = [c for c in wide.columns if "CONTAINER" in c[1]]
    out = {}
    for date, total in totals["total"].items():
        if pd.notna(total):
            out[date.strftime("%Y-%m")] = float(total - wide.loc[date, cont].sum())
    return out


@_ttl_cache(seconds=300)
def build(daily_dir: Path | None = None, alias_path: Path | None = None) -> dict[str, Any]:
    folder = daily_dir or ts.DAILY_DIR
    aliases = load_aliases(alias_path)
    days = _read_days(folder)
    if not days:
        return {"available": False}

    report_dates = pd.to_datetime(pd.Series([d["report_date"] for d in days])).drop_duplicates().sort_values()
    days_per_month = report_dates.dt.strftime("%Y-%m").value_counts().sort_index()
    all_months = [m.strftime("%Y-%m") for m in pd.period_range(report_dates.min(), report_dates.max(), freq="M").to_timestamp()]
    latest = report_dates.max()
    # Complete = enough daily reports AND the month has ended (the current month is never complete).
    complete = [m for m in all_months
                if days_per_month.get(m, 0) >= MIN_REPORT_DAYS_FOR_FULL_MONTH
                and pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0) < latest]
    # Stretches with no daily report for more than a week (ships that came and went then are not seen).
    gaps = [(a + pd.Timedelta(days=1), b - pd.Timedelta(days=1))
            for a, b in zip(report_dates.iloc[:-1], report_dates.iloc[1:]) if (b - a).days > 7]

    cache: dict[str, str] = {}

    def cust(raw: Any) -> str:
        r = str(raw or "")
        if r not in cache:
            cache[r] = canonical_customer(r, aliases)
        return cache[r]

    v = ts.build_voyages(folder)
    if v.empty:
        return {"available": False}
    v = v.copy()
    v["customer"] = v["receiver"].map(cust)
    v["is_container"] = v["direction"].eq("both")
    v["tonnes"] = np.where(v["is_container"], np.nan, v["qty"])
    v["month"] = v["last_seen"].dt.strftime("%Y-%m")

    ev = tw.build_waiting_events(folder)
    if not ev.empty:
        ev = ev.copy()
        ev["customer"] = ev["receiver"].map(cust)
        ship_nr = ev["reason"].fillna("").str.upper().str.contains(r"VESSEL NOT|SHIP NOT")
        ev["who"] = np.where(ev["bucket"] == tw.BUCKET_CUSTOMER, np.where(ship_nr, SHIP_NR, CUSTOMER_NR), ev["bucket"])

    last_day = days[-1]
    now_rows = []
    for sec, status in (("expected", "Expected"), ("anchorage", "Waiting at anchorage"), ("tankers_scheduled", "Waiting (tanker)")):
        for r in last_day.get(sec, []):
            name = ts._vessel_norm(r.get("vessel_name"))
            if not name or re.fullmatch(r"-+", name):
                continue
            cargo = ts._clean_code(str(r.get("cargo") or ""))
            if not cargo or ts.NON_CARGO.search(cargo):
                continue
            now_rows.append({
                "status": status, "vessel": name, "cargo": cargo, "family": ts.classify_cargo(cargo)[0],
                "customer": cust(r.get("receiver_shipper")), "run": str(r.get("run") or "").strip().upper(),
                "quantity_t": _num(ts._qty(r.get("qty")), 0),
                "eta_or_arrival": str(r.get("eta_date") or r.get("doa") or "").strip(),
                "waiting": str(r.get("waiting_duration") or "").strip(),
                "reason": str(r.get("reason_or_note") or "").strip(),
            })

    targets = set(aliases.values())
    passed_through = sorted({c for c in cache.values() if c != NOT_STATED and " + " not in c and c not in targets})

    return {
        "available": True, "voyages": v, "waiting": ev, "now": pd.DataFrame(now_rows),
        "days_per_month": days_per_month, "months": all_months, "complete": complete,
        "latest": latest, "gaps": gaps, "agent_keys": _agent_names(days), "aliases": aliases, "passed_through": passed_through,
        "raw_by_customer": _raw_spellings(cache),
    }


def _raw_spellings(cache: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for raw, c in cache.items():
        if raw.strip():
            out.setdefault(c, []).append(re.sub(r"\s+", " ", raw.upper()).strip())
    return {k: sorted(set(v)) for k, v in out.items()}


# ═══════════════════════════════════════════════════════════════════
# Per-customer numbers
# ═══════════════════════════════════════════════════════════════════

def _windows(complete: list[str]) -> tuple[list[str], list[str]]:
    recent = complete[-TREND_MONTHS:]
    prev = complete[-2 * TREND_MONTHS:-TREND_MONTHS]
    return recent, prev


def _trend(cur_t: float, prev_t: float, cur_c: int, prev_c: int, container_only: bool) -> tuple[str, float | None]:
    if cur_c + prev_c < MIN_CALLS_FOR_TREND:
        return "Too few ships to judge", None
    change = _pct(cur_c, prev_c) if container_only else _pct(cur_t, prev_t)
    if change is None:
        return ("New in recent months" if (cur_c > 0 and prev_c == 0) else "Steady"), None
    # A change counts if it is large in % (small customers swing a lot with one ship), or if it is a smaller %
    # but a large number of tonnes (for a customer like MRPL, -10% is several hundred thousand tonnes).
    big_t = (not container_only) and abs(cur_t - prev_t) >= LARGE_CHANGE_T and abs(change) >= LARGE_CHANGE_PCT
    if change >= TREND_ALERT_PCT or (change > 0 and big_t):
        return "Rising", change
    if change <= -TREND_ALERT_PCT or (change < 0 and big_t):
        return "Falling", change
    return "Steady", change


def _customer_rows(b: dict) -> list[dict]:
    v, ev, now = b["voyages"], b["waiting"], b["now"]
    complete = b["complete"]
    recent, prev = _windows(complete)
    in_complete = v[v["month"].isin(complete)]
    named_tonnes = float(in_complete.loc[in_complete["customer"] != NOT_STATED, "tonnes"].sum())
    not_ready_recent = 0.0
    if not ev.empty:
        not_ready_recent = float(ev[(ev["who"] == CUSTOMER_NR) & ev["month"].isin(recent)]["wait"].sum())
    all_not_ready = float(ev[ev["who"] == CUSTOMER_NR]["wait"].sum()) if not ev.empty else 0.0

    rows = []
    for name, g in v[v["customer"] != NOT_STATED].groupby("customer"):
        gc = g[g["month"].isin(complete)]
        cargo_calls = g[~g["is_container"]]
        tonnes = float(gc["tonnes"].sum())
        r_t = float(g.loc[g["month"].isin(recent), "tonnes"].sum())
        p_t = float(g.loc[g["month"].isin(prev), "tonnes"].sum())
        r_c = int(g["month"].isin(recent).sum())
        p_c = int(g["month"].isin(prev).sum())
        container_only = bool(g["is_container"].all())
        trend, change = _trend(r_t, p_t, r_c, p_c, container_only)

        fam = (g.groupby("family").agg(calls=("vessel", "size"), tonnes=("tonnes", "sum"))
               .sort_values(["tonnes", "calls"], ascending=False))
        flagged = g[g["run"].isin(["F", "C"])]
        dates = g["last_seen"].drop_duplicates().sort_values()   # several cargos on one day = one visit
        gaps = dates.diff().dt.days.dropna()
        last_call = dates.max()

        w = ev[ev["customer"] == name] if not ev.empty else pd.DataFrame()
        w_recent = w[w["month"].isin(recent)] if not w.empty else w
        nr = w[w["who"] == CUSTOMER_NR]["wait"].sum() if not w.empty else 0.0
        snr = w[w["who"] == SHIP_NR]["wait"].sum() if not w.empty else 0.0
        nr_recent = w_recent[w_recent["who"] == CUSTOMER_NR]["wait"].sum() if not w_recent.empty else 0.0
        nxt = now[now["customer"] == name] if not now.empty else pd.DataFrame()

        rows.append({
            "customer": name,
            "joint_entry": " + " in name,
            "agent_name_warning": _key(name) in b["agent_keys"],
            "calls": int(len(g)),
            "cargo_calls": int(len(cargo_calls)),
            "container_calls": int(g["is_container"].sum()),
            "tonnes": _num(tonnes, 0),
            "share_of_traced_tonnes_pct": _num(tonnes / named_tonnes * 100, 1) if named_tonnes else None,
            "tonnes_missing_calls": int(cargo_calls["tonnes"].isna().sum()),
            "main_cargo": fam.index[0] if len(fam) else "",
            "cargos": [{"cargo": f, "calls": int(x["calls"]), "tonnes": _num(x["tonnes"], 0)} for f, x in fam.head(4).iterrows()],
            "inbound_tonnes": _num(gc.loc[gc["direction"] == "inbound", "tonnes"].sum(), 0),
            "outbound_tonnes": _num(gc.loc[gc["direction"] == "outbound", "tonnes"].sum(), 0),
            "foreign_calls": int((flagged["run"] == "F").sum()),
            "coastal_calls": int((flagged["run"] == "C").sum()),
            "recent_tonnes": _num(r_t, 0), "previous_tonnes": _num(p_t, 0),
            "recent_calls": r_c, "previous_calls": p_c,
            "change_pct": change,
            "trend": trend,
            "trend_basis": "calls" if container_only else "tonnes",
            "first_call": g["first_seen"].min().strftime("%Y-%m-%d"),
            "last_call": last_call.strftime("%Y-%m-%d"),
            "days_since_last_call": int((b["latest"] - last_call).days),
            "usual_gap_days": _num(gaps.median(), 0) if len(gaps) >= 2 else None,
            "waiting_events": int(len(w)),
            "waiting_ship_days": _num(w["wait"].sum(), 1) if not w.empty else 0.0,
            "not_ready_ship_days": _num(nr, 1),
            "ship_not_ready_ship_days": _num(snr, 1),
            "share_of_all_not_ready_days_pct": _num(nr / all_not_ready * 100, 1) if all_not_ready else None,
            "recent_not_ready_ship_days": _num(nr_recent, 1),
            "recent_share_of_not_ready_days_pct": _num(nr_recent / not_ready_recent * 100, 1) if not_ready_recent else None,
            "in_latest_report": {
                "expected": int((nxt["status"] == "Expected").sum()) if not nxt.empty else 0,
                "waiting": int((nxt["status"] != "Expected").sum()) if not nxt.empty else 0,
                "expected_tonnes": _num(nxt.loc[nxt["status"] == "Expected", "quantity_t"].sum(), 0) if not nxt.empty else 0.0,
            },
        })
    rows.sort(key=lambda r: (-(r["tonnes"] or 0), -r["calls"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def _fmt_t(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x / 1e6:.2f} million t" if abs(x) >= 1e6 else f"{x:,.0f} t"


def _gap_days_after(b: dict, since: str) -> int:
    """Days without any daily report after a customer's last call (we cannot know whether a ship came then)."""
    t0 = pd.Timestamp(since)
    return sum((min(z, b["latest"]) - max(a, t0)).days + 1 for a, z in b.get("gaps", []) if z >= t0)


def _alerts(rows: list[dict], b: dict) -> list[dict]:
    recent, prev = _windows(b["complete"])
    rl, pl = _window_label(recent), _window_label(prev)
    out = []
    for r in rows:
        share = r["share_of_traced_tonnes_pct"] or 0.0
        big = share >= 5.0
        enough = (share >= MIN_SHARE_FOR_TREND_ALERT_PCT if r["trend_basis"] == "tonnes"
                  else r["recent_calls"] + r["previous_calls"] >= 2 * MIN_CALLS_FOR_TREND)
        if r["trend"] in ("Falling", "Rising") and enough:
            word = "down" if r["trend"] == "Falling" else "up"
            if r["trend_basis"] == "calls":
                msg = (f"{r['customer']}: {r['recent_calls']} calls in {rl}, {word} {abs(r['change_pct']):.0f}% "
                       f"from {r['previous_calls']} in {pl}.")
            else:
                msg = (f"{r['customer']}: {_fmt_t(r['recent_tonnes'])} in {rl}, {word} {abs(r['change_pct']):.0f}% "
                       f"from {_fmt_t(r['previous_tonnes'])} in {pl} ({r['recent_calls']} calls against {r['previous_calls']}).")
            out.append({"type": "falling" if r["trend"] == "Falling" else "rising",
                        "severity": "high" if (big and r["trend"] == "Falling") else "medium",
                        "customer": r["customer"], "share_pct": share, "message": msg})
        gap = r["usual_gap_days"]
        # Joint entries are skipped: the same companies often reappear under a different joint combination.
        if (not r["joint_entry"] and r["calls"] >= QUIET_MIN_CALLS and gap is not None
                and r["days_since_last_call"] - _gap_days_after(b, r["last_call"]) >= max(QUIET_MIN_DAYS, QUIET_GAP_MULTIPLE * gap)):
            out.append({"type": "gone_quiet", "severity": "high" if big else "medium", "customer": r["customer"],
                        "share_pct": share,
                        "message": (f"{r['customer']}: no ship for {r['days_since_last_call']} days (last call {pd.Timestamp(r['last_call']):%d %b %Y}); "
                                    f"it usually calls every {gap:.0f} days.")})
        first = pd.Timestamp(r["first_call"])
        if (b["latest"] - first).days <= NEW_CUSTOMER_DAYS and r["calls"] >= 2 and first > pd.Timestamp(b["months"][0] + "-01") + pd.Timedelta(days=NEW_CUSTOMER_DAYS):
            out.append({"type": "new", "severity": "info", "customer": r["customer"], "share_pct": share,
                        "message": (f"{r['customer']}: new customer, {r['calls']} calls since {pd.Timestamp(r['first_call']):%d %b %Y} "
                                    f"({_fmt_t(r['tonnes'])}, mainly {r['main_cargo']}).")})
        rs = r["recent_share_of_not_ready_days_pct"]
        if rs is not None and rs >= NOT_READY_ALERT_SHARE_PCT:
            out.append({"type": "waiting", "severity": "high" if rs >= 25 else "medium", "customer": r["customer"],
                        "share_pct": share,
                        "message": (f"{r['customer']}: ships waited {r['recent_not_ready_ship_days']:.0f} ship-days in {rl} because "
                                    f"the receiver/shipper was not ready, {rs:.0f}% of all such waiting at the port.")})
    # One alert per customer: several findings about the same customer are joined into one message.
    order = {"high": 0, "medium": 1, "info": 2}
    priority = ["gone_quiet", "falling", "waiting", "rising", "new"]
    merged: dict[str, dict] = {}
    for a in out:
        m = merged.get(a["customer"])
        if m is None:
            merged[a["customer"]] = {**a, "types": [a["type"]]}
            continue
        m["types"].append(a["type"])
        first, rest = (m, a) if priority.index(m["type"]) <= priority.index(a["type"]) else (a, m)
        tail = rest["message"].split(": ", 1)[-1]
        m["message"] = first["message"] + " Also: " + tail[0].lower() + tail[1:]
        m["type"] = first["type"]
        m["severity"] = min(m["severity"], a["severity"], key=lambda x: order[x])
    result = list(merged.values())
    result.sort(key=lambda a: (order[a["severity"]], -(a["share_pct"] or 0)))
    return result


STATUS_BY_TYPE = {"gone_quiet": "Gone quiet", "new": "New customer"}


def _status(row: dict, alert: dict | None) -> str:
    """One word for the table: Gone quiet / New customer / Rising / Falling / Steady / Too few calls."""
    if alert:
        for t in ("gone_quiet", "new"):
            if t in alert["types"]:
                return STATUS_BY_TYPE[t]
    return "New customer" if row["trend"] == "New in recent months" else row["trend"]


def _coverage(b: dict) -> dict:
    v = b["voyages"]
    official = _official_non_container_by_month()
    rows = []
    for m in b["complete"]:
        if m not in official:
            continue
        traced = float(v.loc[v["month"] == m, "tonnes"].sum())
        named = float(v.loc[(v["month"] == m) & (v["customer"] != NOT_STATED), "tonnes"].sum())
        rows.append({"month": m, "official_t": _num(official[m], 0), "traced_t": _num(traced, 0),
                     "traced_pct": _num(traced / official[m] * 100, 1), "named_customer_pct": _num(named / official[m] * 100, 1),
                     "report_days": int(b["days_per_month"].get(m, 0))})
    tr = sum(r["traced_t"] for r in rows)
    of = sum(r["official_t"] for r in rows)
    nm = sum(r["named_customer_pct"] * r["official_t"] / 100 for r in rows)
    out = {"months": rows,
           "traced_pct": _num(tr / of * 100, 1) if of else None,
           "named_customer_pct": _num(nm / of * 100, 1) if of else None}
    if rows:
        out["verdict"] = (
            f"Over {len(rows)} months, ships in the daily reports account for {out['traced_pct']:.0f}% of the non-container "
            f"tonnes in NMPA's official monthly statements (lowest month {min(r['traced_pct'] for r in rows):.0f}%, highest "
            f"{max(r['traced_pct'] for r in rows):.0f}%), and {out['named_customer_pct']:.0f}% is traced to a named customer. "
            "The rest is mostly ships whose whole stay fell on days without a daily report. Customer tonnes here are "
            "therefore a close but incomplete picture, good for ranking and trends, not for billing."
        )
    else:
        out["verdict"] = "No complete month overlaps with the official statements, so coverage could not be checked."
    return out


def _concentration(rows: list[dict]) -> dict:
    shares = sorted([r["share_of_traced_tonnes_pct"] or 0.0 for r in rows], reverse=True)
    cum, n80 = 0.0, 0
    for s in shares:
        cum += s
        n80 += 1
        if cum >= 80:
            break
    return {"top1_pct": _num(sum(shares[:1]), 1), "top3_pct": _num(sum(shares[:3]), 1),
            "top5_pct": _num(sum(shares[:5]), 1), "customers_for_80pct": n80,
            "top3": [r["customer"] for r in rows[:3]]}


# ═══════════════════════════════════════════════════════════════════
# Public
# ═══════════════════════════════════════════════════════════════════

def _settings() -> dict:
    return {"min_report_days_for_full_month": MIN_REPORT_DAYS_FOR_FULL_MONTH, "trend_months": TREND_MONTHS,
            "trend_alert_pct": TREND_ALERT_PCT, "min_share_for_trend_alert_pct": MIN_SHARE_FOR_TREND_ALERT_PCT,
            "min_calls_for_trend": MIN_CALLS_FOR_TREND,
            "large_change_pct": LARGE_CHANGE_PCT, "large_change_t": LARGE_CHANGE_T, "quiet_min_days": QUIET_MIN_DAYS,
            "quiet_gap_multiple": QUIET_GAP_MULTIPLE, "new_customer_days": NEW_CUSTOMER_DAYS,
            "not_ready_alert_share_pct": NOT_READY_ALERT_SHARE_PCT}


HOW_IT_WORKS = [
    "Every ship in NMPA's daily berthed list is one call per cargo and stay; it counts in the month it was last seen.",
    "Tonnes are each ship's cargo parcel from the daily sheet (handled so far + balance). Container ships count as calls only.",
    "Customer = receiver/shipper as written by port staff, with spelling variants merged using data/customer_aliases.csv.",
    "Joint entries such as 'HP/IOC/BPC' are kept as one joint customer, because the sheet does not say how the parcel is split.",
    "Trend = the last 3 complete months against the 3 before them. A month is complete when it has at least 15 daily reports.",
    "Waiting comes from ships listed at anchorage, with the reason written by port staff (see 'Why ships wait').",
]

LIMITS = [
    "Daily reports start in September 2025, so there is no year-on-year comparison yet and seasonal swings are not removed.",
    "Ships whose whole stay fell on days without a daily report are missed; the coverage check above shows how much. "
    "Stretches with no report at all are listed with the period, and are not counted as 'days without a ship'.",
    "Customer names are cleaned by spelling only. The merges in data/customer_aliases.csv need confirming by NMPA Traffic.",
    "Some names written in the receiver column are shipping agents, not cargo owners; these are marked.",
    "Tonnes are ship parcels from an operations sheet, not billed or officially reported tonnes.",
]


@_ttl_cache(seconds=300)
def get_customer_watch() -> dict[str, Any]:
    b = build()
    if not b.get("available"):
        return {"available": False, "note": "No daily vessel position files found in data/daily_vessel_position_parsed/."}
    rows = _customer_rows(b)
    alerts = _alerts(rows, b)
    by_customer = {a["customer"]: a for a in alerts}
    for r in rows:
        r["status"] = _status(r, by_customer.get(r["customer"]))
    recent, prev = _windows(b["complete"])
    v = b["voyages"]
    ns = v[v["customer"] == NOT_STATED]
    return {
        "available": True,
        "label": "From NMPA daily vessel reports - traced ship parcels, not official tonnes",
        "data_source": "data/daily_vessel_position_parsed/ (NMPA Daily Vessel Positions) + data/customer_aliases.csv",
        "period": {"from": b["months"][0], "to": b["latest"].strftime("%Y-%m-%d"),
                   "report_gaps": [{"from": a.strftime("%Y-%m-%d"), "to": z.strftime("%Y-%m-%d")} for a, z in b["gaps"]],
                   "complete_months": b["complete"],
                   "partial_months": [m for m in b["months"] if m not in b["complete"]],
                   "recent_window": recent, "previous_window": prev,
                   "recent_label": _window_label(recent), "previous_label": _window_label(prev),
                   "latest_report": b["latest"].strftime("%Y-%m-%d")},
        "totals": {"calls": int(len(v)), "customers": len(rows),
                   "calls_without_customer": int(len(ns)),
                   "tonnes_traced": _num(v.loc[v["month"].isin(b["complete"]), "tonnes"].sum(), 0)},
        "concentration": _concentration(rows),
        "customers": rows,
        "alerts": alerts,
        "coverage_vs_official": _coverage(b),
        "name_review": {
            "alias_rows": len(b["aliases"]),
            "names_used_as_written": len(b["passed_through"]),
            "examples_used_as_written": b["passed_through"][:25],
            "note": "Names not in data/customer_aliases.csv are used as written. Add a row there to merge a spelling.",
        },
        "settings": _settings(),
        "how_it_works": HOW_IT_WORKS,
        "limits": LIMITS,
    }


def _resolve_name(name: str, rows: list[dict], aliases: dict[str, str]) -> str | None:
    wanted = name.strip().upper()
    names = [r["customer"] for r in rows]
    if wanted in names:
        return wanted
    via_alias = canonical_customer(wanted, aliases)
    if via_alias in names:
        return via_alias
    k = _key(wanted)
    for n in names:
        if _key(n) == k:
            return n
    return None


@_ttl_cache(seconds=300)
def get_customer_detail(name: str) -> dict[str, Any] | None:
    """Monthly series, cargo mix, recent calls, waiting and ships due for one customer. None if unknown."""
    watch = get_customer_watch()
    if not watch.get("available"):
        return None
    b = build()
    resolved = _resolve_name(name, watch["customers"], b["aliases"])
    if resolved is None:
        return None
    summary = next(r for r in watch["customers"] if r["customer"] == resolved)
    v = b["voyages"]
    g = v[v["customer"] == resolved].sort_values("last_seen")

    series = []
    for m in b["months"]:
        gm = g[g["month"] == m]
        series.append({"month": m, "complete": m in b["complete"], "report_days": int(b["days_per_month"].get(m, 0)),
                       "calls": int(len(gm)), "tonnes": _num(gm["tonnes"].sum(), 0),
                       "inbound_tonnes": _num(gm.loc[gm["direction"] == "inbound", "tonnes"].sum(), 0),
                       "outbound_tonnes": _num(gm.loc[gm["direction"] == "outbound", "tonnes"].sum(), 0)})

    mix = []
    for (fam, direction), x in g.groupby(["family", "direction"]):
        f = x[x["run"].isin(["F", "C"])]
        mix.append({"cargo": fam, "direction": direction, "calls": int(len(x)), "tonnes": _num(x["tonnes"].sum(), 0),
                    "foreign_calls": int((f["run"] == "F").sum()), "coastal_calls": int((f["run"] == "C").sum())})
    mix.sort(key=lambda r: (-(r["tonnes"] or 0), -r["calls"]))

    calls = [{"vessel": r.vessel, "cargo": r.cargo, "cargo_group": r.family, "direction": r.direction,
              "first_seen": r.first_seen.strftime("%Y-%m-%d"), "last_seen": r.last_seen.strftime("%Y-%m-%d"),
              "run": r.run, "tonnes": _num(r.tonnes, 0), "written_as": r.receiver}
             for r in g.sort_values("last_seen", ascending=False).head(25).itertuples()]

    ev = b["waiting"]
    w = ev[ev["customer"] == resolved].sort_values("first_seen", ascending=False) if not ev.empty else pd.DataFrame()
    waits = [{"vessel": r.vessel, "cargo": r.cargo, "first_seen": r.first_seen.strftime("%Y-%m-%d"),
              "wait_days": _num(r.wait, 2), "reason_as_written": r.reason, "reason_group": r.who}
             for r in w.head(20).itertuples()] if not w.empty else []
    by_reason = ([{"reason": k, "events": int(len(x)), "ship_days": _num(x["wait"].sum(), 1)}
                  for k, x in w.groupby("who")] if not w.empty else [])
    by_reason.sort(key=lambda r: -r["ship_days"])

    now = b["now"]
    due = now[now["customer"] == resolved].to_dict("records") if not now.empty else []
    return {
        "customer": resolved,
        "summary": summary,
        "monthly": series,
        "cargo_mix": mix,
        "recent_calls": calls,
        "waiting_by_reason": by_reason,
        "recent_waiting": waits,
        "in_latest_report": {"report_date": b["latest"].strftime("%Y-%m-%d"), "ships": due},
        "spellings_seen": b["raw_by_customer"].get(resolved, []),
        "label": watch["label"],
        "limits": LIMITS,
    }
