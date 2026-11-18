"""
Tests for the Vessel Intelligence data layer and features.

Three layers:
  1. Unit tests of the field parsers and reference rules (pure functions).
  2. A synthetic three-day archive that exercises call stitching end to end
     with known answers (arrival → wait → berthing → sailing).
  3. Integration checks against the real DVP archive in data/ (skipped when
     the archive is absent), including the reconciliation with NMPA's
     official August 2026 Operational Performance report.
"""

import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

from backend.app.services import vi_official_kpis as official
from backend.app.services import vi_port_calls as pc
from backend.app.services import vi_reference as ref

ROOT = Path(__file__).resolve().parents[1]
REAL_ARCHIVE = ROOT / "data" / "daily_vessel_position_parsed"
HAS_ARCHIVE = REAL_ARCHIVE.exists() and len(list(REAL_ARCHIVE.glob("*.json"))) > 50


# ──────────────────────────────────────────────────────────────────────
# 1. Parsers and reference rules
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,account,reason", [
    ("WANT OF BERTH (B.12)", "port", "Want of berth"),
    ("WANT OF BERTH(SPM)", "port", "Want of berth"),
    ("RECEIVER NOT RAEADY", "non_port", "Receiver not ready"),
    ("SHIPPER NOT REDY", "non_port", "Shipper not ready"),
    ("LAY CAN 16-09-26", "non_port", "Laycan not started"),
    ("LEY CAN 18-09-2026", "non_port", "Laycan not started"),
    ("NON-WINDOW VSL", "non_port", "Non-window vessel (berthing policy)"),
    ("DE-SLOPPING NON- CARGO VESSEL", "excluded", "Non-cargo call"),
    ("WAITING FOR HIGH TIDE", "port", "Tide / draft window"),
    ("", "unknown", "No reason stated"),
    ("25000", "unknown", "Unreadable (quantity in reason column)"),
])
def test_classify_reason(text, account, reason):
    r = ref.classify_reason(text)
    assert r["account"] == account
    assert r["reason"] == reason


def test_want_of_berth_target():
    assert ref.want_of_berth_target("WANT OF BERTH (B.12)") == "12"
    assert ref.want_of_berth_target("WANT OF BERTH(13)") == "13"
    assert ref.want_of_berth_target("WANT OF BERTH (B.NO.7)") == "7"
    assert ref.want_of_berth_target("WANT OF BERTH(SPM)") == "SPM"
    assert ref.want_of_berth_target("RECEIVER NOT READY") is None


@pytest.mark.parametrize("cargo,berth,cls", [
    ("CRUDE(D)", "SPM", "liquid_bulk"),
    ("LPG(D)", "13", "liquid_bulk"),
    ("BITUMEN(D)", "9", "liquid_bulk"),
    ("STEAM COAL(D)", "15", "dry_bulk_mechanical"),
    ("COAL(D)", "16", "dry_bulk_mechanical"),
    ("IOF(D)", "8", "dry_bulk_mechanical"),
    ("CEMENT(D)", "5", "dry_bulk_conventional"),
    ("STEEL COIL/PLATES", "2", "break_bulk"),
    ("BOXES", "14", "container"),
    ("MRPL SPM OP.", "4", "non_cargo"),
    ("BUNKER BARGE", "SPM", "non_cargo"),
    ("CRUISE SHIP", "4", "cruise"),
    ("", None, "unknown"),
])
def test_classify_cargo(cargo, berth, cls):
    assert ref.classify_cargo(cargo, berth)["cargo_class"] == cls


def test_cargo_flow():
    assert ref.classify_cargo("IOF(L)", "8")["flow"] == "load"
    assert ref.classify_cargo("CRUDE(D)", "SPM")["flow"] == "discharge"


def test_berth_normalisation():
    assert ref.normalize_berth("14(W)") == "14"
    assert ref.normalize_berth("B.NO.5") == "5"
    assert ref.normalize_berth("SPM") == "SPM"
    assert ref.normalize_berth("----") is None
    assert ref.normalize_berth("99") is None
    assert ref.berth_preferences("13/12") == ["13", "12"]
    assert ref.berth_preferences("9 / 9 / 9") == ["9"]
    assert ref.berth_preferences("ANY BERTH") == []


def test_full_date_year_wrap():
    assert ref.full_date("28/12", date(2026, 1, 3)) == date(2025, 12, 28)
    assert ref.full_date("02/01", date(2025, 12, 30)) == date(2026, 1, 2)
    assert ref.full_date("15/7(19-24- 26/7)", date(2026, 8, 1)) == date(2026, 7, 15)
    assert ref.full_date("ETA", date(2026, 8, 1)) is None


