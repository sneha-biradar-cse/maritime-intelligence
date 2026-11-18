"""Downloader logic, tested offline against a fake archive (the real site is not reachable from the test machine)."""
import csv
import importlib.util
from datetime import date

import pytest

spec = importlib.util.spec_from_file_location("dl", __import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "download_daily_reports.py")
dl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dl)


@pytest.mark.parametrize("text,expected", [
    ("Vessel Position 01-09-2025.pdf", date(2025, 9, 1)), ("01.09.2025", date(2025, 9, 1)), ("01/09/2025", date(2025, 9, 1)),
    ("dvp_01092025.pdf", date(2025, 9, 1)), ("1st September 2025", date(2025, 9, 1)), ("01 Sep 2025", date(2025, 9, 1)),
    ("2025-09-01.pdf", date(2025, 9, 1)), ("Annual report", None)])
def test_dates_in_many_formats(text, expected):
    assert dl.date_in(text) == expected


ARCHIVE_P0 = """<html><body>
<a href="/sites/default/files/2025-09/01-09-2025.pdf">Daily Vessel Position 01-09-2025 (310 KB)</a>
<a href="/sites/default/files/2025-09/dvp.pdf">Daily Vessel Position 02.09.2025</a>
<a href="/sites/default/files/2025-09/03092025.pdf">download</a>
<a href="/about-us">About us</a></body></html>"""
ARCHIVE_P1 = """<a href="/files/31-08-2025.pdf">31-08-2025</a>"""


class FakeResp:
    def __init__(self, body: bytes, status=200):
        self.content, self.text, self.status_code = body, body.decode("latin-1"), status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise dl.requests.HTTPError(str(self.status_code))


class FakeSession:
    calls: list[str] = []

    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=0):
        FakeSession.calls.append(url)
        if url == dl.LATEST:
            return FakeResp(b"<a href='/today/26-10-2026.pdf'>26-10-2026</a>")
        if url == dl.ARCHIVE:
            return FakeResp(ARCHIVE_P0.encode())
        if url.endswith("?page=1"):
            return FakeResp(ARCHIVE_P1.encode())
        if url.endswith("03092025.pdf"):
            return FakeResp(b"<html>not a pdf</html>")
        if url.endswith(".pdf"):
            return FakeResp(b"%PDF-1.4 fake")
        return FakeResp(b"", 404)


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(dl.requests, "Session", FakeSession)
    monkeypatch.setattr(dl, "INBOX", tmp_path / "incoming")
    monkeypatch.setattr(dl, "HELD", tmp_path / "held")
    monkeypatch.setattr(dl, "LOG", tmp_path / "download_log.csv")
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    (tmp_path / "held").mkdir()
    (tmp_path / "held" / "01-09-2025.pdf").write_bytes(b"%PDF old")       # already held
    FakeSession.calls = []
    return tmp_path


def log(tmp):
    return {r["date"]: r["result"] for r in csv.DictReader(open(tmp / "download_log.csv"))}


def test_dry_run_downloads_nothing(fake):
    assert dl.main(["--from", "2025-09-01", "--to", "2025-09-04", "--delay", "0", "--dry-run"]) == 0
    r = log(fake)
    assert r["2025-09-01"] == "already held" and r["2025-09-02"].startswith("found (dry run")
    assert r["2025-09-04"].startswith("not found")
    assert not (fake / "incoming").exists()


def test_downloads_only_wanted_days_and_refuses_non_pdfs(fake):
    assert dl.main(["--from", "2025-09-01", "--to", "2025-09-03", "--delay", "0"]) == 0
    r = log(fake)
    assert r["2025-09-02"].startswith("downloaded") and (fake / "incoming" / "02-09-2025.pdf").read_bytes().startswith(b"%PDF")
    assert r["2025-09-03"].startswith("failed") and "not return a PDF" in r["2025-09-03"]
    assert r["2025-09-01"] == "already held"
    assert not any("31-08-2025" in c for c in FakeSession.calls if c.endswith(".pdf"))      # outside the range: not fetched
    dl.main(["--from", "2025-09-02", "--to", "2025-09-02", "--delay", "0"])                # running again: not re-downloaded
    assert log(fake)["2025-09-02"] == "already held"


