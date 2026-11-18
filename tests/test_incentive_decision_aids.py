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


def test_berth_check():
    r = da.berth_check("LPG", 11.1)
    assert r["available"] and r["rows"]
    occ = ie._berth_occupancy()
    fam = occ["fam_berths"][tuple(ie.CARGO["LPG"]["family"])]
    assert sum(fam[x["berth"]] for x in r["rows"]) >= 0.8 * sum(fam.values())          # berths carrying 80% of LPG
    for x in r["rows"]:
        assert x["busy_after_pct"] >= x["busy_now_pct"] and 0 <= x["busy_now_pct"] <= 100
        order = {"Room": 0, "Some room": 1, "Busy": 2}
        expected = max([v for v in (da._verdict(x["busy_after_pct"]), da._cap_verdict(x["capacity_used_after_pct"])) if v], key=order.get)
        assert x["verdict_after"] == expected                                          # the stricter of the two checks
    assert da._verdict(64.9) == "Room" and da._verdict(70) == "Some room" and da._verdict(80.1) == "Busy"
    assert da.berth_check("LPG", 0)["rows"][0]["busy_after_pct"] == r["rows"][0]["busy_now_pct"]
    assert not da.berth_check("Crude oil out of ISPRL", 11.1)["available"]              # no berth record: say so, never guess


def test_pool_guarantees():
    a = da.allocate_pool({"A": 300, "B": 100, "C": -50}, pool_rs=1000, cap_rs_per_t=1e9)    # no cap biting
    pay = {r["customer"]: r["pay_rs"] for r in a["rows"]}
    assert pay == {"A": 750, "B": 250, "C": 0}                                         # proportional; falling cargo gets nothing
    assert a["paid_rs"] + a["unspent_rs"] == a["pool_rs"] == 1000
    b = da.allocate_pool({"A": 300, "B": 100}, pool_rs=1000, cap_rs_per_t=2.0)          # cap: at most 2 per extra tonne
    assert {r["customer"]: r["pay_rs"] for r in b["rows"]} == {"A": 600, "B": 200}
    assert b["paid_rs"] == 800 and b["unspent_rs"] == 200 and all(r["capped"] for r in b["rows"])
    assert da.allocate_pool({"A": -10}, 1000, 5)["paid_rs"] == 0                        # nobody grew: nothing paid


def test_pool_simulation_never_exceeds_budget():
    for cargo in ("LPG", "Crude oil", "Iron ore exports"):
        r = da.pool_simulation(cargo, 2e7, 50)
        if r["available"]:
            assert r["paid_rs"] <= r["pool_rs"] and abs(r["paid_rs"] + r["unspent_rs"] - r["pool_rs"]) <= 1
            assert all(x["pay_per_extra_t_rs"] <= r["cap_rs_per_t"] + 0.01 for x in r["rows"] if x["extra_t"])


def test_nmpa_berth_capacity_and_estimates():
    import pandas as pd
    cap = pd.read_csv(ie.tmk.ROOT / "data" / "nmpa_berth_capacity.csv", dtype={"berth": str})
    assert len(cap) == 17 and abs(cap.usable_capacity_mt.sum() - 74) < 0.5 and abs(cap.rated_capacity_mt.sum() - 105) < 0.5
    assert (cap.usable_capacity_mt <= cap.rated_capacity_mt).all()
    est = da.berth_tonnes_12m()["berths"]
    for k, v in est.items():
        assert (v["tonnes"] is None) == (v["covered_share"] < da.MIN_COVERED)              # estimated only where covered
    crude = {r["berth"]: r for r in da.berth_check("Crude oil", 11.1)["rows"]}
    assert crude["SPM"]["usable_capacity_mt"] == 13.4 and crude["SPM"]["capacity_used_pct"] is not None


