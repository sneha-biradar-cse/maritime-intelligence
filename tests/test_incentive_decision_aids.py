"""Growth check, schemes ending soon, and the Board note / trade notice Word drafts."""
import datetime as dt
import io
import re
import zipfile

from backend.app.services import incentive_decision_aids as da
from backend.app.services import incentive_engine as ie


def test_growth_check_arithmetic():
    g = da.growth_check("LPG", 10)
    assert g["available"]
    assert abs(g["need_pct"] - 10 / 90 * 100) < 0.06                      # discount / (1 - discount)
    assert g["periods"] == len(g["series"]) and 0 <= g["hits"] <= g["periods"]
    assert g["hits"] == sum(1 for p in g["series"] if p["growth_pct"] >= g["need_pct"] - 0.05)
    assert abs(g["share_pct"] - round(g["hits"] / g["periods"] * 100)) <= 1


def test_expiring_schemes_days_and_order():
    e = da.expiring_schemes(today=dt.date(2026, 11, 12))
    days = [r["days_left"] for r in e["rows"]]
    assert days == sorted(days) and all(d >= 0 for d in days)
    iron = next(r for r in e["rows"] if "IOF-Exp-Rebate" in r["notice"])
    assert iron["days_left"] == (dt.date(2027, 3, 31) - dt.date(2026, 11, 12)).days and iron["band"] == "Plan the review"
    jsw = next(r for r in e["rows"] if "JSW" in r["notice"])
    assert jsw["recommendation"].startswith("Look closer")                    # a broad check never gives a firm stop


def _text(docx_bytes):
    z = zipfile.ZipFile(io.BytesIO(docx_bytes))
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= set(z.namelist())
    return re.sub(r"<[^>]+>", " ", z.read("word/document.xml").decode())


def test_board_note_and_trade_notice(monkeypatch):
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_decision_aids.json")
    try:
        rec = ie.create_scheme("LPG", "Blanket discount", 10.0, "2027-01-01", "2027-03-31", 30_000_000, by="test",
                               stop_rule="Stop if LPG does not rise 5% in 2 months")
        note = _text(da.board_note_docx(rec["id"]))
        for must in ("AGENDA NOTE", "Section 27(1)", "1 January 2027", "Resolution sought", "LPG", "11.1%"):
            assert must in note, must
        assert not re.search(r"20\d\d-\d\d-\d\d", note)                    # dates in words, as in official notes
        cost = rec["rate_rs_per_t"] * 0.10 * rec["baseline_tonnes"] / 1e7
        assert f"Rs {cost:,.2f} crore" in note
        notice = _text(da.trade_notice_docx(rec["id"]))
        for must in ("TRADE NOTICE", "Board Resolution No.", "cannot be combined", "Traffic Manager"):
            assert must in notice, must
    finally:
        (ie._schemes_path()).unlink(missing_ok=True)
