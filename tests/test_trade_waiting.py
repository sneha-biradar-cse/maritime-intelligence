"""Tests for the Ship Waiting Analyzer (real NMPA daily vessel reports)."""
import json
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import trade_waiting as tw

client = TestClient(app)


def _write(path, date, anchorage):
    (path / f"{date}.json").write_text(json.dumps({"report_date": date, "berthed": [], "anchorage": anchorage,
                                                   "tankers_scheduled": [], "expected": [], "movements": []}))


def test_buckets():
    assert tw._bucket("RECEIVER NOT READY") == tw.BUCKET_CUSTOMER
    assert tw._bucket("SHIPPER NOT REDY") == tw.BUCKET_CUSTOMER
    assert tw._bucket("WANT OF BERTH (B.12)") == tw.BUCKET_BERTH
    assert tw._bucket("") == tw.BUCKET_OTHER
    assert tw._bucket("25000") == tw.BUCKET_OTHER


def test_longest_wait_kept_and_one_event(tmp_path):
    row = {"vessel_name": "MT TEST", "cargo": "CRUDE(D)", "doa": "01.09.2025", "receiver_shipper": "MRPL",
           "waiting_duration": "1.00 Day", "reason_or_note": "RECEIVER NOT READY"}
    _write(tmp_path, "2025-09-02", [row])
    _write(tmp_path, "2025-09-03", [{**row, "waiting_duration": "2.50 Day"}])
    ev = tw.build_waiting_events(tmp_path)
    assert len(ev) == 1 and ev.iloc[0]["wait"] == 2.5


def test_blank_wait_is_not_counted(tmp_path):
    _write(tmp_path, "2025-09-02", [{"vessel_name": "MT X", "cargo": "CRUDE(D)", "doa": "1", "waiting_duration": ""}])
    assert tw.build_waiting_events(tmp_path).empty


def test_real_data_totals_and_endpoint():
    r = client.get("/trade/waiting").json()
    assert r["available"] and r["overall"]["events"] >= 538   # grows as daily reports are added
    assert r["overall"]["events"] == sum(x["events"] for x in r["by_reason"])
    assert abs(sum(x["share_of_waiting_days_pct"] for x in r["by_reason"]) - 100) < 0.5
    assert r["by_reason"][0]["reason"] == tw.BUCKET_CUSTOMER
