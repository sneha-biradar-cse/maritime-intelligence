"""Make the project's own copy of Poppler (pdftotext, pdfinfo, pdftoppm) usable, if it is installed in tools/poppler."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "poppler"


def ensure_on_path() -> bool:
    """True if pdftotext can be run. Adds the project's own Poppler to PATH (this process and the scripts it starts)."""
    if shutil.which("pdftotext"):
        return True
    for exe in TOOLS.rglob("pdftotext.exe") if TOOLS.exists() else []:
        os.environ["PATH"] = str(exe.parent) + os.pathsep + os.environ.get("PATH", "")
        return shutil.which("pdftotext") is not None
    return False
