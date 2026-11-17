"""
Update the Vessel Intelligence data from NMPA's public website.

    python scripts/update_vessel_intel_data.py            # new reports since the last one we have
    python scripts/update_vessel_intel_data.py --all      # full back-fill (DVP archive starts 31-05-2021)
    python scripts/update_vessel_intel_data.py --dry-run  # list what would be downloaded

Steps
-----
1. Daily Vessel Position (DVP) reports — read the official archive listing
   (newmangaloreport.gov.in/archive-daily-vessel-position?page=N) and download
   every PDF we do not have into data/daily_vessel_position/DD-MM-YYYY.pdf.
   The listing is used (not a guessed URL) because file names vary
   ('01-10-2026_0.pdf', '6-8-2021.pdf').
2. Parse new PDFs with backend/app/services/vessel_position_parser.py into
   data/daily_vessel_position_parsed/. Failures are listed, never hidden —
   2021–2023 reports use an older, smaller layout and may need a parser template.
3. Monthly "Operational Performance" reports (Statistics page) →
   nmpa_public_data/operational_performance/YYYY-MM.pdf.
4. Rebuild derived tables: vessel registry + review queue, vessel stays,
   data/derived/port_calls.csv, data/official/operational_performance.csv.

Then call POST /vessels/intel/refresh (or restart the API).

Etiquette: NMPA's copyright policy allows downloading material published for
download. This script fetches at most one file every --delay seconds
(default 2 s), skips files already present, and identifies itself.
Run it once a day (e.g. 13:30 IST, after the report is published).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import urllib3  # noqa: E402

BASE = "https://newmangaloreport.gov.in"
DVP_LIST = BASE + "/archive-daily-vessel-position?page={page}"
STATS_LIST = BASE + "/index.php/statistics?tid={tid}&page={page}"
DVP_DIR = ROOT / "data" / "daily_vessel_position"
PARSED_DIR = ROOT / "data" / "daily_vessel_position_parsed"
OPPERF_DIR = ROOT / "nmpa_public_data" / "operational_performance"
HEADERS = {"User-Agent": "YellowSense-MPIP research collector (port analytics study; one request per few seconds)"}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MONTHS = {m: i for i, m in enumerate(["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                                       "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], start=1)}


def get(url: str, delay: float, binary: bool = False, retries: int = 2):
    for attempt in range(retries + 1):
        try:
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
            except requests.exceptions.SSLError:
                # NMPA's certificate chain fails standard verification (seen 2026-09)
                r = requests.get(url, headers=HEADERS, timeout=30, verify=False)
            time.sleep(delay)
            if r.status_code == 200:
                return r.content if binary else r.text
            if r.status_code == 404:
                return None
        except requests.exceptions.RequestException as exc:
            print(f"  ! {url}: {exc}")
        time.sleep(delay * (attempt + 2))
    return None


# ──────────────────────────────────────────────────────────────────────
# 1. DVP archive listing
# ──────────────────────────────────────────────────────────────────────

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_HREF_RE = re.compile(r'href="([^"]*/sites/default/files/[^"]+\.pdf)"', re.I)  # 2021 files live outside /dailyvessel/
_DATE_RE = re.compile(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})")


def _row_date(row_html: str, href: str) -> Optional[date]:
    text = html.unescape(re.sub(r"<[^>]+>", " ", row_html))
    for src in (text, href.rsplit("/", 1)[-1]):
        m = _DATE_RE.search(src)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            y = y + 2000 if y < 100 else y
            try:
                return date(y, mo, d)
            except ValueError:
                continue
    return None


def list_dvp(delay: float, stop_before: Optional[date]) -> List[Tuple[date, str]]:
    found: Dict[date, str] = {}
    page = 0
    while True:
        page_html = get(DVP_LIST.format(page=page), delay)
        if not page_html:
            break
        rows = _ROW_RE.findall(page_html)
        new_on_page = 0
        oldest = None
        for row in rows:
            m = _HREF_RE.search(row)
            if not m:
                continue
            href = m.group(1)
            d = _row_date(row, href)
            if not d:
                continue
            url = href if href.startswith("http") else BASE + href
            if d not in found:
                found[d] = url
                new_on_page += 1
            oldest = d if oldest is None or d < oldest else oldest
        print(f"  archive page {page}: {new_on_page} reports (oldest {oldest})")
        if new_on_page == 0 or (stop_before and oldest and oldest < stop_before):
            break
        page += 1
    return sorted(found.items())


def download_dvp(items: List[Tuple[date, str]], since: Optional[date], delay: float, dry: bool) -> List[Path]:
    DVP_DIR.mkdir(parents=True, exist_ok=True)
    new = []
    for d, url in items:
        if since and d < since:
            continue
        out = DVP_DIR / f"{d.strftime('%d-%m-%Y')}.pdf"
        if out.exists():
            continue
        if dry:
            print(f"  would download {d} {url}")
            continue
        content = get(url, delay, binary=True)
        if content and content[:4] == b"%PDF":
            out.write_bytes(content)
            new.append(out)
            print(f"  + {out.name}")
        else:
            print(f"  ! not a PDF: {url}")
    return new


def parse_new(paths: List[Path]) -> Tuple[int, List[str]]:
    import json
    from dataclasses import asdict
    from backend.app.services import vessel_position_parser as vpp
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, []
    for p in paths:
        try:
            day = vpp.parse_pdf(p)
            (PARSED_DIR / f"{p.stem}.json").write_text(json.dumps(asdict(day), indent=2))
            ok += 1
            if day.unparsed_rows:
                print(f"  ~ {p.name}: {len(day.unparsed_rows)} unparsed rows (check layout)")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{p.name}: {exc}")
    return ok, failed


# ──────────────────────────────────────────────────────────────────────
# 3. Monthly Operational Performance reports
# ──────────────────────────────────────────────────────────────────────

def opperf_tid(delay: float) -> Optional[str]:
    page = get(STATS_LIST.format(tid="All", page=0), delay)
    if not page:
        return None
    m = re.search(r'<option value="(\d+)"[^>]*>\s*Operational Performance\s*</option>', page, re.I)
    return m.group(1) if m else None


def list_opperf(delay: float) -> List[Tuple[str, str]]:
    tid = opperf_tid(delay) or "All"
    out: Dict[str, str] = {}
    page = 0
    while True:
        page_html = get(STATS_LIST.format(tid=tid, page=page), delay)
        if not page_html:
            break
        added = 0
        for row in _ROW_RE.findall(page_html):
            text = html.unescape(re.sub(r"<[^>]+>", " ", row))
            if "operational performance" not in text.lower():
                continue
            m = re.search(r"Traffic data for\s+([A-Za-z]+)\s+(\d{4})", text)
            h = re.search(r'href="([^"]+\.pdf)"', row, re.I)
            if not (m and h):
                continue
            mon = MONTHS.get(m.group(1).upper()) or MONTHS.get(next((k for k in MONTHS if k.startswith(m.group(1).upper()[:3])), ""), 0)
            if not mon:
                continue
            key = f"{m.group(2)}-{mon:02d}"
            href = h.group(1)
            if key not in out:
                out[key] = href if href.startswith("http") else BASE + href
                added += 1
        if added == 0:
            break
        page += 1
    return sorted(out.items())


def download_opperf(items: List[Tuple[str, str]], delay: float, dry: bool) -> int:
    OPPERF_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for month, url in items:
        out = OPPERF_DIR / f"operational_performance_{month}.pdf"
        if out.exists():
            continue
        if dry:
            print(f"  would download {month} {url}")
            continue
        content = get(url, delay, binary=True)
        if content and content[:4] == b"%PDF":
            out.write_bytes(content)
            n += 1
            print(f"  + {out.name}")
    return n


# ──────────────────────────────────────────────────────────────────────
# 4. Rebuild
# ──────────────────────────────────────────────────────────────────────

def rebuild() -> None:
    from backend.app.services import vessel_entity_resolution as ver
    from backend.app.services import vessel_stay_duration as vsd
    from backend.app.services import vi_official_kpis, vi_port_calls
    reg = ver.build_vessel_registry()
    ver.find_review_candidates(reg)
    vsd.save_vessel_stays(vsd.build_vessel_stays())
    vi_port_calls.clear_caches()
    info = vi_port_calls.export()
    rows = vi_official_kpis.export()
    print(f"  registry: {len(reg)} vessels · port calls: {info['port_calls']} · official KPI rows: {rows}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="back-fill the whole DVP archive (from 31-05-2021)")
    ap.add_argument("--since", help="only reports on/after YYYY-MM-DD")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests (default 2)")
    ap.add_argument("--skip-dvp", action="store_true")
    ap.add_argument("--skip-opperf", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").date()
    elif not args.all:
        have = sorted(datetime.strptime(p.stem[:10], "%d-%m-%Y").date()
                      for p in PARSED_DIR.glob("*.json") if re.match(r"\d{2}-\d{2}-\d{4}", p.stem))
        since = have[-1] if have else None

    new_pdfs: List[Path] = []
    if not args.skip_dvp:
        print(f"[1/4] Daily Vessel Position archive (since {since or 'the beginning'}) …")
        items = list_dvp(args.delay, since)
        print(f"  {len(items)} reports listed")
        new_pdfs = download_dvp(items, since, args.delay, args.dry_run)
        # also parse any PDF that has no JSON yet (e.g. downloaded earlier)
        pending = [p for p in sorted(DVP_DIR.glob("*.pdf")) if not (PARSED_DIR / f"{p.stem}.json").exists()]
        if pending and not args.dry_run:
            print(f"[2/4] Parsing {len(pending)} new report(s) …")
            ok, failed = parse_new(pending)
            print(f"  parsed {ok}, failed {len(failed)}")
            for f in failed[:20]:
                print(f"  ! {f}")
    if not args.skip_opperf:
        print("[3/4] Monthly Operational Performance reports …")
        n = download_opperf(list_opperf(args.delay), args.delay, args.dry_run)
        print(f"  downloaded {n}")
    if not args.dry_run:
        print("[4/4] Rebuilding derived tables …")
        rebuild()
        print("Done. Now POST http://127.0.0.1:8000/vessels/intel/refresh (or restart the API).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
