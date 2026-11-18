"""
Tariff calculator tests. Every expected figure is worked by hand from the
NMPA Indexed SOR w.e.f. 01.05.2026 (nmpa_public_data/tariff/SOR_extracted.txt);
the SOR clause is cited next to each case.

Run from the project root:  python -m pytest tests/test_tariff_calculator.py -q
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes import cost
from backend.app.services import cost_engine as C
from backend.app.services.sor_wharfage import chargeable_units, match_commodity


def total(**kw):
    base = dict(cargo_type="IOF(D)", cargo_quantity_mt=1000, trade_type="foreign", cargo_flow="import",
                vessel_type="dry_bulk", vessel_grt=None, berth_hours=0)
    base.update(kw)
    return C.calculate_total_cost(**base)


# ---------------- wharfage, 3.1.1 ----------------

def test_wharfage_iron_ore_fines_coastal_real_call():
    # VISHVA BANDHAN, Berth 2, IOF, run C: 53,400 handled + 1,595 balance; B.III.j coastal ₹43.16
    w = C.calculate_wharfage("IOF(D)", 54995, "coastal")
    assert w["sor_code"] == "B.III.j"
    assert w["amount"] == pytest.approx(54995 * 43.16)


@pytest.mark.parametrize("qty,units", [(100.3, 100.5), (100.5, 101), (100.0, 100), (0.2, 1)])
def test_unit_rounding_and_minimum(qty, units):
    # 3.1.1 note 3(b): fractions up to 0.5 -> 0.5, 0.5 and above -> 1; note 4: minimum one tonne
    assert chargeable_units(qty) == units


def test_crude_at_spm_uses_spm_line():
    r = total(cargo_type="CRUDE(D)", cargo_quantity_mt=100000, vessel_type="liquid", berth="SPM")
    assert r["breakdown"]["wharfage"]["sor_code"] == "A.I.j"
    assert r["breakdown"]["wharfage"]["amount"] == pytest.approx(100000 * 34.90)
    r2 = total(cargo_type="CRUDE(D)", cargo_quantity_mt=100000, vessel_type="liquid", berth="10")
    assert r2["breakdown"]["wharfage"]["amount"] == pytest.approx(100000 * 96.60)


# ---------------- berth hire, 2.3.1 ----------------

def test_berth_hire_rounds_part_hours_up():
    # 30,000 GRT foreign dry bulk: 30,000 x US$0.002824 = US$84.72/hr; 35.2 h -> 36 h
    b = C.calculate_berth_hire("dry_bulk", 30000, 35.2, "foreign")
    assert b["chargeable_hours"] == 36
    assert b["amount"] == pytest.approx(36 * 84.72)


def test_berth_hire_minimum_per_hour():
    # 2,000 GRT x 0.002824 = 5.648 < minimum US$9.82/hr
    b = C.calculate_berth_hire("dry_bulk", 2000, 10, "foreign")
    assert b["amount"] == pytest.approx(98.2)


def test_berth_hire_double_banking_and_small_craft():
    assert C.calculate_berth_hire("liquid", 20000, 10, "coastal", double_banked=True)["amount"] == pytest.approx(
        0.5 * 20000 * 0.10861 * 10)
    # boats, barges and craft: ₹136.063 per vessel per hour, no GRT needed
    assert C.calculate_berth_hire("barge_tug_craft", None, 24.5, "coastal")["amount"] == pytest.approx(25 * 136.063, abs=0.01)


def test_berth_hire_without_grt_is_not_guessed():
    b = C.calculate_berth_hire("dry_bulk", None, 30, "foreign")
    assert b["status"] == "needs_grt" and b["amount"] is None


# ---------------- pilotage 2.2.1, port dues 2.1.1 ----------------

@pytest.mark.parametrize("grt,trade,expected", [
    (45000, "coastal", 421950 + 15000 * 11.251),
    (70000, "foreign", 28458 + 10000 * 0.3692),
    (2500, "coastal", 42194.00),          # minimum pilotage fee
    (20000, "foreign", 20000 * 0.5269),
])
def test_pilotage(grt, trade, expected):
    assert C.calculate_pilotage(grt, trade)["amount"] == pytest.approx(expected, abs=0.01)


def test_port_dues_and_ballast_concession():
    assert C.calculate_port_dues("ship_steamer_spm", 40000, "foreign")["amount"] == pytest.approx(16440)
    # 2.1.2 item 1: 25% concession for vessels in ballast
    assert C.calculate_port_dues("ship_steamer_spm", 40000, "foreign", "ballast_no_passengers")["amount"] == pytest.approx(12330)


# ---------------- anchorage 2.5.2, tug hire 2.2.5 / 2.6 ----------------

def test_anchorage_and_spm_tug_minimum():
    a = C.calculate_anchorage(20000, 10.1, "foreign", "post_sailing")
    assert a["chargeable_hours"] == 11 and a["amount"] == pytest.approx(11 * 15.0)
    t = C.calculate_tug_hire(1.2, "foreign", "tug_spm")
    assert t["chargeable_hours"] == 2 and t["amount"] == pytest.approx(2 * 1529.18)


# ---------------- storage 3.2.1 ----------------

def test_import_storage_slabs():
    # 1,000 t, 25 days, 7 free working days -> 18 chargeable: 7 x 5.083 + 7 x 8.884 + 4 x 12.696
    r = total(cargo_quantity_mt=1000, storage_days=25)
    assert r["breakdown"]["transit_storage"]["amount"] == pytest.approx(1000 * (7 * 5.083 + 7 * 8.884 + 4 * 12.696))


def test_free_period_extended_by_holidays_but_not_for_coastal():
    r = total(cargo_quantity_mt=1000, storage_days=25, excluded_days_in_free_period=2)
    assert r["breakdown"]["transit_storage"]["chargeable_days"] == 16
    rc = total(cargo_quantity_mt=1000, storage_days=25, trade_type="coastal", cargo_flow="coastal",
               excluded_days_in_free_period=2)
    assert rc["breakdown"]["transit_storage"]["chargeable_days"] == 10  # 15 days inclusive of holidays


def test_export_storage_flat_rate():
    r = total(cargo_type="IOF(L)", cargo_flow="export", storage_days=30)
    assert r["breakdown"]["transit_storage"]["amount"] == pytest.approx(1000 * 9 * 5.083)


# ---------------- totals, currency, exceptions ----------------

def test_total_and_rounding_to_next_rupee():
    r = total(cargo_quantity_mt=10000.3, vessel_grt=30000, berth_hours=35.2, usd_inr_rate=88.0)
    b = r["breakdown"]
    expected = (10000.5 * 43.16) + (30000 * 0.4110 * 88) + (30000 * 0.5269 * 88) + (36 * 84.72 * 88)
    assert r["total_known_cost"] == pytest.approx(expected, abs=0.05)
    assert r["bill_total_rounded"] == int(-(-round(r["total_known_cost"], 2) // 1))
    assert r["is_complete"] and b["berth_hire"]["currency"] == "USD"


def test_missing_grt_and_exchange_rate_are_reported_not_invented():
    r = total(vessel_grt=None)
    assert set(r["missing_grt_components"]) == {"port_dues", "pilotage", "berth_hire"}
    assert not r["is_complete"]
    r2 = total(vessel_grt=30000, berth_hours=10)
    assert "berth_hire" in r2["unconverted_usd_components"]
    assert r2["total_known_cost"] == pytest.approx(1000 * 43.16)


def test_vessel_status_is_separate_from_cargo_status():
    # foreign-going vessel carrying coastal cargo: coastal wharfage, US$ vessel charges
    r = total(trade_type="coastal", cargo_flow="coastal", vessel_trade_type="foreign", vessel_grt=30000,
              berth_hours=10, usd_inr_rate=88)
    assert r["breakdown"]["wharfage"]["rate_per_mt"] == 43.16
    assert r["breakdown"]["port_dues"]["currency"] == "USD"


def test_ppp_berth_and_kiocl_are_not_billed_by_nmpa():
    r = total(cargo_type="STEAM COAL(D)", cargo_quantity_mt=61769, berth="16", vessel_grt=40000, berth_hours=35,
              usd_inr_rate=88)
    assert r["breakdown"]["wharfage"]["status"] == "not_billed_by_nmpa"
    assert r["breakdown"]["berth_hire"]["status"] == "not_billed_by_nmpa"
    assert r["breakdown"]["port_dues"]["status"] == "calculated"
    k = total(cargo_type="IOP(L)", cargo_flow="export", receiver_shipper="KIOCL", berth="8")
    assert k["breakdown"]["wharfage"]["status"] == "not_billed_by_nmpa"
    assert k["exceptions"][0]["code"] == "kiocl_pellets"


# ---------------- matcher on real NMPA cargo codes ----------------

@pytest.mark.parametrize("raw,code", [
    ("IOF(D)", "B.III.j"), ("IOP(L)", "B.III.i"), ("CPO(D)", "A.V.a"), ("CSFO(D)", "A.V.a"),
    ("S.COAL(D)", "B.IV.a"), ("COKING COAL(D)", "B.IV.b"), ("MS/HSD(D)", "A.I.c"), ("LPG (D)", "A.IV.a"),
    ("AMSUL(D)", "B.II.a"), ("ROCK PHOS.(D)", "B.II.b"), ("PHOS.ACID(D)", "A.II.b"), ("CEMENT(D)", "B.V.a"),
    ("BAGGED SUGAR(L)", "C.j"), ("S.COIL/PLATES", "C.g"), ("COALD)", "B.IV.a"), ("M.CRUDE(D)", "A.I.d"),
])
def test_real_cargo_codes(raw, code):
    assert match_commodity(raw)["code"] == code


@pytest.mark.parametrize("raw", ["MRPL SPM OP.", "BUNKER BARGE", "DREDGING", "SEA TRIAL/ BUNKERS/ CREW CHANGE"])
def test_non_cargo_entries(raw):
    assert match_commodity(raw)["method"] == "non_cargo"


# ---------------- API + past data ----------------

@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(cost.router, prefix="/cost")
    return TestClient(app)


def test_api_calculate_and_past_calls(client):
    calls = client.get("/cost/past-calls", params={"limit": 5}).json()
    assert calls["count"] > 1000 and len(calls["calls"]) == 5
    one = client.get(f"/cost/past-calls/{calls['calls'][0]['id']}").json()
    payload = {k: v for k, v in one["calculator_inputs"].items() if v is not None}
    r = client.post("/cost/calculate", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["breakdown"]["wharfage"]["status"] in ("calculated", "not_billed_by_nmpa")


def test_validation_against_past_data(client):
    v = client.get("/cost/validation").json()
    assert v["past_tariff"]["outliers"] == []
    assert v["summary"]["sor_items_consistent"] == v["summary"]["sor_items_checked"]
    assert all(c["result"] == "consistent" for c in v["past_revenue"]["cargo_lines"])
    for g in v["past_calls"]["by_group"]:
        if g["official_tonnes"] > 0:
            assert g["calls_tonnes"] <= g["official_tonnes"] * 1.05  # calls never exceed what NMPA reported
