"""Phase 2 §2.8 — map metadata + player spawn from `metadata.dat`.

Source (Ruby Marshal; deserialized via `_marshal.dump_dat`):
  metadata.dat — array indexed by Uranium map id. Index 0 is the GLOBAL record;
  indices 1.. are per-map records. Each record is itself an array indexed by the
  Metadata* field id (107__PField_Map.rb:305-379); absent fields are nil.

  Global field ids: 1 Home("uuuu" = [map, x, y, direction] — the player START),
  2 WildBattleBGM, 3 TrainerBattleBGM, 4 WildVictoryME, 5 TrainerVictoryME,
  6 SurfBGM, 7 BicycleBGM, 8.. PlayerA-H graphics.

  Per-map field ids: 1 Outdoor(b), 2 ShowArea, 3 Bicycle, 4 BicycleAlways,
  5 HealingSpot("uuu" = [map, x, y] — respawn/heal point), 6 Weather("eu" =
  [enum, chance]), 7 MapPosition("uuu" = [region, x, y]), 8 DiveMap, 9 DarkMap,
  10 SafariMap, 11 SnapEdges, 12 Dungeon, 13 BattleBack(s), 14-17 per-map BGM/ME
  overrides, 18 MapSize.

Per PHASE2_PLAN §2.8: emit `include/constants/metadata.h` (player spawn) and
`intermediate/map_metadata.json` (per-map metadata for the Phase 5 consumer).
This converter touches no constant namespace, so it doesn't use the IdMap.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ._c_emit import generated_banner, wrap_header
from ._id_map import IdMap
from ._marshal import dump_dat, load_json

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.pbs_converter.metadata"

# Global record field ids (107__PField_Map.rb).
G_HOME = 1
# Per-map record field ids.
M_OUTDOOR, M_SHOWAREA, M_BICYCLE, M_BICYCLEALWAYS, M_HEALINGSPOT = 1, 2, 3, 4, 5
M_WEATHER, M_MAPPOSITION, M_DIVEMAP, M_DARKMAP, M_SAFARIMAP = 6, 7, 8, 9, 10
M_SNAPEDGES, M_DUNGEON, M_BATTLEBACK = 11, 12, 13
M_WILDBGM, M_TRAINERBGM, M_WILDVICTORY, M_TRAINERVICTORY, M_MAPSIZE = 14, 15, 16, 17, 18

# Weather enum (107__PField_Map.rb:367); index 0 = none.
_WEATHER_NAMES = ("None", "Rain", "Storm", "Snow", "Sandstorm", "Sunny", "HeavyRain", "Blizzard")


@dataclass
class GlobalMetadata:
    home_map: int
    home_x: int
    home_y: int
    home_direction: int


@dataclass
class MapMetadata:
    map_id: int
    fields: dict[str, object] = field(default_factory=dict)


def _at(record: list, idx: int) -> object:
    """Field `idx` of a metadata record (records are gappy arrays), or None."""
    if not isinstance(record, list) or idx >= len(record):
        return None
    return record[idx]


def parse_global(raw: list) -> GlobalMetadata:
    if not raw or not isinstance(raw[0], list):
        raise ValueError("metadata.dat: missing global (index 0) record")
    home = _at(raw[0], G_HOME)
    if not (isinstance(home, list) and len(home) == 4):
        raise ValueError(f"metadata.dat: global Home must be [map, x, y, dir], got {home!r}")
    return GlobalMetadata(home_map=home[0], home_x=home[1], home_y=home[2], home_direction=home[3])


def _weather(record: list) -> dict[str, object] | None:
    w = _at(record, M_WEATHER)
    if not w:
        return None
    if not (isinstance(w, list) and len(w) == 2):
        raise ValueError(f"metadata Weather must be [enum, chance], got {w!r}")
    idx, chance = w
    if idx >= len(_WEATHER_NAMES):
        raise ValueError(f"metadata: unknown weather enum {idx}")
    if idx == 0:
        return None
    return {"weather": _WEATHER_NAMES[idx], "chance": chance}


def parse_maps(raw: list) -> list[MapMetadata]:
    out: list[MapMetadata] = []
    for map_id in range(1, len(raw)):
        record = raw[map_id]
        if not record:
            continue
        f: dict[str, object] = {}
        if _at(record, M_OUTDOOR):
            f["outdoor"] = True
        weather = _weather(record)
        if weather:
            f.update(weather)
        for key, idx in (
            ("healing_spot", M_HEALINGSPOT),
            ("map_position", M_MAPPOSITION),
        ):
            v = _at(record, idx)
            if v:
                f[key] = v
        if _at(record, M_DUNGEON):
            f["dungeon"] = True
        if _at(record, M_DARKMAP):
            f["dark_map"] = True
        dive = _at(record, M_DIVEMAP)
        if dive:
            f["dive_map"] = dive
        for key, idx in (
            ("battle_back", M_BATTLEBACK),
            ("wild_battle_bgm", M_WILDBGM),
            ("trainer_battle_bgm", M_TRAINERBGM),
        ):
            v = _at(record, idx)
            if v:
                f[key] = v
        if f:
            out.append(MapMetadata(map_id=map_id, fields=f))
    return out


def emit_constants(g: GlobalMetadata) -> str:
    body = "\n".join(
        [
            f"#define URANIUM_START_MAP {g.home_map}",
            f"#define URANIUM_START_X {g.home_x}",
            f"#define URANIUM_START_Y {g.home_y}",
            f"#define URANIUM_START_DIR {g.home_direction}",
        ]
    )
    banner = generated_banner("metadata.dat (global Home record)", GENERATOR, timestamp=False)
    note = "// Player start position (Uranium map id + tile x/y + facing direction).\n"
    return wrap_header("GUARD_URANIUM_CONSTANTS_METADATA_H", note + body, banner=banner)


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.8 entry point: emit metadata.h (spawn) + map_metadata.json."""
    inter = out_dir / "intermediate"
    inc = out_dir / "include" / "constants"
    inter.mkdir(parents=True, exist_ok=True)
    inc.mkdir(parents=True, exist_ok=True)

    raw = load_json(dump_dat(uranium_src / "Data" / "metadata.dat", inter / "metadata_raw.json"))
    if not isinstance(raw, list):
        raise ValueError("metadata.dat: expected a top-level array")

    g = parse_global(raw)
    maps = parse_maps(raw)

    (inc / "metadata.h").write_text(emit_constants(g), encoding="utf-8")

    note = (
        "Per-map Uranium metadata keyed by Uranium map id (Phase 5 consumer). "
        "Only fields actually present are emitted; player spawn is in "
        "include/constants/metadata.h."
    )
    payload = {
        "_comment": note,
        "maps": {str(m.map_id): m.fields for m in maps},
    }
    (inter / "map_metadata.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logger.info(
        "emitted player spawn (map %d @ %d,%d dir %d) + metadata for %d maps",
        g.home_map,
        g.home_x,
        g.home_y,
        g.home_direction,
        len(maps),
    )
