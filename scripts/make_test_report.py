"""
Run the full test suite and write TEST_REPORT.md: date, Python and package versions, totals, and every test with its result,
so anyone can check the claim independently. Usage: python scripts/make_test_report.py
"""
from __future__ import annotations

import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    xml = ROOT / ".test_results.xml"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"], cwd=ROOT,
                       capture_output=True, text=True)
    suite = ET.parse(xml).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    rows = []
    for tc in suite.iter("testcase"):
        res = "failed" if tc.find("failure") is not None or tc.find("error") is not None else (
            "skipped" if tc.find("skipped") is not None else "passed")
        rows.append((tc.get("classname", "").replace("tests.", ""), tc.get("name"), res, float(tc.get("time", 0))))
    xml.unlink(missing_ok=True)
    total, failed = len(rows), sum(1 for x in rows if x[2] == "failed")
    skipped = sum(1 for x in rows if x[2] == "skipped")
    try:
        import pandas, fastapi
        versions = f"pandas {pandas.__version__}, fastapi {fastapi.__version__}"
    except Exception:
        versions = ""
    lines = [f"# Test report", "", f"Run: {datetime.now().isoformat(timespec='seconds')}  ",
             f"Python {platform.python_version()} on {platform.system()}; {versions}  ",
             f"Command: `python -m pytest -q` from the project folder (re-run with `python scripts/make_test_report.py`)", "",
             f"**{total - failed - skipped} passed, {failed} failed, {skipped} skipped, {total} in total.**", "",
             "What the tests check: every tariff rate used against the Scale of Rates PDF; data files against the official reports; "
             "the incentive rules (eligibility, baselines, slabs, approvals, amendments); the end-to-end workflow; the monthly "
             "update (rollback on failure, safe re-run). They run on the data held in this project.", "",
             "| File | Test | Result | Seconds |", "|---|---|---|---|"]
    lines += [f"| {c} | {n} | {res} | {t:.2f} |" for c, n, res, t in sorted(rows)]
    (ROOT / "TEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{total - failed - skipped} passed, {failed} failed, {skipped} skipped -> TEST_REPORT.md")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
