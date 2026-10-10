"""`scripts/assemble_pathfinder.py`'s `prune_stale_map_dirs`: a generated
`data/maps/<Dir>/` whose map left the slice is removed (make discovers every
per-map map.json by wildcard -- the parked Metro maps 44/45 broke the build),
while git-tracked stock dirs and this build's own dirs are kept."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import assemble_pathfinder as ap  # noqa: E402


def _fork(tmp_path: Path) -> Path:
    fork = tmp_path / "engine"
    maps = fork / "data" / "maps"
    for name in ("LittlerootTown", "MokiTown", "NowtochCityMetroStation"):
        (maps / name).mkdir(parents=True)
        (maps / name / "map.json").write_text("{}", encoding="utf-8")
    (maps / "NoMapJson").mkdir()
    subprocess.run(["git", "init", "-q", str(fork)], check=True)
    subprocess.run(["git", "-C", str(fork), "add", "data/maps/LittlerootTown/map.json"],
                   check=True)
    return fork


def test_prunes_only_untracked_dirs_outside_the_build(tmp_path):
    fork = _fork(tmp_path)
    removed = ap.prune_stale_map_dirs(fork, frozenset({"MokiTown"}), dry_run=False)
    assert removed == ["NowtochCityMetroStation"]
    left = sorted(p.name for p in (fork / "data" / "maps").iterdir())
    assert left == ["LittlerootTown", "MokiTown", "NoMapJson"]


def test_dry_run_removes_nothing(tmp_path):
    fork = _fork(tmp_path)
    removed = ap.prune_stale_map_dirs(fork, frozenset({"MokiTown"}), dry_run=True)
    assert removed == ["NowtochCityMetroStation"]
    assert (fork / "data" / "maps" / "NowtochCityMetroStation").is_dir()
