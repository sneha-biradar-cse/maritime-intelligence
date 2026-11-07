"""
NMPA document harvester: reads NMPA's public listing pages, lists every PDF with its title, classifies it, and downloads only
documents the project does not hold yet (checked by checksum and by name).

Use only with NMPA's permission for automated download (as for scripts/download_daily_reports.py). It is polite: one request at
a time, a pause between requests (default 3 s), a clear User-Agent, and it never re-downloads a document already held.

Where downloads go:
  - monthly statements the monthly update reads (commodity, container, Traffic & Performance)  -> incoming/
    (then: python scripts\\update_trade_data.py checks them and refreshes everything)
  - everything else that matters to the Incentive Engine (trade notices and circulars, Scale of Rates, reports)
    -> nmpa_public_data/harvested/<category>/  for a person to read; nothing is changed automatically.
    Notices whose title mentions a rebate, incentive, concession, discount or waiver are flagged for review.

Also reads the Ministry of Ports' "TRW publication" page (shipmin.gov.in): "Monthly Cargo Traffic handled at Major Ports"
reports for months the project does not hold go to incoming/ (the monthly update reads and checks them); Non-Major Ports
reports go to nmpa_public_data/harvested/ for reference.

Every run writes data/harvest_catalog.csv: page, title, link, category, flag, and what happened.

Usage (PowerShell, from the project folder, venv active):
  python scripts\\harvest_nmpa_documents.py --dry-run          list and classify, download nothing
  python scripts\\harvest_nmpa_documents.py                    download what is new
  python scripts\\harvest_nmpa_documents.py --pages statistics circular-tradenotice --max-pages 5
  python scripts\\harvest_nmpa_documents.py --source ministry     only the Ministry's monthly reports
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode, unquote

import requests

try:
    import truststore      # the computer's own certificate store, as for the daily-report downloader
    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "incoming"
OUT = ROOT / "nmpa_public_data" / "harvested"
CATALOG = ROOT / "data" / "harvest_catalog.csv"
BASE = "https://newmangaloreport.gov.in"
HEADERS = {"User-Agent": "YellowSense-MPIP/1.0 (NMPA project; public documents; polite, permission-based)"}
# listing pages given by the project team; the name is the path on NMPA's site
PAGES = ["statistics", "reports", "circular-tradenotice", "port-tariff", "downloads", "office-memorandums", "sops",
         "act-rules", "index.php/actsandrules", "rti-new", "csr", "index.php/tender-contract-awarded"]
# pages whose documents matter to the Incentive Engine; the others are listed in the catalogue but not downloaded
USEFUL_PAGES = {"statistics", "reports", "circular-tradenotice", "port-tariff", "downloads", "office-memorandums"}

INCENTIVE_WORDS = re.compile(r"rebate|incentive|concession|discount|waiver|waive|reduction in (?:tariff|charges)|green", re.I)
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
MINISTRY = "https://shipmin.gov.in/en/publication/trw-publication"
MON = {m: i for i, m in enumerate(MONTHS.split("|"), 1)}


def _strip(h: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", h).replace("&amp;", "&").replace("&nbsp;", " ").split())


def ministry_rows(html: str, page_url: str) -> list[dict]:
    """Rows of the Ministry's publication table: description, month, year and the PDF link."""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(tds) < 4:
            continue
        link = re.search(r'href="([^"]+\.pdf[^"]*)"', tr, re.I)
        if not link:
            continue
        desc, mon, yr = _strip(tds[1]), _strip(tds[2]).lower()[:3], _strip(tds[3])
        if mon in MON and yr.isdigit():
            out.append({"title": desc, "month": f"{int(yr)}-{MON[mon]:02d}", "link": urljoin(page_url, link.group(1))})
    return out


FULL_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                            "september", "october", "november", "december"], 1)}


