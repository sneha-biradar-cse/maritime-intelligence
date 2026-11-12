"""Tests for the Nov 2026 Incentive Engine improvements: peer-port check, gaming checks, ship charges, portfolio budget,
stacking rule, settlement, retention option, and the public-data fetch script's parsers."""
import importlib.util
import json
import math

import pytest

from backend.app.services import incentive_engine as ie
from backend.app.services import incentive_evaluation as iev
from backend.app.services import incentive_integrity as iig
from backend.app.services import incentive_kpis as ik
from backend.app.services import incentive_portfolio as ipf
from backend.app.services import incentive_rules as ir
from backend.app.services import vessel_charges as vc


# ── ship charges ───────────────────────────────────────────────────────────────────────────────────────
def test_every_ship_charge_rate_is_in_the_scale_of_rates_pdf():
    import re
    txt = re.sub(r"\s+", "", ik._sor_text())      # one PDF reader spaces out some lines ('4 , 2 1 , 9 5 0'): compare without spaces
    missing = [s for s in vc.SOR_STRINGS if s not in txt]
    assert not missing, missing


def test_pilotage_slabs_join_up_and_respect_the_minimum():
    for coastal in (True, False):
        fx = None if coastal else 1.0
        assert vc.pilotage(30000, coastal, fx) == pytest.approx(vc.PILOTAGE["coastal" if coastal else "foreign"][1][1])
        assert vc.pilotage(60000, coastal, fx) == pytest.approx(vc.PILOTAGE["coastal" if coastal else "foreign"][2][1])
        assert vc.pilotage(1000, coastal, fx) == vc.PILOTAGE_MIN["coastal" if coastal else "foreign"]


def test_one_call_by_hand():
    c = vc.call_cost(45000, False, "dry", 50, usd_inr=88.0)
    assert c["port_dues_rs"] == round(45000 * 0.4110 * 88)
    assert c["pilotage_rs"] == round((15807 + 0.4217 * 15000) * 88)
    assert c["berth_hire_rs"] == round(45000 * 0.002824 * 50 * 88)
    assert c["total_rs"] == round(45000 * 0.4110 * 88 + (15807 + 0.4217 * 15000) * 88 + 45000 * 0.002824 * 50 * 88)
    small = vc.call_cost(500, True, "liquid", 2.2)           # minimum per hour; 'part of an hour' counts as an hour
    assert small["berth_hire_rs"] == round(216.52 * 3)
    with pytest.raises(ValueError):
        vc.call_cost(45000, False, "dry", 10)                 # a foreign ship needs an exchange rate


def test_rebates_say_so_when_ship_sizes_are_missing(monkeypatch):
    monkeypatch.setattr(vc, "gt_table", lambda: {})
    monkeypatch.setattr(vc, "_loa_fit", lambda: None)
    r = vc.container_rebate()
    assert r["calls_priced"] == 0 and "cannot be priced" in r["plain"]


# ── did it work? ───────────────────────────────────────────────────────────────────────────────────────
def test_peer_arithmetic_uses_other_ports_not_all_ports():
    s = {"2025-01": (100.0, 1100.0), "2026-01": (130.0, 1230.0)}      # NMPA +30%; other ports 1000 -> 1100 (+10%)
    actual, expected = iev._window_extra(s, ["2026-01"])
    assert actual == 130 and expected == pytest.approx(110.0)


def test_evaluate_on_real_data_has_a_plain_answer():
    r = iev.evaluate("Crude oil", "2026-03-14", "2026-03-31")
    assert r["available"] and r["plain_answer"] and r["verdict"]
    assert r["nmpa_actual_t"] > 0 and r["expected_without_scheme_t"] > 0
    with pytest.raises(KeyError):
        iev.evaluate("Containers", "2026-01-01", "2026-03-31")


# ── gaming checks ────────────────────────────────────────────────────────────────────────────────────
def test_timing_shift_is_flagged():
    monthly = {"2026-01": 100, "2026-02": 100, "2026-03": 200, "2026-04": 40}
    r = iig._timing("2026-01-01", "2026-03-31", monthly, list(monthly))
    assert r["status"] == "Warning"
    r2 = iig._timing("2026-01-01", "2026-03-31", {"2026-01": 100, "2026-02": 110, "2026-03": 105, "2026-04": 100},
                     ["2026-01", "2026-02", "2026-03", "2026-04"])
    assert r2["status"] == "OK"


def test_easy_baseline_is_flagged():
    monthly = {m: 1000.0 for m in ("2026-01", "2026-02", "2026-03", "2026-04")}
    assert iig._easy_baseline("2026-05-01", 1200, 2, monthly, list(monthly))["status"] == "Warning"   # 600 t/month vs 1000
    assert iig._easy_baseline("2026-05-01", 2000, 2, monthly, list(monthly))["status"] == "OK"


def test_related_companies_come_from_the_evidence_file():
    g = iig._groups()
    assert {"PPL (PARADEEP PHOSPHATES)", "MCF"} <= set(g[g.group == "Paradeep Phosphates Ltd"].member)
    assert all(g.source)


def test_integrity_check_runs_for_a_real_customer():
    r = iig.check("Crude oil", "2026-05-01", "2026-10-31", "MRPL")
    assert len(r["checks"]) == 6 and r["summary"]
    assert all(c["status"] in ("OK", "Warning", "Watch", "Note", "Not enough data", "Not checked", "Not checked yet") for c in r["checks"])


