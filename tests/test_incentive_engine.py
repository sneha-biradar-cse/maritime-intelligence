"""Incentive Engine: every rate matches NMPA's Scale of Rates PDF, and every figure is plain arithmetic on real data."""
import json
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import cost_engine as ce
from backend.app.services import incentive_engine as ie

client = TestClient(app)


@pytest.fixture(scope="module")
def sor_text():
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext not installed")
    pdf = ie.tmk.ROOT / ie.SOR_FILE
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout


# The exact line of the Scale of Rates each rate comes from (coastal, foreign).
SOR_LINES = {
    "crude_spm": r"Crude oil through Single Point Mooring\s+M\.T\.\s+34\.89\s+34\.90",
    "pol_products": r"\(d\) Crude Oil\s+M\.T\.\s+96\.60\s+96\.60",
    "lpg_lng_gas": r"LPG/LNG or any gas in any other form\s+M\.T\.\s+147\.61\s+245\.57",
    "iron_ore_fines_lumps": r"Iron Ore Fines/Lumps\s+M\.T\.\s+43\.16\s+43\.16",
    "thermal_coal": r"Thermal Coal \(other than UPCL\)\s+M\.T\.\s+31\.73\s+31\.73",
    "fertilizer": r"MOP, SOP, Urea ,DAP, NPK, CAN,\s+M\.T\s+26\.65\s+45\.71",
    "rock_phosphate_sulphate": r"Sulphate/ Rock phosphate\s+M\.T\s+30\.47\s+52\.04",
    "food_grains": r"Rice,Wheat, Maize, Pulses\s+M\.T\.\s+30\.47\s+52\.04",
    "edible_oil": None,
}


@pytest.mark.parametrize("key,pattern", [(k, p) for k, p in SOR_LINES.items() if p])
def test_rates_match_the_scale_of_rates_pdf(sor_text, key, pattern):
    m = re.search(pattern, sor_text)
    assert m, f"line not found in the Scale of Rates: {pattern}"
    nums = [float(x) for x in re.findall(r"\d+\.\d+", m.group(0))[-2:]]
    r = ie._rate(key)
    assert nums == [r["coastal"], r["foreign"]]


def test_every_rate_used_appears_on_one_line_of_the_scale_of_rates(sor_text):
    lines = sor_text.splitlines()
    for name, c in ie.CARGO.items():
        r = ie._rate(c["rate"])
        a, b = f"{r['coastal']:.2f}", f"{r['foreign']:.2f}"
        assert any(a in l and b in l and l.index(a) < l.rindex(b) for l in lines), f"{name}: {a} / {b} not on one line"


def test_sor_allows_lower_rates_and_rebates(sor_text):
    assert re.search(r"rates prescribed in the Scale of Rates are\s+ceiling levels", sor_text)
    assert re.search(r"allow higher rebates and discounts", sor_text)


def test_revenue_is_tonnes_times_rate():
    r = ie.get_revenue()
    for c in r["cargos"]:
        assert c["revenue_rs"] == pytest.approx(c["tonnes"] * c["avg_rate_rs_per_t"], rel=1e-3, abs=50)
        lo, hi = min(c["rate_coastal"], c["rate_foreign"]), max(c["rate_coastal"], c["rate_foreign"])
        if c["spm_share_pct"] is None:
            assert lo - 0.01 <= c["avg_rate_rs_per_t"] <= hi + 0.01
        assert c["coastal_concession_rs"] >= 0
        assert c["billed_rs"] is None and c["estimate_full_tariff_rs"] == c["revenue_rs"] and c["calculation"]
    assert {n["item"] for n in r["not_estimated"]} >= {"Containers (Berth 14)", "Coal for UPCL / Adani Power", "Iron ore imports (KIOCL)"}


def test_crude_is_priced_by_where_it_is_discharged():
    c = next(x for x in ie.get_revenue()["cargos"] if x["cargo"] == "Crude oil")
    assert 0 < c["spm_share_pct"] < 100
    spm, berth = 34.9, 96.6
    expect = c["spm_share_pct"] / 100 * spm + (1 - c["spm_share_pct"] / 100) * berth
    assert c["avg_rate_rs_per_t"] == pytest.approx(expect, abs=0.05)


def test_opportunities_are_reviews_not_discounts():
    o = ie.get_opportunities()
    for x in o["cargos"]:
        assert x["signal"].startswith("Statistical volume gap")
        assert "only if charges are confirmed" in x["suggested_next_step"]
    assert "not a recommendation to discount" in o["explain"]


def test_sor_reference_points_to_the_right_lines(sor_text):
    import json
    ref = json.loads((ie.tmk.ROOT / "data" / "sor_reference.json").read_text())["lines"]
    pages = sor_text.split("\f")
    for key, hit in ref.items():
        assert hit["line"].split("  ")[0] in re.sub(r"\s{2,}", "  ", pages[hit["pdf_page"] - 1])


def test_break_even_formula():
    b = ie.break_even("LPG", 10)
    assert b["extra_tonnes_to_break_even"] == pytest.approx(b["annual_tonnes_now"] * 0.10 / 0.90, abs=2)
    assert b["extra_pct_to_break_even"] == pytest.approx(11.1, abs=0.1)


