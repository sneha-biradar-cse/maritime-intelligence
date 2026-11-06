"""Tests for the Trade Intelligence module (real NMPA data, no network needed)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import forecasting
from backend.app.services import trade_intelligence as ti

client = TestClient(app)
RAW_CSV = Path(__file__).resolve().parents[1] / "data" / "port_cargo_monthly.csv"


def _series(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_canon_merges_spelling_variants():
    assert ti._canon("OTH.LIQ") == ti._canon("OTH. LIQ") == ti._canon("oth liq")


def test_window_compare_matches_by_calendar_date_not_position():
    s = _series([10] * 24)
    s = s.drop(pd.Timestamp("2024-06-01"))  # gap in the earlier year
    cur, prev, yoy, used = ti._window_compare(s, pd.Timestamp("2025-12-01"), 12)
    assert used == 11            # June skipped on both sides
    assert cur == prev == 110
    assert yoy == 0


def test_momentum_signals():
    rising = ti._momentum(_series(np.linspace(100, 300, 24)))
    falling = ti._momentum(_series(np.linspace(300, 100, 24)))
    steady = ti._momentum(_series([100.0] * 24))
    irregular = ti._momentum(_series([0] * 14 + [500, 0, 0, 0, 500, 0, 0, 0, 0, 0]))
    assert rising["signal"] == "Rising"
    assert falling["signal"] == "Falling"
    assert steady["signal"] == "Steady"
    assert irregular["signal"] == "Irregular"


def test_build_flow_table_rebuilds_prior_year_without_overriding_real_rows():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-01", "2023-01-01"]),
        "section": ["UNLOADED", "UNLOADED", "UNLOADED"],
        "commodity": ["COAL", "IRON ORE", "COAL"],
        "traffic_tonnes_current": [100.0, 50.0, 80.0],
        "traffic_tonnes_prev_year": [80.0, 40.0, 70.0],
    })
    flow = ti.build_flow_table(df)
    coal23 = flow[(flow.key == "COAL") & (flow.date == "2023-01-01")].iloc[0]
    assert coal23.tonnes == 80.0 and coal23.source == "report"  # real row wins
    ore23 = flow[(flow.key == "IRONORE") & (flow.date == "2023-01-01")]
    assert ore23.iloc[0].tonnes == 40.0 and ore23.iloc[0].source == "prior_year_column"


# ── real data ────────────────────────────────────────────────────────────────
def test_latest_month_totals_match_raw_csv():
    """Independent check: read the CSV directly and sum the latest month ourselves."""
    s = ti.get_trade_summary()
    raw = pd.read_csv(RAW_CSV)
    raw["date"] = pd.to_datetime(raw["month"] + " " + raw["year"].astype(str), format="%B %Y")
    d = pd.Timestamp(s["as_of"] + "-01")
    for section, key in (("UNLOADED", "inbound"), ("LOADED", "outbound")):
        rows = raw[(raw.section == section) & (raw.date == d)].copy()
        rows["k"] = rows.commodity.str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
        rows = rows.drop_duplicates("k", keep="last")
        assert s["latest_month"][f"{key}_tonnes"] == pytest.approx(rows.traffic_tonnes_current.sum(), rel=1e-6)


def test_yoy_matches_independent_calculation():
    s = ti.get_trade_summary()
    flows = ti.get_monthly_flows(120)["series"]
    by = {r["month"]: r for r in flows}
    y, m = map(int, s["as_of"].split("-"))
    cur, prev = by[s["as_of"]]["inbound_tonnes"], by[f"{y-1}-{m:02d}"]["inbound_tonnes"]
    assert s["inbound"]["yoy_pct_latest_month"] == pytest.approx((cur / prev - 1) * 100, abs=0.1)


def test_missing_months_are_missing_not_zero():
    dq = ti.get_trade_summary()["data_quality"]
    series = {r["month"]: r for r in ti.get_monthly_flows(120)["series"]}
    for m in dq["missing_months"]:
        assert series[m]["inbound_tonnes"] is None
        assert series[m]["status"] == "missing"


def test_forecast_trade_uses_service_output():
    out = forecasting.forecast_trade()
    snap = ti.get_legacy_trade_snapshot()
    assert out["engine"] == "trade_intelligence_v3_real"
    for k, v in snap.items():
        assert out[k] == v


# ── API ──────────────────────────────────────────────────────────────────────
def _no_nan(text: str):
    json.loads(text, parse_constant=lambda c: pytest.fail(f"non-finite JSON value {c}"))


@pytest.mark.parametrize("url", ["/trade/summary", "/trade/flows?months=60", "/trade/commodities",
                                  "/trade/commodities?direction=inbound", "/trade/alerts", "/trade/overseas-coastal", "/trade/commodity?name=IRON%20ORE"])
def test_real_endpoints_ok_and_valid_json(url):
    r = client.get(url)
    assert r.status_code == 200
    _no_nan(r.text)


def test_unknown_commodity_404():
    assert client.get("/trade/commodity?name=NOPE").status_code == 404


@pytest.mark.parametrize("url", ["/trade/flows?months=1", "/trade/flows?months=999", "/trade/commodities?direction=x"])
def test_bad_params_422(url):
    assert client.get(url).status_code == 422


@pytest.mark.parametrize("url", ["/trade/lanes", "/trade/commodity-prices", "/trade/opportunities"])
def test_simulated_endpoints_are_gone(url):
    # The trade module is real-data only; the old simulated panels were removed.
    r = client.get(url)
    assert r.status_code == 404 or "is_demo" not in r.text


def test_alerts_follow_their_rules():
    body = client.get("/trade/alerts").json()
    rows = {(r["commodity"], r["direction"]): r for r in ti.get_commodity_flows()["commodities"]}
    for a in body["alerts"]:
        r = rows[(a["commodity"], a["direction"])]
        assert r["share_of_direction_pct"] >= ti.ALERT_MIN_SHARE_PCT
        if a["severity"] == "warning":
            assert r["yoy_pct_last_3_months"] <= -ti.ALERT_YOY_3M_PCT and r["signal"] == "Falling"
        elif a["severity"] == "positive":
            assert r["yoy_pct_last_3_months"] >= ti.ALERT_YOY_3M_PCT and r["signal"] == "Rising"
        else:
            assert r["signal"] == "Irregular"
    sev = [a["severity"] for a in body["alerts"]]
    assert sev == sorted(sev, key={"warning": 0, "positive": 1, "info": 2}.get)


# ── checked against the official NMPA statement for August 2026 ──────────────────
# Figures below are copied from "Commodity wise traffic statement August 2026.pdf"
# (TOTAL (A) = unloaded, TOTAL (B) = loaded), not computed from our CSV.
def test_august_2026_matches_official_nmpa_statement():
    f = {r["month"]: r for r in ti.get_monthly_flows(24)["series"]}
    assert f["2026-08"]["inbound_tonnes"] == 3_055_786      # TOTAL (A)
    assert f["2026-08"]["outbound_tonnes"] == 783_650       # TOTAL (B)
    assert f["2025-08"]["inbound_tonnes"] == 2_815_470
    assert f["2025-08"]["outbound_tonnes"] == 1_069_635


def test_verification_script_passes_against_official_pdf():
    import shutil, subprocess, sys
    pdf = RAW_CSV.parents[1] / "nmpa_public_data" / "Commodity wise traffic statement August 2026.pdf"
    if not pdf.exists() or not shutil.which("pdftotext"):
        pytest.skip("official PDF or pdftotext not available")
    script = RAW_CSV.parents[1] / "scripts" / "verify_trade_against_nmpa.py"
    r = subprocess.run([sys.executable, str(script), str(pdf)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULT: OK" in r.stdout


# ── overseas vs coastal (Ministry monthly report) ────────────────────────────
def test_overseas_plus_coastal_equals_total_every_month():
    raw = pd.read_csv(RAW_CSV.parent / "port_overseas_coastal_monthly.csv")
    assert (raw.overseas_t + raw.coastal_t == raw.total_t).all()
    assert (raw.prev_year_overseas_t + raw.prev_year_coastal_t == raw.prev_year_total_t).all()


def test_ministry_totals_agree_with_nmpa_statements():
    """Ministry total = NMPA loaded + unloaded + shore handling, so it must be a little above ours."""
    oc = pd.read_csv(RAW_CSV.parent / "port_overseas_coastal_monthly.csv").set_index("month")
    flows = {r["month"]: r for r in ti.get_monthly_flows(120)["series"]}
    checked = 0
    for month, row in oc.iterrows():
        f = flows.get(month)
        if not f or f["inbound_tonnes"] is None or f["outbound_tonnes"] is None:
            continue                                    # e.g. June 2026 is missing from the NMPA CSV
        shore = row.total_t - (f["inbound_tonnes"] + f["outbound_tonnes"])
        assert 0 <= shore <= 120_000, (month, shore)    # shore handling is 30-110 thousand tonnes a month
        checked += 1
    assert checked >= 6


def test_known_official_overseas_coastal_figures():
    body = client.get("/trade/overseas-coastal").json()
    jul = next(r for r in body["series"] if r["month"] == "2026-07")
    assert (jul["overseas_tonnes"], jul["coastal_tonnes"], jul["total_tonnes"]) == (2_749_638, 1_247_661, 3_997_299)
    ytd = body["financial_year_to_date"]
    assert ytd["total_tonnes"] == 24_180_198          # ministry's printed April-September 2026-27 total
    assert ytd["total_yoy_pct"] == pytest.approx(6.94, abs=0.05)   # ministry's printed % change (we round to 1 decimal)


# ── months checked against NMPA's own published statements (text transcribed from the PDFs) ──
@pytest.mark.parametrize("month_name,file", [("March", "March_2026"), ("April", "April_2026"), ("May", "May_2026")])
def test_csv_matches_official_statement_transcripts(month_name, file):
    import re
    raw = pd.read_csv(RAW_CSV)
    raw["k"] = raw.commodity.map(ti._canon)
    num = lambda x: 0.0 if x == "-" else float(x.replace(",", ""))
    checked = 0
    for line in (RAW_CSV.parent / "nmpa_official_transcripts" / f"{file}.txt").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        section = {"U": "UNLOADED", "L": "LOADED"}[line[0]]
        toks = line[2:].split()
        if len(toks) < 8:                       # rows with no pct column (all-nil cargo) are skipped
            continue
        name, cur, prev = " ".join(toks[:-8]), num(toks[-7]), num(toks[-6])
        row = raw[(raw.year == 2026) & (raw.month == month_name) & (raw.section == section) & (raw.k == ti._canon(name))]
        assert len(row) == 1, name
        assert row.iloc[0].traffic_tonnes_current == cur, (name, "this year")
        assert row.iloc[0].traffic_tonnes_prev_year == prev, (name, "last year")
        checked += 1
    assert checked >= 17


def test_brief_has_findings_sources_and_real_numbers():
    body = client.get("/trade/brief").json()
    assert len(body["findings"]) >= 4
    assert {"cargo", "overseas_coastal", "alerts"} <= set(body["sources"])
    for s in body["sources"].values():
        assert s["data_file"].startswith("data/") and s["origin"]
    text = " ".join(body["findings"])
    import pandas as pd
    latest = pd.Timestamp(ti.get_trade_summary()["as_of"] + "-01").strftime("%B %Y")
    assert latest in text and "million tonnes" in text
    top = body["concentration"]["inbound_top3"]
    assert [x["share_pct"] for x in top] == sorted((x["share_pct"] for x in top), reverse=True)
    _no_nan(client.get("/trade/brief").text)


# ── 2023 data correction (POL PRODUCTS / FOOD GRAINS outbound, Jan-Jul 2023) ─────────────────────
def test_jan_and_feb_2023_outbound_match_official_nmpa_statements():
    """Figures below were read from NMPA's own Jan 2023 and Feb 2023 statements (TOTAL (B) loaded, POL, food grains)."""
    p = ti._prepared()
    wide = p["wide"]
    out = wide[ti.OUTBOUND]
    jan, feb = pd.Timestamp("2023-01-01"), pd.Timestamp("2023-02-01")
    assert p["totals"].loc[jan, "outbound"] == 748_536
    assert p["totals"].loc[feb, "outbound"] == 756_873
    assert out.loc[jan, ti._canon("POL PRODUCTS")] == 396_357
    assert out.loc[feb, ti._canon("POL PRODUCTS")] == 432_711
    assert out.loc[jan, ti._canon("FOOD GRAINS")] == 29_782
    assert out.loc[feb, ti._canon("FOOD GRAINS")] == 468


