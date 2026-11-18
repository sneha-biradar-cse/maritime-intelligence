"""Customer name review: decisions change nothing until applied; applying uses only confirmed decisions; backup kept."""
import shutil

import pytest

from backend.app.services import customer_names as cn
from backend.app.services import trade_customers as tcu


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    alias = tmp_path / "customer_aliases.csv"
    shutil.copy2(tcu.ALIAS_FILE, alias)
    monkeypatch.setattr(tcu, "ALIAS_FILE", alias)
    monkeypatch.setattr(cn, "_dec_path", lambda: tmp_path / "decisions.json")
    tcu.build.cache_clear()
    yield alias
    tcu.build.cache_clear()


def test_list_is_sorted_and_has_no_false_letter_match(sandbox):
    r = cn.review_list()
    t = [it["evidence"].get("tonnes_12m", 0) + it["evidence"].get("other", {}).get("tonnes_12m", 0) for it in r["items"]]
    assert t == sorted(t, reverse=True)                                   # biggest cargo first
    cands = [set(it["names"]) for it in r["items"] if it["kind"] == "candidate"]
    assert {"IOCL", "KIOCL"} not in cands and {"ERM", "E. RAMAMURTHY MINERALS"} in cands


def test_decisions_change_nothing_until_applied(sandbox):
    before = sandbox.read_text()
    it = next(i for i in cn.review_list()["items"] if i["kind"] == "candidate" and "ERM" in i["names"])
    cn.decide(it["id"], "same", "A (traffic)", keep_name="E. RAMAMURTHY MINERALS")
    assert sandbox.read_text() == before                                  # recording a decision changes no figure
    with pytest.raises(ValueError):
        cn.decide(it["id"], "maybe", "A")
    res = cn.apply("A (traffic)")
    assert res["applied"] == 1 and res["names_merged"] == 1
    assert "ERM,E. RAMAMURTHY MINERALS,Confirmed by A (traffic)" in sandbox.read_text()
    assert list(sandbox.parent.glob("customer_aliases.backup-*.csv"))     # backup kept
    assert cn.apply("A")["applied"] == 0                                   # nothing applied twice


def test_spelling_marked_different_is_unmerged(sandbox):
    sp = next(i for i in cn.review_list()["items"] if i["kind"] == "spelling")
    cust, variants = sp["names"][0], sp["names"][1:]
    cn.decide(sp["id"], "different", "A (traffic)")
    cn.decide(next(i for i in cn.review_list()["items"] if i["kind"] == "identity")["id"], "not_sure", "A")
    res = cn.apply("A (traffic)")
    assert res["applied"] == 1 and res["spellings_unmerged"] >= 1           # 'not sure' is never applied
    rows = [ln.split(",") for ln in sandbox.read_text().splitlines() if not ln.startswith("#")]
    assert not any(r[1].strip() == cust and tcu._key(r[0]) in {tcu._key(v) for v in variants} for r in rows if len(r) > 1)
