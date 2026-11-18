"""The major-ports map must work without internet: its outline ships with the platform and Streamlit serves it."""
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_map_outline_ships_with_the_platform():
    f = ROOT / "frontend" / "static" / "topojson" / "asia_110m.json"
    assert f.exists() and f.stat().st_size > 10_000
    assert json.loads(f.read_text())["type"] == "Topology"


def test_static_serving_is_on_and_the_map_uses_it():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    assert cfg["server"]["enableStaticServing"] is True
    assert '"topojsonURL": "/app/static/topojson/"' in (ROOT / "frontend" / "app.py").read_text(encoding="utf-8")
