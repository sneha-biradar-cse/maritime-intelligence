"""
Fetch the PUBLIC data the Incentive Engine improvements need, and save it in the project with its source.

  python scripts/fetch_public_incentive_data.py vessel-gt      ship sizes (gross tonnage) from Wikidata, a free public
                                                               register, matched to the ships in NMPA's daily reports
  python scripts/fetch_public_incentive_data.py fx             USD -> INR rates (ECB reference rates via the Frankfurter API)
  python scripts/fetch_public_incentive_data.py fx --rbi-file RBI_reference_rates.csv
                                                               load RBI / FBIL reference rates you downloaded (the rate the
                                                               Scale of Rates actually uses); these win over ECB rates
  python scripts/fetch_public_incentive_data.py other-ports    download the source documents of other ports' schemes listed in
                                                               data/other_ports_schemes.csv into nmpa_public_data/other_ports/
  python scripts/fetch_public_incentive_data.py all            all three (no RBI file)
  Add --dry-run to see what would be fetched without saving anything.

What each source is good for:
  * Wikidata holds gross tonnage for well-known ships only, matched here by NAME. A ship can be renamed and two ships can
    share a name, so these sizes are labelled "public register (name match)" and are for planning only. The sizes on NMPA's
    own port-dues bills (put them in data/vessel_gt.csv) always win.
  * ECB rates are close to, but not the same as, the RBI reference rate the Scale of Rates uses; they are labelled
    "estimate". RBI/FBIL rates loaded with --rbi-file are labelled official.
  * Other ports' documents are archived so every scheme in the catalogue can be read in the original.

Polite: one request at a time, a pause between requests, a clear User-Agent; documents already held are not downloaded again.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HEADERS = {"User-Agent": "YellowSense-MPIP/1.0 (NMPA incentive engine; public data; polite) python-requests"}
WIKIDATA = "https://query.wikidata.org/sparql"
FX_URLS = ["https://api.frankfurter.dev/v1/{a}..{b}?base=USD&symbols=INR", "https://api.frankfurter.app/{a}..{b}?from=USD&to=INR"]
GT_PUBLIC = ROOT / "data" / "vessel_gt_public.csv"
FX_FILE = ROOT / "data" / "fx_usd_inr.csv"
OTHER_PORTS = ROOT / "data" / "other_ports_schemes.csv"
OTHER_OUT = ROOT / "nmpa_public_data" / "other_ports"
OTHER_CATALOG = ROOT / "data" / "other_ports_sources_catalog.csv"

# Every item on Wikidata with an IMO ship number (P458) and a gross tonnage (P1093).
SPARQL_GT = """SELECT ?item ?itemLabel ?imo ?gt WHERE {
  ?item wdt:P458 ?imo ; wdt:P1093 ?gt .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}"""


def _session():
    import requests
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def norm(name: str) -> str:
    """Same rule as the daily reports: upper case, notes in brackets removed, single spaces, no punctuation."""
    n = re.sub(r"\(.*?\)", "", str(name or "")).upper()
    n = re.sub(r"^(MV|M\.V\.|MT|M\.T\.)\s+", "", n.strip())
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# ── ship sizes ─────────────────────────────────────────────────────────────────────────────────────────
def parse_wikidata(payload: dict) -> list[dict]:
    rows = []
    for b in payload.get("results", {}).get("bindings", []):
        try:
            gt = float(b["gt"]["value"])
        except (KeyError, ValueError):
            continue
        label = b.get("itemLabel", {}).get("value", "")
        if not label or re.fullmatch(r"Q\d+", label) or gt <= 0:
            continue
        rows.append({"label": label, "imo": b.get("imo", {}).get("value", ""), "gt": gt,
                     "item": b.get("item", {}).get("value", "")})
    return rows


def match_ships(register: list[dict], names: list[str]) -> tuple[list[dict], list[str]]:
    """Exact match on the normalised name. A name shared by ships with different sizes is skipped (ambiguous)."""
    by: dict[str, list[dict]] = {}
    for r in register:
        by.setdefault(norm(r["label"]), []).append(r)
    out, ambiguous = [], []
    for n in sorted(set(names)):
        hits = by.get(norm(n), [])
        if not hits:
            continue
        sizes = {round(h["gt"]) for h in hits}
        if len(sizes) > 1:
            ambiguous.append(n)
            continue
        h = hits[0]
        out.append({"vessel_name": n, "imo": h["imo"], "gt": round(h["gt"]), "matched_label": h["label"],
                    "source": f"Wikidata {h['item'].rsplit('/', 1)[-1]} (name match; confirm with IMO number)",
                    "retrieved": date.today().isoformat()})
    return out, ambiguous


def project_ship_names() -> list[str]:
    names = set()
    reg = ROOT / "data" / "vessel_registry.json"
    if reg.exists():
        names |= set(json.loads(reg.read_text(encoding="utf-8")))
    stays = ROOT / "data" / "vessel_stays.json"
    if stays.exists():
        names |= {s["vessel_norm"] for s in json.loads(stays.read_text(encoding="utf-8"))}
    return sorted(n for n in names if n and not re.match(r"^\d+\s|TUG|PILOT|DREDG|BARGE", n))


def cmd_vessel_gt(dry: bool) -> int:
    names = project_ship_names()
    print(f"Ships in the project's daily reports: {len(names)}")
    if dry:
        print(f"Would query {WIKIDATA} once (all ships with an IMO number and a gross tonnage) and match by name.")
        return 0
    s = _session()
    r = s.get(WIKIDATA, params={"query": SPARQL_GT, "format": "json"}, timeout=120,
              headers={"Accept": "application/sparql-results+json"})
    r.raise_for_status()
    register = parse_wikidata(r.json())
    print(f"Wikidata ships with a gross tonnage: {len(register)}")
    rows, ambiguous = match_ships(register, names)
    GT_PUBLIC.parent.mkdir(exist_ok=True)
    with GT_PUBLIC.open("w", newline="", encoding="utf-8") as f:
        f.write("# Ship sizes from a public register (Wikidata), matched by NAME to ships in NMPA's daily reports.\n")
        f.write("# For planning only; sizes from NMPA's own bills go in data/vessel_gt.csv and always win.\n")
        w = csv.DictWriter(f, fieldnames=["vessel_name", "imo", "gt", "matched_label", "source", "retrieved"])
        w.writeheader()
        w.writerows(rows)
    print(f"Matched {len(rows)} of {len(names)} ships ({len(ambiguous)} names skipped as ambiguous) -> {GT_PUBLIC.relative_to(ROOT)}")
    if len(rows) < 50:
        print("Coverage is low: Wikidata lists mainly well-known ships. The reliable source is NMPA's port-dues bills "
              "(GRT is printed on each); put them in data/vessel_gt.csv (vessel_name, imo, gt, source).")
    return 0


# ── exchange rates ────────────────────────────────────────────────────────────────────────────────────
def parse_frankfurter(payload: dict) -> list[dict]:
    return [{"date": d, "usd_inr": round(float(v["INR"]), 4), "source": "ECB reference rate via Frankfurter API (estimate)"}
            for d, v in sorted(payload.get("rates", {}).items()) if "INR" in v]


def parse_rbi_table(path: Path) -> list[dict]:
    """A CSV or Excel file downloaded from the RBI / FBIL reference-rate page: a date column and a US dollar column."""
    import pandas as pd
    df = pd.read_excel(path) if path.suffix.lower() in (".xls", ".xlsx") else pd.read_csv(path)
    dcol = next((c for c in df.columns if re.search(r"date", str(c), re.I)), None)
    ucol = next((c for c in df.columns if re.search(r"\bUSD\b|US\s*DOLLAR|DOLLAR", str(c), re.I)), None)
    if dcol is None or ucol is None:
        raise ValueError(f"could not find a date column and a US dollar column in {path.name}: {list(df.columns)}")
    out = []
    for d, u in zip(pd.to_datetime(df[dcol], dayfirst=True, errors="coerce"), pd.to_numeric(df[ucol], errors="coerce")):
        if pd.notna(d) and pd.notna(u) and u > 0:
            out.append({"date": d.strftime("%Y-%m-%d"), "usd_inr": round(float(u), 4),
                        "source": f"RBI/FBIL reference rate (official; file {path.name})"})
    return out


def merge_fx(existing: list[dict], new: list[dict]) -> list[dict]:
    """One rate per date; an official RBI/FBIL rate is never replaced by an estimate."""
    by = {r["date"]: r for r in existing}
    for r in new:
        old = by.get(r["date"])
        if old and "official" in old["source"].lower() and "official" not in r["source"].lower():
            continue
        by[r["date"]] = r
    return [by[d] for d in sorted(by)]


def _read_fx() -> list[dict]:
    if not FX_FILE.exists():
        return []
    with FX_FILE.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(line for line in f if not line.startswith("#"))]


def _write_fx(rows: list[dict]) -> None:
    with FX_FILE.open("w", newline="", encoding="utf-8") as f:
        f.write("# USD -> INR. The Scale of Rates uses the RBI reference rate on the day a ship enters; ECB rates are estimates.\n")
        w = csv.DictWriter(f, fieldnames=["date", "usd_inr", "source"])
        w.writeheader()
        w.writerows(rows)


def cmd_fx(dry: bool, rbi_file: str | None, start: str) -> int:
    new = []
    if rbi_file:
        new = parse_rbi_table(Path(rbi_file))
        print(f"RBI/FBIL file: {len(new)} rates")
    else:
        a, b = start, date.today().isoformat()
        if dry:
            print("Would fetch " + FX_URLS[0].format(a=a, b=b))
            return 0
        s = _session()
        for u in FX_URLS:
            try:
                r = s.get(u.format(a=a, b=b), timeout=60)
                r.raise_for_status()
                new = parse_frankfurter(r.json())
                if new:
                    break
            except Exception as e:                    # try the next address
                print(f"  {u.split('/')[2]}: {e}")
        print(f"ECB rates fetched: {len(new)}")
    if dry:
        return 0
    if not new:
        print("Nothing fetched; data/fx_usd_inr.csv left unchanged.")
        return 1
    rows = merge_fx(_read_fx(), new)
    _write_fx(rows)
    print(f"{len(rows)} rates now in {FX_FILE.relative_to(ROOT)}")
    return 0


# ── other ports' documents ──────────────────────────────────────────────────────────────────────────────
def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9 ._()-]", "_", name).strip()[:120]


def cmd_other_ports(dry: bool, pause: float) -> int:
    import pandas as pd
    d = pd.read_csv(OTHER_PORTS, dtype=str).fillna("")
    urls, seen = [], set()
    for r in d.itertuples():
        if r.source_url.startswith("http") and r.source_url not in seen:
            seen.add(r.source_url)
            urls.append((r.port, r.scheme, r.source_url))
    print(f"Source documents listed: {len(urls)}")
    held = {}
    if OTHER_CATALOG.exists():
        for r in csv.DictReader(OTHER_CATALOG.open(encoding="utf-8")):
            held[r["url"]] = r
    s = None if dry else _session()
    out = []
    for port, scheme, url in urls:
        if url in held and held[url].get("status") == "saved" and (ROOT / held[url]["file"]).exists():
            out.append(held[url])
            continue
        if dry:
            print(f"  would fetch {url}")
            continue
        rec = {"port": port, "scheme": scheme, "url": url, "file": "", "sha256": "", "status": "", "fetched": datetime.now().isoformat(timespec="seconds")}
        try:
            r = s.get(url, timeout=60)
            r.raise_for_status()
            ext = ".pdf" if "pdf" in r.headers.get("Content-Type", "").lower() or url.lower().endswith(".pdf") else ".html"
            base = _safe(unquote(Path(urlparse(url).path).stem) or "document")
            folder = OTHER_OUT / _safe(port)
            folder.mkdir(parents=True, exist_ok=True)
            f = folder / (base + ext)
            f.write_bytes(r.content)
            rec.update({"file": str(f.relative_to(ROOT)), "sha256": hashlib.sha256(r.content).hexdigest(), "status": "saved"})
        except Exception as e:
            rec["status"] = f"failed: {e}"[:200]
        print(f"  {rec['status']:<10} {port}: {url}")
        out.append(rec)
        time.sleep(pause)
    if not dry:
        with OTHER_CATALOG.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["port", "scheme", "url", "file", "sha256", "status", "fetched"])
            w.writeheader()
            w.writerows(out)
        print(f"Catalogue: {OTHER_CATALOG.relative_to(ROOT)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["vessel-gt", "fx", "other-ports", "all"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rbi-file", help="CSV/Excel of RBI or FBIL reference rates (fx only)")
    ap.add_argument("--fx-start", default="2025-04-01", help="first date for ECB rates (fx only)")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between downloads (other-ports)")
    a = ap.parse_args(argv)
    rc = 0
    if a.what in ("vessel-gt", "all"):
        rc |= cmd_vessel_gt(a.dry_run)
    if a.what in ("fx", "all"):
        rc |= cmd_fx(a.dry_run, a.rbi_file, a.fx_start)
    if a.what in ("other-ports", "all"):
        rc |= cmd_other_ports(a.dry_run, a.pause)
    return rc


if __name__ == "__main__":
    sys.exit(main())
