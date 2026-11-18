"""Every NMPA scheme judged so far, and the customer-readiness condition."""
import pandas as pd

from backend.app.services import incentive_scheme_review as sr


def test_simple_check_other_ports_are_all_ports_minus_new_mangalore():
    for g, d in sr._monthly_by_group().items():
        if len(d):
            assert ((d["all_ports"] - d["nmpa"] - d["others"]).abs() < 1).all(), g


def test_simple_check_arithmetic():
    e = sr.simple_compare("Coal", "2026-01", "2026-09")
    assert e["available"]
    d = sr._monthly_by_group()["Coal"]
    n_c, n_p = d.loc[e["months"], "nmpa"].sum(), d.loc[e["compared_with"], "nmpa"].sum()
    o_c, o_p = d.loc[e["months"], "others"].sum(), d.loc[e["compared_with"], "others"].sum()
    assert abs(e["nmpa_growth_pct"] - (n_c / n_p - 1) * 100) < 0.06
    assert abs(e["others_growth_pct"] - (o_c / o_p - 1) * 100) < 0.06
    assert abs(e["effect_points"] - (e["nmpa_growth_pct"] - e["others_growth_pct"])) < 0.06


def test_review_uses_the_right_check_and_never_guesses():
    rows = {r["short"]: r for r in sr.get_scheme_review()["rows"]}
    assert rows["Fertiliser priority berthing"]["check"] == "Full check"
    assert rows["Crude & LPG waiver, Mar 2026"]["check"] == "Full check"
    assert rows["Cape-size rebate, Berth 16 (coal)"]["check"] == "Simple check"
    assert rows["Middle East container waiver"]["check"] == "Simple check"
    assert rows["New export cargo concession"]["result"] == "Cannot be measured"
    assert rows["Harit green cargo concession"]["result"] == "Cannot be measured"
    assert "Crude & LPG waiver (LPG)" not in rows          # one row: the Ministry groups them together in March
    assert sr.simple_compare("Coal", "2099-01", "2099-03")["status"] == "Too early"


def test_readiness_condition_is_consistent():
    strict = sr.readiness_condition(months=6, max_wait_days=0.0)
    loose = sr.readiness_condition(months=6, max_wait_days=10.0)
    every = sr.readiness_condition(months=6, max_wait_days=10_000.0)
    assert strict["available"] and strict["calls"] == loose["calls"] == every["calls"]
    assert strict["qualifying_calls"] <= loose["qualifying_calls"] <= every["qualifying_calls"] == every["calls"]
    by = pd.DataFrame(strict["by_customer"])
    assert (by["qualifying"] <= by["calls"]).all()
