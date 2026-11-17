"""Monthly settlement list: calls from the daily reports, container and Cape-size rules, no guessing without GRT."""
from backend.app.services import incentive_settlement as st


def test_calls_are_unique_and_dated():
    calls = st.calls_from_reports()
    keys = [(c["vessel"], c["berth"], c["berthed"]) for c in calls]
    assert len(keys) == len(set(keys)) and len(calls) > 1000
    assert all(c["berthed"] <= c["last_report"] and c["hours_approx"] >= 24 for c in calls)


def test_container_rebate_follows_the_notice_in_force_on_each_date():
    oct_ = st.settlement_list("2026-10")                                      # 25% rebate (notice 2023-4) applied before 3 Nov 2026
    assert oct_["container"]["calls"] and all(x["notice"] == "1/2/2014-DTM (C)/2023-4" for x in oct_["container"]["calls"])
    for x in st.settlement_list("2026-11")["container"]["calls"]:
        assert x["notice"] == ("Comrc/DTM(C)/2026-27/01" if x["berthed"] >= "2026-11-03" else "1/2/2014-DTM (C)/2023-4")
    assert st.container_period("2025-06-30")["notice"] == "1/2/2014-DTM (C)/2023-3" and st.container_period("2023-12-31") is None
    nov = st.settlement_list("2026-11")
    names = {x["vessel"] for x in nov["container"]["calls"]}
    assert "SM KAVERI" in names
    for x in nov["container"]["calls"]:
        assert x["berth"].startswith("14")                                  # calls on 1-2 Nov fall under the earlier notice
        assert x["rebate_low_rs"] is None or x["rebate_low_rs"] <= x["rebate_high_rs"]


def test_capesize_rule(monkeypatch):
    base = {"port_dues_rs": 1_000_000, "pilotage_rs": 500_000, "berth_hire_rs": 300_000}
    monkeypatch.setattr(st, "_price", lambda c, kind: {**base, "grt": 95_000} if c["vessel"] == "BIG" else
                        ({**base, "grt": 40_000} if c["vessel"] == "SMALL" else None))
    monkeypatch.setattr(st, "calls_from_reports", lambda: [
        {"vessel": v, "berth": "16", "berthed": "2026-10-10", "last_report": "2026-10-12", "run": "F", "cargo": "COAL",
         "receiver_shipper": "", "loa": "", "hours_approx": 72, "month": "2026-10", "first_report": "2026-10-10"}
        for v in ("BIG", "SMALL", "UNKNOWN")])
    rows = {x["vessel"]: x for x in st.settlement_list("2026-10")["capesize"]["calls"]}
    assert rows["BIG"]["status"] == "Eligible" and rows["BIG"]["rebate_rs"] == 450_000      # 30% of (10 + 5) lakh
    assert rows["SMALL"]["status"].startswith("Not eligible") and rows["SMALL"]["rebate_rs"] == 0
    assert rows["UNKNOWN"]["status"].startswith("Check the GRT on the bill") and rows["UNKNOWN"]["rebate_rs"] is None


def test_calls_carry_the_agent_for_ship_charge_claims():
    nov = st.settlement_list("2026-11")
    assert nov["container"]["calls"] and all("agent" in x for x in nov["container"]["calls"])
    assert any(x["agent"] for x in nov["container"]["calls"])                  # the claimant for a ship-charge rebate
