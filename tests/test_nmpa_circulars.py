"""NMPA circulars: sorting, duplicates, and automatic reading only after NMPA's permission."""
import importlib.util
from pathlib import Path

import pytest

from backend.app.services import nmpa_circulars as nc

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(nc, "_p", lambda name: tmp_path / Path(name).name)
    return tmp_path


def test_real_titles_are_sorted():
    cases = {"Revision of Discount offered on Port Dues under 'Harit Shrey' Environmental Ship Index (ESI)": "Incentive or concession",
             "Indexed SOR w.e.f 01.05.2026 (0.65%)": "Tariff or charges",
             "Weather Advisory-II dated 16.07.24: Local Cautionary Signal Number Three (LC-III) hoisted": "Weather and safety",
             "Guidelines for priority berthing of fertiliser vessels": "Rules and procedures",
             "Commodity wise traffic Statement - May 2026": "Traffic and statistics",
             "Tender for allotment of land on lease - Plot A": "Tenders and land"}
    for t, c in cases.items():
        assert nc.classify(t)["category"] == c, t


def test_add_duplicates_and_done(tmp_store):
    r = nc.add("Indexed SOR w.e.f 01.05.2026 (0.65%)", "2026-05-01", "https://example.org/sor.pdf", "A")
    assert r["affects"] == "Tariff calculator" and r["status"] == "Open"
    with pytest.raises(ValueError, match="Already listed"):
        nc.add("Another title for the same file", "", "https://example.org/sor.pdf", "A")
    with pytest.raises(ValueError):
        nc.add("SOR", "", "", "A")                                         # too vague to be a circular title
    assert nc.mark_done(r["id"], "B", "checked the tariff version")["status"] == "Done"
    assert nc.get_circulars()["open"] == 0


def test_reader_waits_for_permission(tmp_store):
    spec = importlib.util.spec_from_file_location("w", ROOT / "scripts" / "watch_nmpa_circulars.py")
    w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
    called = []
    out = w.run(fetch=lambda u: called.append(u) or "", pause=0)
    assert out["read"] is False and called == []                          # no request at all without permission
    with pytest.raises(ValueError):
        nc.record_permission(True, "Approver", "")                         # a reference is required
    nc.record_permission(True, "Approver", "Email of 20 Nov 2026 from the Traffic Manager")
    page = ('<ul><li><a href="/sites/default/files/a.pdf">Revision of discount on port dues for green ships</a></li>'
            '<li><a href="/home">Home</a></li></ul>')
    first = w.run(fetch=lambda u: page, pause=0)
    assert first["read"] and first["first"] and nc.get_circulars()["open"] == 0          # starting point, marked done
    assert not any(r["title"] == "Home" for r in nc.get_circulars()["rows"])              # menu links are not circulars
    page2 = page.replace("</ul>", '<li><a href="/sites/default/files/b.pdf">Procedure for berthing of LPG vessels</a></li></ul>')
    w.run(fetch=lambda u: page2, pause=0)
    open_ = [r for r in nc.get_circulars()["rows"] if r["status"] == "Open"]
    assert [r["category"] for r in open_] == ["Rules and procedures"]                     # only the new one is open