def test_clock_and_wait_parsers():
    assert ref.parse_clock("13:00") == (time(13, 0), "exact")
    assert ref.parse_clock("24:00")[0] == time(23, 59)
    assert ref.parse_clock("PM") == (time(18, 0), "half_day")
    assert ref.parse_clock("E.RT.TIME") == (None, "date")
    assert ref.parse_wait_days("0.87 Day") == 0.87
    assert ref.parse_wait_days("12.46 Days") == 12.46
    assert ref.parse_wait_days("PM") is None


def test_vessel_key_cleanups():
    assert ref.vessel_key("10 BARROW ISLAND") == "BARROW ISLAND"
    assert ref.vessel_key("MSC MANASA F") == "MSC MANASA"
    assert ref.vessel_key("RODOS (13.80) B.10/11") == "RODOS"
    assert ref.vessel_key("RV.SAMUDRA SHAUDHIKAMA (1.9)") == "RV SAMUDRA SHAUDHIKAMA"
    assert ref.is_header_echo("NIL")


def test_qty_and_boxes():
    assert ref.parse_qty("96,986") == 96986
    assert ref.parse_qty("----") is None
    assert ref.parse_boxes("600(I)+500(E )") == 1100


# ──────────────────────────────────────────────────────────────────────
# Official KPI parser
# ──────────────────────────────────────────────────────────────────────

OFFICIAL_SNIPPET = """TRAFFIC & PERFORMANCE FOR THE MONTH OF AUGUST 2026
1) No. of vessels handled
a) Dry Bulk (Total) 27 23 126 118
c) Liquid Bulk 58 80 334 352
e) Overall 107* 125** 570*** 595****
2) Avg. Pre-berthing detention (In days)
Port Account (In days)
b) Break Bulk - - - -
e) Overall 0.08 0.27 0.21 0.15
Other than Port A/c. (In days)
e) Overall 0.80 0.53 0.84 0.52
Total (In days)
e) Overall 0.88 0.80 1.05 0.67
7) Total Traffic handled (In Tonnes)
e) Overall 38,85,913 39,58,458 1,96,56,657 1,81,48,993
"""


def test_official_parse_text():
    rm, rows = official.parse_text(OFFICIAL_SNIPPET, "snippet")
    assert rm == date(2026, 8, 1)
    get = {(r["month"], r["metric"], r["component"], r["cargo_class"], r["period"]): r["value"] for r in rows}
    assert get[("2026-08", "vessels_handled", "total", "overall", "month")] == 107
    assert get[("2025-08", "vessels_handled", "total", "overall", "month")] == 125
    assert get[("2026-08", "pre_berthing_days", "port_account", "overall", "month")] == 0.08
    assert get[("2026-08", "pre_berthing_days", "other_than_port_account", "overall", "ytd")] == 0.84
    assert get[("2026-08", "traffic_t", "total", "overall", "month")] == 3885913
    assert get[("2026-08", "pre_berthing_days", "port_account", "break_bulk", "month")] is None


@pytest.mark.skipif(not (ROOT / "nmpa_public_data" / "operational performance August 2026.pdf").exists(), reason="PDF not present")
def test_official_parse_real_pdf():
    rm, rows, status = official.parse_pdf(ROOT / "nmpa_public_data" / "operational performance August 2026.pdf")
    assert status == "ok" and rm == date(2026, 8, 1)
    assert len(rows) == 59 * 4


# ──────────────────────────────────────────────────────────────────────
# 2. Synthetic archive — call stitching with known answers
# ──────────────────────────────────────────────────────────────────────

def _empty_berth(n):
    return {"berth_no": str(n), "vessel_name": "----"}


