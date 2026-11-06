"""Next 7 days: date/berth reading, berth outlook rules, and the endpoint on the real latest report."""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import trade_lookahead as tl

client = TestClient(app)


@pytest.mark.parametrize("text,ref,expected", [
    ("27/10", "2026-10-26", "2026-10-27"),
    ("02/01", "2026-12-30", "2027-01-02"),      # across the year end
    ("28/12", "2027-01-02", "2026-12-28"),
    ("19/05/24", "2026-09-16", "2024-05-19"),
    ("COMPLETED", "2026-10-26", None),
])
def test_day(text, ref, expected):
    got = tl._day(text, pd.Timestamp(ref))
    assert (got.strftime("%Y-%m-%d") if got is not None else None) == expected


@pytest.mark.parametrize("text,expected", [
    ("12 / 13", ["12", "13"]), ("10/11/SPM", ["10", "11", "SPM"]), ("14W", ["14W"]), ("13/12/9", ["13", "12", "9"]),
    ("12(P)/9", ["12", "9"]),
])
def test_berths(text, expected):
    assert tl._berths(text) == expected


def _write(tmp_path, date, berthed=(), expected=(), anchorage=()):
    (tmp_path / f"{date}.json").write_text(json.dumps({
        "report_date": pd.Timestamp(date).strftime("%Y-%m-%d"), "berthed": list(berthed), "anchorage": list(anchorage),
        "tankers_scheduled": [], "expected": list(expected), "movements": []}))


def test_berth_outlook_queues_two_ships_for_one_berth(tmp_path):
    tl.get_lookahead.cache_clear()
    _write(tmp_path, "10-03-2026",
           berthed=[{"berth_no": "16", "vessel_name": "ON BERTH", "cargo": "COAL(D)", "etd": "11/03", "receiver_shipper": "APL",
                     "run": "F", "qty_total": "20000", "qty_balance": "30000", "agent": ""}],
           expected=[{"vessel_name": "FIRST", "eta_date": "10/03", "eta_time": "12:00", "cargo": "COAL(D)", "qty": "50000",
                      "receiver_shipper": "APL", "berth_prefer": "16", "run": "F"},
                     {"vessel_name": "SECOND", "eta_date": "10/03", "eta_time": "18:00", "cargo": "IOF(D)", "qty": "40000",
                      "receiver_shipper": "KIOCL", "berth_prefer": "8", "run": "C"}])
    x = tl.get_lookahead(tmp_path)
    due = {s["vessel"]: s for s in x["due"]}
    assert due["FIRST"]["likely_wait_days"] > 0.5 and "ON BERTH" in due["FIRST"]["berth_outlook"]
    assert due["SECOND"]["likely_wait_days"] == 0
    assert x["totals"]["ships_due"] == 2 and x["totals"]["tonnes_due"] == 90000
    tl.get_lookahead.cache_clear()


def test_endpoint_on_real_latest_report():
    r = client.get("/trade/next-7-days")
    assert r.status_code == 200
    body = json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))
    assert body["available"] and body["report_date"]
    for s in body["due"]:
        assert s["berth_outlook"]
