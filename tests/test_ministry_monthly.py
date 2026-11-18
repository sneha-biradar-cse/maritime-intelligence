"""All-port monthly file from the Ministry reports, and the non-major ports table."""
import subprocess
import sys

import pandas as pd
import pytest

from backend.app.services import trade_benchmark as tb

ROOT = tb.ROOT


def test_parser_runs_and_checks_every_report():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "parse_ministry_major_ports.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr        # the script asserts overseas + coastal = total and ports = printed total


def test_months_are_continuous_and_complete():
    d = pd.read_csv(ROOT / "data" / "major_ports_monthly.csv")
    months = sorted(d["month"].unique())
    # Continuous from November 2024 (earlier months come only from the 'last year' columns of the reports held)
    expected = [m.strftime("%Y-%m") for m in pd.date_range("2024-11-01", months[-1] + "-01", freq="MS")]
    assert set(expected) <= set(months)
    assert (d.groupby("month")["port"].nunique() == 13).all()        # 12 ports + all-port total


def test_ports_add_up_to_all_port_total_every_month():
    d = pd.read_csv(ROOT / "data" / "major_ports_monthly.csv")
    p = d.pivot_table(index="month", columns="port", values="total_t")
    ports = [c for c in p.columns if c != "All major ports"]
    assert ((p[ports].sum(axis=1) - p["All major ports"]).abs() <= 12).all()


def test_derived_months_equal_nmpa_own_reports():
    """Months derived from April-to-date columns match NMPA's Traffic & Performance totals to the tonne."""
    d = pd.read_csv(ROOT / "data" / "major_ports_monthly.csv")
    nm = d[d["port"] == "New Mangalore"].set_index("month")
    perf = pd.read_csv(ROOT / "data" / "nmpa_performance_monthly.csv")
    t = perf[(perf.metric == "traffic_t") & (perf.category == "overall") & (perf.period == "month") & (perf.year == "current")]
    t = t.set_index("report_month")["value"]
    derived = [m for m in nm.index if str(nm.loc[m, "basis"]).startswith("derived") and m in t.index]
    assert derived, "expected at least one derived month to check"
    for m in derived:
        assert nm.loc[m, "total_t"] == t[m], m


def test_non_major_table_adds_up_to_printed_totals():
    d = pd.read_csv(ROOT / "data" / "non_major_ports_2026-07.csv")
    assert ((d.overseas_t + d.coastal_t) == d.total_t).all()
    assert d.groupby("period").total_t.sum().to_dict() == {
        "2025-07": 60_553_203, "2026-07": 62_647_129, "2025-26 Apr-Jul": 246_423_076, "2026-27 Apr-Jul": 247_334_767}


def test_benchmark_trend_in_api():
    b = tb.get_benchmark()
    assert b["trend"]["months"] and b["regional"]["neighbours"]