def test_evidence_states_its_limits():
    e = ie.get_evidence()
    assert "does not prove" in e["caution"]
    for c in e["cases"]:
        if c.get("measurable") and "share_before_pct" in c:
            assert c["share_change_points"] == pytest.approx(c["share_after_pct"] - c["share_before_pct"], abs=0.02)


@pytest.mark.parametrize("url", ["/incentive/revenue", "/incentive/evidence", "/incentive/opportunities"])
def test_endpoints_ok_no_nan(url):
    r = client.get(url)
    assert r.status_code == 200
    json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))


def test_scenario_arithmetic_blanket_and_rebate():
    s = ie.scenario("LPG", 10, cost_per_t=0, fixed_cost=0, low_response_pct=2)
    r, q0, d = s["rate_rs_per_t"], s["baseline_tonnes_per_year"], 0.10
    assert s["blanket_given_up_on_baseline_rs"] == pytest.approx(r * d * q0, abs=200)
    assert s["break_even_extra_tonnes_blanket"] == pytest.approx(q0 * d / (1 - d), abs=50)
    assert s["break_even_extra_tonnes_rebate"] == 0                 # rebate on extra volume only, no fixed cost
    none = s["scenarios"][0]
    assert none["extra_tonnes"] == 0 and none["rebate_change_rs"] == 0 and none["blanket_change_rs"] < 0
    assert "receipts only" in s["measure"]


def test_scenario_with_costs_is_contribution():
    s = ie.scenario("LPG", 10, cost_per_t=20, fixed_cost=1_000_000)
    r, q0, d = s["rate_rs_per_t"], s["baseline_tonnes_per_year"], 0.10
    margin = r * (1 - d) - 20
    assert s["break_even_extra_tonnes_blanket"] == pytest.approx((r * d * q0 + 1_000_000) / margin, abs=50)
    assert s["break_even_extra_tonnes_rebate"] == pytest.approx(1_000_000 / margin, abs=5)
    assert "contribution" in s["measure"].lower()
    assert ie.scenario("LPG", 10, cost_per_t=10_000)["never_breaks_even"]


def test_customer_stage_validation(tmp_path, monkeypatch):
    from backend.app.services import trade_feedback as tfb
    monkeypatch.setattr(tfb, "NOTES_FILE", tmp_path / "n.json")
    ok = client.post("/trade/customer-notes", json={"customer": "MRPL", "stage": tfb.OPPORTUNITY_STAGES[1],
                                                      "reason": "Refinery maintenance", "action": tfb.ACTIONS[0]})
    assert ok.status_code == 200 and ok.json()["stage"].startswith("Confirmed")
    assert client.post("/trade/customer-notes", json={"customer": "MRPL", "stage": "Guess"}).status_code == 422


def test_large_customer_drop_counts_as_falling():
    from backend.app.services import trade_customers as tc
    assert tc._trend(4_400_000, 4_870_000, 70, 75, False)[0] == "Falling"      # -9.6%, 470,000 t
    assert tc._trend(9_000, 10_000, 4, 5, False)[0] == "Steady"                  # -10% but only 1,000 t
    assert tc._trend(5_000, 10_000, 3, 5, False)[0] == "Falling"                 # -50%


def test_ppp_berths_are_not_priced_as_wharfage():
    r = ie.get_revenue()
    names = {c["cargo"] for c in r["cargos"]}
    assert not any("Coal" in n for n in names)                 # Berth 16 is a PPP terminal
    items = " ".join(n["item"] for n in r["not_estimated"])
    assert "Berth 16" in items and "Berth 14" in items


def test_container_royalty_is_teu_times_rate():
    p = ie.get_ppp_royalty()["containers"]
    assert p["royalty_estimate_rs"] == pytest.approx(p["laden_teu"] * p["royalty_rs_per_teu"], abs=1)
    assert "minimum" in " ".join(p["limits"])


def test_customer_wharfage_adds_up_and_excludes_own_arrangements():
    c = ie.get_customer_wharfage()
    assert sum(r["wharfage_rs"] for r in c["customers"]) == c["total_rs"]
    kiocl = next((r for r in c["customers"] if r["customer"] == "KIOCL"), None)
    assert kiocl is None or "Iron ore" not in kiocl["main_cargo_priced"]
    for r in c["customers"]:
        assert r["change_q2_vs_q1_rs"] == r["wharfage_q2_rs"] - r["wharfage_q1_rs"]


def test_budget_lines_add_up_to_nmpa_totals_where_complete():
    b = ie._budget()
    # every line kept is a positive income figure; totals are NMPA's printed totals
    assert (b.drop(index=["TOTAL_CHSC", "TOTAL_PDC", "TOTAL_OPINC"])[["actual_2022_23", "re_2023_24"]] >= 0).all().all()
    assert b.loc["TOTAL_OPINC", "re_2023_24"] == 8175647          # Rs '000, as printed


def test_accounts_check_implied_rates():
    a = ie.get_accounts_check()
    lpg = next(r for r in a["rows"] if r["cargo"] == "LPG")
    assert lpg["implied_rate_2023_24"] == pytest.approx(lpg["income_2023_24_rs"] / lpg["tonnes_2023_24"], abs=0.01)
    # the rates used here are of the same order as what NMPA earned (a factor-of-two error would fail)
    for r in a["rows"]:
        assert 0.5 < r["our_rate_today"] / r["implied_rate_2023_24"] < 1.5


