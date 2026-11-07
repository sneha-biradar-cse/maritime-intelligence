"""
Monthly / daily update for Trade Intelligence - one command.

1. Put any new PDFs in the folder  incoming/  (daily vessel position reports, NMPA commodity-wise statements,
   NMPA container statements, NMPA Traffic & Performance reports, Ministry "Cargo handled at Major Ports" reports).
2. Run:  python scripts/update_trade_data.py
3. Restart the backend.

The script sorts each file to the right place (skipping exact duplicates, and stopping on a same-date file with
different contents), reads it, re-runs every check against the official figures, and writes data/last_update.json.

All or nothing: the data folder is copied before anything changes. If any step fails or any check fails, the data folder
is put back exactly as it was and the new PDFs are returned to incoming/, so the dashboard never shows a half-updated state.
Re-running with the same files changes nothing (identical files are recognised by their checksum and skipped).
Log sections: added, revised (an original that differs from the record held), verified, skipped (identical), rejected
(not recognised, or a different file for a date already held), checks.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
INBOX = ROOT / "incoming"
PUBLIC = ROOT / "nmpa_public_data"
DAILY_PDF = ROOT / "data" / "daily_vessel_position"
DAILY_JSON = ROOT / "data" / "daily_vessel_position_parsed"


DAILY_NAME = re.compile(r"^\d{2}[-_.]\d{2}[-_.]\d{4}(?:\s*\(\d+\)|_\d+)?\.pdf$", re.I)


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def kind_of(p: Path) -> str:
    n = p.name.lower()
    # A daily report is named ONLY by its date (01-09-2025.pdf, 01-09-2025 (1).pdf, 01-09-2025_0.pdf, 01.09.2025.pdf).
    # Other documents that merely start with a date (e.g. '05-09-2025-Revision-in-Credit-Rating-....pdf') are not daily reports.
    if DAILY_NAME.match(p.name):
        return "daily"
    if "major port" in n and "non" not in n:
        return "ministry"
    if "container traffic" in n or "container statement" in n:      # NMPA Statement II; not e.g. a company notice about a container terminal
        return "container"
    if "performance" in n:
        return "performance"
    if "commodity" in n:
        return "commodity"
    return "unknown"


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


class UpdateFailed(Exception):
    pass


def main() -> int:
    """Run the update inside a snapshot: on any failure, restore the data folder and return the new files to incoming/."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from _poppler import ensure_on_path
    ensure_on_path()                       # the project's own Poppler (tools/poppler), if installed
    INBOX.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap = ROOT / f".update_snapshot_{stamp}"
    shutil.copytree(ROOT / "data", snap / "data")
    moved: list[tuple[Path, Path]] = []
    try:
        code = _update(moved)
        shutil.rmtree(snap, ignore_errors=True)
        return code
    except Exception as e:                                   # roll back everything
        shutil.rmtree(ROOT / "data", ignore_errors=True)
        shutil.copytree(snap / "data", ROOT / "data")
        for src, dst in moved:
            if dst.exists():
                shutil.move(str(dst), src)
        shutil.rmtree(snap, ignore_errors=True)
        fail = {"failed": datetime.now().isoformat(timespec="seconds"), "error": str(e)[:500],
                "result": "Nothing changed: the data folder was restored and the new files are back in incoming/."}
        (ROOT / "data" / "last_update_failed.json").write_text(json.dumps(fail, indent=2), encoding="utf-8")
        print(json.dumps(fail, indent=2))
        return 2


