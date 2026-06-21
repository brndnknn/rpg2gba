"""Image pipeline step 1 — Uranium tileset source resolution.

Resolve an Uranium `tileset_id` to its on-disk art:
  - the tileset PNG (RMXP static tiles, 32x32 each, 8 per row, ids >= 384), and
  - the 7 autotile-slot template PNGs (ids 48..383; slot n = tile_id//48 - 1).

Inputs come from the deserialized `tilesets.json` (`deserialize.rb tilesets`,
which now carries `autotile_names` — a 7-slot array, '' = unused slot) and the
unpacked Uranium `Graphics/` tree (`Tilesets/` + `Autotiles/`).

Fail loud (CLAUDE.md §4.5): a *named* asset that doesn't resolve to a real file
aborts with the name. A missing PNG would otherwise silently render as blank art.
An empty slot name is legitimate (`None`), not an error.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# RMXP tile-id geometry (mirrors tile_map.py + 039_TileDrawingHelper_v17.rb).
AUTOTILE_SLOTS = 7          # autotile_names is always length 7
AUTOTILE_BASE = 48          # ids 48..383 are autotiles, 48 per slot
STATIC_BASE = 384           # ids >= 384 are static tiles
RMXP_TILE_PX = 32           # one RMXP tile is 32x32 px
TILESET_COLUMNS = 8         # static tileset atlas is 8 tiles wide (256 px)

DEFAULT_TILESETS_JSON = Path("output/uranium-build/tilesets.json")


def slot_for_base(base: int) -> int:
    """Autotile slot index (0..6) for an autotile *base* id (48, 96, ... 336)."""
    if not (AUTOTILE_BASE <= base < STATIC_BASE):
        raise ValueError(f"base {base} is not an autotile base id (48..336)")
    return base // AUTOTILE_BASE - 1


def base_for_slot(slot: int) -> int:
    """Inverse of slot_for_base: the base id (48, 96, ...) owning a slot."""
    if not 0 <= slot < AUTOTILE_SLOTS:
        raise ValueError(f"slot {slot} out of range 0..{AUTOTILE_SLOTS - 1}")
    return AUTOTILE_BASE * (slot + 1)


@dataclass(frozen=True)
class TilesetSources:
    """Resolved art for one Uranium tileset.

    `autotiles` is a length-7 tuple aligned to RMXP autotile slots; an entry is
    `None` when that slot is unused (empty name in the source data)."""

    tileset_id: int
    name: str
    tileset_name: str
    tileset_png: Path
    autotiles: tuple[Path | None, ...]

    def autotile_for_base(self, base: int) -> Path | None:
        """The autotile PNG for an autotile *base* id (or None for an empty slot)."""
        return self.autotiles[slot_for_base(base)]

    def autotile_for_tile(self, tile_id: int) -> Path | None:
        """The autotile PNG backing a stored autotile tile_id (48..383), or None."""
        if not (AUTOTILE_BASE <= tile_id < STATIC_BASE):
            raise ValueError(f"tile_id {tile_id} is not an autotile id (48..383)")
        return self.autotiles[tile_id // AUTOTILE_BASE - 1]


def default_graphics_dir() -> Path:
    """`<RPG2GBA_URANIUM_SRC>/Graphics`, loading .env-paths if the env isn't set."""
    if "RPG2GBA_URANIUM_SRC" not in os.environ:
        # Lazy import: pipeline pulls in click etc.; only needed for the env default.
        from rpg2gba.pipeline import _load_dotenv

        _load_dotenv()
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        raise RuntimeError(
            "RPG2GBA_URANIUM_SRC is not set (and .env-paths didn't provide it); "
            "pass graphics_dir= explicitly or point the env at the unpacked Uranium tree"
        )
    return Path(src) / "Graphics"


def load_tileset_sources(
    tileset_id: int,
    *,
    tilesets_json: Path = DEFAULT_TILESETS_JSON,
    graphics_dir: Path | None = None,
) -> TilesetSources:
    """Resolve one tileset's art. `graphics_dir` defaults to the Uranium tree."""
    gfx = graphics_dir if graphics_dir is not None else default_graphics_dir()
    raw = json.loads(Path(tilesets_json).read_text(encoding="utf-8"))
    entry = raw.get(str(tileset_id))
    if entry is None:
        raise KeyError(
            f"tileset {tileset_id} absent from {tilesets_json}; "
            f"regenerate with `deserialize.rb tilesets`"
        )

    tileset_name = entry.get("tileset_name") or ""
    if not tileset_name:
        raise ValueError(f"tileset {tileset_id} has no tileset_name in {tilesets_json}")
    tileset_png = _resolve(tileset_name, gfx / "Tilesets", what=f"tileset {tileset_id}")

    names = entry.get("autotile_names") or []
    if len(names) != AUTOTILE_SLOTS:
        # RMXP always stores exactly 7; a different length means a stale/odd dump.
        raise ValueError(
            f"tileset {tileset_id}: expected {AUTOTILE_SLOTS} autotile_names, "
            f"got {len(names)} — re-dump tilesets.json"
        )
    autotiles: list[Path | None] = []
    for slot, name in enumerate(names):
        if not name:
            autotiles.append(None)
            continue
        autotiles.append(
            _resolve(name, gfx / "Autotiles", what=f"tileset {tileset_id} autotile slot {slot}")
        )

    return TilesetSources(
        tileset_id=tileset_id,
        name=entry.get("name") or "",
        tileset_name=tileset_name,
        tileset_png=tileset_png,
        autotiles=tuple(autotiles),
    )


def _resolve(name: str, directory: Path, *, what: str) -> Path:
    """`<directory>/<name>.png`, with a case-insensitive fallback. Fail loud."""
    exact = directory / f"{name}.png"
    if exact.is_file():
        return exact
    # RMXP stores names case-sensitively but filesystems / re-packs can differ.
    target = f"{name}.png".lower()
    if directory.is_dir():
        for p in directory.iterdir():
            if p.name.lower() == target:
                logger.debug("%s: case-folded %r -> %s", what, name, p.name)
                return p
    raise FileNotFoundError(
        f"{what}: asset {name!r} not found in {directory} (looked for {exact.name})"
    )
