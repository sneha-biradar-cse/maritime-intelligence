"""Tests for the cargo-level foreign/coastal ESTIMATE built from NMPA daily vessel reports."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_split as ts

client = TestClient(app)


def _day(path, date, rows):
    base = {"run": "", "cargo": "", "receiver_shipper": "", "qty_total": ""}
    (path / f"{date}.json").write_text(json.dumps({
        "report_date": date, "berthed": [{**base, **r} for r in rows],
        "anchorage": [], "tankers_scheduled": [], "expected": [], "movements": [],
    }))


# ── cargo code rules ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("code,family,direction", [
    ("CRUDE(D)", "Crude oil", "inbound"),
    ("IOF(L)", "Iron ore", "outbound"),
    ("IOF(D)", "Iron ore", "inbound"),
    ("LPG (D)", "LPG", "inbound"),
    ("MS(L)", "Petroleum products (fuels)", "outbound"),
    ("BOXES", "Containers", "both"),
    ("COAL TAR PITCH (L)", "Coal tar pitch", "outbound"),
    ("S.COAL(D)", "Coal", "inbound"),
    ("SOMETHING NEW", "Other cargo", "unknown"),
])
def test_classify_cargo(code, family, direction):
    assert ts.classify_cargo(code) == (family, direction)


# ── voyages ───────────────────────────────────────────────────────────────────
def test_same_ship_on_consecutive_days_is_one_voyage_and_a_long_gap_makes_two(tmp_path):
    ship = {"vessel_name": "ALPHA (9.1)", "run": "F", "cargo": "CRUDE(D)", "receiver_shipper": "MRPL", "qty_total": "40000"}
    _day(tmp_path, "2025-09-01", [ship])
    _day(tmp_path, "2025-09-02", [ship])
    _day(tmp_path, "2025-11-15", [ship])           # 74 days later = a new call
    v = ts.build_voyages(tmp_path)
    assert len(v) == 2
    assert v["qty"].max() == 40000


def test_non_cargo_rows_and_placeholders_are_dropped(tmp_path):
    _day(tmp_path, "2025-09-01", [
        {"vessel_name": "TUG ONE", "run": "C", "cargo": "SPM OP."},
        {"vessel_name": "BUNKERER", "run": "C", "cargo": "BUNKER BARGE"},
        {"vessel_name": "----", "run": "", "cargo": ""},
        {"vessel_name": "REAL SHIP", "run": "C", "cargo": "CEMENT(D)", "receiver_shipper": "AMBUJA"},
    ])
    v = ts.build_voyages(tmp_path)
    assert list(v["vessel"]) == ["REAL SHIP"]


def test_blank_or_mixed_run_flag_is_left_out_of_the_split(tmp_path, monkeypatch):
    _day(tmp_path, "2025-09-01", [
        {"vessel_name": f"S{i}", "run": r, "cargo": "LPG(D)"} for i, r in enumerate(["F", "F", "C", "F/C", ""])
    ])
    monkeypatch.setattr(ts, "DAILY_DIR", tmp_path)
    monkeypatch.setattr(ts, "_validation", lambda v: {"months": [], "verdict": "n/a"})
    out = ts.get_cargo_split()
    fam = out["families"][0]
    assert (fam["foreign_ships"], fam["coastal_ships"]) == (2, 1)
    assert out["voyages_total"] == 5 and out["voyages_with_run_flag"] == 3 and out["voyages_mixed_or_blank_flag"] == 2


def test_joint_receivers_are_split():
    import pandas as pd
    top = ts._top_customers(pd.Series(["HP/IOC/BPC", "IOCL", "VARIOUS", "HP"]))
    assert {t["customer"]: t["ships"] for t in top}["HP"] == 2
    assert all(t["customer"] != "VARIOUS" for t in top)


# ── real data ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def split():
    return ts.get_cargo_split()


def test_counts_add_up_and_shares_are_valid(split):
    assert sum(f["ships"] for f in split["families"]) == split["voyages_with_run_flag"]
    for f in split["families"]:
        assert f["foreign_ships"] + f["coastal_ships"] == f["ships"]
        assert 0 <= f["coastal_share_by_ships_pct"] <= 100
        if f["coastal_share_by_quantity_pct"] is not None:
            assert 0 <= f["coastal_share_by_quantity_pct"] <= 100


def test_validation_months_exist_in_the_ministry_file_and_miss_is_independent(split):
    official = {r["month"][:7]: r["coastal_share_pct"] for r in ti.get_overseas_coastal()["series"]}
    v = split["validation_against_ministry"]
    assert v["months"]
    for m in v["months"]:
        assert m["month"] in official
        assert m["official_coastal_share_pct"] == pytest.approx(official[m["month"]], abs=0.05)
    misses = [abs(m["estimate_by_ships_pct"] - m["official_coastal_share_pct"]) for m in v["months"]]
    assert v["avg_miss_points_by_ships"] == pytest.approx(sum(misses) / len(misses), abs=0.1)


def test_estimate_is_labelled_and_limits_are_stated(split):
    assert "ESTIMATE" in split["label"]
    assert split["limits"] and split["how_it_works"]


def test_endpoint_ok_and_no_nan():
    r = client.get("/trade/cargo-split")
    assert r.status_code == 200
    json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))