@pytest.fixture
def synthetic_archive(tmp_path, monkeypatch):
    d = tmp_path / "parsed"
    d.mkdir()
    reports = {
        # day 1: expected, ETA 02/03 06:00
        "2026-03-01": {"expected": [{"sl_no": "1", "vessel_name": "TEST STAR", "run": "F", "draft": "11.2", "loa": "229",
                                     "eta_date": "02/03", "eta_time": "06:00", "cargo": "CRUDE(D)", "agent": "AG", "receiver_shipper": "MRPL",
                                     "qty": "90000", "berth_prefer": "10/11"}],
                       "movements": []},
        # day 2: at anchorage since 02/03 08:00, want of berth
        "2026-03-02": {"anchorage": [{"sl_no": "1", "vessel_name": "TEST STAR (11.20) B.10/11", "run": "F", "loa": "229", "doa": "02/03",
                                      "clock_time": "08:00", "waiting_duration": "0.08 Day", "cargo": "CRUDE(D)", "agent": "AG",
                                      "receiver_shipper": "MRPL", "qty": "90000", "reason_or_note": "WANT OF BERTH (B.10)"}],
                       # programme: berths tomorrow 20:00 (later revised)
                       "movements": [{"date": "2026-03-03", "section": "movement", "event_type": "berths", "vessel_name": "TEST STAR",
                                      "berth_no": "10", "time": "20:00"}]},
        # day 3: still waiting; revised programme berths 03/03 22:00
        "2026-03-03": {"anchorage": [{"sl_no": "1", "vessel_name": "TEST STAR", "run": "F", "loa": "229", "doa": "02/03",
                                      "clock_time": "08:00", "waiting_duration": "1.08 Days", "cargo": "CRUDE(D)", "agent": "AG",
                                      "receiver_shipper": "MRPL", "qty": "90000", "reason_or_note": "WANT OF BERTH (B.10)"}],
                       "movements": [{"date": "2026-03-03", "section": "movement", "event_type": "berths", "vessel_name": "TEST STAR",
                                      "berth_no": "10", "time": "22:00"}]},
        # day 4: alongside B10 with balance; sailing programmed 05/03 04:00
        "2026-03-04": {"berthed": [_empty_berth(9),
                                   {"berth_no": "10", "vessel_name": "TEST STAR", "run": "F", "loa": "229", "arrival_date": "02/03",
                                    "berthing_date": "03/03", "cargo": "CRUDE(D)", "agent": "AG", "receiver_shipper": "MRPL",
                                    "qty_day": "60000", "qty_total": "60000", "qty_balance": "30000", "etd": "05/03"}],
                       "movements": [{"date": "2026-03-05", "section": "movement", "event_type": "sails", "vessel_name": "TEST STAR",
                                      "berth_no": None, "time": "04:00"}]},
        # day 5: another vessel, so the archive extends past the sailing
        "2026-03-05": {"berthed": [{"berth_no": "12", "vessel_name": "OTHER SHIP", "run": "C", "arrival_date": "05/03",
                                    "berthing_date": "05/03", "cargo": "LPG(D)", "qty_total": "1000", "qty_balance": "9000"}],
                       "movements": []},
    }
    for rd, body in reports.items():
        day = {"report_date": rd, "berthed": [], "anchorage": [], "tankers_scheduled": [], "expected": [], "movements": [], "unparsed_rows": []}
        day.update(body)
        dd = date.fromisoformat(rd)
        (d / f"{dd.strftime('%d-%m-%Y')}.json").write_text(json.dumps(day))
    monkeypatch.setattr(pc, "ARCHIVE_DIR", d)
    pc.clear_caches()
    yield d
    monkeypatch.undo()
    pc.clear_caches()


def test_synthetic_call_stitching(synthetic_archive):
    calls = [c for c in pc.port_calls() if c["vessel"] == "TEST STAR"]
    assert len(calls) == 1, [c["call_id"] for c in calls]
    c = calls[0]
    assert c["status"] == "sailed"
    assert c["cargo_class"] == "liquid_bulk"
    assert c["declared_eta"] == datetime(2026, 3, 2, 6, 0)
    assert c["arrival_dt"] == datetime(2026, 3, 2, 8, 0)
    assert c["eta_error_h"] == 2.0
    # berthing = LAST programme revision issued before the event (22:00, not 20:00)
    assert c["first_berth_dt"] == datetime(2026, 3, 3, 22, 0)
    assert c["wait_h"] == 38.0
    assert c["wait_port_h"] == 38.0 and c["wait_non_port_h"] == 0.0
    assert c["depart_dt"] == datetime(2026, 3, 5, 4, 0)
    assert c["at_berth_h"] == 30.0
    assert c["qty_t"] == 90000
    assert c["primary_berth"] == "10"
    assert c["berth_prefs"] == ["10", "11"]


def test_synthetic_report_time_default(synthetic_archive):
    # too few anchorage rows to estimate → documented default
    assert pc.report_reference_time() == time(10, 0)


