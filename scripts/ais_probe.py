"""AIS probe for New Mangalore Port (aisstream.io).

Listens to the live aisstream.io feed for a box around NMPA for a few minutes
and answers three questions before we build anything on it:

  1. How many ships does the free feed actually see off Mangalore?
  2. How many of them broadcast an IMO number (AIS Message 5 / static data)?
  3. Do those IMO numbers match the ships in NMPA's Daily Vessel Position
     report and our manual lookup (data/reference/vessel_imo_lookup.csv)?

The API key is NEVER stored in code. Put it in an environment variable or in
a `.env` file at the project root (which is git-ignored):

    AISSTREAM_API_KEY=your_key_here

Run (Windows):   scripts\\ais_probe.bat --minutes 10
Run (any OS):    python scripts/ais_probe.py --minutes 10 [--wide]

Outputs (data/ais/, git-ignored):
    ais_positions_<stamp>.csv   every position report received
    ais_static_<stamp>.csv      one row per ship: MMSI, IMO, call sign, type,
                                length, beam, draught, destination, AIS ETA
    ais_probe_<stamp>.txt       summary + match against our IMO lookup
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "ais"
IMO_LOOKUP = ROOT / "data" / "reference" / "vessel_imo_lookup.csv"
URL = "wss://stream.aisstream.io/v0/stream"

# [lat, lon] corners. Port basin + outer anchorage + approach channel.
BOX_PORT = [[12.55, 74.40], [13.30, 74.95]]
# Wider coastal approach (Karwar to Kasaragod, ~70 nm offshore) for ETA work.
BOX_WIDE = [[11.80, 73.40], [14.60, 75.00]]

# NMPA reference point (approx. harbour entrance) for distance-to-port.
PORT_LAT, PORT_LON = 12.925, 74.795

AIS_TYPE = {
    range(20, 30): "Wing in ground", range(30, 31): "Fishing",
    range(31, 33): "Towing", range(33, 34): "Dredging",
    range(35, 36): "Military", range(36, 37): "Sailing",
    range(37, 38): "Pleasure", range(40, 50): "High speed craft",
    range(50, 51): "Pilot", range(51, 52): "Search & rescue",
    range(52, 53): "Tug", range(53, 54): "Port tender",
    range(55, 56): "Law enforcement", range(60, 70): "Passenger",
    range(70, 80): "Cargo", range(80, 90): "Tanker",
}


def ship_type_name(code) -> str:
    try:
        code = int(code)
    except (TypeError, ValueError):
        return ""
    for rng, name in AIS_TYPE.items():
        if code in rng:
            return name
    return "Other" if code else ""


def imo_valid(imo) -> bool:
    """IMO check digit: sum(d_i * w_i, w = 7..2) mod 10 == last digit."""
    s = str(imo or "").strip()
    if not re.fullmatch(r"\d{7}", s) or s == "0000000":
        return False
    total = sum(int(d) * w for d, w in zip(s[:6], range(7, 1, -1)))
    return total % 10 == int(s[6])


def load_key() -> str:
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("AISSTREAM_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("AISSTREAM_API_KEY not set. Add it to .env at the project "
                 "root or set it as an environment variable.")
    return key


def norm_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 3440.065 * asin(sqrt(a))


NAV_STATUS = {0: "Under way (engine)", 1: "At anchor", 2: "Not under command",
              3: "Restricted manoeuvre", 5: "Moored", 7: "Fishing",
              8: "Under way (sailing)", 15: "Not defined"}


async def listen(key: str, box, minutes: float, ships: dict, pos_rows: list):
    try:
        import websockets
    except ImportError:
        sys.exit("Missing package: pip install websockets")

    sub = {
        "APIKey": key,
        "BoundingBoxes": [box],
        "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport",
                               "ShipStaticData", "StaticDataReport"],
    }
    deadline = time.monotonic() + minutes * 60
    last_note = 0.0
    while time.monotonic() < deadline:
        try:
            async with websockets.connect(URL, open_timeout=20) as ws:
                await ws.send(json.dumps(sub))  # must be sent within 3 s
                while time.monotonic() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        continue
                    msg = json.loads(raw)
                    if "error" in msg:
                        sys.exit(f"aisstream error: {msg['error']}")
                    handle(msg, ships, pos_rows)
                    now = time.monotonic()
                    if now - last_note > 30:
                        left = max(0, int((deadline - now) / 60))
                        with_imo = sum(1 for s in ships.values() if imo_valid(s.get("imo")))
                        print(f"  {len(ships):3d} ships seen, {with_imo:3d} with IMO, "
                              f"{len(pos_rows):5d} positions  (~{left} min left)")
                        last_note = now
        except SystemExit:
            raise
        except Exception as exc:  # network blip: reconnect
            print(f"  connection dropped ({exc.__class__.__name__}: {exc}); reconnecting in 5 s")
            await asyncio.sleep(5)


def handle(msg: dict, ships: dict, pos_rows: list):
    mtype = msg.get("MessageType")
    meta = msg.get("MetaData", {}) or {}
    body = (msg.get("Message", {}) or {}).get(mtype, {}) or {}
    mmsi = str(meta.get("MMSI") or body.get("UserID") or "")
    if not mmsi:
        return
    s = ships.setdefault(mmsi, {"mmsi": mmsi})
    if meta.get("ShipName", "").strip():
        s.setdefault("name", meta["ShipName"].strip())
    s["last_seen_utc"] = meta.get("time_utc", "")

    if mtype in ("PositionReport", "StandardClassBPositionReport"):
        lat, lon = body.get("Latitude", meta.get("latitude")), body.get("Longitude", meta.get("longitude"))
        nav = body.get("NavigationalStatus")
        row = {
            "time_utc": meta.get("time_utc", ""), "mmsi": mmsi,
            "name": s.get("name", ""), "lat": lat, "lon": lon,
            "sog_kn": body.get("Sog"), "cog": body.get("Cog"),
            "heading": body.get("TrueHeading"),
            "nav_status": NAV_STATUS.get(nav, nav if nav is not None else ""),
            "dist_to_port_nm": round(haversine_nm(lat, lon, PORT_LAT, PORT_LON), 1)
            if lat is not None and lon is not None else "",
        }
        pos_rows.append(row)
        s.update({"lat": lat, "lon": lon, "sog_kn": row["sog_kn"],
                  "nav_status": row["nav_status"], "dist_to_port_nm": row["dist_to_port_nm"]})

    elif mtype == "ShipStaticData":  # Class A, AIS Message 5
        dim = body.get("Dimension", {}) or {}
        eta = body.get("Eta", {}) or {}
        s.update({
            "name": (body.get("Name") or s.get("name", "")).strip(),
            "imo": str(body.get("ImoNumber") or "") or s.get("imo", ""),
            "call_sign": (body.get("CallSign") or "").strip(),
            "ais_type": body.get("Type"),
            "ship_type": ship_type_name(body.get("Type")),
            "length_m": (dim.get("A") or 0) + (dim.get("B") or 0) or "",
            "beam_m": (dim.get("C") or 0) + (dim.get("D") or 0) or "",
            "draught_m": body.get("MaximumStaticDraught"),
            "destination": (body.get("Destination") or "").strip(),
            "ais_eta": (f"{eta.get('Month', 0):02d}-{eta.get('Day', 0):02d} "
                        f"{eta.get('Hour', 0):02d}:{eta.get('Minute', 0):02d}") if eta else "",
            "class": "A",
        })
    elif mtype == "StaticDataReport":  # Class B (small craft, no IMO)
        a = body.get("ReportA", {}) or {}
        b = body.get("ReportB", {}) or {}
        if a.get("Valid") and a.get("Name", "").strip():
            s["name"] = a["Name"].strip()
        if b.get("Valid"):
            dim = b.get("Dimension", {}) or {}
            s.update({"call_sign": (b.get("CallSign") or "").strip(),
                      "ais_type": b.get("ShipType"),
                      "ship_type": ship_type_name(b.get("ShipType")),
                      "length_m": (dim.get("A") or 0) + (dim.get("B") or 0) or ""})
        s["class"] = "B"


def write_outputs(ships: dict, pos_rows: list, stamp: str, minutes: float, box) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    static_cols = ["mmsi", "imo", "imo_valid", "name", "call_sign", "ship_type", "ais_type",
                   "length_m", "beam_m", "draught_m", "destination", "ais_eta",
                   "nav_status", "sog_kn", "lat", "lon", "dist_to_port_nm", "class",
                   "last_seen_utc", "lookup_imo", "lookup_match"]

    lookup = {}
    if IMO_LOOKUP.exists():
        with IMO_LOOKUP.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lookup.setdefault(norm_name(r.get("vessel_name", "")), []).append(r)
    lookup_by_imo = {r["imo_number"]: r for rows in lookup.values() for r in rows}

    for s in ships.values():
        s["imo_valid"] = imo_valid(s.get("imo"))
        cands = lookup.get(norm_name(s.get("name", "")), [])
        if s["imo_valid"] and s["imo"] in lookup_by_imo:
            s["lookup_imo"], s["lookup_match"] = s["imo"], "IMO matches lookup"
        elif cands:
            s["lookup_imo"] = "/".join(c["imo_number"] for c in cands)
            s["lookup_match"] = ("NAME matches, IMO differs (different ship?)"
                                 if s["imo_valid"] else "NAME matches, no IMO in AIS")
        else:
            s["lookup_imo"], s["lookup_match"] = "", ""

    static_path = OUT_DIR / f"ais_static_{stamp}.csv"
    with static_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=static_cols, extrasaction="ignore")
        w.writeheader()
        for s in sorted(ships.values(), key=lambda x: (x.get("dist_to_port_nm") or 999)):
            w.writerow(s)

    pos_path = OUT_DIR / f"ais_positions_{stamp}.csv"
    with pos_path.open("w", newline="", encoding="utf-8") as f:
        cols = ["time_utc", "mmsi", "name", "lat", "lon", "sog_kn", "cog",
                "heading", "nav_status", "dist_to_port_nm"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(pos_rows)

    allv = list(ships.values())
    class_a = [s for s in allv if s.get("class") == "A"]
    with_imo = [s for s in allv if s["imo_valid"]]
    big = [s for s in allv if s.get("ship_type") in ("Cargo", "Tanker", "Passenger")]
    at_anchor = [s for s in allv if s.get("nav_status") == "At anchor"]
    moored = [s for s in allv if s.get("nav_status") == "Moored"]
    matched = [s for s in allv if s.get("lookup_match") == "IMO matches lookup"]
    conflict = [s for s in allv if "differs" in (s.get("lookup_match") or "")]

    lines = [
        f"AIS probe, New Mangalore Port, {stamp} (listened {minutes:g} min)",
        f"Box [lat, lon]: {box}",
        "",
        f"Ships seen (any AIS message):      {len(allv)}",
        f"  sent static data, Class A:       {len(class_a)}",
        f"  with a valid IMO number:         {len(with_imo)}",
        f"  cargo / tanker / passenger:      {len(big)}",
        f"  at anchor (nav status):          {len(at_anchor)}",
        f"  moored (nav status):             {len(moored)}",
        f"Position reports received:         {len(pos_rows)}",
        "",
        f"Matched to our IMO lookup by IMO:  {len(matched)}",
        f"Same name, different IMO:          {len(conflict)}",
        "",
        "Ships with IMO (nearest first):",
    ]
    for s in sorted(with_imo, key=lambda x: (x.get("dist_to_port_nm") or 999)):
        lines.append(f"  {s.get('name',''):<24} IMO {s['imo']}  MMSI {s['mmsi']}  "
                     f"{s.get('ship_type',''):<10} L={s.get('length_m','')}m  "
                     f"{s.get('nav_status','')}  {s.get('dist_to_port_nm','')} nm  "
                     f"dest={s.get('destination','')}  {s.get('lookup_match','')}")
    lines += ["", "Note: Class A static data (with IMO) is broadcast every 6 minutes, "
              "so a 10-minute run should catch most large ships in range.",
              "Terms: aisstream.io data is for our internal dashboard/demo; check "
              "their terms before republishing."]
    summary = OUT_DIR / f"ais_probe_{stamp}.txt"
    summary.write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--wide", action="store_true", help="use the wider coastal approach box")
    args = ap.parse_args()

    key = load_key()
    box = BOX_WIDE if args.wide else BOX_PORT
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%MZ")
    print(f"Listening to aisstream.io for {args.minutes:g} min, box {box} ...")
    ships, pos_rows = {}, []
    try:
        asyncio.run(listen(key, box, args.minutes, ships, pos_rows))
    except KeyboardInterrupt:
        print("Stopped early; writing what was received.")
    summary = write_outputs(ships, pos_rows, stamp, args.minutes, box)
    print()
    print(summary.read_text(encoding="utf-8"))
    print(f"\nFiles written to {OUT_DIR}")


if __name__ == "__main__":
    main()
