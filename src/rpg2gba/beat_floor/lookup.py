"""Per-row floor lookup for consumers outside the CLI (REDERIVATION_PLAN.md
§16.3 C5): archetype templates at registration time and the checker's
⊇-floor rule.

A beat may claim rows on any map -- a predecessor's seam side, a boundary
page on the previous chapter's map -- so lookup is by row id, not by chapter.
Floors are computed per map and cached per `(build_dir, map_id)`; the decoded
map data is the same `build_dir/maps/MapNNN.json` `floor_for_chapter` reads.
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.chapter_manifest.schema import parse_row_id

_REF_DIR = Path(__file__).resolve().parents[3] / "reference"


def default_build_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


@cache
def _common_events(build_dir: str) -> list[dict]:
    return json.loads((Path(build_dir) / "common_events.json").read_text(encoding="utf-8"))


@cache
def _switch_labels() -> dict[int, str]:
    from rpg2gba.conversion_agent.flag_registry import load_label_tables

    switch_labels, _var_labels = load_label_tables(
        _REF_DIR / "uranium_switches.json", _REF_DIR / "uranium_variables.json")
    return switch_labels


@cache
def _connections(build_dir: str) -> tuple[list, ...]:
    """`connections.json`'s contents, for seam-row floors (`beat_floor.terrain`).
    A `floor_for_row` lookup on a seam row needs this exactly like
    `walk.floor_for_chapter` does -- absent here, every seam row this cache
    serves would silently come back connection-less (`walk.floor_for_map`'s
    own `()` default), which is a worse failure than the extra file read."""
    path = Path(build_dir) / "connections.json"
    if not path.exists():
        return ()
    return tuple(json.loads(path.read_text(encoding="utf-8")))


@cache
def _door_cells(build_dir: str) -> dict[int, frozenset[tuple[int, int]]]:
    """The emitted layout's door cells (`walk.load_door_cells`), for the
    `warp` floor's `arrives_on_door`."""
    from rpg2gba.beat_floor.walk import load_door_cells

    return load_door_cells(build_dir)


@cache
def resolved_rows(build_dir: str) -> dict:
    """The story model's resolved computed rows over its modelled chain
    (`story_state.model.build_chapter_stories(resolved_out=)`), for
    `walk.floor_for_map`. Empty for a build dir with no `system.json`: a
    synthetic test corpus has no chapter chain to resolve against."""
    if not (Path(build_dir) / "system.json").is_file():
        return {}
    from rpg2gba.story_state.__main__ import _CHAIN
    from rpg2gba.story_state.model import build_chapter_stories

    out: dict = {}
    build_chapter_stories(list(_CHAIN), build_dir=Path(build_dir),
                          chapters_path=_REF_DIR / "chapters.json", resolved_out=out)
    return out


@cache
def floor_for_map_cached(
    build_dir: str, map_id: int, *, stripped_ce_ids: frozenset[int] | None = None,
) -> dict[str, RowFloor]:
    """`walk.floor_for_map`, cached per `(build_dir, map_id, stripped_ce_ids)`.

    `stripped_ce_ids` is part of the `@cache` key deliberately: leaving it
    out would let a call with an explicit strip set silently answer a later
    call with a different one (or `None`) from the same cache entry, and
    since it changes the floor's actual assertions (not just bookkeeping),
    that would be a correctness bug hiding behind a cache -- worse than the
    minor cost of one cache entry per distinct set actually requested. It
    is a `frozenset`, so it is hashable and safe to key on."""
    from rpg2gba.beat_floor.walk import floor_for_map

    path = Path(build_dir) / "maps" / f"Map{map_id:03d}.json"
    map_data = json.loads(path.read_text(encoding="utf-8"))
    return floor_for_map(
        map_id, map_data,
        common_events=_common_events(build_dir), switch_labels=_switch_labels(),
        door_cells=_door_cells(build_dir),
        connections=list(_connections(build_dir)),
        stripped_ce_ids=stripped_ce_ids,
        resolved_rows=resolved_rows(build_dir))


def floor_for_row(
    row_id: str, *, build_dir: Path | None = None,
    stripped_ce_ids: frozenset[int] | None = None,
) -> RowFloor:
    """The floor for one manifest row id. Fails loud (KeyError) when the
    row's map yields no floor for that id -- a claimed row the floor cannot
    see is a bug in the claim or in the floor, never an empty floor."""
    resolved = str(build_dir if build_dir is not None else default_build_dir())
    parsed = parse_row_id(row_id)
    floors = floor_for_map_cached(resolved, parsed.map_id, stripped_ce_ids=stripped_ce_ids)
    try:
        return floors[row_id]
    except KeyError:
        raise KeyError(
            f"beat_floor: no floor for row {row_id!r} on map {parsed.map_id} "
            f"(build_dir {resolved})") from None
