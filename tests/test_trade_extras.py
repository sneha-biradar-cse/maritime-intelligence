"""Monthly brief PDF, data freshness, customer-name list, target by cargo, and the one-command update script."""
import importlib.util
import io
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import trade_target as tt

client = TestClient(app)


def test_brief_pdf_is_one_page():
    r = client.get("/trade/brief.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    from pypdf import PdfReader
    assert len(PdfReader(io.BytesIO(r.content)).pages) == 1


def test_freshness_lists_every_source():
    f = client.get("/trade/freshness").json()["sources"]
    assert set(f) == {"nmpa_commodity_statements", "ministry_major_ports", "nmpa_container_statements",
                      "nmpa_traffic_performance", "nmpa_daily_reports"}
    assert all(f.values())


def test_customer_names_csv():
    r = client.get("/trade/customer-names.csv")
    lines = r.text.splitlines()
    assert r.status_code == 200 and lines[0].startswith("written_in_daily_report,counted_as,ship_calls")
    assert any(",PPL (PARADEEP PHOSPHATES)," in l for l in lines)


def test_target_by_cargo_adds_up():
    g = tt.get_target_by_cargo()
    assert sum(r["change_tonnes"] for r in g["cargos"]) == pytest.approx(g["total_change_tonnes"], abs=len(g["cargos"]))
    json.dumps(g, allow_nan=False)


def _update_module():
    spec = importlib.util.spec_from_file_location("upd", tt.ROOT / "scripts" / "update_trade_data.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("name,kind", [
    ("27-10-2026.pdf", "daily"), ("Cargo handled at Major Ports October 2026.pdf", "ministry"),
    ("container traffic for the month of October 2026.pdf", "container"),
    ("operational performance October 2026.pdf", "performance"),
    ("Commodity wise traffic statement October 2026.pdf", "commodity"), ("something.pdf", "unknown"),
])
def test_update_script_recognises_files(name, kind, tmp_path):
    from pathlib import Path
    assert _update_module().kind_of(Path(name)) == kind


def test_update_script_skips_a_file_already_held(tmp_path, monkeypatch):
    m = _update_module()
    inbox = tmp_path / "incoming"
    inbox.mkdir()
    held = sorted(m.DAILY_PDF.glob("*.pdf"))[0]
    shutil.copy(held, inbox / held.name)
    monkeypatch.setattr(m, "INBOX", inbox)
    monkeypatch.setattr(m, "run", lambda args: (0, "ok"))           # do not re-run the parsers in a unit test
    monkeypatch.setattr(m, "_sync_overseas_coastal", lambda log: None)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    m.main()
    log = json.loads((tmp_path / "data" / "last_update.json").read_text())
    assert log["skipped"] and not log["added"] and not log["problems"]


def test_seasonality_iron_ore_peaks_in_winter():
    r = client.get("/trade/seasonality", params={"name": "IRON ORE"})
    assert r.status_code == 200
    out = r.json()["directions"]["outbound"]
    assert len(out["complete_years"]) >= 3
    assert set(out["busiest_months"]) & {"Dec", "Jan", "Feb", "Mar"}
    assert abs(sum(out["seasonal_index"]) / 12 - 100) < 2          # an index averages 100
    assert client.get("/trade/seasonality", params={"name": "NO SUCH CARGO"}).status_code == 404


def test_cargo_mix_shares_add_up_each_year():
    m = client.get("/trade/cargo-mix").json()
    for fy in m["financial_years"]:
        assert abs(sum(r["share_pct"][fy] for r in m["cargos"]) - 100) < 1.0
        assert sum((r["tonnes"][fy] or 0) for r in m["cargos"]) == m["totals_tonnes"][fy]


def test_alert_feedback_round_trip(tmp_path, monkeypatch):
    from backend.app.services import trade_feedback as tfb
    monkeypatch.setattr(tfb, "FILE", tmp_path / "fb.json")
    r = client.post("/trade/alert-feedback", json={"key": "customer|VEDANTA", "status": "Explained",
                                                   "note": "Plant maintenance until December", "by": "Traffic"})
    assert r.status_code == 200 and r.json()["status"] == "Explained"
    items = client.get("/trade/alert-feedback").json()["items"]
    assert items["customer|VEDANTA"]["note"].startswith("Plant maintenance")
    assert client.post("/trade/alert-feedback", json={"key": "x", "status": "Bogus"}).status_code == 422
    client.post("/trade/alert-feedback", json={"key": "customer|VEDANTA", "status": "Open"})
    assert "customer|VEDANTA" not in client.get("/trade/alert-feedback").json()["items"]


def test_market_share_shares_are_consistent():
    r = client.get("/trade/market-share").json()
    assert r["available"]
    for c in r["cargos"]:
        assert 0 <= c["share_pct"] <= 100
        assert c["share_pct"] == pytest.approx(c["nmpa_tonnes"] / c["all_ports_tonnes"] * 100, abs=0.01)
        if c["status"] == "Losing share":
            assert c["growth_gap_points"] <= -5
    assert 3 < r["nmpa_share_of_all_major_ports_pct"] < 8