def month_in(text: str) -> str | None:
    """'2026-10' from a title or file name such as 'Container Traffic Statement October 2026' or 'Oct-2026'."""
    t = unquote(text).lower()
    m = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december|"
                  r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)[\s,._'-]*(20\d{2})", t)
    if not m:
        return None
    name = m.group(1)
    num = FULL_MONTHS.get(name) or MON.get(name[:3])
    return f"{m.group(2)}-{num:02d}" if num else None


def month_from_pdf(content: bytes) -> str | None:
    """The month a statement covers, read from the text of its first pages (e.g. 'for the month of October 2026')."""
    import io
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = " ".join((pg.extract_text() or "") for pg in pdf.pages[:2])
    except Exception:
        return None
    m = re.search(r"(?:month\s+of|for|during|upto|up\s+to|ending)\s+((?:january|february|march|april|may|june|july|august|september|"
                  r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)[\s,.'-]*20\d{2})", text, re.I)
    return month_in(m.group(1)) if m else month_in(text[:600])


def latest_held_statement_months() -> dict[str, str]:
    """Latest month already held for each statement type the monthly update reads."""
    import pandas as pd
    out = {}
    try:
        a = pd.read_csv(ROOT / "data" / "port_cargo_monthly.csv")
        out["NMPA commodity-wise traffic statement"] = max(f"{int(y)}-{FULL_MONTHS[str(m).lower()]:02d}"
                                                           for m, y in zip(a["month"], a["year"]) if str(m).lower() in FULL_MONTHS)
    except Exception:
        pass
    for cat, f, col in (("NMPA container traffic statement", "nmpa_container_commodities.csv", "month"),
                        ("NMPA Traffic & Performance report", "nmpa_performance_monthly.csv", "report_month")):
        try:
            out[cat] = str(pd.read_csv(ROOT / "data" / f)[col].astype(str).max())
        except Exception:
            pass
    return out


def held_ministry_months() -> set[str]:
    f = ROOT / "data" / "major_ports_monthly.csv"
    if not f.exists():
        return set()
    import pandas as pd
    return set(pd.read_csv(f)["month"].astype(str))


class LinkParser(HTMLParser):
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


def classify(title: str, url: str, page: str) -> tuple[str, str]:
    """(category, where it goes) from the link's title, file name and page. 'incoming' = read by the monthly update."""
    t = f"{title} {unquote(url.rsplit('/', 1)[-1])}".lower()
    if re.search(r"daily\s*vessel|vessel\s*position", t) or re.fullmatch(r".*\d{2}[-_.]\d{2}[-_.]\d{4}\.pdf", t.strip()):
        return "Daily vessel position (use download_daily_reports.py)", "skip"
    if re.search(r"commodity|commodity\s*wise", t) and re.search(rf"({MONTHS})|statement|traffic", t):
        return "NMPA commodity-wise traffic statement", "incoming"
    if re.search(r"container", t) and re.search(rf"({MONTHS})|statement|teu|traffic", t):
        return "NMPA container traffic statement", "incoming"
    if re.search(r"performance|operational", t) and re.search(rf"({MONTHS})|traffic", t):
        return "NMPA Traffic & Performance report", "incoming"
    if re.search(r"scale\s*of\s*rates|\bsor\b|tariff", t):
        return ("Scale of Rates (PROPOSED or DRAFT - not in force)" if re.search(r"draft|propos", t) else "Scale of Rates / tariff"), "harvested"
    if page == "circular-tradenotice" or re.search(r"trade\s*notice|circular", t):
        return "Trade notice / circular", "harvested"
    if re.search(r"annual\s*report|administration\s*report|budget|accounts", t):
        return "Annual / administration report, budget or accounts", "harvested"
    return "Other", "skip"


def next_pages(html: str, page_url: str, path: str) -> list[str]:
    """Pagination links on the same listing (?page=N), so every page of a long list is read."""
    p = LinkParser()
    p.feed(html)
    out = []
    for href, _ in p.links:
        if not href or "page=" not in href:
            continue
        u = urljoin(page_url, href)
        if urlparse(u).path.rstrip("/").endswith(path.split("/")[-1]):
            out.append(u)
    return out


def held_checksums() -> set[str]:
    out = set()
    for folder in (ROOT / "nmpa_public_data", ROOT / "data" / "daily_vessel_position", INBOX):
        if folder.exists():
            for f in folder.rglob("*.pdf"):
                out.add(hashlib.md5(f.read_bytes()).hexdigest())
    return out


def held_names() -> set[str]:
    return {f.name.lower() for f in (ROOT / "nmpa_public_data").rglob("*.pdf")} | {f.name.lower() for f in INBOX.glob("*.pdf")}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="list and classify; download nothing")
    ap.add_argument("--pages", nargs="*", default=PAGES, help="listing pages to read (paths on NMPA's site)")
    ap.add_argument("--max-pages", type=int, default=15, help="pages of each listing to read at most (default 15)")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between requests (default 3)")
    ap.add_argument("--all", action="store_true", help="also download documents from pages not used by the Incentive Engine")
    ap.add_argument("--source", choices=["all", "nmpa", "ministry"], default="all", help="which website(s) to read")
    args = ap.parse_args(argv)
    s = requests.Session()
    s.headers.update(HEADERS)
    found: dict[str, dict] = {}
    if args.source in ("all", "ministry"):
        held_m = held_ministry_months()
        queue, seen, n = [MINISTRY], set(), 0
        while queue and n < args.max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            n += 1
            try:
                r = s.get(url, timeout=60)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"  Ministry page {n}: {e}")
                continue
            rows_ = ministry_rows(r.text, url)
            for m in rows_:
                major = re.search(r"major\s*port", m["title"], re.I) and not re.search(r"non[\s-]*major", m["title"], re.I)
                found.setdefault(m["link"], {
                    "page": "shipmin trw-publication", "title": m["title"], "link": m["link"],
                    "category": "Ministry: Major Ports monthly cargo report" if major else "Ministry: Non-Major Ports monthly cargo report",
                    "destination": ("incoming" if major else "harvested"), "flag": "", "month": m["month"],
                    "result": ("already held (month in data/major_ports_monthly.csv)" if (major and m["month"] in held_m) else "")})
            months_ = sorted(x["month"] for x in rows_)
            print(f"  Ministry page {n}: {len(rows_)} reports" + (f" ({months_[0]} to {months_[-1]})" if months_ else ""))
            more = [x for x in next_pages(r.text, url, "trw-publication") if x not in seen]
            if months_ and min(months_) < "2024-02":           # the project's Ministry data starts in Feb 2024: older pages not needed
                more = []
            queue.extend(m for m in more if m not in queue)
            time.sleep(args.delay)
    for path in (args.pages if args.source in ("all", "nmpa") else []):
        queue, seen, n = [f"{BASE}/{path.strip('/')}"], set(), 0
        while queue and n < args.max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            n += 1
            try:
                r = s.get(url, timeout=60)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"  {path} page {n}: {e}")
                continue
            p = LinkParser()
            p.feed(r.text)
            k = 0
            for href, text in p.links:
                if not href:
                    continue
                u = urljoin(url, href)
                if ".pdf" not in u.lower():
                    continue
                if u not in found:
                    cat, dest = classify(text, u, path)
                    found[u] = {"page": path, "title": text or unquote(u.rsplit("/", 1)[-1]), "link": u, "category": cat,
                                "destination": dest, "flag": "incentive-related: review" if INCENTIVE_WORDS.search(f"{text} {u}") else "",
                                "result": ""}
                    k += 1
            more = [x for x in next_pages(r.text, url, path) if x not in seen]
            queue.extend(m for m in more if m not in queue)
            print(f"  {path} page {n}: {k} new PDF links" + (f" ({len(more)} more pages listed)" if more else ""))
            time.sleep(args.delay)
    known_md5, known_names = held_checksums(), held_names()
    latest = latest_held_statement_months()
    for row in found.values():
        if row["destination"] == "incoming" and row["category"] in latest and not row["result"]:
            m = month_in(f"{row['title']} {row['link'].rsplit('/', 1)[-1]}")
            row["month"] = m or ""
            if m is None:
                row["inspect"] = True            # month read from inside the PDF after download
            elif m <= latest[row["category"]]:
                row["destination"] = "archive"   # kept for history; never fed to the update
    todo_n = sum(1 for r in found.values() if not r["result"] and (r["destination"] != "skip" or args.all))
    if todo_n and not args.dry_run:
        print(f"\nDownloading up to {todo_n} documents, about {args.delay:.0f} s apart (files already held are skipped):", flush=True)
    k_ = 0
    for row in found.values():
        name = unquote(row["link"].rsplit("/", 1)[-1])
        if row["result"]:
            continue
        if not args.dry_run and (row["destination"] != "skip" or args.all):
            k_ += 1
            print(f"  {k_} of {todo_n}: {(row['title'] or name)[:80]}", flush=True)
        if row["category"].startswith("Ministry: Major") and "major port" not in name.lower():
            name = f"Cargo handled at Major Ports {row.get('month', '')} - {name}"     # the monthly update recognises 'major port'
        if row["destination"] == "skip" and not args.all:
            row["result"] = "listed only (not used by the Incentive Engine)"
            continue
        if name.lower() in known_names:
            row["result"] = "already held (same file name)"
            continue
        if args.dry_run:
            row["result"] = "new (dry run, not downloaded)"
            continue
        try:
            r = s.get(row["link"], timeout=120)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError("the link did not return a PDF")
            if hashlib.md5(r.content).hexdigest() in known_md5:
                row["result"] = "already held (same contents)"
            else:
                if row.get("inspect"):
                    m = month_from_pdf(r.content)
                    row["month"] = m or ""
                    lat = latest.get(row["category"], "")
                    row["destination"] = "incoming" if (m and m > lat) else "archive"
                    row["note"] = f"month {m} read from inside the PDF" if m else "month not found inside the PDF either"
                if row["destination"] == "archive":
                    folder = OUT / "older_statements" / re.sub(r"[^A-Za-z0-9]+", "_", row["category"])[:40]
                else:
                    folder = INBOX if row["destination"] == "incoming" else OUT / re.sub(r"[^A-Za-z0-9]+", "_", row["category"])[:40]
                folder.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r'[<>:"/\\|?*]+', "_", name)[:150] or "document.pdf"
                if folder == INBOX:          # make sure the monthly update recognises what it is
                    prefix = {"NMPA commodity-wise traffic statement": "commodity wise traffic statement",
                              "NMPA container traffic statement": "container traffic statement",
                              "NMPA Traffic & Performance report": "operational performance"}.get(row["category"], "")
                    if prefix and prefix.split()[0] not in safe.lower():
                        safe = f"{prefix} - {safe}"
                    if row["category"].startswith("Ministry: Major") and "major port" not in safe.lower():
                        safe = f"Cargo handled at Major Ports - {safe}"
                (folder / safe).write_bytes(r.content)
                known_md5.add(hashlib.md5(r.content).hexdigest())
                row["result"] = f"downloaded to {folder.relative_to(ROOT)}" + (f" ({row['note']})" if row.get("note") else "")
        except (requests.RequestException, ValueError) as e:
            row["result"] = f"failed: {e}"
        time.sleep(args.delay)
    CATALOG.parent.mkdir(exist_ok=True)
    rows = sorted(found.values(), key=lambda r: (r["category"], r["title"]))
    with open(CATALOG, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["page", "category", "title", "month", "flag", "result", "destination", "link", "note"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["category"]] = by.get(r["category"], 0) + 1
    print(f"\n{len(rows)} PDF links found:")
    for c, n in sorted(by.items(), key=lambda x: -x[1]):
        new = sum(1 for r in rows if r["category"] == c and r["result"].startswith(("new", "downloaded")))
        print(f"  {n:4}  {c}" + (f"   ({new} new)" if new else ""))
    flagged = [r for r in rows if r["flag"] and r["result"].startswith(("new", "downloaded"))]
    if flagged:
        print("\nNew documents that mention a rebate, incentive, concession, discount or waiver (read these):")
        for r in flagged[:20]:
            print(f"  - {r['title'][:110]}")
    print(f"\nDetails: {CATALOG.relative_to(ROOT)}")
    if any(r["result"].startswith("downloaded to incoming") for r in rows):
        print("Next: python scripts\\update_trade_data.py  (checks the new statements and refreshes everything)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
