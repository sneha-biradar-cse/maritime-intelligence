"""
Install Poppler (the free PDF text tools pdftotext, pdfinfo, pdftoppm) into this project's own folder, tools/poppler.
The project's checks read NMPA and Ministry statements with these tools. Windows does not include them.

- Installs a PINNED version from its official release page and checks the file's SHA-256 fingerprint before using it:
  a file that does not match exactly is refused and deleted. Nothing outside the project folder is changed (no system
  settings, no PATH change); the project's scripts find it by themselves.
- Does nothing if Poppler is already available.
Usage:  python scripts\\setup_poppler.py
"""
from __future__ import annotations

import hashlib
import platform
import shutil
import sys
import zipfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _poppler import TOOLS, ensure_on_path  # noqa: E402

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

VERSION = "26.09.0-0"
URL = f"https://github.com/oschwartz10612/poppler-windows/releases/download/v{VERSION}/Release-{VERSION}.zip"
SHA256 = "7a6f256a0ddf7536182246a5733331bf4677cbcc34f4663774947ad34556c8d0"


def main() -> int:
    if ensure_on_path():
        print("Poppler is available (pdftotext found). Nothing to do.")
        return 0
    if platform.system() != "Windows":
        print("Poppler is not installed. On Linux: sudo apt install poppler-utils ; on macOS: brew install poppler")
        return 1
    TOOLS.mkdir(parents=True, exist_ok=True)
    tmp = TOOLS / f"Release-{VERSION}.zip"
    print(f"Downloading Poppler {VERSION} (about 42 MB) from its official release page ...")
    with requests.get(URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        h = hashlib.sha256()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                h.update(chunk)
    if h.hexdigest() != SHA256:
        tmp.unlink(missing_ok=True)
        print("REFUSED: the downloaded file's fingerprint does not match the expected one. Nothing was installed.")
        return 2
    with zipfile.ZipFile(tmp) as z:
        z.extractall(TOOLS)
    tmp.unlink(missing_ok=True)
    if not ensure_on_path():
        print("Poppler was unpacked but pdftotext was not found. Nothing else was changed.")
        return 2
    print(f"Poppler {VERSION} installed in {TOOLS} (fingerprint checked). The project's scripts will use it automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
