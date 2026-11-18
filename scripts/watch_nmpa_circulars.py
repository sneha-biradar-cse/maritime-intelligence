"""
Read NMPA's own circulars and trade notices page and add new notices to the platform's list (data/nmpa_circulars.json).

Runs ONLY after NMPA's permission for automated reading has been recorded in the platform (Schemes -> NMPA circulars),
because NMPA's website asks programs not to read it automatically. Without it, it prints a message and does nothing.
One page, one request, a pause before it; the first run records what is there as the starting point (marked done),
so only later notices are shown as new.

  python scripts/watch_nmpa_circulars.py            (part of the weekly refresh)
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PAGE = "https://newmangaloreport.gov.in/circular-tradenotice"
PAUSE_S = 5


def _reader():
    spec = importlib.util.spec_from_file_location("cw", ROOT / "scripts" / "watch_competitor_notices.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(fetch=None, pause: float = PAUSE_S) -> dict:
    from backend.app.services import nmpa_circulars as nc
    if not nc.permission()["granted"]:
        print("NMPA circulars: not read. NMPA's permission for automated reading is not recorded in the platform yet.")
        return {"read": False, "added": 0}
    cw = _reader()
    time.sleep(pause)
    html = (fetch or cw._get)(PAGE)
    items = cw.extract(html, PAGE, keep_all=True)
    first = not nc._load(nc.STORE, [])
    added = 0
    for it in items:
        try:
            r = nc.add(it["title"], it.get("date_on_page") or "", it["url"], by="weekly refresh", source="watch")
            added += 1
            if first:
                nc.mark_done(r["id"], "weekly refresh", "Starting point: already on NMPA's page at the first reading.")
        except ValueError:
            continue                                           # already listed, or not a notice title
    print(f"NMPA circulars: {len(items)} read, {added} new" + (" (first reading: recorded as the starting point)" if first else ""))
    return {"read": True, "added": added, "first": first}


if __name__ == "__main__":
    run()
