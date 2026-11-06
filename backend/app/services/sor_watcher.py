"""
NMPA SOR (Scale of Rates) update watcher.

Checks the public NMPA "Circular and Trade Notice" page for new PDF
entries whose title looks like a Scale of Rates / tariff update, and
flags them for manual re-transcription into cost_engine.py.

Why detection-only, not auto-update: the SOR is a large, irregularly
structured document (see backend/app/services/cost_engine.py's own
docstrings) -- cargo lines get renamed, added, or dropped between
versions, and concessions/notes change independently of the numeric
rates. Blindly re-parsing a new PDF into the rate dictionaries risks
silently mis-transcribing a value, which is worse than staying on the
last known-good rates with a human in the loop. This script's job is
only to make sure that human finds out a new SOR/tariff circular
exists -- see cost_engine.py's TARIFF_VERSION / EFFECTIVE_TO for the
version it should be checked against.

Per SOR Chapter I, 1.2(xiv)(a): "The next annual indexation ... The
indexed SOR to be intimated by NMPA to the stakeholders" -- i.e. NMPA
itself says indexed-SOR updates get announced through this same
circular/trade-notice channel, so watching it is the textually
correct mechanism, not a guess.

Run manually:
    python -m backend.app.services.sor_watcher

Schedule it (pick one):
    Windows Task Scheduler -- run monthly, and weekly during
        April-May each year (annual re-indexation is 1 May).
    A scheduled GitHub Actions workflow, if this repo is hosted on
        GitHub, using the same cron cadence.

Exit code is 1 when a new SOR/tariff-looking circular is found (so a
scheduled job can treat that as "needs attention"), 0 otherwise.
"""

import json
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

CIRCULAR_PAGE_URL = "https://newmangaloreport.gov.in/circular-tradenotice"
BASE_URL = "https://newmangaloreport.gov.in"

MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "sor_watch_manifest.json"
)

# Keywords that suggest a circular is about the Scale of Rates itself,
# not routine port operations (dredging notices, health advisories, etc).
SOR_KEYWORDS = (
    "sor",
    "scale of rate",
    "schedule of rate",
    "indexed sor",
    "tariff",
    "wpi",
)

# The page renders one <a href="...pdf">title</a> per row, followed
# later in the same row by a "dd/mm/yyyy - hh:mm" last-updated stamp.
ROW_PATTERN = re.compile(
    r'href="(?P<href>/sites/default/files/[^"]+\.pdf)"[^>]*>\s*'
    r"(?P<title>[^<]*)</a>.*?"
    r"(?P<date>\d{2}/\d{2}/\d{4}\s*-\s*\d{2}:\d{2})",
    re.IGNORECASE | re.DOTALL,
)


def fetch_page(url: str) -> str:
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.SSLError:
        # NMPA's certificate chain fails standard verification as of
        # this writing (confirmed 2026-09-15). Falling back to an
        # unverified request is a real MITM risk on a hostile network
        # -- only acceptable here because this script only *reads* a
        # public government notice board and never sends credentials.
        warnings.warn(
            "TLS verification failed for newmangaloreport.gov.in; "
            "retrying without certificate verification.",
            stacklevel=2,
        )
        resp = requests.get(url, timeout=20, verify=False)
        resp.raise_for_status()
        return resp.text


def parse_entries(html: str) -> list[dict]:
    entries = []
    for m in ROW_PATTERN.finditer(html):
        href = m.group("href")
        title = m.group("title").strip() or href.rsplit("/", 1)[-1]
        entries.append(
            {
                "title": title,
                "url": urljoin(BASE_URL, href),
                "last_updated": m.group("date").strip(),
            }
        )
    return entries


def looks_like_sor(entry: dict) -> bool:
    haystack = (entry["title"] + " " + entry["url"]).lower()
    return any(kw in haystack for kw in SOR_KEYWORDS)


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"seen_urls": []}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def check_for_updates() -> list[dict]:
    """Fetch the circulars page and return any not-yet-seen SOR/tariff entries."""

    html = fetch_page(CIRCULAR_PAGE_URL)
    sor_entries = [e for e in parse_entries(html) if looks_like_sor(e)]

    manifest = load_manifest()
    seen_urls = set(manifest.get("seen_urls", []))

    new_entries = [e for e in sor_entries if e["url"] not in seen_urls]

    manifest["seen_urls"] = sorted(seen_urls | {e["url"] for e in sor_entries})
    manifest["last_checked"] = datetime.now(timezone.utc).isoformat()
    save_manifest(manifest)

    return new_entries


def main() -> int:
    new_entries = check_for_updates()

    if not new_entries:
        print("No new SOR/tariff-related circulars since last check.")
        return 0

    print(
        f"{len(new_entries)} new SOR/tariff-related circular(s) found "
        f"on {CIRCULAR_PAGE_URL}:\n"
    )
    for entry in new_entries:
        print(f"  - {entry['title']}")
        print(f"    {entry['url']}")
        print(f"    published: {entry['last_updated']}")
        print()

    print(
        "ACTION NEEDED: open the PDF(s) above, compare against the rate "
        "tables in backend/app/services/cost_engine.py, and re-transcribe "
        "any changed values by hand. Update TARIFF_VERSION / EFFECTIVE_FROM "
        "/ EFFECTIVE_TO once done."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
