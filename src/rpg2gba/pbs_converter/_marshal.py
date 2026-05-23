"""Shared helper for the Ruby-Marshal `.dat` → JSON path (PHASE2_PLAN D2).

Several Phase 2 sources (`trainers.dat`, `trainertypes.dat`, `encounters.dat`,
`metadata.dat`, `tm.dat`, `types.dat`) are Ruby `Marshal.dump` blobs, not the
custom Essentials binary `_binary.py` handles. Rather than reimplement Ruby
Marshal in Python (a known rabbit hole — D2), the `rxdata_deserializer`'s
`deserialize.rb dat` mode loads one Marshal `.dat` and dumps a JSON view of the
object graph. The Marshal-based converters call `dump_dat` to produce that JSON,
then `load_json` to read it back.

Custom Essentials classes serialize as `{"__class__": "<Name>", ...ivars}`; plain
hashes/arrays/scalars pass through. The Python side interprets those shapes.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _deserializer() -> Path:
    """Absolute path to the bundled `deserialize.rb`."""
    return Path(__file__).resolve().parents[1] / "rxdata_deserializer" / "deserialize.rb"


def dump_dat(src: Path, out_json: Path) -> Path:
    """Marshal-load `src` via Ruby and write its JSON view to `out_json`.

    Fail-loud (CLAUDE §4.5): a non-zero Ruby exit raises with stderr attached.
    Returns `out_json` for chaining with `load_json`.
    """
    src = Path(src)
    out_json = Path(out_json)
    if not src.is_file():
        raise FileNotFoundError(f"Marshal source not found: {src}")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    script = _deserializer()
    proc = subprocess.run(
        ["ruby", str(script), "dat", str(src), str(out_json)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"deserialize.rb failed on {src} (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    logger.debug("deserialized %s -> %s", src.name, out_json)
    return out_json


def load_json(path: Path) -> object:
    """Read a JSON file produced by `dump_dat` (or any JSON sidecar)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
