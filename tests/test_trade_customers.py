"""Tests for Customer Watch (real NMPA daily vessel reports) and the voyage fixes it relies on."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import trade_customers as tc
from backend.app.services import trade_split as ts

client = TestClient(app)
ALIASES = tc.load_aliases()


def _day(path, date, berthed=(), anchorage=(), expected=()):
    base = {"run": "", "cargo": "", "receiver_shipper": "", "qty_total": "", "qty_balance": "", "agent": ""}
    (path / f"{date}.json").write_text(json.dumps({
        "report_date": date, "berthed": [{**base, **r} for r in berthed],
        "anchorage": list(anchorage), "tankers_scheduled": [], "expected": list(expected), "movements": [],
    }))


# ── customer names ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("HP/IOC/BPC", "BPCL + HPCL + IOCL"),
    ("IOC/BPC/HP", "BPCL + HPCL + IOCL"),
    ("HPCL/IOCL/BPCL", "BPCL + HPCL + IOCL"),
    ("IOCL", "IOCL"),
    ("SANTHOSHIMAT HAA", "SANTHOSHIMATHAA"),
    ("MRPL 40000", "MRPL"),
    ("UF 250(I)+250(E )", "UF"),
    ("AEGIS C/O SEALORD", "AEGIS"),
    ("NFL A/C IPL", "IPL"),
    ("EPSILON", "EPSILON CARBON"),
    ("VARIOUS", tc.NOT_STATED),
    ("RECEIVER/ SHIPPER", tc.NOT_STATED),
    ("199(I)+150(E )", tc.NOT_STATED),
    ("90(P) + 75(CREW)", tc.NOT_STATED),
    ("", tc.NOT_STATED),
    ("SOME NEW COMPANY", "SOME NEW COMPANY"),
])
def test_canonical_customer(raw, expected):
    assert tc.canonical_customer(raw, ALIASES) == expected


# ── voyage fixes in trade_split ───────────────────────────────────────────────
def test_two_ships_on_alternate_days_are_two_voyages_not_more(tmp_path):
    """Regression: voyage numbers used to be shared across ships, splitting one call into several."""
    a = {"vessel_name": "ALPHA (9.1)", "run": "F", "cargo": "CRUDE(D)", "receiver_shipper": "MRPL", "qty_total": "1000", "qty_balance": "9000"}
    b = {"vessel_name": "BRAVO", "run": "C", "cargo": "IOF(D)", "receiver_shipper": "KIOCL", "qty_total": "500", "qty_balance": "500"}
    _day(tmp_path, "2025-09-01", [a])
    _day(tmp_path, "2025-09-02", [b])
    _day(tmp_path, "2025-09-03", [{**a, "qty_total": "6000", "qty_balance": "4000"}, {**b, "qty_total": "1000", "qty_balance": ""}])
    v = ts.build_voyages(tmp_path)
    assert len(v) == 2


def test_parcel_is_handled_plus_balance(tmp_path):
    ship = {"vessel_name": "HISUI (10.90)", "run": "F", "cargo": "LPG(D)", "receiver_shipper": "IOC/HPC/BPC",
            "qty_total": "1472", "qty_balance": "30632"}
    _day(tmp_path, "2026-08-22", [ship])
    _day(tmp_path, "2026-08-24", [{**ship, "qty_total": "16800", "qty_balance": "15304"}])
    v = ts.build_voyages(tmp_path)
    assert len(v) == 1
    assert v.iloc[0]["qty"] == 32104 and v.iloc[0]["qty_handled"] == 16800


@pytest.mark.parametrize("raw,clean", [
    ("VISHVA PRERNA (12.50-A)", "VISHVA PRERNA"), ("VISHVA PRERNA (BACK LDG)", "VISHVA PRERNA"),
    ("UNION GLORY (5.90) B.3/ 2/ 6/ 7", "UNION GLORY"), ("SM NEW ORLEANS 12.0-A)", "SM NEW ORLEANS"),
    ("SEA GULL 18", "SEA GULL 18"),
])
def test_vessel_name_notes_are_removed(raw, clean):
    assert ts._vessel_norm(raw) == clean


# ── rules on a small made-up folder ───────────────────────────────────────────
def test_trend_and_quiet_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "_official_non_container_by_month", lambda: {})
    monkeypatch.setattr(tc, "MIN_REPORT_DAYS_FOR_FULL_MONTH", 1)
    monkeypatch.setattr(tc, "TREND_MONTHS", 1)
    monkeypatch.setattr(tc, "MIN_CALLS_FOR_TREND", 2)
    # BIG calls every 5 days in month 1 and 2, then stops; SMALL calls once a month.
    dates = ["2025-09-01", "2025-09-06", "2025-09-11", "2025-09-16", "2025-10-01", "2025-10-06"]
    for i, d in enumerate(dates):
        _day(tmp_path, d, [{"vessel_name": f"SHIP{i}", "run": "C", "cargo": "IOF(D)", "receiver_shipper": "BIG", "qty_total": "50000"}])
    _day(tmp_path, "2025-11-20", [{"vessel_name": "SMALL1", "run": "F", "cargo": "COAL(D)", "receiver_shipper": "SMALL", "qty_total": "1000"}])
    # Reports keep coming (no reporting gap), with other customers' ships, up to early December, so November is a
    # finished month and BIG's silence is real silence rather than missing reports.
    import pandas as pd
    for i, d in enumerate(list(pd.date_range("2025-10-11", "2025-11-30", freq="5D")) + [pd.Timestamp("2025-12-02")]):
        if d.strftime("%Y-%m-%d") != "2025-11-20":
            _day(tmp_path, d.strftime("%Y-%m-%d"), [{"vessel_name": f"OTHER{i}", "run": "F", "cargo": "COAL(D)",
                                                     "receiver_shipper": "OTHER", "qty_total": "1000"}])
    tc.build.cache_clear()
    b = tc.build(tmp_path)
    rows = {r["customer"]: r for r in tc._customer_rows(b)}
    big = rows["BIG"]
    assert big["calls"] == 6 and big["tonnes"] == 300000
    assert big["recent_calls"] == 0 and big["previous_calls"] == 2       # Nov vs Oct
    assert big["trend"] == "Falling" and big["change_pct"] == -100.0
    alerts = tc._alerts(list(rows.values()), b)
    big_alerts = [a for a in alerts if a["customer"] == "BIG"]
    assert len(big_alerts) == 1                                       # merged, not duplicated
    assert big_alerts[0]["type"] == "gone_quiet" and set(big_alerts[0]["types"]) == {"gone_quiet", "falling"}
    assert "Also:" in big_alerts[0]["message"]
    tc.build.cache_clear()


# ── real data ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def watch():
    return tc.get_customer_watch()


def test_real_data_shares_and_counts_are_consistent(watch):
    assert watch["available"]
    rows = watch["customers"]
    assert abs(sum(r["share_of_traced_tonnes_pct"] or 0 for r in rows) - 100) < 1.0
    assert sum(r["calls"] for r in rows) + watch["totals"]["calls_without_customer"] == watch["totals"]["calls"]
    for r in rows:
        assert r["cargo_calls"] + r["container_calls"] == r["calls"]
        assert r["customer"] != tc.NOT_STATED


def test_real_data_is_checked_against_official_statements(watch):
    cov = watch["coverage_vs_official"]
    assert cov["months"], "at least one complete month must overlap the NMPA monthly statements"
    for m in cov["months"]:
        assert 50 <= m["traced_pct"] <= 120          # parcels must be in the same range as official tonnes
        assert m["named_customer_pct"] <= m["traced_pct"] + 0.1


def test_trend_windows_use_complete_months_only(watch):
    p = watch["period"]
    assert set(p["recent_window"]) <= set(p["complete_months"])
    assert set(p["previous_window"]) <= set(p["complete_months"])
    assert not set(p["recent_window"]) & set(p["previous_window"])


def test_alerts_follow_their_rules(watch):
    rows = {r["customer"]: r for r in watch["customers"]}
    assert len({a["customer"] for a in watch["alerts"]}) == len(watch["alerts"]), "one alert per customer"
    for a in watch["alerts"]:
        r = rows[a["customer"]]
        assert a["type"] in a["types"]
        types = set(a["types"])
        if "falling" in types:
            big = abs((r["recent_tonnes"] or 0) - (r["previous_tonnes"] or 0)) >= tc.LARGE_CHANGE_T
            assert r["trend"] == "Falling" and (r["change_pct"] <= -tc.TREND_ALERT_PCT or (big and r["change_pct"] <= -tc.LARGE_CHANGE_PCT))
        if "rising" in types:
            big = abs((r["recent_tonnes"] or 0) - (r["previous_tonnes"] or 0)) >= tc.LARGE_CHANGE_T
            assert r["trend"] == "Rising" and (r["change_pct"] >= tc.TREND_ALERT_PCT or (big and r["change_pct"] >= tc.LARGE_CHANGE_PCT))
        if "gone_quiet" in types:
            assert not r["joint_entry"] and r["days_since_last_call"] >= tc.QUIET_MIN_DAYS and r["status"] == "Gone quiet"
        if "waiting" in types:
            assert r["recent_share_of_not_ready_days_pct"] >= tc.NOT_READY_ALERT_SHARE_PCT


def test_endpoints_ok_no_nan_and_unknown_is_404(watch):
    r = client.get("/trade/customers")
    assert r.status_code == 200
    json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))
    top = watch["customers"][0]["customer"]
    d = client.get("/trade/customer", params={"name": top.lower()})
    assert d.status_code == 200 and d.json()["customer"] == top
    json.loads(d.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))
    assert client.get("/trade/customer", params={"name": "NO SUCH CUSTOMER"}).status_code == 404


def test_detail_months_add_up_to_summary(watch):
    top = watch["customers"][0]
    d = tc.get_customer_detail(top["customer"])
    assert sum(m["calls"] for m in d["monthly"]) == top["calls"]
    complete_t = sum(m["tonnes"] or 0 for m in d["monthly"] if m["complete"])
    assert complete_t == pytest.approx(top["tonnes"], abs=2)
