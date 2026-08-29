"""Builds the generated half of the per-chapter manifest (see the package
docstring in ``__init__.py``).

Joins three sources under ``output/uranium-build/`` for the chapter's own map
list (``reference/chapters.json``):

* ``maps/Map###.json``            — one row per event page, unconditionally
  (the generator never filters — see Q2(ii) in PLAYTEST_AUTHORING_IMPROVEMENT.md)
* ``connections.json``            — one seam row per overland connection
  touching a chapter map, emitted from that map's side
* ``transpile_unhandled.jsonl``   — joined on (map_id, event_id, page) to set
  ``unhandled``, which vetoes a `cosmetic` disposition (Q1)

Nothing here is authored and nothing here filters. Idempotence (CLAUDE.md
§4.2) is load-bearing: every tuple field on `ManifestRow` is built pre-sorted
so re-running the generator against unchanged input reproduces the same JSON
byte for byte.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from rpg2gba.chapter_atlas.census import (
    CODE_CONDITIONAL,
    CODE_SCRIPT,
    CODE_SCRIPT_CONT,
    COND_TYPE_SCRIPT,
    MECHANIC_BY_HEAD,
    RUBY_KEYWORDS,
    _script_head,
)
from rpg2gba.chapter_manifest.schema import (
    ManifestRow,
    PageCondition,
    SeamRef,
    content_hash,
    page_row_id,
    row_to_dict,
    seam_row_id,
)

logger = logging.getLogger(__name__)

# RMXP trigger codes -> human labels. Kept local rather than imported: the
# conversion agent's human backend has its own private copy (`_TRIGGERS` in
# `conversion_agent/backends/human.py`) and `metadata_wiring.py` has the
# numeric constants, but neither is a shared source of truth for this string
# form, and this dict is small enough not to need one.
_TRIGGER_NAMES: dict[int, str] = {
    0: "action",
    1: "player_touch",
    2: "event_touch",
    3: "autorun",
    4: "parallel",
}

# Numeric command code -> effect tag. Codes absent from this table are not
# silently dropped: `_extract_page` puts them in `other_codes` instead (Q2iii).
# 0 (list terminator) and 509 (the RMXP editor's per-step display duplicate of
# a preceding 209 move-route command) are handled separately, before this
# table is consulted, because they are not "unrecognized" — they are ignored
# by design.
_CODE_EFFECT: dict[int, str] = {
    201: "warp",
    121: "switch_write",
    122: "var_write",
    123: "self_switch_write",
    209: "move_route",
    210: "move_route",
    241: "bgm",
    242: "bgm",
    249: "se",  # Play ME; grouped with `se` per the brief (not `bgm`)
    250: "se",
    101: "text",
    401: "text",
    102: "choice",
    402: "choice",
    403: "choice",
    404: "choice",
    314: "heal",
    125: "money",
    117: "common_event",
    322: "graphic",
    323: "graphic",
    204: "graphic",  # Change Map Settings — panorama/fog, cosmetic-safe like 322/323
    208: "graphic",  # Change Transparent Flag
    207: "animation",  # Show Animation
    223: "screen_fx",  # Change Screen Color Tone
    # Loop (112) / Break Loop (113) / Exit Event Processing (115): not
    # cosmetic-safe. 115 in particular terminates the remainder of a page's
    # command list, so a page carrying it cannot honestly be called decoration
    # — see schema.py's comment on COSMETIC_SAFE_TAGS.
    112: "control_flow",
    113: "control_flow",
    115: "control_flow",
}

# Codes that participate in extraction but never produce an effect tag or an
# `other_codes` entry by themselves: the list terminator, 509 (ignored
# duplicate of 209, per the brief), 106 (Wait), 108 (Comment) and its 408
# (Comment continuation) rider, and 413 (Repeat Above / loop terminator — same treatment as 412, the branch terminator: both
# are structural closers with no independent meaning of their own).
_CODE_IGNORED: frozenset[int] = frozenset({0, 509, 106, 108, 408, 413})
_CODE_BRANCH: frozenset[int] = frozenset({111, 411, 412})

# Script-call head -> effect tag, for the Ruby half of extraction. Distinct
# from `MECHANIC_BY_HEAD` (census.py), which maps heads to prose mechanic
# descriptions for the atlas; this maps the subset of heads the manifest's
# EFFECT_TAGS vocabulary actually has a tag for.
_HEAD_EFFECT: dict[str, str] = {
    "pbTrainerBattle": "trainerbattle",
    "pbDoubleTrainerBattle": "trainerbattle",
    "pbWildBattle": "wild_battle",
    "pbItemBall": "giveitem",
    "pbReceiveItem": "giveitem",
    "pbNicknameAndStore": "givemon",
    "pbAddPokemon": "givemon",
    "pbPokemonMart": "shop",
    "pbPokemonBerryMart": "shop",
    "pbHealAll": "heal",
    "pbPokeCenterPC": "pc",
    "pbTrainerPC": "pc",
    "pbSetSelfSwitch": "self_switch_write",
    "pbCallBub": "bubble_ui",
    "pbEraseThisEvent": "erase_event",
    "setTempSwitchOn": "temp_switch_write",
    # `get_character` is a read-only character resolver (-1=player, 0=self,
    # else event id) — deliberately absent here: it carries no effect tag.
}

# Script-call head -> required capability, for `ManifestRow.requires`.
# Every entry here is verified to occur in the corpus; the map-file count as of
# 2026-08-27 is in the trailing comment. Do NOT add a head from general Pokemon
# knowledge -- this table shipped with six invented entries (`pbStrength`,
# `pbCutTree`, `pbSurf`, `pbWaterfall`, `pbDive`, `pbFishing`) that match ZERO
# map files, written from priors rather than from the data. That is the §4.7
# "verify against the real source" rule violated on the Essentials side, and it
# would have let the capability checker validate `blocked:cut` for a capability
# this game never spells that way. Grep the corpus before adding a row.
#
# Note also what this table structurally CANNOT express: Surf/Dive/Waterfall are
# terrain-tag mechanics, not event scripts, so no head→capability mapping can
# ever reach them. Terrain-gated capabilities need a second source.
_HEAD_REQUIRES: dict[str, str] = {
    "pbRockSmash": "rock_smash",              # 6 maps
    "pbRockSmashRandomEncounter": "rock_smash",  # 6 maps
    "pbPushThisBoulder": "strength",          # 15 maps
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_name_table(path: Path) -> dict[int, str]:
    """Reads `uranium_switches.json` / `uranium_variables.json`'s ``{"id": "name"}``
    shape. Absent file or absent id both resolve to `None` names upstream —
    this only loads what exists."""
    if not path.exists():
        return {}
    raw = _load_json(path)
    return {int(k): v for k, v in raw.items()}


def _load_unhandled_counts(path: Path) -> Counter[tuple[int, int, int]]:
    counts: Counter[tuple[int, int, int]] = Counter()
    if not path.exists():
        logger.warning("no transpile_unhandled.jsonl at %s; unhandled counts blank", path)
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        map_id = row.get("map_id")
        event_id = row.get("event_id")
        page = row.get("page")
        if map_id is None or event_id is None or page is None:
            continue
        counts[(map_id, event_id, page)] += 1
    return counts


def _build_condition(
    raw: dict[str, Any],
    switch_names: dict[int, str],
    var_names: dict[int, str],
) -> PageCondition:
    kwargs: dict[str, Any] = {}
    if raw.get("switch1_valid"):
        sw1 = raw["switch1_id"]
        kwargs["switch1_id"] = sw1
        kwargs["switch1_name"] = switch_names.get(sw1)
    if raw.get("switch2_valid"):
        sw2 = raw["switch2_id"]
        kwargs["switch2_id"] = sw2
        kwargs["switch2_name"] = switch_names.get(sw2)
    if raw.get("variable_valid"):
        var_id = raw["variable_id"]
        kwargs["variable_id"] = var_id
        kwargs["variable_name"] = var_names.get(var_id)
        kwargs["variable_min"] = raw.get("variable_value")
    if raw.get("self_switch_valid"):
        kwargs["self_switch_ch"] = raw["self_switch_ch"]
    return PageCondition(**kwargs)


def _script_text(cmd: dict[str, Any]) -> str:
    params = cmd.get("parameters") or []
    return str(params[0]) if params else ""


def _extract_scripts(commands: list[dict[str, Any]]) -> list[str]:
    """Splits a page's command list into logical scripts.

    A code-355 command always opens a *new* script, even when it immediately
    follows another 355 (e.g. two one-line scripts in adjacent if/else
    branches, as map 32's boulder events do). A code-655 command is a
    continuation of *whatever script immediately precedes it* — it never
    starts one. Getting this wrong merges independent one-liners into a
    single block and loses every head but the first: on map 32's boulder
    events, four consecutive bare 355 commands (`pbEraseThisEvent`,
    `pbRockSmashRandomEncounter`, `pbEraseThisEvent`,
    `pbRockSmashRandomEncounter`) are four separate scripts, not one.
    """
    blocks: list[str] = []
    current: list[str] | None = None
    for cmd in commands:
        code = cmd.get("code")
        if code == CODE_SCRIPT:
            if current is not None:
                blocks.append("\n".join(current))
            current = [_script_text(cmd)]
        elif code == CODE_SCRIPT_CONT:
            if current is None:
                current = [_script_text(cmd)]
            else:
                current.append(_script_text(cmd))
        else:
            if current is not None:
                blocks.append("\n".join(current))
                current = None
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def _extract_page(commands: list[dict[str, Any]]) -> dict[str, Any]:
    """Numeric dispatch + Ruby script-head recognition over one page's command
    list. Returns the raw ingredients; the caller assembles the row."""
    effects: set[str] = set()
    other_codes: set[int] = set()
    script_typed_conditions = 0

    for cmd in commands:
        code = cmd.get("code")
        if code is None or code in _CODE_IGNORED:
            continue
        if code in _CODE_BRANCH:
            if code == CODE_CONDITIONAL:
                params = cmd.get("parameters") or []
                if (len(params) >= 2 and params[0] == COND_TYPE_SCRIPT
                        and isinstance(params[1], str)):
                    script_typed_conditions += 1
            continue
        if code in (CODE_SCRIPT, CODE_SCRIPT_CONT):
            continue  # handled by _extract_scripts, not the numeric table
        tag = _CODE_EFFECT.get(code)
        if tag is not None:
            effects.add(tag)
        else:
            other_codes.add(code)

    script_heads: set[str] = set()
    unrecognized_heads: set[str] = set()
    requires: set[str] = set()

    def _record_head(head: str) -> None:
        script_heads.add(head)
        if head in _HEAD_EFFECT:
            effects.add(_HEAD_EFFECT[head])
        if head in _HEAD_REQUIRES:
            requires.add(_HEAD_REQUIRES[head])
        # Recognition is judged against `MECHANIC_BY_HEAD` alone (Q2iii), not
        # against whether the manifest also has an effect tag for the head:
        # `pbSetSelfSwitch` gets an effect tag (`self_switch_write`) but is
        # still absent from `MECHANIC_BY_HEAD`, so it is still unrecognized —
        # confirmed against the map-32 fixture.
        if head not in MECHANIC_BY_HEAD:
            unrecognized_heads.add(head)

    for block in _extract_scripts(commands):
        head = _script_head(block)
        if not head or head in RUBY_KEYWORDS:
            continue
        _record_head(head)

    # Also inspect code-111 script-typed conditional *expressions* for heads:
    # `pbTrainerBattle(...)` lives in `parameters[1]` of a type-12 branch, not
    # in a 355/655 block, and every trainer battle in the corpus is exactly
    # this shape (census.py's note, reused verbatim by the brief).
    for cmd in commands:
        if cmd.get("code") != CODE_CONDITIONAL:
            continue
        params = cmd.get("parameters") or []
        if len(params) >= 2 and params[0] == COND_TYPE_SCRIPT and isinstance(params[1], str):
            head = _script_head(params[1])
            if not head or head in RUBY_KEYWORDS:
                continue
            _record_head(head)

    return {
        "effects": tuple(sorted(effects)),
        "other_codes": tuple(sorted(other_codes)),
        "script_heads": tuple(sorted(script_heads)),
        "unrecognized_heads": tuple(sorted(unrecognized_heads)),
        "requires": tuple(sorted(requires)),
        "script_typed_conditions": script_typed_conditions,
    }


def _generate_page_rows(
    map_id: int,
    map_data: dict[str, Any],
    switch_names: dict[int, str],
    var_names: dict[int, str],
    unhandled_counts: Counter[tuple[int, int, int]],
) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    for event in map_data.get("events", []):
        event_id = event["id"]
        event_name = event.get("name")
        for page_idx, page in enumerate(event.get("pages", [])):
            commands = page.get("list") or []
            extracted = _extract_page(commands)
            condition = _build_condition(
                page.get("condition") or {}, switch_names, var_names)
            trigger_raw = page.get("trigger")
            trigger = _TRIGGER_NAMES.get(trigger_raw, str(trigger_raw))
            row = ManifestRow(
                row_id=page_row_id(map_id, event_id, page_idx),
                kind="page",
                map_id=map_id,
                content_hash=content_hash(page),
                effects=extracted["effects"],
                script_heads=extracted["script_heads"],
                unrecognized_heads=extracted["unrecognized_heads"],
                other_codes=extracted["other_codes"],
                requires=extracted["requires"],
                unhandled=unhandled_counts.get((map_id, event_id, page_idx), 0),
                script_typed_conditions=extracted["script_typed_conditions"],
                event_id=event_id,
                event_name=event_name,
                page_idx=page_idx,
                condition=condition,
                trigger=trigger,
            )
            rows.append(row)
    return rows


def _generate_seam_rows(
    map_ids: set[int],
    connections: list[list[Any]],
) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    for conn in connections:
        if len(conn) < 6:
            continue
        map_a, dir_a, off_a, map_b, dir_b, off_b = conn[:6]
        if map_a in map_ids:
            seam = SeamRef(
                map_id=map_a, direction=dir_a, offset=off_a,
                other_map_id=map_b, other_direction=dir_b, other_offset=off_b,
            )
            rows.append(ManifestRow(
                row_id=seam_row_id(map_a, dir_a, map_b),
                kind="seam",
                map_id=map_a,
                content_hash=content_hash(list(conn)),
                effects=("warp",),
                seam=seam,
            ))
        if map_b in map_ids:
            seam = SeamRef(
                map_id=map_b, direction=dir_b, offset=off_b,
                other_map_id=map_a, other_direction=dir_a, other_offset=off_a,
            )
            rows.append(ManifestRow(
                row_id=seam_row_id(map_b, dir_b, map_a),
                kind="seam",
                map_id=map_b,
                content_hash=content_hash(list(conn)),
                effects=("warp",),
                seam=seam,
            ))
    return rows


def _load_chapter_maps(chapter_id: str, chapters_path: Path) -> list[int]:
    data = _load_json(chapters_path)
    for chapter in data.get("chapters", []):
        if chapter.get("id") == chapter_id:
            return list(chapter.get("maps", []))
    raise ValueError(f"chapter manifest: no chapter {chapter_id!r} in {chapters_path}")


def generate_chapter_manifest(
    chapter_id: str,
    *,
    build_dir: Path,
    chapters_path: Path,
) -> list[ManifestRow]:
    """Generates every manifest row for `chapter_id`'s maps.

    Pure derivation from `build_dir` (`output/uranium-build/`) and
    `chapters_path` (`reference/chapters.json`). Never filters (Q2ii): every
    page of every event on every chapter map is emitted, plus one seam row per
    `connections.json` entry touching a chapter map, from that map's side.
    """
    map_ids = _load_chapter_maps(chapter_id, chapters_path)
    maps_dir = build_dir / "maps"

    switch_names = _load_name_table(
        Path("reference/uranium_switches.json"))
    var_names = _load_name_table(
        Path("reference/uranium_variables.json"))
    unhandled_counts = _load_unhandled_counts(build_dir / "transpile_unhandled.jsonl")

    conn_path = build_dir / "connections.json"
    connections = _load_json(conn_path) if conn_path.exists() else []

    rows: list[ManifestRow] = []
    for map_id in map_ids:
        map_path = maps_dir / f"Map{map_id:03d}.json"
        if not map_path.exists():
            raise FileNotFoundError(
                f"chapter manifest: no converted map for id {map_id} at {map_path}")
        map_data = _load_json(map_path)
        rows.extend(_generate_page_rows(
            map_id, map_data, switch_names, var_names, unhandled_counts))

    rows.extend(_generate_seam_rows(set(map_ids), connections))

    rows.sort(key=lambda r: r.row_id)
    return rows


def write_manifest(rows: list[ManifestRow], path: Path) -> None:
    """Serializes `rows` to JSON deterministically: sorted by row_id, indent
    2, trailing newline, non-ASCII left as-is. Idempotence (CLAUDE.md §4.2)
    depends on this being the only writer and on every field within a row
    already being pre-sorted by the generator."""
    ordered = sorted(rows, key=lambda r: r.row_id)
    payload = [row_to_dict(row) for row in ordered]
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")
