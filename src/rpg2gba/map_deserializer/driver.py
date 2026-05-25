"""Drive the Ruby rxdata deserializer and place per-map JSON (PHASE3_PLAN §3.1).

Shells to `rxdata_deserializer/deserialize.rb rxdata <data_dir> <out_dir>`,
mirroring the subprocess pattern in `pbs_converter/_marshal.py`. The Ruby side
owns Marshal loading + shaping; this layer owns orchestration (clean, count
check) and is the entry point the `phase3` pipeline command calls.

Idempotence (CLAUDE §4.2/§4.4): a clean re-run wipes `maps/` first, so output is
a pure function of the inputs.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _deserializer() -> Path:
    """Absolute path to the bundled `deserialize.rb`."""
    return Path(__file__).resolve().parents[1] / "rxdata_deserializer" / "deserialize.rb"


def run(uranium_src: Path, out_dir: Path, clean: bool = False) -> int:
    """Deserialize every map + CommonEvents/System/MapInfos into `out_dir`.

    Writes `out_dir/maps/MapNNN.json` plus `common_events.json`, `system.json`,
    and `map_infos.json`. Returns the number of map files produced.

    Fail-loud: a non-zero Ruby exit (e.g. a map that won't Marshal-load) raises
    with stderr attached.
    """
    uranium_src = Path(uranium_src)
    out_dir = Path(out_dir)
    data_dir = uranium_src / "Data"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"no Data/ under {uranium_src}")

    maps_dir = out_dir / "maps"
    if clean and maps_dir.exists():
        logger.info("wiping %s", maps_dir)
        shutil.rmtree(maps_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    script = _deserializer()
    proc = subprocess.run(
        ["ruby", str(script), "rxdata", str(data_dir), str(out_dir)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"deserialize.rb rxdata failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )

    n_maps = len(list(maps_dir.glob("Map*.json")))
    logger.info("deserialized %d maps → %s", n_maps, maps_dir)
    return n_maps
