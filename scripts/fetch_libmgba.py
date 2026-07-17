"""Install the mGBA Python bindings (libmgba-py) into the current venv.

The bindings are not on PyPI; hanzi's fork publishes prebuilt zips (abi3, so
one Linux build covers Python 3.11+). The Linux build dynamically links the
system libmgba.so.0.10 — installed alongside mgba-qt — so no compiling.
Idempotent: re-running overwrites the installed package.

Usage: python scripts/fetch_libmgba.py
"""
import io
import shutil
import sys
import sysconfig
import zipfile
from pathlib import Path

import requests

RELEASE_URL = ("https://github.com/hanzi/libmgba-py/releases/download/"
               "0.2.0-2/libmgba-py_0.2.0_ubuntu-lunar.zip")


def main() -> None:
    purelib = Path(sysconfig.get_paths()["purelib"])
    if "site-packages" not in str(purelib):
        sys.exit(f"refusing to install outside a venv: {purelib}")
    print(f"downloading {RELEASE_URL}")
    resp = requests.get(RELEASE_URL, timeout=120)
    resp.raise_for_status()
    target = purelib / "mgba"
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.startswith("mgba/")]
        zf.extractall(purelib, members=names)
    print(f"installed {target}")
    import mgba  # noqa: F401  (import check while the venv is live)
    print("import mgba: OK")


if __name__ == "__main__":
    main()
