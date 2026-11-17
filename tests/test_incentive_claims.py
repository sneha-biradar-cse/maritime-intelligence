"""Rebate claims: lifecycle, no double claims, amounts only go down, separation of duties, budget limit."""
import json

import pytest

from backend.app.services import auth
from backend.app.services import incentive_claims as icl
from backend.app.services import incentive_engine as ie

IRON = "NMPA/TM/IOF-Exp-Rebate/26-27"


@pytest.fixture
def tmp_claims(monkeypatch, tmp_path):
    monkeypatch.setattr(icl, "CLAIMS_FILE", str(tmp_path / "claims.json"))
    monkeypatch.setattr(icl, "_path", lambda: tmp_path / "claims.json")
    return tmp_path


def test_full_journey_to_paid(tmp_claims):
    assert any(s["ref"] == IRON for s in icl.schemes_for_claims())
    c = icl.submit(IRON, "KIOCL", "2026-09-23", "2027-03-31", 100000, 863000, "A (traffic)")
    icl.move(c["id"], "Verified", "B (finance)", amount_rs=800000, tonnes=92700)
    icl.move(c["id"], "Approved", "C (approver)", pilot=True)
    p = icl.move(c["id"], "Paid", "D (finance)", payment_ref="CN-2027-014")
    assert p["status"] == "Paid" and p["paid_rs"] == p["approved_rs"] == 800000
    assert [h["status"] for h in p["history"]] == ["Submitted", "Verified", "Approved", "Paid"]
    g = icl.get_claims()
    assert g["count"]["Paid"] == 1 and g["by_scheme"][0]["paid_rs"] == 800000


def test_no_double_claims(tmp_claims):
    c = icl.submit(IRON, "KIOCL", "2026-10-01", "2026-12-31", 1, 1000, "A")
    with pytest.raises(ValueError, match="Already claimed"):
        icl.submit(IRON, "kiocl", "2026-12-01", "2027-01-31", 1, 1000, "A")           # overlapping, any case
    icl.move(c["id"], "Rejected", "B", note="Wrong period")
    assert icl.submit(IRON, "KIOCL", "2026-12-01", "2027-01-31", 1, 1000, "A")["status"] == "Submitted"


def test_amounts_and_steps(tmp_claims):
    c = icl.submit(IRON, "VEDANTA", "2026-10-01", "2026-12-31", 10, 1000, "A")
    with pytest.raises(ValueError, match="more than the amount claimed"):
        icl.move(c["id"], "Verified", "B", amount_rs=1200, tonnes=10)
    with pytest.raises(ValueError, match="cannot go to Paid"):
        icl.move(c["id"], "Paid", "B", payment_ref="x")
    icl.move(c["id"], "Verified", "B", amount_rs=900, tonnes=9)
    with pytest.raises(ValueError, match="more than the verified"):
        icl.move(c["id"], "Approved", "C", amount_rs=950)
    icl.move(c["id"], "Approved", "C", amount_rs=900)
    with pytest.raises(ValueError, match="reference"):
        icl.move(c["id"], "Paid", "D", payment_ref=" ")
    with pytest.raises(ValueError, match="reason"):
        icl.move(c["id"], "Rejected", "D", note="")


def test_separation_of_duties(tmp_claims):
    c = icl.submit(IRON, "JSW", "2026-10-01", "2026-12-31", 10, 1000, "A (traffic)")
    with pytest.raises(PermissionError):
        icl.move(c["id"], "Verified", "A (traffic)", amount_rs=1000, tonnes=10, pilot=True)
    icl.move(c["id"], "Verified", "B (traffic)", amount_rs=1000, tonnes=10, pilot=True)
    with pytest.raises(PermissionError):
        icl.move(c["id"], "Approved", "B (traffic)", pilot=True)
    assert icl.move(c["id"], "Approved", "C (approver)", pilot=True)["status"] == "Approved"
    assert auth.ACTION_ROLES["claim_approve"] == {"approver"} and auth.ACTION_ROLES["claim_pay"] == {"finance"}


def test_budget_limit_for_register_schemes(tmp_claims, monkeypatch):
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_claims_schemes.json")
    try:
        rec = ie.create_scheme("LPG", "Rebate on extra volume", 10.0, "2027-01-01", "2027-03-31", 1_000_000, by="t")
        rows = ie._load_schemes(); rows[0]["status"] = "Approved"; ie._save_schemes(rows)
        a = icl.submit(rec["id"], "IOCL", "2027-01-01", "2027-03-31", 10, 700_000, "A")
        b = icl.submit(rec["id"], "HPCL", "2027-01-01", "2027-03-31", 10, 600_000, "A")
        for x in (a, b):
            icl.move(x["id"], "Verified", "B", amount_rs=x["claimed_rs"], tonnes=10)
        icl.move(a["id"], "Approved", "C")
        with pytest.raises(ValueError, match="over its budget"):
            icl.move(b["id"], "Approved", "C")                                       # 7 + 6 lakh > 10 lakh budget
        assert icl.move(b["id"], "Approved", "C", amount_rs=300_000)["approved_rs"] == 300_000
    finally:
        ie._schemes_path().unlink(missing_ok=True)


def test_claims_allowed_under_a_recently_ended_scheme(tmp_claims):
    refs = {s["ref"]: s for s in icl.schemes_for_claims()}
    assert "Comrc/DTM(C)/2026-27/01" in refs                                    # in force
    assert "1/2/2014-DTM (C)/2023-4" in refs and "ended" in refs["1/2/2014-DTM (C)/2023-4"]["name"]   # superseded 02.11.2026
    assert "NMPT/TM/Cont/2021" not in refs                                      # ended in 2022: too old to claim
