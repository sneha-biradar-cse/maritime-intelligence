"""Customer call sheet: right schemes for the right customers, cautions kept, one page."""
import subprocess
import tempfile

import pytest

from backend.app.services import customer_sheet as cs


def test_no_scheme_from_a_generic_word():
    s = cs.sheet("MRPL")                                            # fuel oil is not 'green fuels'
    assert not any("Green Policy" in x["notice"] for x in s["schemes"])
    assert any("not ready" in p for p in s["talking_points"])         # MRPL's ships waited on its side


def test_iron_ore_rebate_with_and_without_caution():
    k = " ".join(cs.sheet("KIOCL")["talking_points"])
    assert "confirm their eligibility" in k                           # own arrangement noted by the iron ore monitor
    v = " ".join(cs.sheet("VEDANTA")["talking_points"])
    assert "IOF-Exp-Rebate" in v and "confirm their eligibility" not in v


def test_one_page_and_unknown_customer():
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False); f.write(cs.sheet_pdf("IOCL")); f.close()
    assert "Pages:           1" in subprocess.run(["pdfinfo", f.name], capture_output=True, text=True).stdout
    with pytest.raises(KeyError):
        cs.sheet("NO SUCH COMPANY LTD")


def test_talking_point_agrees_with_status():
    for c in ("IOCL", "MRPL", "KIOCL"):
        s = cs.sheet(c)
        st = (s["row"] or {}).get("status", "")
        if any("fell last quarter" in p for p in s["talking_points"]):
            assert st in ("Falling", "Falling fast", "Stopped")                # never 'fell' when the engine says steady
