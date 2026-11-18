"""
Container cargo by commodity - what Mangalore's hinterland imports and exports in boxes.

Data (real): data/nmpa_container_commodities.csv, read from NMPA's monthly Statement II
("Containerised traffic handled during <month>") by scripts/parse_nmpa_containers.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.services.forecasting import _ttl_cache

ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / "data" / "nmpa_container_commodities.csv"


def _pct(a: float, b: float) -> float | None:
    return round((a / b - 1) * 100, 1) if b else None


@_ttl_cache(seconds=300)
def get_container_trade() -> dict[str, Any]:
    if not FILE.exists():
        return {"available": False}
    d = pd.read_csv(FILE)
    month = sorted(d["month"].unique())[-1]
    x = d[(d["month"] == month) & (d["commodity"].str.lower() != "others")]
    m = pd.Timestamp(month + "-01")
    ytd_label = f"April to {m.strftime('%B %Y')}"
    out = {}
    for direction in ("import", "export"):
        g = x[x["direction"] == direction].sort_values("teu_ytd", ascending=False)
        tot = d[(d["month"] == month) & (d["direction"] == direction)]
        rows = [{"commodity": r.commodity, "teu_ytd": int(r.teu_ytd), "teu_ytd_prev": int(r.teu_ytd_prev),
                 "teu_growth_pct": _pct(r.teu_ytd, r.teu_ytd_prev), "tonnes_ytd": int(r.t_ytd),
                 "teu_month": int(r.teu_month), "teu_month_prev": int(r.teu_month_prev),
                 "share_pct": round(r.teu_ytd / tot["teu_ytd"].sum() * 100, 1) if tot["teu_ytd"].sum() else None}
                for r in g.itertuples() if r.teu_ytd > 0 or r.teu_ytd_prev > 0]
        out[direction] = {"commodities": rows, "laden_teu_ytd": int(tot["teu_ytd"].sum()),
                          "laden_teu_ytd_prev": int(tot["teu_ytd_prev"].sum()),
                          "growth_pct": _pct(tot["teu_ytd"].sum(), tot["teu_ytd_prev"].sum())}
    big = lambda rows: [r for r in rows if r["teu_ytd_prev"] >= 500]
    movers = sorted(big(out["import"]["commodities"]) + big(out["export"]["commodities"]),
                    key=lambda r: abs(r["teu_ytd"] - r["teu_ytd_prev"]), reverse=True)[:4]
    monthly = (d.groupby(["month", "direction"])["teu_month"].sum().unstack(fill_value=0).reset_index())
    trend = [{"month": r["month"], "import_teu": int(r.get("import", 0)), "export_teu": int(r.get("export", 0))}
             for _, r in monthly.iterrows()]
    return {"available": True, "month": month, "ytd_label": ytd_label, **out, "monthly_laden_teu": trend,
            "biggest_changes": [{"commodity": r["commodity"], "change_teu": r["teu_ytd"] - r["teu_ytd_prev"],
                                 "growth_pct": r["teu_growth_pct"]} for r in movers],
            "source": f"NMPA Statement II, containerised traffic, {m.strftime('%B %Y')} (data/nmpa_container_commodities.csv)",
            "limits": ["Laden boxes only (empty boxes and tare weight are left out).",
                       "'Others' is not shown as a commodity."]}