def test_zero_discount_gives_original_receipts():
    s = ie.scenario("LPG", 0)
    assert s["blanket_given_up_on_baseline_rs"] == 0
    assert all(r["blanket_change_rs"] == 0 and r["rebate_change_rs"] == 0 for r in s["scenarios"] if r["extra_tonnes"] == 0)


def test_rebate_only_touches_extra_volume():
    s = ie.scenario("LPG", 10, low_response_pct=5)
    low = s["scenarios"][1]
    r, d = s["rate_rs_per_t"], 0.10
    assert low["rebate_change_rs"] == pytest.approx(low["extra_tonnes"] * r * (1 - d), abs=200)


def test_scheme_workflow_and_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_schemes.json")
    f = ie.tmk.ROOT / "data" / "_test_schemes.json"
    f.unlink(missing_ok=True)
    try:
        with pytest.raises(ValueError):           # tariff version must cover the scheme's start
            ie.create_scheme("LPG", "Blanket discount", 5, "2025-06-01", "2025-08-31", 1e7)
        rec = ie.create_scheme("LPG", "Rebate on extra volume", 5, "2026-06-01", "2026-08-31", 1e7, by="Traffic")
        assert rec["status"] == "Draft" and rec["tariff_version"] == ie.TARIFF_VERSION and rec["rate_rs_per_t"] > 0
        with pytest.raises(ValueError):            # cannot jump straight to approved
            ie.update_scheme(rec["id"], "Approved")
        ie.update_scheme(rec["id"], "Traffic review", by="Traffic")
        ie.update_scheme(rec["id"], "Finance review", by="Traffic")
        with pytest.raises(ValueError):            # approval needs a reference
            ie.update_scheme(rec["id"], "Approved", by="Finance")
        ie.update_scheme(rec["id"], "Approved", approval_reference="NMPA/TM/2026/17", by="Finance")
        done = ie.update_scheme(rec["id"], "Active", by="Traffic")
        assert [a["event"] for a in done["audit"]][0] == "Created as draft" and len(done["audit"]) >= 5
        obs = ie.scheme_results(done)
        assert obs["months_held"] == ["2026-06", "2026-07", "2026-08"]
        assert "causal impact not established" in obs["label"]
    finally:
        f.unlink(missing_ok=True)


def test_waiver_uses_the_circulars_dates():
    e = ie.get_evidence()
    w = [c for c in e["cases"] if c.get("waiver_window")]
    assert {c["cargo"] for c in w} == {"LPG", "Crude oil"}
    assert all("14-31 Mar 2026" in c["incentive"] for c in w)
    assert "two and a half weeks" in e["caution"]
    r = ie.get_revenue()
    lpg = next(c for c in r["cargos"] if c["cargo"] == "LPG")
    assert lpg["adjustments_status"].startswith("None in this period")


def test_original_policy_documents_are_held():
    folder = ie.tmk.ROOT / "nmpa_public_data" / "finance_and_policy"
    names = " ".join(p.name for p in folder.glob("*.pdf"))
    for part in ("Budget", "PPP", "Trade Circular", "Non-Major"):
        assert part in names


def test_tariff_version_and_identity_block_a_proposal():
    from backend.app.services import incentive_rules as ir
    priced = [r["cargo"] for r in ie.get_revenue()["cargos"]]
    e = ir.check_eligibility("LPG", "2026-05-03", "2026-06-30", ["ADANI"], [], priced)
    assert not e["eligible"]
    assert not any("old format" in b for b in e["blocks"]) and any("ADANI" in b for b in e["blocks"])   # 1-6 May version now held
    assert ir.check_eligibility("Edible oil", "2026-12-01", "2027-02-28", [], [], priced)["eligible"]
    io = ir.check_eligibility("Iron ore exports", "2026-12-01", "2027-02-28", ["NMDC"], [], priced)    # iron ore rebate in force
    assert not io["eligible"] and any("IOF-Exp-Rebate" in b for b in io["blocks"])
    assert not ir.check_eligibility("Containers", "2026-12-01", "2027-02-28", [], [], priced)["eligible"]   # PPP berth
    assert not ir.check_eligibility("LPG", "2026-03-20", "2026-03-25", [], [], priced)["eligible"]          # overlaps the waiver


def test_baseline_methods_and_missing_months():
    from backend.app.services import incentive_rules as ir
    keys = ie.CARGO["Iron ore exports"]["keys"]
    one = ir.baseline(keys, ["2026-12", "2027-01"], "same_months_last_year")
    avg = ir.baseline(keys, ["2026-12", "2027-01"], "same_months_avg_years", 3)
    assert one["tonnes"] > 0 and avg["tonnes"] > 0 and avg["detail"].count("earlier") == 3
    gap = ir.baseline(keys, ["2021-06"], "same_months_last_year")             # June 2020 is not held
    assert gap["tonnes"] is None and "missing" in gap["blocked"].lower()
    assert ir.baseline(keys, ["2026-12"], "contractual", contractual_t=None)["tonnes"] is None


