"""Official NMPA performance and container commodity data: parsed figures equal the printed ones."""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import trade_containers as tco
from backend.app.services import trade_performance as tp

client = TestClient(app)


def _perf():
    return pd.read_csv(tp.FILE)


def _val(d, month, metric, cat, year, basis=""):
    x = d[(d.report_month == month) & (d.period == "month") & (d.metric == metric) & (d.category == cat)
          & (d.year == year) & (d.basis.fillna("") == basis)]
    return float(x.value.iloc[0])


def test_august_2026_report_values_as_printed():
    d = _perf()
    assert _val(d, "2026-08", "pre_berthing_detention_days", "liquid_bulk", "current", "other_than_port_account") == 1.17
    assert _val(d, "2026-08", "pre_berthing_detention_days", "liquid_bulk", "previous", "other_than_port_account") == 0.69
    assert _val(d, "2026-08", "pre_berthing_detention_days", "liquid_bulk", "current", "port_account") == 0.04
    assert _val(d, "2026-08", "traffic_t", "overall", "current") == 3_885_913
    assert _val(d, "2026-08", "vessels", "overall", "current") == 107


def test_targets_read_from_nmpa_reports():
    d = _perf()
    t = d[d.metric == "traffic_target_t"].set_index("report_month")["value"]
    assert t["2026-08"] == 53_000_000 and t["2025-08"] == 48_500_000


def test_report_traffic_equals_ministry_total():
    d = _perf()
    oc = pd.read_csv(tp.ROOT / "data" / "port_overseas_coastal_monthly.csv").set_index("month")
    assert _val(d, "2026-08", "traffic_t", "overall", "current") == oc.loc["2026-08", "total_t"]


def test_container_commodities_add_up_to_printed_totals():
    d = pd.read_csv(tco.FILE)
    aug = d[d.month == "2026-08"]
    # Printed TOTAL tonnage minus printed tare weight, August 2026 (Statement II)
    assert aug[aug.direction == "export"].t_month.sum() == 87_692 - 17_761
    assert abs(aug[aug.direction == "import"].t_month.sum() - (123_802 - 14_946)) <= 2


def test_liquid_waiting_shares_are_consistent():
    p = tp.get_official_performance()
    total = sum(r["share_of_liquid_waiting_pct"] for r in p["liquid_waiting_by_customer"])
    assert total <= 100.5


@pytest.mark.parametrize("url", ["/trade/performance", "/trade/containers"])
def test_endpoints_ok_no_nan(url):
    r = client.get(url)
    assert r.status_code == 200 and r.json()["available"]
    json.loads(r.text, parse_constant=lambda c: pytest.fail(f"non-finite {c}"))
