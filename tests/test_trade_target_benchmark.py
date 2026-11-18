"""Tests for the target tracker, the major-port benchmark and the derived June 2026."""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import trade_benchmark as tb
from backend.app.services import trade_intelligence as ti
from backend.app.services import trade_target as tt

client = TestClient(app)


PRINTED_ALL_PORT_TOTALS = {   # "Total" row of Table-1 in each Ministry report
    "major_ports_ministry_2026-07.csv": {"2025-07": 72_875_498, "2026-07": 79_307_204,
                                         "2025-26 Apr-Jul": 292_912_328, "2026-27 Apr-Jul": 312_948_085},
    "major_ports_ministry_2026-09.csv": {"2025-09": 73_134_587, "2026-09": 82_387_997,
                                         "2025-26 Apr-Sep": 437_433_875, "2026-27 Apr-Sep": 472_745_575},
}


@pytest.mark.parametrize("name,printed", PRINTED_ALL_PORT_TOTALS.items())
def test_ministry_table_is_transcribed_exactly(name, printed):
    d = pd.read_csv(tb.ROOT / "data" / name)
    assert ((d["overseas_t"] + d["coastal_t"]) == d["total_t"]).all()
    assert d.groupby("period")["total_t"].sum().to_dict() == printed
    assert len(d["port"].unique()) == 12


def test_ministry_august_equals_nmpa_traffic_and_performance_report():
    """August 2026 is derived (Apr-Sep minus Apr-Jul minus Sep); NMPA's own August report prints 38,85,913 and 39,58,458."""
    oc = pd.read_csv(tb.ROOT / "data" / "port_overseas_coastal_monthly.csv").set_index("month")
    assert (oc.loc["2026-08", "total_t"], oc.loc["2026-08", "prev_year_total_t"]) == (3_885_913, 3_958_458)


def test_ministry_new_mangalore_rows_match_the_overseas_coastal_file():
    oc = pd.read_csv(tb.ROOT / "data" / "port_overseas_coastal_monthly.csv").set_index("month")
    for name, month in (("major_ports_ministry_2026-07.csv", "2026-07"), ("major_ports_ministry_2026-09.csv", "2026-09")):
        d = pd.read_csv(tb.ROOT / "data" / name)
        nm = d[(d["port"] == "New Mangalore") & (d["period"] == month)].iloc[0]
        assert (nm["overseas_t"], nm["coastal_t"], nm["total_t"]) == tuple(oc.loc[month, ["overseas_t", "coastal_t", "total_t"]])


def test_benchmark_ranks_and_headline():
    b = tb.get_benchmark()
    ranks = sorted(p["rank_by_tonnes"] for p in b["ports"])
    assert ranks == list(range(1, 13))
    assert b["home"]["port"] == "New Mangalore" and str(b["home"]["rank_by_growth"]) in b["headline"]


def test_june_2026_statement_equals_the_value_we_had_derived():
    """June 2026 was first derived from year-to-date figures (3,530,792 t); NMPA's June statement, added later, says the same."""
    f = {r["month"]: r for r in ti.get_monthly_flows(12)["series"]}
    june = f["2026-06"]
    assert june["status"] == "reported" and june["total_tonnes"] == 3_530_792
    ministry = pd.read_csv(tb.ROOT / "data" / "port_overseas_coastal_monthly.csv").set_index("month").loc["2026-06", "total_t"]
    assert 0 <= ministry - june["total_tonnes"] <= 120_000          # Ministry = NMPA statement + shore handling


def test_target_arithmetic():
    t = tt.get_target_tracker()
    assert t["available"]
    assert len(t["months_done"]) + len(t["months_left"]) == 12
    needed = (t["target_tonnes"] - t["done_tonnes"]) / len(t["months_left"])
    assert t["needed_per_month_tonnes"] == pytest.approx(needed, abs=2)
    assert t["projection_if_same_as_last_year_tonnes"] == pytest.approx(
        t["done_tonnes"] + t["remaining_months_last_year_tonnes"], abs=2)


def test_target_done_equals_ministry_april_to_september():
    t = tt.get_target_tracker()
    if t["months_done"][-1] == "2026-09":
        assert t["done_tonnes"] == 24_180_198      # Ministry Table-1, New Mangalore, April-September 2026-27


@pytest.mark.parametrize("url", ["/trade/target", "/trade/benchmark"])
def test_endpoints_ok_no_nan(url):
    r = client.get(url)
    assert r.status_code == 200
    json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))


def test_ministry_file_matches_the_original_pdfs():
    """Runs scripts/verify_ministry_overseas_coastal.py against the Ministry PDFs kept in nmpa_public_data/."""
    import shutil
    import subprocess
    import sys
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext (poppler) not installed")
    r = subprocess.run([sys.executable, str(tb.ROOT / "scripts" / "verify_ministry_overseas_coastal.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "RESULT: OK" in r.stdout
