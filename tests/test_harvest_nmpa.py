"""NMPA document harvester, tested offline against a fake site (NMPA's site is not reachable from the test machine)."""
import csv
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hv", ROOT / "scripts" / "harvest_nmpa_documents.py")
hv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hv)

SITE = {
    "statistics": b"""<a href="/sites/default/files/2026-11/Commodity%20wise%20traffic%20statement%20Nov%202026.pdf">Commodity wise traffic statement November 2026</a>
                      <a href="/sites/default/files/2026-11/stmt2.pdf">Container Traffic Statement II - November 2026</a>
                      <a href="/statistics?page=1">next</a>""",
    "statistics?page=1": b"""<a href="/sites/default/files/2026-11/perf.pdf">Operational performance November 2026</a>""",
    "circular-tradenotice": b"""<a href="/files/rebate.pdf">Trade Notice - Rebate of 25% on wharfage for coastal cement</a>
                                <a href="/files/anpr.pdf">Trade Circular - HSRP number plates</a>""",
    "port-tariff": b"""<a href="/files/Draft%20SOR.pdf">Draft SOR 2027</a><a href="/files/held.pdf">Scale of Rates 2026</a>""",
}


class Resp:
    def __init__(self, body, status=200):
        self.content, self.text, self.status_code = body, body.decode("latin-1"), status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise hv.requests.HTTPError(str(self.status_code))


class Session:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=0):
        path = url.replace(hv.BASE + "/", "")
        if path in SITE:
            return Resp(SITE[path])
        if url.endswith(".pdf"):
            return Resp(b"%PDF-1.4 " + url.encode())
        return Resp(b"", 404)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(hv.requests, "Session", Session)
    for k, v in {"ROOT": tmp_path, "INBOX": tmp_path / "incoming", "OUT": tmp_path / "nmpa_public_data" / "harvested",
                 "CATALOG": tmp_path / "data" / "harvest_catalog.csv"}.items():
        monkeypatch.setattr(hv, k, v)
    (tmp_path / "nmpa_public_data").mkdir(parents=True)
    (tmp_path / "nmpa_public_data" / "held.pdf").write_bytes(b"%PDF old")
    return tmp_path


def rows(tmp):
    return {r["title"]: r for r in csv.DictReader(open(tmp / "data" / "harvest_catalog.csv", encoding="utf-8"))}


def test_dry_run_lists_and_classifies_without_downloading(site):
    hv.main(["--dry-run", "--pages", "statistics", "circular-tradenotice", "port-tariff", "--delay", "0"])
    r = rows(site)
    assert r["Commodity wise traffic statement November 2026"]["destination"] == "incoming"
    assert r["Container Traffic Statement II - November 2026"]["category"] == "NMPA container traffic statement"
    assert r["Operational performance November 2026"]["category"] == "NMPA Traffic & Performance report"   # page 2 was read
    assert "review" in r["Trade Notice - Rebate of 25% on wharfage for coastal cement"]["flag"]
    assert r["Trade Circular - HSRP number plates"]["flag"] == ""
    assert "not in force" in r["Draft SOR 2027"]["category"]
    assert r["Scale of Rates 2026"]["result"].startswith("already held")
    assert not (site / "incoming").exists()


def test_downloads_statements_to_incoming_and_notices_for_review(site):
    hv.main(["--pages", "statistics", "circular-tradenotice", "--delay", "0"])
    inbox = sorted(p.name for p in (site / "incoming").glob("*.pdf"))
    assert any(n.startswith("commodity wise traffic statement") or "Commodity" in n for n in inbox)
    assert any(n.lower().startswith("container traffic statement") for n in inbox)            # keyword added for the update
    assert any(n.lower().startswith("operational performance") for n in inbox)
    notices = list((site / "nmpa_public_data" / "harvested").rglob("*.pdf"))
    assert len(notices) == 2 and all(p.read_bytes().startswith(b"%PDF") for p in notices)
    hv.main(["--pages", "circular-tradenotice", "--delay", "0"])                              # second run: nothing new
    assert all(r["result"].startswith("already held") for r in rows(site).values())


MIN_TABLE = """<table><tr><th>Sr. No.</th><th>Description</th><th>Month</th><th>Year</th><th>Download</th></tr>
<tr><td>1</td><td>Monthly Cargo Traffic handled at Non Major Ports during October 2026</td><td>Oct</td><td>2026</td>
<td><a href="https://shipmin.gov.in/sites/default/files/Cargo%20handled%20at%20Non-Major%20Ports%20Oct%202026.pdf">Download(2.35 MB)</a></td></tr>
<tr><td>2</td><td>Monthly Cargo Traffic handled at Major Ports during October 2026</td><td>Oct</td><td>2026</td>
<td><a href="https://shipmin.gov.in/sites/default/files/Report%20Oct%202026.pdf">Download(1.4 MB)</a></td></tr>
<tr><td>3</td><td>Monthly Cargo Traffic handled at Major Ports during September 2026</td><td>Sep</td><td>2026</td>
<td><a href="https://shipmin.gov.in/sites/default/files/Cargo%20handled%20at%20Major%20Ports%20Sep%202026.pdf">Download(1.4 MB)</a></td></tr>
</table><a href="/en/publication/trw-publication?qt-trw_publication=0&amp;page=1">next</a>"""