def test_excel_workbook_has_every_day_and_traceability():
    import pandas as pd
    spec2 = importlib.util.spec_from_file_location("ex", dl.ROOT / "scripts" / "export_daily_reports_excel.py") \
        if (dl.ROOT / "scripts").exists() else None
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec2 = importlib.util.spec_from_file_location("ex", root / "scripts" / "export_daily_reports_excel.py")
    ex = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(ex)
    out = ex.main()
    x = pd.ExcelFile(out)
    assert x.sheet_names == ["About", "Report days", "Berthed", "Waiting", "Expected"]
    days = pd.read_excel(x, "Report days")
    assert len(days) == len(list((root / "data" / "daily_vessel_position_parsed").glob("*.json")))
    b = pd.read_excel(x, "Berthed")
    assert {"report_date", "source_pdf", "day_check_status", "receiver_shipper"} <= set(b.columns)
    assert not b["vessel_name"].astype(str).str.startswith("-").any()          # empty berths left out


def test_certificate_options(fake, monkeypatch):
    seen = {}
    real_init = FakeSession.__init__

    def init(self):
        real_init(self)
        seen["session"] = self
    monkeypatch.setattr(FakeSession, "__init__", init)
    dl.main(["--from", "2025-09-02", "--to", "2025-09-02", "--delay", "0", "--dry-run", "--ca-bundle", "my.pem"])
    assert seen["session"].verify == "my.pem"
    dl.main(["--from", "2025-09-02", "--to", "2025-09-02", "--delay", "0", "--dry-run", "--insecure"])
    assert seen["session"].verify is False


def test_typo_dates_do_not_stop_the_crawl_and_are_reported(tmp_path, monkeypatch):
    """Like the real archive: a page of January 2026 reports containing a link dated 2025-01-05 (typo) must not stop the
    crawl; the older pages are still read."""
    pages = {
        dl.LATEST: b"",
        dl.ARCHIVE: b"".join(f"<a href='/f/{d:02d}-01-2026.pdf'>{d:02d}-01-2026</a>".encode() for d in range(10, 20))
                    + b"<a href='/f/x.pdf'>05-01-2025</a><a href='/f/y.pdf'>16-04-2502</a>",
        dl.ARCHIVE + "?page=1": b"".join(f"<a href='/f/{d:02d}-12-2025.pdf'>{d:02d}-12-2025</a>".encode() for d in range(1, 31)),
        dl.ARCHIVE + "?page=2": b"".join(f"<a href='/f/{d:02d}-10-2025.pdf'>{d:02d}-10-2025</a>".encode() for d in range(1, 31)),
    }

    class S(FakeSession):
        def get(self, url, timeout=0):
            if url in pages:
                return FakeResp(pages[url])
            return FakeResp(b"%PDF fake") if url.endswith(".pdf") else FakeResp(b"")
    monkeypatch.setattr(dl.requests, "Session", S)
    for k, v in {"INBOX": tmp_path / "in", "HELD": tmp_path / "held", "LOG": tmp_path / "log.csv", "ROOT": tmp_path}.items():
        monkeypatch.setattr(dl, k, v)
    (tmp_path / "held").mkdir()
    dl.main(["--from", "2025-12-05", "--to", "2025-12-06", "--delay", "0", "--dry-run"])
    r = {x["date"]: x["result"] for x in csv.DictReader(open(tmp_path / "log.csv"))}
    assert r["2025-12-05"].startswith("found") and r["2025-12-06"].startswith("found")       # page 1 was still read
    assert any(v.startswith("left out") for v in r.values())                                  # the typos are reported


def test_nothing_missing_is_handled(tmp_path, monkeypatch, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "daily_reports_missing_pdfs.csv").write_text("report_date,file_date,weekday,parsed_json,berthed_rows\n")
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    assert dl.main(["--dry-run"]) == 0
    assert "No missing days" in capsys.readouterr().out
