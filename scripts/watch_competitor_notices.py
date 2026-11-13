"""
Competitor scheme watch: new incentive and tariff notices at Cochin, VOC Tuticorin and Mormugao.

Reads the public notice pages listed in data/competitor_sources.csv (NMPA can add or change pages there), keeps the
links whose titles are about rebates, concessions, discounts, incentives, waivers, exemptions, priority berthing or
tariff changes, and records them in data/competitor_notices.csv with the day each was first seen.

The first time a page is read, everything already on it is recorded as the starting point ("baseline"), so old
notices are not reported as new. After that, a notice not seen before is new. A page that cannot be read is reported
in data/competitor_watch_status.json; nothing already recorded is lost.

Polite reading: one page at a time, a pause between pages, a clear User-Agent, the computer's own certificates.
Usage:  python scripts/watch_competitor_notices.py            (read all pages)
        python scripts/watch_competitor_notices.py --dry-run  (show what would be read; change nothing)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "competitor_sources.csv"
STORE = ROOT / "data" / "competitor_notices.csv"
STATUS = ROOT / "data" / "competitor_watch_status.json"
FIELDS = ["port", "title", "url", "kind", "date_on_page", "first_seen", "baseline", "page"]
HEADERS = {"User-Agent": "YellowSense-MPIP/1.0 (NMPA project; public notices; polite, one page at a time)"}
PAUSE_S = 3

INCENTIVE_WORDS = r"rebate|concession|discount|incentive|waiver|waive|exempt|priority berthing|reduction in|relief"
TARIFF_WORDS = r"tariff|scale of rates|\bsor\b|indexation|charges|royalty|wharfage|port dues|pilotage|berth hire"
GENERIC_LINK_TEXT = {"view", "download", "click here", "here", "pdf", "read more", "more", "open", ""}
DATE_RE = re.compile(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|[A-Z][a-z]{2}-\d{1,2},\s?\d{4}|\d{1,2}-\d{1,2}-\d{4})\b")


class _Blocks(HTMLParser):
    """Collects each table row / list item / paragraph as a block of text with the links inside it."""
    BLOCK_TAGS = {"tr", "li", "p", "div"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self._stack = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK_TAGS:
            self._stack.append({"text": [], "links": []})
        elif tag == "a" and self._stack:
            href = dict(attrs).get("href") or ""
            self._stack[-1]["links"].append({"href": href, "text": []})

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS and self._stack:
            b = self._stack.pop()
            text = " ".join(" ".join(b["text"]).split())
            links = [{"href": l["href"], "text": " ".join(" ".join(l["text"]).split())} for l in b["links"]]
            if links:
                self.blocks.append({"text": text, "links": links})
            elif self._stack:                                   # plain text joins the enclosing block
                self._stack[-1]["text"].append(text)

    def handle_data(self, data):
        if self._stack:
            self._stack[-1]["text"].append(data)
            if self._stack[-1]["links"]:
                self._stack[-1]["links"][-1]["text"].append(data)


def classify(title: str) -> str | None:
    t = title.lower()
    if re.search(INCENTIVE_WORDS, t):
        return "Incentive or concession"
    if re.search(TARIFF_WORDS, t):
        return "Tariff or charges"
    return None


def extract(html: str, base_url: str) -> list[dict]:
    """Notices on a page: title, absolute link, kind, any date printed beside it. Duplicate links are kept once."""
    p = _Blocks()
    p.feed(html)
    out, seen = [], set()
    for b in p.blocks:
        for l in b["links"]:
            href = l["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            title = l["text"] if l["text"].lower() not in GENERIC_LINK_TEXT and len(l["text"]) > 12 else b["text"]
            title = " ".join(title.split())
            m0 = DATE_RE.search(b["text"]) or DATE_RE.search(title)
            if m0 and title.startswith(m0.group(1)):                    # the date is kept in its own column
                title = title[len(m0.group(1)):].strip(" -:|")
            title = re.sub(r"(\s+(view|download|pdf|click here))+\s*$", "", title, flags=re.I).strip()[:300]
            kind = classify(title)
            if not kind:
                continue
            url = urljoin(base_url, href)
            if url in seen:
                continue
            seen.add(url)
            m = DATE_RE.search(b["text"]) or DATE_RE.search(title)
            out.append({"title": title, "url": url, "kind": kind, "date_on_page": m.group(1) if m else ""})
    return out


def _load_store() -> list[dict]:
    if not STORE.exists():
        return []
    with STORE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _get(url: str) -> str:
    import requests
    try:
        import truststore            # the computer's own certificate store, as for the other downloaders
        truststore.inject_into_ssl()
    except Exception:
        pass
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    r.encoding = r.encoding or r.apparent_encoding
    return r.text


def run(dry: bool = False, fetch=_get, today: date | None = None) -> dict:
    today = today or date.today()
    with SOURCES.open(encoding="utf-8", newline="") as f:
        sources = list(csv.DictReader(f))
    if dry:
        for s in sources:
            print(f"  would read: {s['port']} - {s['page']}: {s['url']}")
        return {"dry_run": True, "pages": len(sources)}
    store = _load_store()
    known = {r["url"] for r in store}
    prev = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    # pages read successfully before (kept separately: two pages can link the same notice, which is recorded once)
    pages_seen_before = set(prev.get("pages_read", [])) | {p["url"] for p in prev.get("pages", []) if p.get("ok")}
    status, new_rows = [], []
    for i, s in enumerate(sources):
        if i:
            time.sleep(PAUSE_S)
        try:
            items = extract(fetch(s["url"]), s["url"])
        except Exception as e:                                     # a page that cannot be read is reported, not hidden
            status.append({"port": s["port"], "page": s["page"], "url": s["url"], "ok": False, "found": 0, "new": 0,
                           "error": f"{type(e).__name__}: {str(e)[:160]}"})
            print(f"  {s['port']} - {s['page']}: could not be read ({type(e).__name__})")
            continue
        first_time = s["url"] not in pages_seen_before
        fresh = [it for it in items if it["url"] not in known]
        for it in fresh:
            known.add(it["url"])
            new_rows.append({"port": s["port"], **it, "first_seen": today.isoformat(),
                             "baseline": "yes" if first_time else "no", "page": s["url"]})
        status.append({"port": s["port"], "page": s["page"], "url": s["url"], "ok": True, "found": len(items),
                       "new": 0 if first_time else len(fresh), "first_read": first_time,
                       "note": ("Page read for the first time: its notices are the starting point, not new."
                                if first_time else "") + ("" if items else " No incentive or tariff notices found on the page "
                                                          "(it may load its list with JavaScript).")})
        print(f"  {s['port']} - {s['page']}: {len(items)} incentive/tariff notices, "
              f"{'starting point' if first_time else str(len(fresh)) + ' new'}")
    if new_rows:
        write_header = not STORE.exists()
        with STORE.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if write_header:
                w.writeheader()
            w.writerows(new_rows)
    pages_read = sorted(pages_seen_before | {p["url"] for p in status if p["ok"]})
    summary = {"last_run": today.isoformat(), "pages": status, "pages_read": pages_read,
               "new": sum(p["new"] for p in status), "pages_failed": sum(1 for p in status if not p["ok"])}
    STATUS.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv[1:]
    s = run(dry=dry)
    if not dry:
        print(f"\nNew incentive or tariff notices at competitor ports: {s['new']}"
              + (f"; pages that could not be read: {s['pages_failed']}" if s["pages_failed"] else ""))
    sys.exit(0 if dry or s["pages_failed"] < len(s["pages"]) else 1)
