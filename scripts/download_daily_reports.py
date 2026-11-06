"""
Download NMPA "Daily Vessel Position" PDFs from NMPA's public archive into incoming/, ready for the monthly update.

Use only with NMPA's permission for automated download (the site's robots.txt otherwise asks programs not to crawl it).
It is deliberately polite: one request at a time, a pause between requests (default 3 s), a clear User-Agent, and it downloads
ONLY the dates asked for (by default the days listed in data/daily_reports_missing_pdfs.csv), never re-downloading a file.

Usage (PowerShell, from the project folder, venv active):
  python scripts\\download_daily_reports.py --dry-run                 list what it finds on the archive pages, download nothing
  python scripts\\download_daily_reports.py                           download the missing days (data/daily_reports_missing_pdfs.csv)
  python scripts\\download_daily_reports.py --from 2026-10-27 --to 2026-11-30   download a date range
  python scripts\\download_daily_reports.py --max-pages 60 --delay 5  settings

Then:  python scripts\\update_trade_data.py   (reads each PDF, checks it against the record already held, and refreshes everything)

Every run writes data/download_log.csv: each date wanted, the link found, and what happened (downloaded / already held /
not found on the archive / failed and why). Nothing is assumed: a date that is not on the archive is reported, not invented.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

try:   # use the computer's own certificate store (Windows / macOS), like a web browser does; fixes "unable to get local issuer
    import truststore   # certificate" when a site does not send its full certificate chain
    truststore.inject_into_ssl()
    TRUST = "the computer's certificate store (truststore)"
except ImportError:
    TRUST = "Python's certificate bundle (install 'truststore' to use the computer's own store)"

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "incoming"
HELD = ROOT / "data" / "daily_vessel_position"
LOG = ROOT / "data" / "download_log.csv"
BASE = "https://newmangaloreport.gov.in"
ARCHIVE = BASE + "/archive-daily-vessel-position"
LATEST = BASE + "/index.php/daily-vessel-position"
HEADERS = {"User-Agent": "YellowSense-MPIP/1.0 (NMPA project; daily vessel position archive; polite, permission-based)"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class LinkParser(HTMLParser):
    """Collect every <a href> with its visible text (no third-party libraries needed)."""

    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def date_in(text: str) -> date | None:
    """A report date from a link's text or URL: 01-09-2025, 01.09.2025, 01/09/2025, 01_09_2025, 01092025, 1st September 2025,
    01 Sep 2025, 2025-09-01."""
    t = text.lower()
    for pat, order in ((r"(\d{4})[-_.](\d{1,2})[-_.](\d{1,2})", "ymd"), (r"(\d{1,2})[-_./](\d{1,2})[-_./](\d{4})", "dmy"),
                       (r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", "dmy")):
        m = re.search(pat, t)
        if m:
            a, b, c = (int(x) for x in m.groups())
            y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                return date(y, mo, d)
            except ValueError:
                pass
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?[\s,_-]*([a-z]{3})[a-z]*[\s,_-]*(20\d{2})", t)
    if m and m.group(2) in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


def pdf_links(html: str, page_url: str) -> list[tuple[str, date | None, str]]:
    p = LinkParser()
    p.feed(html)
    out = []
    for href, text in p.links:
        if not href:
            continue
        url = urljoin(page_url, href)
        if ".pdf" in url.lower() or "download" in url.lower() or "pdf" in text.lower():
            out.append((url, date_in(text) or date_in(url.rsplit("/", 1)[-1]), text))
    return out


def sane_dates(links: list[tuple[str, date | None, str]], max_gap_days: int = 45):
    """Keep links whose date fits the rest of the page. The archive lists about 20 consecutive days per page, so a date far
    from the page's typical date (e.g. '2502-04-16' or '2025-01-05' among January 2026 reports) is a typo on the site: it is
    reported, not used, and never decides when to stop."""
    dated = [x for x in links if x[1] and date(2000, 1, 1) <= x[1] <= date.today() + timedelta(days=2)]
    odd = [x for x in links if x[1] and x not in dated]
    if len(dated) >= 3:
        mid = sorted(x[1] for x in dated)[len(dated) // 2]
        keep = [x for x in dated if abs((x[1] - mid).days) <= max_gap_days]
        odd += [x for x in dated if x not in keep]
        dated = keep
    return dated, odd


def wanted_dates(args) -> set[date]:
    if args.date_from or args.date_to:
        d0 = datetime.strptime(args.date_from or args.date_to, "%Y-%m-%d").date()
        d1 = datetime.strptime(args.date_to or args.date_from, "%Y-%m-%d").date()
        return {date.fromordinal(o) for o in range(d0.toordinal(), d1.toordinal() + 1)}
    f = ROOT / "data" / "daily_reports_missing_pdfs.csv"
    with open(f, newline="", encoding="utf-8") as fh:
        return {datetime.strptime(r["report_date"], "%Y-%m-%d").date() for r in csv.DictReader(fh)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="list what is found; download nothing")
    ap.add_argument("--from", dest="date_from", help="first date, YYYY-MM-DD (default: the missing days list)")
    ap.add_argument("--to", dest="date_to", help="last date, YYYY-MM-DD")
    ap.add_argument("--max-pages", type=int, default=80, help="archive pages to read at most (default 80)")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between requests (default 3)")
    ap.add_argument("--ca-bundle", help="a certificate file (.pem) to trust, e.g. one supplied by your organisation's IT")
    ap.add_argument("--insecure", action="store_true",
                    help="LAST RESORT: do not verify the site's certificate. Use only on a trusted network, and only if the other "
                         "options fail; every downloaded file is still checked to be a PDF")
    args = ap.parse_args(argv)
    want = wanted_dates(args)
    if not want:
        print("No missing days in data/daily_reports_missing_pdfs.csv: every report day held has its original PDF. "
              "To fetch newer days, give a range, e.g.  --from 2026-10-27 --to 2026-11-30")
        return 0
    held = {p.stem for p in HELD.glob("*.pdf")} | {p.stem[:10] for p in INBOX.glob("*.pdf")}
    print(f"Dates wanted: {len(want)} ({min(want)} to {max(want)}). Already held: {sum(d.strftime('%d-%m-%Y') in held for d in want)}.")
    s = requests.Session()
    s.headers.update(HEADERS)
    if args.insecure:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        s.verify = False
        print("WARNING: certificate checks are OFF (--insecure).")
    elif args.ca_bundle:
        s.verify = args.ca_bundle
    print(f"Certificates checked with: {'nothing (--insecure)' if args.insecure else (args.ca_bundle or TRUST)}")
    ssl_failures = 0
    found: dict[date, tuple[str, str]] = {}
    suspects: list[tuple[str, date, str]] = []
    seen_urls: set[str] = set()
    pages = [LATEST] + [ARCHIVE] + [f"{ARCHIVE}?page={i}" for i in range(1, args.max_pages)]
    empty_streak = 0
    for i, url in enumerate(pages):
        try:
            r = s.get(url, timeout=60)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  page {url}: {e}")
            if isinstance(e, requests.exceptions.SSLError):
                ssl_failures += 1
                if ssl_failures >= 2:
                    print("\nThe site's security certificate could not be verified. Try, in order:\n"
                          "  1. python -m pip install truststore   (then run this again; uses Windows' own certificate store)\n"
                          "  2. ask your IT team for the certificate file and run with  --ca-bundle path\\to\\file.pem\n"
                          "  3. last resort, on a trusted network only:  --insecure")
                    break
            empty_streak += 1
            if empty_streak >= 3:
                break
            continue
        links = [x for x in pdf_links(r.text, url) if x[0] not in seen_urls]
        seen_urls |= {x[0] for x in links}
        dated, odd = sane_dates(links)
        for u, d, text in dated:
            found.setdefault(d, (u, text))
        suspects.extend(odd)
        mid = sorted(x[1] for x in dated)[len(dated) // 2] if dated else None
        print(f"  page {i}: {len(links)} PDF links, {len(dated)} with a date"
              + (f" ({min(x[1] for x in dated)} to {max(x[1] for x in dated)})" if dated else "")
              + (f"; {len(odd)} with a date that does not fit the page (typo on the site?), not used" if odd else ""))
        empty_streak = empty_streak + 1 if (url != LATEST and not links) else 0
        # archive is newest first: stop once a whole page (its typical date) is well before the earliest date wanted
        if empty_streak >= 2 or (mid and url != LATEST and mid < min(want) - timedelta(days=7)):
            break
        time.sleep(args.delay)
    print(f"Archive dates found: {len(found)}; of the dates wanted: {len(want & set(found))}.")
    rows = []
    for d in sorted(want):
        name = d.strftime("%d-%m-%Y")
        if name in held:
            rows.append({"date": d.isoformat(), "file": f"{name}.pdf", "link": "", "result": "already held"})
            continue
        if d not in found:
            rows.append({"date": d.isoformat(), "file": "", "link": "", "result": "not found on the archive pages read"})
            continue
        url, text = found[d]
        if args.dry_run:
            rows.append({"date": d.isoformat(), "file": f"{name}.pdf", "link": url, "result": "found (dry run, not downloaded)"})
            continue
        try:
            r = s.get(url, timeout=120)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError("the link did not return a PDF")
            INBOX.mkdir(exist_ok=True)
            (INBOX / f"{name}.pdf").write_bytes(r.content)
            rows.append({"date": d.isoformat(), "file": f"{name}.pdf", "link": url, "result": f"downloaded ({len(r.content) // 1024} KB)"})
            print(f"  downloaded {name}.pdf")
        except (requests.RequestException, ValueError) as e:
            rows.append({"date": d.isoformat(), "file": "", "link": url, "result": f"failed: {e}"})
        time.sleep(args.delay)
    if suspects:
        print(f"Links with a date that does not fit their page (left out; check them by hand on the site): "
              + "; ".join(f"{t or u.rsplit('/', 1)[-1]} -> read as {d}" for u, d, t in suspects[:10]))
        for u, d, t in suspects:
            rows.append({"date": d.isoformat(), "file": "", "link": u, "result": f"left out: date does not fit its page ({t})"})
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "file", "link", "result"])
        w.writeheader()
        w.writerows(rows)
    summary = {}
    for r in rows:
        k = r["result"].split(" (")[0].split(":")[0]
        summary[k] = summary.get(k, 0) + 1
    print("Result: " + "; ".join(f"{v} {k}" for k, v in summary.items()) + f". Details: {LOG.relative_to(ROOT)}")
    if not args.dry_run and any(r["result"].startswith("downloaded") for r in rows):
        print("Next: python scripts\\update_trade_data.py  (reads and checks the new PDFs, then refreshes everything)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
