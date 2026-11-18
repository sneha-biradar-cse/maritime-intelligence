"""Public reference data: NMPA's budget (cost per tonne) and the Ministry's port-wise turnaround times."""
import importlib.util
from pathlib import Path

import pandas as pd

from backend.app.services import incentive_decision_aids as da

ROOT = Path(__file__).resolve().parents[1]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def test_budget_parser_reads_nmpa_figures_exactly():
    rows = _script("fetch_nmpa_cost_reference").parse_budget_text((ROOT / "tests/fixtures/nmpa_budget_2024_25_extract.txt").read_text())
    saved = pd.read_csv(ROOT / "data" / "nmpa_cost_reference.csv")
    assert [(r["year"], r["basis"]) for r in rows] == list(zip(saved.year, saved.basis))
    for r, s in zip(rows, saved.itertuples()):
        assert r["cargo_handling_expenditure_cr"] == s.cargo_handling_expenditure_cr and r["traffic_lakh_t"] == s.traffic_lakh_t


def test_cost_reference():
    c = da.cost_reference()
    assert c["available"] and c["suggested_rs_per_t"] == 18.21                         # 77.97 cr / 428.06 lakh t
    assert all(r["handling_cost_per_t_rs"] < r["handling_income_per_t_rs"] for r in c["rows"])


def test_turnaround_table_and_cross_check():
    years, rows = _script("fetch_turnaround_benchmark").parse_table((ROOT / "tests/fixtures/ministry_turnaround_extract.md").read_text())
    assert years[-1] == "2025-26" and ["New Mangalore Port", 45.99, 43.09, 40.44, 40.37, 43.23] in rows
    b = da.turnaround_benchmark()
    assert b["nmpa_rank"] == 3 and b["nmpa_hours"] == 43.23 and len(b["ports"]) == 12
    perf = pd.read_csv(ROOT / "data" / "nmpa_performance_monthly.csv")
    x = perf[(perf.metric == "turn_round_time_hrs") & (perf.basis == "pilot") & (perf.category == "overall")
             & (perf.period == "ytd") & (perf.year == "current") & (perf.report_month == "2026-03")]
    if not x.empty:
        assert round(float(x.value.iloc[0]), 2) == 43.23                                  # Ministry figure = NMPA's own statement


def test_approval_route_never_enforces_unconfirmed(tmp_path, monkeypatch):
    from backend.app.services import trade_market as tmk
    r = da.approval_route("Rebate claim: approve payment", 8e5)
    assert r["confirmed_rows"] == 0 and r["answer"]["authority"] is None                  # as shipped: nothing confirmed
    assert any("delegation1.pdf" in x["url"] for x in r["references"])
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "approval_references.csv").write_text((ROOT / "data" / "approval_references.csv").read_text())
    (tmp_path / "data" / "approval_matrix.csv").write_text(
        "decision,authority,up_to_rs,confirmed_by_nmpa,confirmed_on,basis,note\n"
        "Rebate claim: approve payment,Traffic Manager,500000,yes,2027-01-10,NMPA order,\n"
        "Rebate claim: approve payment,Deputy Chairperson,2500000,yes,2027-01-10,NMPA order,\n"
        "Rebate claim: approve payment,Chairperson,,no,,draft,\n")                            # unconfirmed row must be ignored
    monkeypatch.setattr(tmk, "ROOT", tmp_path)
    assert da.approval_route("Rebate claim: approve payment", 3e5)["answer"]["authority"] == "Traffic Manager"
    assert da.approval_route("Rebate claim: approve payment", 8e5)["answer"]["authority"] == "Deputy Chairperson"
    big = da.approval_route("Rebate claim: approve payment", 9e6)["answer"]
    assert big["authority"] is None and "refer upwards" in big["message"]                  # the unconfirmed Chairperson row is not used


def test_citizen_charter_standards_and_scheme_history():
    c = da.charter_standards()
    std = {r["service"]: r["standard"] for r in c["standards"]}
    assert std["Pilotage"] == 120 and std["Allotment of berths to vessels"] == 30 and std["Payments to suppliers/contractors"] == 5
    assert std["Cargo handling at wharves and oil jetties"] == 16000
    n = pd.read_csv(ROOT / "data" / "nmpa_incentive_notices.csv", dtype=str).fillna("")
    assert (n.status == "In force").sum() == 5                                          # history rows never count as in force
    cape = n[n.cargos.str.contains("Cape-size")].sort_values("valid_from")
    assert list(cape.valid_from) == ["2021-04-03", "2022-04-03", "2023-04-03", "2025-04-03"]   # unbroken since April 2021
    assert all(cape.valid_to.iloc[i] < cape.valid_from.iloc[i + 1] for i in range(len(cape) - 1))
    assert all(r.source for r in n.itertuples() if not r.file)                          # every row without a held PDF names its source
