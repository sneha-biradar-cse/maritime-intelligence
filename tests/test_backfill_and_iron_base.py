"""Back-fill of older daily reports (direct mode) and the iron ore base built from whatever months are held."""
import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dl", ROOT / "scripts" / "download_daily_reports.py")
dl = importlib.util.module_from_spec(spec); spec.loader.exec_module(dl)


class R:
    def __init__(self, status, content): self.status_code, self.content = status, content


def test_direct_fetch_pdf_variants_and_refusals():
    site = {"10-04-2025.pdf": R(200, b"%PDF-1.4 ..."), "10-03-2025_0.pdf": R(200, b"%PDF-1.7 ..."),
            "11-04-2025.pdf": R(200, b"<html>Page not found</html>")}
    get = lambda url: site.get(url.rsplit("/", 1)[-1], R(404, b""))
    url, got = dl.direct_fetch(get, date(2025, 4, 10))
    assert url.endswith("/dailyvessel/10-04-2025.pdf") and got.startswith(b"%PDF")
    url, got = dl.direct_fetch(get, date(2025, 3, 10))
    assert url.endswith("10-03-2025_0.pdf")                                       # the _0 variant NMPA sometimes uses
    url, why = dl.direct_fetch(get, date(2025, 4, 11))
    assert url is None and "not on the site" in why                               # an HTML error page is never saved as a report
    url, why = dl.direct_fetch(lambda u: (_ for _ in ()).throw(OSError("network down")), date(2025, 4, 12))
    assert url is None and why.startswith("failed")


def test_iron_ore_base_reports_its_months():
    from backend.app.services import incentive_engine as ie
    m = ie.iron_ore_rebate_monitor()
    assert 0 < m["base_months_held"] <= 12 and m["base_complete"] == (m["base_months_held"] == 12)
    assert all(e["fy2025_26_base_t"] == e["sep2025_mar2026_t"] for e in m["exporters"])    # old field kept for compatibility
    if not m["base_complete"]:
        assert "back-fill" in " ".join(m["limits"]).lower()