def test_rebuilt_december_2022_matches_official_statement():
    """Dec 2022 is rebuilt from the prior-year column of Dec 2023; the official Dec 2022 statement has the same figures."""
    flow = ti.build_flow_table(forecasting.load_cargo_dataset())
    dec = flow[flow["date"] == pd.Timestamp("2022-12-01")].set_index(["section", "key"])["tonnes"]
    official = {("UNLOADED", "TOTALCRUDE"): 1_683_976, ("UNLOADED", "TOTALCOAL"): 399_168, ("UNLOADED", "IRONORE"): 211_130,
                ("UNLOADED", "TOTALLPG"): 249_965, ("UNLOADED", "POLPRODUCTS"): 49_097,
                ("LOADED", "IRONORE"): 219_175, ("LOADED", "POLPRODUCTS"): 535_487}
    for k, v in official.items():
        assert dec[k] == v, k
    assert dec.xs("UNLOADED").sum() == 3_041_735 and dec.xs("LOADED").sum() == 937_176


def test_prior_year_crosscheck_leaves_only_known_differences():
    """Every cargo-month that appears both as a real report and as the next year's prior-year column must agree,
    except the reclassifications NMPA made between edible oil and other liquid cargoes (they cancel out) and
    one still-unexplained difference (Dec 2023 cement) that needs the Dec 2023 PDF."""
    df = forecasting.load_cargo_dataset()
    d = df[df["section"].isin([ti.INBOUND, ti.OUTBOUND]) & (df["date"] >= ti.FIRST_CONSISTENT_MONTH)].copy()
    d["key"] = d["commodity"].map(ti._canon)
    cur = d.drop_duplicates(["date", "section", "key"], keep="last")[["date", "section", "key", "traffic_tonnes_current"]]
    cur = cur.rename(columns={"date": "target", "traffic_tonnes_current": "reported"})
    later = d.assign(target=d["date"] - pd.DateOffset(years=1))[["target", "section", "key", "traffic_tonnes_prev_year"]]
    m = later.merge(cur, on=["target", "section", "key"])
    bad = m[(m["traffic_tonnes_prev_year"] - m["reported"]).abs() >= 0.5]
    reclass = bad[bad["key"].isin(["EDIBLEOIL", "OTHLIQCARGOES"])]
    net = reclass.assign(diff=reclass["traffic_tonnes_prev_year"] - reclass["reported"]).groupby("target")["diff"].sum()
    assert (net.abs() < 0.5).all(), "edible oil / other liquid differences must cancel out month by month"
    rest = bad[~bad["key"].isin(["EDIBLEOIL", "OTHLIQCARGOES"])]
    assert set(zip(rest["target"].dt.strftime("%Y-%m"), rest["key"])) <= {("2023-12", "TOTALCEMENT")}