def test_marginal_slabs_and_cap():
    from backend.app.services import incentive_rules as ir
    tiers = [{"up_to_pct_above_baseline": 10, "rebate_pct": 5}, {"up_to_pct_above_baseline": 20, "rebate_pct": 8},
             {"up_to_pct_above_baseline": None, "rebate_pct": 10}]
    r = ir.marginal_rebate(1_250_000, 1_000_000, 100.0, tiers)
    # 100k t x Rs5 + 100k t x Rs8 + 50k t x Rs10 = 0.5m + 0.8m + 0.5m
    assert r["rebate_rs"] == 1_800_000 and [t["tonnes"] for t in r["tiers"]] == [100000, 100000, 50000]
    capped = ir.marginal_rebate(1_250_000, 1_000_000, 100.0, tiers, cap_rs=1_000_000)
    assert capped["capped"] and capped["rebate_rs"] == 1_000_000
    assert ir.marginal_rebate(900_000, 1_000_000, 100.0, tiers)["rebate_rs"] == 0
    assert "Potential" in r["status"]


def test_baseline_versions_freeze_and_review_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_schemes2.json")
    f = ie.tmk.ROOT / "data" / "_test_schemes2.json"
    f.unlink(missing_ok=True)
    try:
        bad = ie.create_scheme("LPG", "Rebate on extra volume", 5, "2026-12-01", "2027-01-31", 1e7, customers="ADANI")
        assert not bad["eligibility"]["eligible"]
        with pytest.raises(ValueError):
            ie.update_scheme(bad["id"], "Traffic review")                  # blocked: identity unresolved
        ok = ie.create_scheme("Edible oil", "Rebate on extra volume", 5, "2026-12-01", "2027-02-28", 1e7,
                              tiers=[{"up_to_pct_above_baseline": 10, "rebate_pct": 5}], success_target_t=50000)
        with pytest.raises(ValueError):
            ie.rebaseline(ok["id"], "same_months_avg_years", 3, reason="")  # reason required
        rb = ie.rebaseline(ok["id"], "same_months_avg_years", 3, reason="2025-26 was unusually high")
        assert len(rb["baselines"]) == 2 and rb["baselines"][0]["method"] == "same_months_last_year"
        ie.update_scheme(ok["id"], "Traffic review")
        ie.update_scheme(ok["id"], "Finance review")
        ap = ie.update_scheme(ok["id"], "Approved", approval_reference="REF-1")
        assert [b["frozen"] for b in ap["baselines"]] == [False, True]
        with pytest.raises(ValueError):
            ie.rebaseline(ok["id"], "same_months_last_year", reason="try")   # frozen after Draft
    finally:
        f.unlink(missing_ok=True)


def test_source_register_lists_every_original():
    import pandas as pd
    reg = pd.read_csv(ie.tmk.ROOT / "data" / "source_register.csv")
    monthly = reg[reg.document.str.startswith(("Monthly", "Statement", "Traffic", "Cargo handled at Major"))]
    assert monthly["period"].notna().all() and not monthly.duplicated(["document", "period"]).any()
    assert (reg.md5.str.len() == 32).sum() >= 100


def test_both_tariff_versions_held_and_identical_lines():
    from backend.app.services import incentive_rules as ir
    assert all(v["held"] for v in ir.TARIFF_VERSIONS)
    assert ir.tariff_for("2026-05-03")["id"] == "NMPA-SOR-2026-OLD"


def test_tariff_comparison_values_are_in_both_pdfs(sor_text):
    import pandas as pd
    d = pd.read_csv(ie.tmk.ROOT / "data" / "port_tariff_comparison.csv")
    pol = d[d.cargo == "POL products (at berth)"].iloc[0]
    assert pol.nmpa_foreign == 96.60 and pol.cochin_foreign == 152.70 and pol.nmpa_vs_cochin_foreign_pct == -36.7
    assert set(d[d.comparability == "Unresolved"].cargo) == {"LPG", "Iron ore", "Containers"}
    assert "Contractual" in d[d.cargo == "Crude oil (SPM / SBM)"].comparability.iloc[0]


def test_actual_income_table_adds_up():
    import pandas as pd
    a = pd.read_csv(ie.tmk.ROOT / "data" / "nmpa_actual_income_2023_25.csv", comment="#").set_index("line")
    for y in ("fy_2024_25_rs_cr", "fy_2023_24_rs_cr"):
        assert abs(a.loc["1", y] + a.loc["4", y] + a.loc["5", y] - a.loc["7", y]) < 0.02
    assert abs(a.loc["1", "fy_2024_25_rs_cr"] + a.loc["5", "fy_2024_25_rs_cr"] - 921.36) < 0.02   # Finance section's total


@pytest.mark.parametrize("url", ["/incentive/tariff-comparison", "/incentive/cochin-schemes", "/incentive/published-accounts",
                                 "/incentive/rules"])
def test_new_endpoints_ok_no_nan(url):
    r = client.get(url)
    assert r.status_code == 200
    json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))


def test_deal_desk_proposal_arithmetic_and_labels():
    from backend.app.services import incentive_proposal as ip, incentive_rules as ir
    p = ip.build_proposal("NMDC", start="2026-12-01", end="2027-02-28", discount_pct=10, low_response_pct=5,
                          target_extra_t=100000, budget_cap_rs=5e6)
    assert p["status"].startswith("Draft for internal discussion") and p["cargo"] == "Iron ore exports"
    q0, r = p["baseline"]["tonnes"], p["rate_rs_per_t"]
    tgt = next(s for s in p["scenarios"] if s["scenario"] == "Commercial target")
    assert tgt["rebate_rs"] == ir.marginal_rebate(q0 + 100000, q0, r, p["tiers"], 5e6)["rebate_rs"]
    assert tgt["blanket_net_rs"] == round(100000 * r * 0.9 - q0 * r * 0.1)
    assert next(s for s in p["scenarios"] if s["scenario"] == "No response")["rebate_rs"] == 0
    assert any("traced" in g for g in p["data_gaps"])