def _update(moved: list) -> int:
    known = {md5(p) for p in list(PUBLIC.glob("*.pdf")) + list(DAILY_PDF.glob("*.pdf"))}
    log = {"started": datetime.now().isoformat(timespec="seconds"), "added": [], "revised": [], "verified": [], "skipped": [],
           "rejected": [], "problems": [], "checks": {}}
    verified_days, corrected_days = [], []
    todo = {"commodity": []}
    for p in sorted(INBOX.glob("*.pdf")):
        h = md5(p)
        if h in known:
            log["skipped"].append(f"{p.name}: already held (identical file)")
            p.unlink()
            continue
        k = kind_of(p)
        if k == "daily":
            d = re.sub(r"[_.]", "-", re.match(r"(\d{2}[-_.]\d{2}[-_.]\d{4})", p.name).group(1))
            dst = DAILY_PDF / f"{d}.pdf"
            if dst.exists():
                log["rejected"].append(f"{p.name}: a different report for {d} is already held - check which one is correct")
                continue
            from backend.app.services import vessel_position_parser as vp
            shutil.move(str(p), dst)
            moved.append((p, dst))
            parsed = asdict(vp.parse_pdf(dst))
            jp = DAILY_JSON / f"{d}.json"
            if jp.exists():
                # An original arriving for a day already held as JSON: compare, then keep the reading of the PDF.
                key = lambda rows: sorted((str(r.get("berth_no") or ""), str(r.get("vessel_name") or "").strip(),
                                           str(r.get("cargo") or "").strip(), str(r.get("qty_total") or "").strip()) for r in rows)
                old = json.loads(jp.read_text(encoding="utf-8"))
                strip = lambda j: {k: v for k, v in j.items() if k != "unparsed_rows"}
                same = strip(old) == strip(json.loads(json.dumps(parsed)))          # every field, not only the main ones
                cargo_same = (key(old.get("berthed", [])) == key(parsed["berthed"])
                              and len(old.get("anchorage", [])) == len(parsed["anchorage"])
                              and len(old.get("expected", [])) == len(parsed["expected"]))
                if not same:
                    jp.with_suffix(".json.before_pdf").write_text(jp.read_text(encoding="utf-8"), encoding="utf-8")
                    corrected_days.append(d)
                log["verified" if same else "revised"].append(
                    f"daily report {d}: " + ("original PDF matches the data held in every field" if same else
                    ("original PDF differs in minor fields (dates or the movements list); " if cargo_same else
                     "original PDF DIFFERS in ships, cargo or quantities; ") + "old copy kept as .json.before_pdf; PDF reading now used"))
                if same:
                    verified_days.append(d)
            jp.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            log["added"].append(f"daily report {d}: {len(parsed['berthed'])} berths, {len(parsed['unparsed_rows'])} unread rows")
        elif k == "unknown":
            log["rejected"].append(f"{p.name}: not recognised - rename it like the files in nmpa_public_data/ (left in incoming/)")
        else:
            dst = PUBLIC / p.name
            shutil.move(str(p), dst)
            moved.append((p, dst))
            known.add(h)
            log["added"].append(f"{k}: {p.name}")
            if k == "commodity":
                todo["commodity"].append(dst)
    statements_added = any(not a.startswith("daily report") for a in log["added"])
    if statements_added and shutil.which("pdftotext") is None:
        raise UpdateFailed(
            "New NMPA / Ministry statements need the free Poppler tools (pdftotext), which are not installed on this computer. "
            "Run:  python scripts\\setup_poppler.py  (installs it into the project's own folder, fingerprint-checked), "
            "then run the update again; scripts\\refresh_all.py does this automatically. Daily vessel reports do not need Poppler.")
    if not statements_added:
        log["checks"]["statements"] = "no new statements: NMPA and Ministry figures left as they are"
    for pdf in todo["commodity"]:
        code, out = run(["scripts/verify_trade_against_nmpa.py", str(pdf), "--append"])
        log["checks"][f"commodity statement {pdf.name}"] = "OK" if code == 0 else "FAILED: " + (out.splitlines()[-1][:300] if out else "")
    if statements_added:                      # re-read the statements only when a new one arrived (needs Poppler)
        for script in ("parse_ministry_major_ports.py", "parse_ministry_commodities.py", "parse_nmpa_performance.py",
                       "parse_nmpa_containers.py"):
            code, out = run([f"scripts/{script}"])
            log["checks"][script] = (out.splitlines()[-1] if out else "ok") if code == 0 else "FAILED: " + out[-300:]
        _sync_overseas_coastal(log)
        code, out = run(["scripts/verify_ministry_overseas_coastal.py"])
        log["checks"]["ministry overseas/coastal vs PDFs"] = (out.splitlines()[-1] if out else "OK") if code == 0 else "FAILED: " + out[-300:]
    code, out = run(["scripts/build_daily_manifest.py", "--verified", *verified_days, "--corrected", *corrected_days])
    log["checks"]["daily report manifest"] = (out.splitlines()[-1] if out else "ok") if code == 0 else "FAILED: " + out[-300:]
    code, out = run(["scripts/build_source_register.py"])
    log["checks"]["source register"] = (out.splitlines()[-1] if out else "ok") if code == 0 else "FAILED: " + out[-300:]
    failed = [k for k, v in log["checks"].items() if str(v).startswith("FAILED")]
    if failed:
        raise UpdateFailed("check(s) failed: " + "; ".join(f"{k}: {log['checks'][k]}" for k in failed))
    try:
        from backend.app.services import incentive_engine as ie
        log["data_current"] = ie.data_version()
    except Exception as e:                                   # the update itself succeeded; report, do not roll back
        log["data_current"] = f"could not be read: {e}"
    log["finished"] = datetime.now().isoformat(timespec="seconds")
    (ROOT / "data" / "last_update.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps(log, indent=2))
    print("\nDone. Restart the backend so the dashboard reads the new data." if not (log["problems"] or log["rejected"])
          else "\nDone. Some files were not used (see 'rejected'); the rest is updated. Restart the backend.")
    return 1 if (log["problems"] or log["rejected"]) else 0


def _sync_overseas_coastal(log: dict) -> None:
    """Add any month the Ministry file now covers to data/port_overseas_coastal_monthly.csv (New Mangalore row)."""
    import pandas as pd
    mp = pd.read_csv(ROOT / "data" / "major_ports_monthly.csv")
    nm = mp[mp["port"] == "New Mangalore"].set_index("month")
    oc_path = ROOT / "data" / "port_overseas_coastal_monthly.csv"
    oc = pd.read_csv(oc_path)
    added = []
    for m in nm.index:
        prev = f"{int(m[:4]) - 1}{m[4:]}"
        if m in set(oc["month"]) or prev not in nm.index or m < oc["month"].min():
            continue
        r, pv = nm.loc[m], nm.loc[prev]
        oc = pd.concat([oc, pd.DataFrame([{
            "month": m, "overseas_t": int(r.overseas_t), "coastal_t": int(r.coastal_t), "total_t": int(r.total_t),
            "prev_year_overseas_t": int(pv.overseas_t), "prev_year_coastal_t": int(pv.coastal_t), "prev_year_total_t": int(pv.total_t),
            "basis": "derived_from_cumulative" if str(r.basis).startswith("derived") else "advance_estimate",
            "source": "data/major_ports_monthly.csv (Ministry Table-1)"}])])
        added.append(m)
    if added:
        oc.sort_values("month").to_csv(oc_path, index=False)
    log["checks"]["overseas/coastal months added"] = ", ".join(added) or "none new"


if __name__ == "__main__":
    sys.exit(main())