# ──────────────────────────────────────────────────────────────────────
# 3. Real archive
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_ARCHIVE, reason="real DVP archive not present")
class TestRealArchive:
    def setup_method(self):
        pc.clear_caches()

    def test_report_reference_time_is_morning(self):
        t = pc.report_reference_time()
        assert time(8, 0) <= t <= time(12, 0)

    def test_board_shapes(self):
        from backend.app.services import vi_features as vi
        b = vi.port_call_board()
        assert {"alongside", "waiting", "expected", "programme", "alerts", "summary", "lineage"} <= set(b)
        assert b["lineage"]["status"].startswith("REAL")
        for a in b["alongside"]:
            assert a["berth"] is None or a["berth"] in ref.berth_order()

    def test_eta_linking_quality(self):
        from backend.app.services import vi_features as vi
        e = vi.eta_accuracy()
        assert e["expected_lists_matched_to_an_arrival_pct"] > 75
        assert e["declared_eta"]["within_24h_pct"] > 70

    def test_departure_forecast_not_worse_than_nmpa_etd(self):
        from backend.app.services import vi_features as vi
        b = vi.completion_backtest()
        assert b["all_points"]["chosen"]["mae_h"] <= b["all_points"]["etd_noon"]["mae_h"] + 1.0

    @pytest.mark.skipif(not (ROOT / "nmpa_public_data" / "operational performance August 2026.pdf").exists(), reason="official PDF absent")
    def test_reconciles_with_nmpa_official_august_2026(self):
        from backend.app.services import vi_features as vi
        perf = vi.performance()
        aug = next(r for r in perf["reconciliation"] if r["month"] == "2026-08")
        rows = {(r["cargo_class"], r["metric_key"]): r for r in aug["rows"]}
        tot = rows[("overall", "pre_berthing_days|total")]
        assert abs(tot["dvp_derived"] - tot["official"]) < 0.25
        port = rows[("overall", "pre_berthing_days|port_account")]
        assert abs(port["dvp_derived"] - port["official"]) < 0.1
        liq = rows[("liquid_bulk", "vessels_handled|total")]
        assert 0.85 <= liq["dvp_derived"] / liq["official"] <= 1.15

    def test_api_endpoints(self):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        c = TestClient(app)
        for path in ["/vessels/intel/board", "/vessels/intel/arrivals", "/vessels/intel/berth-plan",
                     "/vessels/intel/performance", "/vessels/intel/waiting", "/vessels/intel/data-quality",
                     "/vessels/intel/wait-model", "/vessels/intel/berthing-fit", "/vessels/intel/report-dates"]:
            assert c.get(path).status_code == 200, path
        assert c.get("/vessels/intel/board?as_of=2000-01-01").status_code == 404
        assert c.get("/vessels/intel/calls/NOPE").status_code == 404


# ──────────────────────────────────────────────────────────────────────
# Ship identity (IMO lookup)
# ──────────────────────────────────────────────────────────────────────

def test_imo_check_digit():
    from backend.app.services import vi_reference as ref
    for good in ("9731195", "9814181", "9347152", "9571129", "9783174"):
        assert ref.imo_check_digit_ok(good)
    for bad in ("9731194", "973119", "ABCDEFG", "", None):
        assert not ref.imo_check_digit_ok(bad)


def test_imo_lookup_rows_all_valid():
    from backend.app.services import vi_reference as ref
    import csv
    with ref.IMO_LOOKUP_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "vessel_imo_lookup.csv is empty"
    assert all(ref.imo_check_digit_ok(r["imo_number"]) for r in rows)
    assert len({r["imo_number"] for r in rows}) == len(rows), "duplicate IMO in lookup"


def test_same_name_ships_separated_by_loa():
    from backend.app.services import vi_reference as ref
    assert ref.vessel_identity("BEAGLE", 229)["imo"] == "9731195"
    assert ref.vessel_identity("BEAGLE", 183)["imo"] == "9814181"
    assert ref.vessel_identity("OCEAN PIONEER", 144.09)["imo"] == "9347152"
    assert ref.vessel_identity("OCEAN PIONEER", 31)["imo"] == "9571129"
    # name alone is not enough when the name is shared
    amb = ref.vessel_identity("BEAGLE", None)
    assert amb["imo"] is None and amb["imo_match"] == "ambiguous"
    # same name, size matches neither -> no IMO assigned
    mis = ref.vessel_identity("BEAGLE", 120)
    assert mis["imo"] is None and mis["imo_match"] == "loa_mismatch"
    assert ref.vessel_identity("NO SUCH SHIP", 200)["imo_match"] == "not_looked_up"