def test_ministry_commodity_table_adds_up():
    import pandas as pd
    d = pd.read_csv(tt.ROOT / "data" / "major_ports_commodity_monthly.csv")
    for (per, thr), g in d.groupby(["period", "through"]):
        if "Total" not in set(g.commodity):
            continue
        detailed = g[~g.commodity.isin(["Total", "TEUs"]) & ~g.commodity.str.startswith("P:")]
        principal = g[g.commodity.str.startswith("P:") | (g.commodity == "Container Tonnes")]
        total = g[g.commodity == "Total"]["tonnes"].iloc[0]
        parts = detailed if detailed["commodity"].nunique() > 5 else principal
        assert abs(parts["tonnes"].sum() - total) <= 25, (per, thr)
    sep = d[(d.period == "ytd") & (d.through == "2026-09")].set_index("commodity")["tonnes"]
    assert sep["Total"] == 472_745_575 and sep["POL Crude"] == 94_320_511      # printed in the September 2026 report


def test_container_lines_endpoint():
    r = client.get("/trade/container-lines").json()
    assert r["available"] and r["lines"]
    assert all(l["status"] in ("New", "Not seen for 60+ days", "Calling") for l in r["lines"])
    json.dumps(r, allow_nan=False)


def test_customer_notes_round_trip(tmp_path, monkeypatch):
    from backend.app.services import trade_feedback as tfb
    monkeypatch.setattr(tfb, "NOTES_FILE", tmp_path / "notes.json")
    r = client.post("/trade/customer-notes", json={"customer": "Vedanta", "owner": "Traffic - R. Kumar",
                                                   "follow_up": "2000-01-01", "note": "Called: maintenance till Dec", "by": "RK"})
    assert r.status_code == 200 and r.json()["owner"].startswith("Traffic")
    g = client.get("/trade/customer-notes").json()
    assert g["customers"]["VEDANTA"]["notes"][0]["text"].startswith("Called")
    assert g["follow_ups_due"][0]["customer"] == "VEDANTA"
    assert client.post("/trade/customer-notes", json={"customer": "X", "follow_up": "not a date"}).status_code == 422


def test_main_group_share_has_every_month():
    from backend.app.services import trade_market as tm
    g = tm.get_market_share()["monthly_share_groups"]
    assert len(g) >= 24
    for r in g:
        assert all(v is not None for k, v in r.items() if k != "month"), r["month"]


def test_april_reports_store_full_financial_years():
    import pandas as pd
    d = pd.read_csv(tt.ROOT / "data" / "major_ports_commodity_monthly.csv")
    fy = d[(d.period == "ytd") & (d.commodity == "Total") & (d.through == "2025-03")]["tonnes"].iloc[0]
    assert 840_000_000 < fy < 870_000_000                       # FY 2024-25, about 854 MMT at all major ports
    assert d[(d.period == "ytd") & (d.through == "2025-04")].empty  # April-to-date is never the full-year column


def test_annual_port_commodity_adds_up_and_matches_monthly_total():
    import pandas as pd
    a = pd.read_csv(tt.ROOT / "data" / "major_ports_annual_port_commodity.csv")
    for fy, g in a.groupby("financial_year"):
        allp = g[g.port == "All Ports"].iloc[0]
        assert abs(g[g.port != "All Ports"]["total"].sum() - allp["total"]) <= 2
    # the annual 2024-25 total equals the Ministry's monthly April-March figure (thousand tonnes)
    d = pd.read_csv(tt.ROOT / "data" / "major_ports_commodity_monthly.csv")
    ytd = d[(d.period == "ytd") & (d.through == "2025-03") & (d.commodity == "Total")]["tonnes"].iloc[0]
    assert abs(a[(a.port == "All Ports") & (a.financial_year == "2024-25")]["total"].iloc[0] * 1000 - ytd) < 1000


def test_port_competition_endpoint():
    r = client.get("/trade/port-competition").json()
    assert r["available"] and "Crude and POL products" in r["groups"]
    assert r["groups"]["All cargo"]["new_mangalore"]["port"] == "New Mangalore"


@pytest.mark.parametrize("name,kind", [
    ("01-09-2025.pdf", "daily"), ("01-09-2025 (1).pdf", "daily"), ("01-09-2025_0.pdf", "daily"), ("01.09.2025.pdf", "daily"),
    ("05-09-2025-Revision-in-Credit-Rating-JSW-Mangalore-Container-Terminal.pdf", "unknown"),
])
def test_only_date_named_files_are_daily_reports(name, kind):
    from pathlib import Path
    assert _update_module().kind_of(Path(name)) == kind


def test_unconfirmed_identities_are_not_merged():
    from backend.app.services import trade_customers as tc
    al = tc.load_aliases()
    assert tc.canonical_customer("ADANI", al) == "ADANI"
    assert tc.canonical_customer("MCF", al) == "MCF"
    assert tc.canonical_customer("PARADEEP PHOS", al) == "PPL (PARADEEP PHOSPHATES)"      # spelling of the same name


def test_every_daily_report_has_a_status():
    import pandas as pd
    m = pd.read_csv(tt.ROOT / "data" / "daily_reports_manifest.csv")
    assert m["status"].notna().all() and len(m) == len(list((tt.ROOT / "data" / "daily_vessel_position_parsed").glob("*.json")))
    miss = pd.read_csv(tt.ROOT / "data" / "daily_reports_missing_pdfs.csv")
    assert set(miss["file_date"]) == set(m[m["status"].str.startswith("Original not obtained")]["file_date"])
    r = client.get("/trade/data-status").json()
    assert "Not a claim of 100% accuracy" in r["claim"] and r["daily_reports"]["not_checked"] == len(miss)
