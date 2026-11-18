"""
Bulk-downloads NMPA's public "Daily Vessel Position" reports (Traffic
Department "Proceedings of the Operation Meeting") for a date range,
where published at the predictable
/sites/default/files/dailyvessel/DD-MM-YYYY.pdf path.

Confirmed 2026-09-15: this path pattern is real, and dates going back
at least a full year (15-09-2025) are still live -- though not every
single date has a file (spot checks found gaps, e.g. 15-08-2026 and
15-03-2026 both 404 while neighbouring months hit). This script
records what's actually available; it does not assume full coverage,
and re-running it later only fills in gaps (already-downloaded files
are skipped), so it doubles as the daily incremental collector once
the historical backfill is done.

Each report is a scanned/typed table: vessels currently berthed (with
arrival/berthing dates, cargo, daily/cumulative tonnage handled,
ETD), vessels waiting at anchorage (with an explicit reason -- want
of berth, shipper not ready, lay-can not started, etc.), vessels
expected, and a same-day "Movements" log with exact berthing/sailing
timestamps. See PROJECT_DOCUMENTATION/22_NMPA_VISIT_BRIEFING.md
(Q3 / Project Status Part B) for why this is the dataset that
unlocks real vessel-stay and berth-occupancy prediction -- previously
blocked because our only NMPA data was monthly aggregated tonnage.

This script only downloads PDFs; it does not parse them into
structured data. Each day's table layout is inconsistent enough
(merged cells, free-text notes sections) that extraction needs its
own dedicated step with spot-checking, not a blind batch parse.
"""

import sys
import time
import warnings
from datetime import date, timedelta
from pathlib import Path

import requests
import urllib3

URL_TEMPLATE = (
    "https://newmangaloreport.gov.in/sites/default/files/dailyvessel/{}.pdf"
)
OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "daily_vessel_position"

# NMPA's certificate chain fails standard verification (confirmed
# 2026-09-15) so every request falls back to verify=False below --
# suppress the resulting per-request warning instead of printing it
# hundreds of times over a year-long backfill.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _get(url: str, retries: int = 2) -> requests.Response | None:
    """GET with a TLS-verification fallback and a couple of retries
    for transient network errors, so one flaky request doesn't abort
    a multi-hundred-day backfill. Returns None (not an exception) if
    every attempt fails -- the caller records that day as missing and
    moves on; re-running the script later will retry it, since
    already-downloaded days are skipped.
    """

    last_error = None
    for attempt in range(retries + 1):
        try:
            return requests.get(url, timeout=15)
        except requests.exceptions.SSLError:
            try:
                return requests.get(url, timeout=15, verify=False)
            except requests.exceptions.RequestException as exc:
                last_error = exc
        except requests.exceptions.RequestException as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(2 * (attempt + 1))

    warnings.warn(f"Giving up on {url} after {retries + 1} attempts: {last_error}")
    return None


def fetch_range(start: date, end: date, delay_seconds: float = 0.5):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    found, missing = [], []

    day = start
    while day <= end:
        stamp = day.strftime("%d-%m-%Y")
        out_path = OUT_DIR / f"{stamp}.pdf"

        if out_path.exists():
            found.append(day)
            day += timedelta(days=1)
            continue

        resp = _get(URL_TEMPLATE.format(stamp))

        if resp is not None and resp.status_code == 200 and resp.content[:4] == b"%PDF":
            out_path.write_bytes(resp.content)
            found.append(day)
        else:
            missing.append(day)

        day += timedelta(days=1)
        time.sleep(delay_seconds)

    return found, missing


def main() -> int:
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 380
    end = date.today()
    start = end - timedelta(days=days_back)

    print(f"Fetching Daily Vessel Position reports {start} .. {end} ...")
    found, missing = fetch_range(start, end)
    total = len(found) + len(missing)

    print(f"\nFound: {len(found)} / {total} days "
          f"({(len(found) / total * 100 if total else 0):.0f}% coverage)")
    print(f"Saved to: {OUT_DIR}")

    if missing:
        preview = ", ".join(d.isoformat() for d in missing[:20])
        more = " ..." if len(missing) > 20 else ""
        print(f"Missing dates ({len(missing)}): {preview}{more}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