def test_ministry_reports(site, monkeypatch):
    (site / "data").mkdir(exist_ok=True)
    (site / "data" / "major_ports_monthly.csv").write_text("month,port,total_t\n2026-09,New Mangalore,1\n")
    SITE_M = {hv.MINISTRY: MIN_TABLE.encode(), "https://shipmin.gov.in/en/publication/trw-publication?qt-trw_publication=0&page=1":
              b"<table><tr><td>1</td><td>Monthly Cargo handled at Major Ports Jan 2024</td><td>Jan</td><td>2024</td>"
              b"<td><a href='/sites/default/files/old.pdf'>Download</a></td></tr></table>"}

    class S(Session):
        def get(self, url, timeout=0):
            if url in SITE_M:
                return Resp(SITE_M[url])
            return super().get(url, timeout)
    monkeypatch.setattr(hv.requests, "Session", S)
    hv.main(["--source", "ministry", "--delay", "0"])
    r = rows(site)
    oct_major = r["Monthly Cargo Traffic handled at Major Ports during October 2026"]
    assert oct_major["month"] == "2026-10" and oct_major["result"] == "downloaded to incoming"
    assert r["Monthly Cargo Traffic handled at Major Ports during September 2026"]["result"].startswith("already held")
    assert r["Monthly Cargo Traffic handled at Non Major Ports during October 2026"]["category"].startswith("Ministry: Non-Major")
    got = [p.name for p in (site / "incoming").glob("*.pdf")]
    assert len(got) == 1 and "major port" in got[0].lower() and "non" not in got[0].lower()   # the update will read it as Ministry


def test_only_statements_newer_than_data_held_and_no_other_documents(site, monkeypatch):
    (site / "data").mkdir(exist_ok=True)
    (site / "data" / "nmpa_container_commodities.csv").write_text("month,direction,commodity\n2026-09,in,x\n")
    (site / "data" / "nmpa_performance_monthly.csv").write_text("report_month,month\n2026-09,x\n")
    (site / "data" / "port_cargo_monthly.csv").write_text("month,year\nOctober,2026\n")
    SITE2 = {"statistics": b"""<a href="/f/c1.pdf">Container Traffic Statement September 2026</a>
                               <a href="/f/c2.pdf">Container Traffic Statement October 2026</a>
                               <a href="/f/c3.pdf">Container Traffic Statement 2019</a>
                               <a href="/f/p1.pdf">Operational performance October 2026</a>
                               <a href="/f/k1.pdf">Commodity wise traffic statement October 2026</a>""",
             "downloads": b"""<a href="/f/form.pdf">Application form for gate pass</a>"""}

    class S(Session):
        def get(self, url, timeout=0):
            path = url.replace(hv.BASE + "/", "")
            return Resp(SITE2[path]) if path in SITE2 else super().get(url, timeout)
    monkeypatch.setattr(hv.requests, "Session", S)
    hv.main(["--source", "nmpa", "--pages", "statistics", "downloads", "--delay", "0"])
    r = rows(site)
    arch = "nmpa_public_data/harvested/older_statements"
    assert arch in r["Container Traffic Statement September 2026"]["result"].replace("\\", "/")   # older: archived, not updated
    assert r["Container Traffic Statement October 2026"]["result"] == "downloaded to incoming"
    unclear = r["Container Traffic Statement 2019"]                                               # month not in the title
    assert arch in unclear["result"].replace("\\", "/") and "not found inside the PDF" in unclear["result"]  # never guessed
    assert r["Operational performance October 2026"]["result"] == "downloaded to incoming"
    assert arch in r["Commodity wise traffic statement October 2026"]["result"].replace("\\", "/")
    assert r["Application form for gate pass"]["result"].startswith("listed only")           # 'Other': never downloaded
    assert len(list((site / "incoming").glob("*.pdf"))) == 2                                 # only the two newer statements



def test_month_read_from_inside_a_real_statement():
    pdf = next(p for p in (ROOT / "nmpa_public_data").rglob("*.pdf") if "container traffic for the month of April" in p.name)
    assert hv.month_from_pdf(pdf.read_bytes()) == "2026-04"


def test_project_poppler_is_found_without_system_changes(tmp_path, monkeypatch):
    spec2 = importlib.util.spec_from_file_location("pp", ROOT / "scripts" / "_poppler.py")
    pp = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(pp)
    bin_ = tmp_path / "poppler-26.09.0" / "Library" / "bin"
    bin_.mkdir(parents=True)
    (bin_ / "pdftotext.exe").write_bytes(b"MZ")
    monkeypatch.setattr(pp, "TOOLS", tmp_path)
    monkeypatch.setenv("PATH", "/nowhere")
    calls = []
    monkeypatch.setattr(pp.shutil, "which", lambda n: (calls.append(n), str(bin_ / "pdftotext.exe") if str(bin_) in pp.os.environ["PATH"] else None)[1])
    assert pp.ensure_on_path() is True and str(bin_) in pp.os.environ["PATH"]          # this process only; nothing installed


def test_poppler_installer_pins_version_and_fingerprint():
    src = (ROOT / "scripts" / "setup_poppler.py").read_text(encoding="utf-8")
    assert 'SHA256 = "7a6f256a0ddf7536182246a5733331bf4677cbcc34f4663774947ad34556c8d0"' in src and "REFUSED" in src
