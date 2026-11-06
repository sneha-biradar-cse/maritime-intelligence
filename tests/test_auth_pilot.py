"""Pilot mode: logins and roles are checked by the backend on every action that changes data."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import auth, incentive_engine as ie, trade_feedback as tfb

client = TestClient(app)


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(tfb, "NOTES_FILE", tmp_path / "notes.json")
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_pilot_schemes.json")
    f = ie.tmk.ROOT / "data" / "_test_pilot_schemes.json"
    f.unlink(missing_ok=True)
    for u, n, r in [("ravi", "R. Kumar", "traffic"), ("fin", "S. Rao", "finance"), ("boss", "A. Menon", "approver"),
                    ("md", "Viewer One", "viewer")]:
        auth.add_user(u, n, r, "correct-horse-1")
    tok = {u: client.post("/auth/login", json={"username": u, "password": "correct-horse-1"}).json()["token"]
           for u in ("ravi", "fin", "boss", "md")}
    yield {u: {"Authorization": f"Bearer {t}"} for u, t in tok.items()}
    f.unlink(missing_ok=True)


def test_demo_mode_without_users(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "none.json")
    m = client.get("/auth/mode").json()
    assert m["pilot_mode"] is False and "not attributable" in m["note"]


def test_passwords_are_hashed_and_wrong_password_refused(pilot):
    stored = json.loads(auth.USERS_FILE.read_text())
    assert "correct-horse-1" not in json.dumps(stored) and len(stored["ravi"]["hash"]) == 64
    assert client.post("/auth/login", json={"username": "ravi", "password": "wrong-password"}).status_code == 401
    with pytest.raises(ValueError):
        auth.add_user("x", "X", "traffic", "short")


def test_actions_need_login_and_the_right_role(pilot):
    body = {"cargo": "Edible oil", "scope": "Rebate on extra volume", "discount_pct": 5, "start": "2026-12-01",
            "end": "2027-02-28", "budget_cap_rs": 1e7, "tiers": [{"up_to_pct_above_baseline": None, "rebate_pct": 5}]}
    assert client.post("/incentive/schemes", json=body).status_code == 401                       # not logged in
    assert client.post("/incentive/schemes", json=body, headers=pilot["md"]).status_code == 403   # viewer
    assert client.post("/incentive/schemes", json=body, headers=pilot["fin"]).status_code == 403  # finance cannot create
    sch = client.post("/incentive/schemes", json=body, headers=pilot["ravi"]).json()
    sid = sch["id"]
    assert sch["audit"][0]["by"] == "R. Kumar (traffic)"                                         # the logged-in person
    go = lambda who, st, ref=None: client.post(f"/incentive/schemes/{sid}", headers=pilot[who],
                                                 json={"status": st, "approval_reference": ref, "by": "someone else"})
    assert go("ravi", "Traffic review").status_code == 200
    assert go("ravi", "Finance review").status_code == 200
    assert go("ravi", "Approved", "REF-1").status_code == 403                                     # traffic cannot approve
    assert go("fin", "Approved", "REF-1").status_code == 403                                      # nor finance
    ok = go("boss", "Approved", "REF-1")
    assert ok.status_code == 200
    rec = ok.json()
    assert rec["audit"][-1]["by"] == "A. Menon (approver)"                                        # typed name ignored
    assert go("boss", "Active").status_code == 403                                                # activation is Traffic's
    assert go("ravi", "Active").status_code == 200
    am = client.post(f"/incentive/schemes/{sid}/amend", headers=pilot["fin"], json={"changes": {"discount_pct": 6}, "reason": "x"})
    assert am.status_code == 403


def test_customer_notes_and_feedback_roles(pilot):
    assert client.post("/trade/customer-notes", json={"customer": "MRPL", "owner": "x"}).status_code == 401
    assert client.post("/trade/customer-notes", json={"customer": "MRPL", "owner": "x"}, headers=pilot["md"]).status_code == 403
    r = client.post("/trade/customer-notes", json={"customer": "MRPL", "owner": "R. Kumar", "note": "Called"}, headers=pilot["ravi"])
    assert r.status_code == 200
    assert client.get("/auth/me", headers=pilot["ravi"]).json()["user"]["role"] == "traffic"
    client.post("/auth/logout", headers=pilot["ravi"])
    assert client.get("/auth/me", headers=pilot["ravi"]).status_code == 401                       # token gone after logout