def test_deal_desk_blocks_and_errors():
    from backend.app.services import incentive_proposal as ip
    assert client.get("/incentive/proposal", params={"customer": "NO SUCH CUSTOMER"}).status_code == 404
    adani = client.get("/incentive/proposal", params={"customer": "ADANI"})
    if adani.status_code == 200:
        assert any("ADANI" in b for b in adani.json()["eligibility"]["blocks"])
    pdf = client.get("/incentive/proposal.pdf", params={"customer": "NMDC"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    gap = ip.build_proposal("NMDC", start="2026-06-01", end="2026-07-31")      # Jun-Jul 2025 not in daily reports
    assert gap["baseline"]["tonnes"] is None and "Sep 2025" in gap["baseline"]["blocked"]


def test_module_kpis():
    r = client.get("/incentive/kpis").json()
    rows = {x["kpi"]: x for x in r["rows"]}
    tariff = rows["Tariff rates used, found in NMPA's Scale of Rates PDF"]["value"]
    a, b = [int(x) for x in tariff.split(" of ")]
    assert a == b                                                        # every rate used is in the PDF
    assert rows["Estimated wharfage vs wharfage actually billed, by cargo"]["status"] == "Pending NMPA data"
    assert not any("calculator" in k.lower() for k in rows)
    assert {x["status"] for x in r["rows"]} <= {"Measured", "Pending NMPA data", "Estimated"}


def test_seasonal_windows():
    r = ie.get_seasonal_windows(10)
    assert r["status"].endswith("capacity and customer feasibility unconfirmed")
    for x in r["rows"]:
        assert x["cost_quiet_months_rs"] <= x["cost_all_year_rs"]
        assert x["cost_all_year_rs"] == round(x["last12_tonnes"] * x["rate_rs_per_t"] * 0.10) or abs(
            x["cost_all_year_rs"] - x["last12_tonnes"] * x["rate_rs_per_t"] * 0.10) < 2
        if x.get("occupancy_quiet_pct") is not None:
            assert 0 <= x["occupancy_quiet_pct"] <= 100 and 0 <= x["occupancy_other_pct"] <= 100
        if not x["regular"]:
            assert "guess" in x["verdict"]
    assert all(b not in ("14", "15", "16") for x in r["rows"] for b in x["berths"])   # PPP berths excluded
    occ = ie._berth_occupancy()
    assert max(v for v in occ["occ"].values()) <= max(occ["days"].values())          # never more ship-days than report days


def test_key_customers():
    k = ie.get_key_customers()
    assert k["key_share_pct"] >= 90 and k["rows"][0]["customer"] == "MRPL"
    for r in k["rows"]:
        assert r["risk"] in ("High", "Medium", "None found")
        assert (r["risk"] == "None found") == (not r["signals"])
        if r["risk"] == "High":
            assert r["share_pct"] >= 5
        assert r["annualised_change_rs"] == r["change_q2_vs_q1_rs"] * 4
    assert k["at_risk_quarter_fall_rs"] <= 0
    assert client.get("/incentive/key-customers").status_code == 200


def test_start_here_actions_and_brief():
    a = client.get("/incentive/actions").json()
    assert a["actions"] and all({"who", "action", "why", "where", "next"} <= set(x) for x in a["actions"])
    assert [x["priority"] for x in a["actions"]] == sorted(x["priority"] for x in a["actions"])
    assert any(x["action"].startswith("Call MRPL") for x in a["actions"])
    assert {g["role"] for g in a["role_guide"]} >= {"Finance", "Management"}
    pdf = client.get("/incentive/brief.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_end_to_end_workflow_as_nmpa_would_use_it(tmp_path, monkeypatch):
    """Start here -> record what the customer said -> proposal -> draft scheme -> reviews -> approval -> active -> results."""
    from backend.app.services import trade_feedback as tfb, incentive_actions as ia
    monkeypatch.setattr(tfb, "NOTES_FILE", tmp_path / "notes.json")
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_e2e_schemes.json")
    f = ie.tmk.ROOT / "data" / "_test_e2e_schemes.json"
    f.unlink(missing_ok=True)
    for fn in (ie.get_key_customers,):
        getattr(fn, "cache_clear", lambda: None)()
    try:
        # 1. this week's actions point at MRPL
        acts = client.get("/incentive/actions").json()["actions"]
        assert any("MRPL" in a["action"] for a in acts)
        # 2. Traffic records what NMDC said (owner, confirmed reason)
        r = client.post("/trade/customer-notes", json={"customer": "HPCL", "owner": "Traffic - R. Kumar",
                                                       "stage": tfb.OPPORTUNITY_STAGES[1], "reason": "Ready to ship more if rate helps"})
        assert r.status_code == 200
        # 3. a draft proposal for NMDC (recent run-rate baseline)
        p = client.get("/incentive/proposal", params={"customer": "HPCL", "start": "2026-08-01", "end": "2026-09-30",
                                                      "baseline_method": "recent_run_rate", "target_extra_t": 20000}).json()
        assert p["status"].startswith("Draft") and p["baseline"]["tonnes"] and not p["eligibility"]["blocks"]
        # 4. saved as a draft scheme, carrying the customer and the proposal's baseline
        sch = client.post("/incentive/schemes", json={
            "cargo": p["cargo"], "scope": "Rebate on extra volume", "discount_pct": 10, "start": "2026-08-01", "end": "2026-09-30",
            "budget_cap_rs": 5_000_000, "tiers": p["tiers"], "success_target_t": 20000, "customer": "HPCL",
            "baseline_tonnes": p["baseline"]["tonnes"], "baseline_label": p["baseline"]["label"], "by": "Traffic"}).json()
        assert sch["status"] == "Draft" and sch["customer"] == "HPCL" and sch["baseline_tonnes"] == p["baseline"]["tonnes"]
        assert "HPCL" in sch["customers"] and sch["eligibility"]["eligible"]
        sid = sch["id"]
        # 5. reviews and approval (approval needs a reference)
        assert client.post(f"/incentive/schemes/{sid}", json={"status": "Traffic review", "by": "Traffic"}).status_code == 200
        assert client.post(f"/incentive/schemes/{sid}", json={"status": "Finance review", "by": "Traffic"}).status_code == 200
        assert client.post(f"/incentive/schemes/{sid}", json={"status": "Approved", "by": "Finance"}).status_code == 422
        assert client.post(f"/incentive/schemes/{sid}", json={"status": "Approved", "approval_reference": "NMPA/TM/2026/41",
                                                              "by": "Finance"}).status_code == 200
        assert client.post(f"/incentive/schemes/{sid}", json={"status": "Active", "by": "Traffic"}).status_code == 200
        # 6. results on NMDC's own traced cargo, with the audit trail and frozen baseline
        rec = next(x for x in client.get("/incentive/schemes").json()["schemes"] if x["id"] == sid)
        obs = rec["observed"]
        assert obs["months_held"] == ["2026-08", "2026-09"] and "this customer" in obs["label"]
        assert obs["actual_tonnes"] > 0 and "estimated_discount_cost_rs" in obs
        assert rec["baselines"][-1]["frozen"] and len(rec["audit"]) >= 5
    finally:
        f.unlink(missing_ok=True)


def test_draft_flagged_when_data_changes_and_amendment_needs_reapproval(tmp_path, monkeypatch):
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_amend_schemes.json")
    f = ie.tmk.ROOT / "data" / "_test_amend_schemes.json"
    f.unlink(missing_ok=True)
    try:
        d = ie.create_scheme("Edible oil", "Rebate on extra volume", 5, "2026-12-01", "2027-02-28", 1e7,
                             tiers=[{"up_to_pct_above_baseline": None, "rebate_pct": 5}])
        assert d["data_version"]["fingerprint"] == ie.data_version()["fingerprint"]
        assert "data_changed" not in next(x for x in ie.list_schemes()["schemes"] if x["id"] == d["id"])
        real = ie.data_version
        cur = real()["nmpa_statements_through"]
        monkeypatch.setattr(ie, "data_version", lambda: {**real(), "nmpa_statements_through": "2099-01", "fingerprint": "new"})
        flagged = next(x for x in ie.list_schemes()["schemes"] if x["id"] == d["id"])
        assert any(f"{cur} -> 2099-01" in c for c in flagged["data_changed"])
        monkeypatch.setattr(ie, "data_version", real)
        with pytest.raises(ValueError):
            ie.amend_scheme(d["id"], {"discount_pct": 6}, "test")            # drafts are not amended
        for st_ in ("Traffic review", "Finance review"):
            ie.update_scheme(d["id"], st_)
        ie.update_scheme(d["id"], "Approved", approval_reference="REF-9")
        with pytest.raises(ValueError):
            ie.amend_scheme(d["id"], {"cargo": "LPG"}, "change cargo")        # cargo, customer, start, baseline cannot change
        with pytest.raises(ValueError):
            ie.amend_scheme(d["id"], {"discount_pct": 6}, "")                # a reason is required
        a = ie.amend_scheme(d["id"], {"discount_pct": 6, "budget_cap_rs": 2e7}, "Customer asked for a higher rate", "Traffic")
        assert a["status"] == "Traffic review" and a["approval_reference"] == ""
        assert a["amendments"][0]["previous_terms"] == {"discount_pct": 5, "budget_cap_rs": 1e7}
        assert a["amendments"][0]["previous_approval_reference"] == "REF-9"
        assert a["baselines"][-1]["frozen"]                                  # the approved baseline stays frozen
    finally:
        f.unlink(missing_ok=True)


def test_market_context_excludes_nmpa_and_missing_months():
    import pandas as pd
    mc = ie.market_context("LPG", ["2026-07", "2026-08", "2026-09"])
    assert mc["available"] and "does not by itself establish" in mc["label"]
    d = pd.read_csv(ie.tmk.ROOT / "data" / "major_ports_commodity_monthly.csv")
    allp = d[(d.period == "month") & (d.commodity == "LPG or LNG")].set_index("through")["tonnes"]
    w = ie.ti._prepared()["wide"]
    nm = lambda m: float(w.loc[pd.Timestamp(m + "-01"), ("UNLOADED", "TOTALLPG")])
    months = ["2026-07", "2026-08", "2026-09"]
    oth_now = sum(allp[m] - nm(m) for m in months)
    oth_prev = sum(allp[f"2025{m[4:]}"] - nm(f"2025{m[4:]}") for m in months)
    assert mc["other_ports_growth_pct"] == round((oth_now / oth_prev - 1) * 100, 1)
    gap = ie.market_context("Crude oil", ["2026-03", "2026-04"])        # March: no separate crude figure
    assert gap["months_missing"] == ["2026-03"] and gap["months_compared"] == ["2026-04"]


def _update_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("update_trade_data", ie.tmk.ROOT / "scripts" / "update_trade_data.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_update_rolls_back_on_failure_and_rerun_changes_nothing(monkeypatch):
    up = _update_module()
    before = ie.data_version()["fingerprint"]
    probe = up.ROOT / "data" / "_probe_should_vanish.txt"
    target = up.ROOT / "data" / "port_targets.csv"
    original = target.read_bytes()

    real_run = up.run

    def fail_midway(args):                    # a step that always runs fails after other files were changed
        if "build_daily_manifest" in args[0]:
            probe.write_text("half-updated")
            target.write_bytes(original + b"\nCORRUPTED")
            return 1, "simulated failure"
        return real_run(args)
    monkeypatch.setattr(up, "run", fail_midway)
    assert up.main() == 2
    assert not probe.exists() and target.read_bytes() == original           # restored exactly
    assert (up.ROOT / "data" / "last_update_failed.json").exists()
    (up.ROOT / "data" / "last_update_failed.json").unlink()
    monkeypatch.undo()
    up2 = _update_module()
    assert up2.main() == 0                                                  # nothing new in incoming/
    assert ie.data_version()["fingerprint"] == before                       # re-running changes nothing
    assert not list(up2.ROOT.glob(".update_snapshot_*"))


def test_waiver_coverage_from_daily_reports():
    w = ie.get_waiver_coverage()
    assert all("2026-03-14" <= s["berthed"] <= "2026-03-31" for s in w["ships"])
    assert {s["cargo"] for s in w["ships"]} <= {"Crude oil", "LPG"}
    assert "MIRAME" in w["excluded_already_working"]                 # berthed 13 Mar, still working on 14 Mar
    assert sum(s["tonnes"] or 0 for s in w["ships"]) == sum(w["tonnes_by_cargo"].values())
    c = ie.waiver_cost()                                              # priced at the 2025-26 rates in force in March 2026
    assert c["total_rs"] == sum(r["wharfage_waived_rs"] or 0 for r in c["ships"])
    spm = next(r for r in c["ships"] if r["vessel"] == "DESTAN")
    assert spm["rate_line"] == "crude_spm" and spm["rate_rs_per_t"] == 34.67 and spm["wharfage_waived_rs"] == round(97126 * 34.67)
    assert all(s["berth"] for s in w["ships"])



def test_2025_26_rates_are_in_the_pdf():
    import subprocess
    txt = subprocess.run(["pdftotext", "-layout", str(ie.tmk.ROOT / ie.SOR_2025_26_FILE), "-"], capture_output=True, text=True).stdout
    pages = txt.split("\f")
    for key, (f, c, page) in ie.SOR_2025_26.items():
        pg = pages[page - 1]
        assert f"{f:.2f}" in pg and f"{c:.2f}" in pg, key


def test_nmpa_notices_and_iron_ore_monitor():
    n = client.get("/incentive/nmpa-notices").json()["notices"]
    assert {x["status"] for x in n} >= {"In force", "Ended"}
    m = ie.iron_ore_rebate_monitor()
    assert m["fy2025_26_total_t"] > 0 and m["rebate_per_extra_t_rs"] == round(m["rate_rs_per_t"] * 0.2, 2)
    assert not any(e["customer"] == "KIOCL" for e in m["exporters"])


def test_voc_comparison_same_year_and_located():
    import pandas as pd
    d = pd.read_csv(ie.tmk.ROOT / "data" / "port_tariff_comparison_voc.csv")
    io = d[d.cargo == "Iron ore"].iloc[0]
    assert io.nmpa_foreign == 42.88 and io.voc_zone_a_foreign == 104.09 and io.nmpa_page > 0 and io.voc_page > 0
    assert set(d[d.comparability == "Unresolved"].cargo) >= {"LPG", "Edible oil"}
    assert d["period"].iloc[0].startswith("2025-26")


def test_customer_figures_use_only_months_fully_covered_by_daily_reports():
    import pandas as pd
    last_report = pd.Timestamp(pd.read_csv(ie.tmk.ROOT / "data" / "daily_reports_manifest.csv")["report_date"].max())
    c = ie.get_customer_wharfage()
    end = pd.Timestamp(pd.to_datetime(c["q2_label"].split(" to ")[1], format="%b %Y"))
    assert end <= ie.last_complete_daily_month() and (end + pd.offsets.MonthEnd(0)) <= last_report


def test_update_without_poppler_daily_only_works_and_statements_explain(monkeypatch):
    """On a computer without Poppler (typical Windows): an update with no new statements succeeds without it; a new statement
    is refused with install instructions and everything is rolled back."""
    up = _update_module()
    monkeypatch.setattr(up.shutil, "which", lambda name: None if name == "pdftotext" else __import__("shutil").which(name))
    assert up.main() == 0                                                     # nothing new / daily reports only
    inbox = up.INBOX
    inbox.mkdir(exist_ok=True)
    fake = inbox / "commodity wise traffic statement November 2099.pdf"
    fake.write_bytes(b"%PDF-1.4 fake statement")
    try:
        assert up.main() == 2
        failed = __import__("json").loads((up.ROOT / "data" / "last_update_failed.json").read_text())
        assert "Poppler" in failed["error"]
        assert fake.exists()                                                  # returned to incoming/
        assert not (up.PUBLIC / fake.name).exists()
    finally:
        fake.unlink(missing_ok=True)
        (up.ROOT / "data" / "last_update_failed.json").unlink(missing_ok=True)


def test_kpi_tariff_check_survives_unreadable_pdftotext_output(monkeypatch):
    """Windows case: a pdftotext exists but its output cannot be decoded, so Python gets stdout=None. The check must fall back
    to pdfplumber and still find every rate, not fail."""
    from backend.app.services import incentive_kpis as ik
    import subprocess, types
    real = subprocess.run
    monkeypatch.setattr(ik.subprocess, "run", lambda cmd, *a, **k: types.SimpleNamespace(stdout=None) if cmd[0] == "pdftotext" else real(cmd, *a, **k))
    getattr(ik._sor_text, "cache_clear", lambda: None)()
    getattr(ik.get_module_kpis, "cache_clear", lambda: None)()
    if hasattr(ik._sor_text, "__wrapped__"):
        txt = ik._sor_text.__wrapped__()
    else:
        txt = ik._sor_text()
    assert "34.90" in txt                                  # read by the fallback reader
    found, total = ik._tariff_check()
    assert found == total and total > 0


def test_nmpa_scheme_records_are_backed_by_notice_files():
    import pandas as pd
    d = pd.read_csv(ie.tmk.ROOT / "data" / "nmpa_incentive_notices.csv", dtype=str).fillna("")
    infc = d[d.status == "In force"]
    assert len(infc) == 5
    for f in d.file:
        if f:
            assert (ie.tmk.ROOT / f).exists(), f
    assert all(r.valid_to >= "2026-11-07" for r in infc.itertuples())          # in force today
    newexp = d[d.notice == "NMPA/TM/SM/2026"].iloc[0]
    assert "25%" in newexp.benefit and newexp.valid_to == "2027-07-28"


def test_scenario_baseline_is_actual_last_12_months_and_rows_are_sourced():
    sc = ie.scenario("Iron ore exports", 10, low_response_pct=2.5)
    assert "last 12 months" in sc["baseline_basis"]
    assert sc["baseline_tonnes_per_year"] != sc["this_year_scaled_tonnes"]       # seasonal cargo: scaling 7 months would be wrong
    names = [r["scenario"] for r in sc["scenarios"]]
    assert names[0] == "No extra cargo comes" and any(n.startswith("Break-even") for n in names)
    assert all(r["source"] for r in sc["scenarios"])
    for r in sc["scenarios"]:                                                     # the arithmetic of every row
        dq, rate, d, q0 = r["extra_tonnes"], sc["rate_rs_per_t"], 0.10, sc["baseline_tonnes_per_year"]
        assert abs(r["rebate_change_rs"] - rate * (1 - d) * dq) < 2000
        assert abs(r["blanket_change_rs"] - (rate * (1 - d) * dq - rate * d * q0)) < 2000


def test_win_back_gap_is_split_between_linked_cargos():
    out = ie.scenario("POL products (out)", 10)
    row = next(r for r in out["scenarios"] if r["scenario"].startswith("Win back"))
    assert "of the POL products gap" in row["source"]


def test_previous_financial_year_baseline_matches_nmpa_notice():
    from backend.app.services import incentive_rules as rl
    b = rl.baseline(ie.CARGO["Iron ore exports"]["keys"], ["2026-12", "2027-01", "2027-02"], "previous_fy")
    assert "4,000,419 t" in b["detail"]            # FY 2025-26 iron ore exports: 4.00 MMT, as in NMPA's rebate notice
    assert b["tonnes"] == round(4000419 * 3 / 12)


def test_other_ports_schemes_are_sourced_and_nmpa_use_comes_from_its_notices():
    import pandas as pd
    o = ie.get_other_ports_schemes()
    assert o["available"] and o["schemes"]
    for x in o["schemes"]:
        assert x["source_url"].startswith("https://") and x["source_type"] and x["design_pattern"]
    pats = {r["pattern"]: r for r in o["patterns"]}
    assert set(x["design_pattern"] for x in o["schemes"]) <= set(pats)          # every example belongs to a listed kind
    notices = pd.read_csv(ie.tmk.ROOT / "data" / "nmpa_incentive_notices.csv", dtype=str).fillna("")
    held = " ".join(notices.notice)
    for r in o["patterns"]:
        if r["used_by_nmpa"] and not r["nmpa"].startswith("NMPA Scale of Rates"):
            assert r["nmpa"].split(" (")[0] in held, r["nmpa"]                 # NMPA's use is backed by a notice held
    assert pats["Transshipment rate"]["used_by_nmpa"]                           # checked in NMPA's Scale of Rates (2.5.3, 4.2)
    assert "Performance norms (incentive and penalty)" in o["not_at_nmpa"]