# ── portfolio, stacking, settlement, retention ─────────────────────────────────────────────────────────
@pytest.fixture
def policy_file(monkeypatch):
    rel = "data/_test_incentive_policy.json"
    monkeypatch.setattr(ipf, "POLICY_FILE", rel)
    f = ie.tmk.ROOT / rel
    yield f
    if f.exists():
        f.unlink()


def test_default_policy_keeps_the_old_rule(policy_file):
    priced = [r["cargo"] for r in ie.get_revenue()["cargos"]]
    e = ir.check_eligibility("Iron ore exports", "2026-12-01", "2027-02-28", [], [], priced, discount_pct=5)
    assert not e["eligible"]                                   # overlaps the 20% iron ore rebate: blocked by default


def test_board_ceiling_allows_or_blocks_stacking(policy_file):
    ipf.save_policy({"allow_combination": True, "max_combined_benefit_pct": 30})
    priced = [r["cargo"] for r in ie.get_revenue()["cargos"]]
    ok = ir.check_eligibility("Iron ore exports", "2026-12-01", "2027-02-28", [], [], priced, discount_pct=5)
    assert ok["eligible"] and ok["stacking"]["combined_pct"] == 25
    no = ir.check_eligibility("Iron ore exports", "2026-12-01", "2027-02-28", [], [], priced, discount_pct=15)
    assert not no["eligible"]
    with pytest.raises(ValueError):
        ipf.save_policy({"max_combined_benefit_pct": 150})


def _rec(**kw):
    base = {"id": "T-1", "scope": "Rebate on extra volume", "commitment_t": 1000.0, "clawback_rule": "proportional", "settlement": ""}
    base.update(kw)
    return base


def test_settlement_proportional_and_all_or_nothing(monkeypatch):
    res = {"months_held": ["2026-01", "2026-02", "2026-03"], "months_total": 3, "estimated_discount_cost_rs": 100000,
           "actual_tonnes": 800}
    monkeypatch.setattr(ie, "scheme_results", lambda rec: res)
    p = ipf.settlement(_rec())
    assert p["shortfall_t"] == 200 and p["clawback_rs"] == 20000 and p["final_rebate_rs"] == 80000
    a = ipf.settlement(_rec(clawback_rule="all_or_nothing", settlement="At billing"))
    assert a["clawback_rs"] == 100000 and "recovered" in a["plain"]
    met = ipf.settlement(_rec(commitment_t=700))
    assert met["clawback_rs"] == 0


def test_settlement_in_progress_shows_on_track(monkeypatch):
    monkeypatch.setattr(ie, "scheme_results", lambda rec: {"months_held": ["2026-01"], "months_total": 4,
                                                           "estimated_discount_cost_rs": 5000, "actual_tonnes": 200})
    p = ipf.settlement(_rec(commitment_t=1000))
    assert p["commitment_to_date_t"] == 250 and p["ahead_or_behind_t"] == -50


def test_retention_break_even_equals_the_discount_share():
    r = ipf.retention_option(10000, 50.0, 10)
    assert r["cost_rs"] == 50000
    assert r["break_even_chance_pct"] == pytest.approx(10 / 90 * 100, abs=0.1)     # cost / (revenue kept at the lower rate)


def test_portfolio_runs():
    p = ipf.portfolio()
    assert p["annual_wharfage_rs"] > 0 and p["plain"]


# ── fetch script parsers (no network) ─────────────────────────────────────────────────────────────────
def _script():
    spec = importlib.util.spec_from_file_location("fetch", ie.tmk.ROOT / "scripts" / "fetch_public_incentive_data.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_wikidata_parse_and_name_match_skip_ambiguous():
    m = _script()
    payload = {"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q1"}, "itemLabel": {"value": "Ever Given"}, "imo": {"value": "9811000"}, "gt": {"value": "220940"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q2"}, "itemLabel": {"value": "Ocean Star"}, "imo": {"value": "1"}, "gt": {"value": "30000"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q3"}, "itemLabel": {"value": "Ocean Star"}, "imo": {"value": "2"}, "gt": {"value": "52000"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q4"}, "itemLabel": {"value": "Q4"}, "imo": {"value": "3"}, "gt": {"value": "1000"}}]}}
    reg = m.parse_wikidata(payload)
    assert len(reg) == 3                                       # unlabeled item dropped
    rows, amb = m.match_ships(reg, ["EVER GIVEN", "OCEAN STAR", "UNKNOWN"])
    assert [r["vessel_name"] for r in rows] == ["EVER GIVEN"] and rows[0]["gt"] == 220940 and amb == ["OCEAN STAR"]


def test_fx_parse_and_official_rates_win():
    m = _script()
    ecb = m.parse_frankfurter({"rates": {"2026-10-01": {"INR": 88.5}, "2026-10-02": {"INR": 88.6}}})
    off = [{"date": "2026-10-01", "usd_inr": 88.4, "source": "RBI/FBIL reference rate (official; file x.csv)"}]
    merged = m.merge_fx(off, ecb)
    assert {r["date"]: r["usd_inr"] for r in merged} == {"2026-10-01": 88.4, "2026-10-02": 88.6}


def test_new_routes_answer():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    c = TestClient(app)
    assert c.get("/incentive/evaluate", params={"cargo": "Crude oil", "start": "2026-03-14", "end": "2026-03-31"}).status_code == 200
    assert c.get("/incentive/vessel-charges/call", params={"grt": 30000, "coastal": True, "hours": 10}).status_code == 200
    assert c.get("/incentive/vessel-charges/call", params={"grt": 30000, "hours": 10}).status_code == 422   # no exchange rate
    assert c.get("/incentive/portfolio").status_code == 200
    assert c.get("/incentive/policy").json()["clawback_rules"]
