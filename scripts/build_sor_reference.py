"""
Locate every Scale of Rates line used by the Incentive Engine in NMPA's tariff PDF and record its page, so the
dashboard can show "where this rate comes from" without needing PDF tools on the server.
Writes data/sor_reference.json. Re-run after a new Scale of Rates is added.

Usage: python scripts/build_sor_reference.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.services import incentive_engine as ie  # noqa: E402


def main() -> None:
    pdf = ROOT / ie.SOR_FILE
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    pages = text.split("\f")
    ref = {}
    for name, c in ie.CARGO.items():
        r = ie._rate(c["rate"])
        a, b = f"{r['coastal']:.2f}", f"{r['foreign']:.2f}"
        kw = c.get("sor_find", "")
        hit = None
        for n, page in enumerate(pages, 1):
            for line in page.splitlines():
                if a in line and b in line and line.index(a) < line.rindex(b) and (not kw or kw.lower() in line.lower()):
                    printed = re.search(r"-\s*(\d+)\s*-", page)
                    hit = {"pdf_page": n, "printed_page": int(printed.group(1)) if printed else None,
                           "line": re.sub(r"\s{2,}", "  ", line.strip())}
                    break
            if hit:
                break
        if not hit:
            raise SystemExit(f"{name}: rate {a} / {b} not found in {pdf.name}")
        ref[c["rate"]] = hit
    out = {"file": ie.SOR_FILE, "lines": ref}
    (ROOT / "data" / "sor_reference.json").write_text(json.dumps(out, indent=2))
    print(f"{len(ref)} tariff lines located -> data/sor_reference.json")


if __name__ == "__main__":
    main()