def test_brief_is_one_page_with_all_sections():
    import subprocess, tempfile
    from backend.app.services import incentive_actions as ia
    pdf = ia.brief_pdf()
    assert pdf[:4] == b"%PDF"
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False); f.write(pdf); f.close()
    pages = subprocess.run(["pdfinfo", f.name], capture_output=True, text=True).stdout
    text = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    assert "Pages:           1" in pages                                                   # one page
    for s in ("1. The picture", "4. NMPA schemes ending", "5. Rebate claims", "6. Against the other major ports", "7. Berths near"):
        assert s in text
    assert "nothing in it is a decision" in text


def test_net_benefit_is_never_firmer_than_the_evidence():
    r = da.net_benefit_review()
    rows = {x["short"]: x for x in r["rows"]}
    for x in r["rows"]:
        res = (x["result"] or "").lower()
        if any(w in res for w in ("too early", "too few", "cannot be measured", "information")):
            assert x["verdict"] in ("Not yet", "Indicative only", "Cost not priced")             # never "paid for itself"
        if x["net_low_rs"] is not None:
            assert x["net_low_rs"] <= x["net_high_rs"] and x["earned_low_rs"] <= x["earned_high_rs"]
        if x["verdict"] == "Cost not priced":
            assert x["cost_rs"] is None and x["net_low_rs"] is None                            # an unpriced cost is never shown as a number
    w = rows["Crude & LPG waiver, Mar 2026"]
    assert w["earned_high_rs"] == 0 and w["net_low_rs"] == -w["cost_rs"] and w["cost_rs"] > 3e7  # no extra cargo: net = minus the cost
    assert "relief measure" in w["why"].lower()
    assert rows["Fertiliser priority berthing"]["verdict"] == "Indicative only"


def test_board_note_carries_the_new_evidence(tmp_path, monkeypatch):
    import subprocess
    assert all("Harit" not in x for x in da._earlier_schemes("Iron ore exports"))            # 'iron' is not in 'environmental'
    assert any("Fertiliser" in x for x in da._earlier_schemes("Fertilizer (finished)"))      # both spellings, plural
    monkeypatch.setattr(ie, "SCHEMES_FILE", "data/_test_board_note2.json")
    try:
        rec = ie.create_scheme("LPG", "Rebate on extra volume", 10.0, "2027-04-01", "2028-03-31", 2_000_000, by="t")
        f = tmp_path / "note.docx"
        f.write_bytes(da.board_note_docx(rec["id"]))
        t = subprocess.run(["pandoc", "-t", "plain", str(f)], capture_output=True, text=True).stdout
        for part in ("Earlier NMPA schemes for this cargo", "Kept per extra tonne", "Berth capacity", "Approval route: to be confirmed by NMPA"):
            assert part in t, part
        assert "Gen.2" in t                                                                   # the March 2026 waiver as precedent
    finally:
        ie._schemes_path().unlink(missing_ok=True)


def test_compare_designs_is_consistent():
    r = da.compare_designs("LPG", 10, 5)
    rows = {x["design"]: x for x in r["rows"]}
    a, b = rows["Discount on all cargo"], rows["Rebate on extra cargo only"]
    assert a["cost_rs"] > b["cost_rs"] > 0                                  # all cargo costs more than extra only
    assert rows["Shared budget pool"]["cost_rs"] <= b["cost_rs"] + 1        # the pool never pays more than its budget
    if "Rebate only when the customer is ready" in rows:
        assert rows["Rebate only when the customer is ready"]["cost_rs"] <= b["cost_rs"]
    be = float(a["pays_when"].split("%")[0])                                # at break-even, the all-cargo net is about zero
    at = da.compare_designs("LPG", 10, be)["rows"][0]["net_rs"]
    assert abs(at) < 0.01 * da.compare_designs("LPG", 10, be)["rows"][0]["cost_rs"]
    assert da.compare_designs("LPG", 10, 0)["rows"][1]["cost_rs"] == 0      # no extra cargo: a rebate on extra costs nothing
