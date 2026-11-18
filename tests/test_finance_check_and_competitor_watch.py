"""Finance check (our estimates against NMPA's bills) and the competitor scheme watch."""
import datetime as dt
import importlib.util
import json
from pathlib import Path

from backend.app.services import auth
from backend.app.services import competitor_watch as cw
from backend.app.services import finance_check as fc


def test_finance_check_arithmetic(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "FILE", tmp_path / "finance_billing.csv")
    lines = ["month,cargo,charge,tonnes,amount_rs"]
    for cargo in ("LPG", "Crude oil", "Iron ore exports"):
        for m in ("2026-03", "2026-06", "2026-08"):
            e = fc.estimate(cargo, m)
            lines.append(f"{m},{cargo},wharfage,{e['tonnes']:.0f},{e['amount'] * 1.05:.0f}")
    lines.append("2026-08,LPG,port_dues,0,1000")
    assert fc.save("\n".join(lines), "test")["saved"]
    c = fc.compare()
    assert abs(c["accuracy_pct"] - 95.2) < 0.05                                 # bills 5% above -> 1 - 0.05/1.05
    for r in c["rows"]:
        assert abs(r["amount_difference_pct"] - (-4.8)) < 0.05 and abs(r["tonnes_difference_pct"]) < 0.05
    assert c["other_charges"] == [{"charge": "port_dues", "amount_rs": 1000.0}]


def test_finance_check_uses_the_rate_in_force_each_month():
    old, new = fc.estimate("Iron ore exports", "2026-03"), fc.estimate("Iron ore exports", "2026-08")
    assert old["rate_basis"] == new["rate_basis"] == "in force" and old["rate"] < new["rate"]


def test_finance_check_refuses_bad_files():
    _, problems = fc.parse("month,cargo,charge,tonnes,amount_rs\n2026-5,Diamonds,coffee,-1,abc")
    joined = " ".join(problems)
    for must in ("2026-5", "Diamonds", "coffee", "tonnes", "amount_rs"):
        assert must in joined
    assert fc.parse("a,b\n1,2")[1][0].startswith("Missing column")


def test_only_finance_can_upload_billing():
    assert auth.ACTION_ROLES["finance_upload"] == {"finance"}


def _watcher(tmp_path):
    spec = importlib.util.spec_from_file_location("w", Path("scripts/watch_competitor_notices.py"))
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    w.SOURCES, w.STORE, w.STATUS, w.PAUSE_S = tmp_path / "s.csv", tmp_path / "n.csv", tmp_path / "st.json", 0
    w.SOURCES.write_text("port,page,url\nCochin,TN,https://c.example/tn\nVOC,News,https://v.example/n\nMormugao,D,https://m.example/d\n")
    return w


COCHIN = ('<ul><li><a href="/a.pdf">Trade Notice No.09-2023- Concession in VRC for Timber Log Imports</a></li>'
          '<li><a href="/b.pdf">Trade Notice no.13 of 2021-QR Code based Access Control</a></li></ul>'
          '<nav><a href="/">Home</a><a href="/tenders">Tenders</a></nav>')
VOC = ('<table><tr><td>May-30,2025</td><td>Levy of Additional Berth Hire Charges - Concession</td><td><a href="a.pdf">View</a></td></tr>'
       '<tr><td>May-28,2025</td><td>Maximum Permissible Berthing Parameters</td><td><a href="b.pdf">View</a></td></tr></table>')


def test_competitor_watch_baseline_then_new(tmp_path):
    w = _watcher(tmp_path)
    pages = {"https://c.example/tn": COCHIN, "https://v.example/n": VOC}

    def fetch(url):
        if url not in pages:
            raise ConnectionError("not reachable")
        return pages[url]
    s1 = w.run(fetch=fetch, today=dt.date(2026, 11, 12))
    assert s1["new"] == 0 and s1["pages_failed"] == 1                            # first read = starting point
    titles = [r["title"] for r in w._load_store()]
    assert any("Timber Log" in t for t in titles) and not any("QR Code" in t or t == "Home" for t in titles)
    voc = next(r for r in w._load_store() if r["port"] == "VOC")
    assert voc["date_on_page"] == "May-30,2025" and not voc["title"].startswith("May") and not voc["title"].endswith("View")
    pages["https://v.example/n"] = VOC.replace("</table>", '<tr><td>Nov-10,2026</td><td>Rebate on vessel charges for new services</td>'
                                                          '<td><a href="c.pdf">View</a></td></tr></table>')
    s2 = w.run(fetch=fetch, today=dt.date(2026, 11, 19))
    assert s2["new"] == 1
    assert [r["title"] for r in w._load_store() if r["baseline"] == "no"] == ["Rebate on vessel charges for new services"]


def test_dashboard_reader(tmp_path, monkeypatch):
    w = _watcher(tmp_path)
    w.run(fetch=lambda u: COCHIN, today=dt.date(2026, 11, 1))
    w.run(fetch=lambda u: COCHIN.replace("</ul>", '<li><a href="/z.pdf">Waiver of port dues for coastal ships</a></li></ul>'),
          today=dt.date(2026, 11, 10))
    monkeypatch.setattr(cw, "STORE", w.STORE)
    monkeypatch.setattr(cw, "STATUS", w.STATUS)
    monkeypatch.setattr(cw, "SOURCES", w.SOURCES)
    g = cw.get_watch(today=__import__("pandas").Timestamp("2026-11-12"))
    assert g["available"] and len(g["new"]) == 3                                 # one new link on each of the three pages
    assert all(r["title"] == "Waiver of port dues for coastal ships" for r in g["new"])
    assert json.loads(w.STATUS.read_text())["last_run"] == "2026-11-10"


def test_competitor_watch_two_pages_linking_the_same_notice(tmp_path):
    """Two pages of one port can link the same notice; the second page must still report its own new notices later."""
    w = _watcher(tmp_path)
    w.SOURCES.write_text("port,page,url\nCochin,TN,https://c.example/tn\nCochin,Tariff,https://c.example/tariff\n")
    same = '<ul><li><a href="/a.pdf">Concession in VRC for timber log imports</a></li></ul>'
    w.run(fetch=lambda u: same, today=dt.date(2026, 11, 12))
    pages = {"https://c.example/tn": same,
             "https://c.example/tariff": same.replace("</ul>", '<li><a href="/t.pdf">Revised tariff for cruise ships</a></li></ul>')}
    s2 = w.run(fetch=lambda u: pages[u], today=dt.date(2026, 11, 19))
    tariff_page = next(p for p in s2["pages"] if p["page"] == "Tariff")
    assert not tariff_page["first_read"] and tariff_page["new"] == 1
