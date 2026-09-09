"""Builds the generated half of the per-chapter manifest (see the package
docstring in ``__init__.py``).

Joins four sources under ``output/uranium-build/`` for the chapter's own map
list (``reference/chapters.json``):

* ``maps/Map###.json``            — one row per event page, unconditionally
  (the generator never filters — see Q2(ii) in PLAYTEST_AUTHORING_IMPROVEMENT.md),
  except diagonal-stair events (`tileset_converter.stairs`), which are
  absorbed into a `kind="terrain"` row instead of an ordinary page row
* ``connections.json``            — one seam row per overland connection
  touching a chapter map, emitted from that map's side
* ``transpile_unhandled.jsonl``   — joined on (map_id, event_id, page) to set
  ``unhandled``, which vetoes a `cosmetic` disposition (Q1) — but only for
  rows on a map that ``scripts/`` (below) says was actually staged
* ``scripts/Map###.pory``         — ground truth for which maps were
  transpiled at all; a map absent here gets `unhandled=None` on every row,
  not `0` (`_load_staged_map_ids`) — see `ManifestRow.unhandled`'s docstring

Nothing here is authored and nothing here filters. Idempotence (CLAUDE.md
§4.2) is load-bearing: every tuple field on `ManifestRow` is built pre-sorted
so re-running the generator against unchanged input reproduces the same JSON
byte for byte.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import asdict
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
    TerrainRef,
    content_hash,
    page_row_id,
    row_to_dict,
    seam_row_id,
    terrain_row_id,
)
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.tileset_converter.stairs import (
    BEHAVIOR_BY_SIDE,
    StairCell,
    detect_stair_cells,
)
from rpg2gba.traversal.capabilities import CapabilityMap, build_capability_map
from rpg2gba.traversal.graph import MapGraph, build_map_graph
from rpg2gba.traversal.reachability import derive_blocked_verdict_for_event_from_starts

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

# --- reachability-derived requires (second source; schema.py's `requires`
# field docstring) ------------------------------------------------------
#
# `_HEAD_REQUIRES` above finds capability gates in a row's own INTERACTION --
# the event's script literally contains `pbRockSmash`. It cannot see a gate on
# a row's APPROACH: an NPC standing behind a rockslide carries no
# rock-smash-flavoured script of its own, because the geometry is the gate,
# not the text (`reference/frozen/slice2_derivation_diff.md`'s two-source
# split, confirmed on CH04: 24 approach-gated rows the head table cannot see,
# 4 interaction-gated rows it already covers, no overlap).
#
# Deriving "approach gated by which capability" needs a start cell -- the
# tile the player is actually standing on when they first reach this map --
# which is chapter authoring knowledge, not something recoverable from decoded
# map data alone. This table holds only start cells that have been verified
# against a chapter's own boot-walk harness; a (chapter, map) pair absent from
# it gets no reachability-derived requires at all (see
# `_build_reachability_context`), same as the corpus behaved before this
# table existed -- `_HEAD_REQUIRES` alone keeps covering it. That is a
# graceful degrade, not a fail-loud gap: most of the corpus has no verified
# start cell yet, and that is the chapter's current, expected, temporary
# state, not corrupted input data.
#
# CH04/map035 (21,56): `playtest/chapters/ch04.py:234`'s `KEVLAR_SEAM_ARROW`
# comment -- the MB_NORTH_ARROW_WARP tile lands the player at map035 (21,56).
# Cross-checked against the independent validation run recorded in
# `reference/frozen/slice2_derivation_diff.md`.
#
# Registering a new entry is a step in THAT chapter's own build, not a
# mystery to reverse-engineer here: the cost is finding the one cell the
# player is actually standing on at first arrival on that map, and it must
# come from the chapter's own boot-walk harness (an arrow-warp landing spot,
# a warp-exit constant, an emulator-observed post-load position) -- never
# guessed from map geometry or wiki prose. CH04's entry above is the worked
# example: `(21, 56)` is not this table's own invention, it is a comment
# transcribed from `ch04.py`'s harness constant and then cross-checked
# against an independent validation run. An entry added without that kind of
# citation is exactly the "written from priors, matches zero maps" failure
# `_HEAD_REQUIRES`'s own comment warns about, just moved to a different table.
#
# CH05/map036 (17,39) and CH05/map037 (16,26): both are warp-exit constants in
# the sense the paragraph above allows, read straight out of the decoded corpus
# rather than transcribed from a harness -- each map is entered by exactly ONE
# code-201 transfer, so its arrival cell is a fact about the data, not a choice:
#   map 36 <- `Map035.json` ev001 at (20,33), destination (17,39). Sole entry.
#   map 37 <- `Map036.json` ev002 at (17,4),  destination (16,26). Sole entry.
# Reproduced by `extract_warp_exits` on each source map, and both agree with the
# entrance cell the CH05 dry run used independently
# (`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`, §5.7).
#
# Stated plainly, because the paragraph above asks for a boot-walk citation and
# this is not one: **CH05 has no boot-walk harness yet** -- the chapter is not
# built. What backs these two entries is warp geometry plus an independent prose
# analysis, which is strictly stronger than a hand-typed guess and strictly
# weaker than an observed post-load position. If CH05's boot walk ever lands the
# player somewhere other than these cells, that is the harness correcting this
# table, and this comment is the reason to believe the harness.
# CH05/map035 (19,49) is the first entry in this table backed by the strongest
# citation the paragraph above names: an emulator-observed post-load position.
# CH05 does not WARP onto Route 02 -- it inherits the player there when CH04's
# last beat hands over -- so there is no warp-exit constant to read and no
# geometry to reason from; the only way to know the cell is to run it. The
# step-7 headless runs of 2026-09-06 recorded B1's entry as map 35 (19,49),
# identically across runs 4, 6, 7 and 8 and across both attempts of each.
#
# It is registered because the route solver needs it. CH05 begins with a walk
# across Route 02 to the cave mouth, and a plan whose entry node is anywhere
# else does not contain that walk -- which is how B1 came to leave the approved
# route onto Map035 EV012's trigger tile (Timothy, event touch) with nothing
# planning around it.
#
# The value type is a frozenset of cells, not a single cell (operator,
# 2026-09-09 -- REDERIVATION_PLAN.md P6a). Map 73 (Kevlar's building strip) is
# one map record holding FOUR shops in FOUR disconnected walkable components
# (verified: 70x15, five components; the four arrival cells -- (44,12)
# boutique, (5,11) bike shop, (24,12) Maury, (64,12) couple -- each sit in a
# different one), each entered by its own door from the town square. A single
# start cell can only flood one component, so it would judge every event
# behind the other three doors unreachable when they are perfectly reachable
# through their own doors -- and a wrong entry here is worse than a missing
# one: absent, `has_walkable_approach` returns None ("unanswerable", honest);
# present-but-wrong it returns False, a confident wrong answer. Every entry
# below is still cited exactly as the paragraphs above require; a
# single-cell map is simply the one-element case of the general shape.
_CHAPTER_MAP_START_CELLS: dict[tuple[str, int], frozenset[tuple[int, int]]] = {
    ("CH04", 35): frozenset({(21, 56)}),
    ("CH05", 35): frozenset({(19, 49)}),
    ("CH05", 36): frozenset({(17, 39)}),
    ("CH05", 37): frozenset({(16, 26)}),
}

ReachabilityContext = tuple[MapGraph, CapabilityMap, frozenset[tuple[int, int]]]


def _build_reachability_context(
    chapter_id: str,
    map_id: int,
    maps_dir: Path,
    tilesets_json: Path,
) -> ReachabilityContext | None:
    """The (graph, capability_map, start_cells) triple for reachability-
    derived requires on `map_id`, or None if `map_id` has no verified start
    cells for `chapter_id` yet (see `_CHAPTER_MAP_START_CELLS`).

    `start_cells` is a frozenset, not a single cell, because one map can hold
    several disconnected walkable components each entered by its own door
    (Kevlar's building strip, map 73 -- see the table's comment block); the
    reachability flood unions all of them via
    `reachability.derive_blocked_verdict_for_event_from_starts`.

    `maps_dir`/`tilesets_json` are threaded through from the same `build_dir`
    the generator itself reads (never the traversal package's own defaults),
    so a chapter built against a non-default `build_dir` (e.g. a test
    fixture) doesn't silently fall back to reading the real corpus."""
    starts = _CHAPTER_MAP_START_CELLS.get((chapter_id, map_id))
    if starts is None:
        logger.warning(
            "chapter manifest: %s map %03d has no verified start cell -- the "
            "offline reachability source was NOT consulted for this map. "
            "Terrain-gated capabilities (surf, waterfall) cannot appear in "
            "requires[] for ANY row on this map as a result, and _HEAD_REQUIRES "
            "structurally cannot express them either -- an absence of requires "
            "entries here is not evidence the map has no capability gates. "
            "Register a verified start cell in _CHAPTER_MAP_START_CELLS during "
            "this chapter's build to close the gap.",
            chapter_id, map_id,
        )
        return None
    graph = build_map_graph(map_id, maps_dir=maps_dir, tilesets_json=tilesets_json)
    capability_map = build_capability_map(map_id, maps_dir=maps_dir, tilesets_json=tilesets_json)
    return graph, capability_map, starts


def _reachability_requires(
    context: ReachabilityContext | None,
    event_cell: tuple[int, int],
) -> tuple[str, ...]:
    """Capabilities needed to even APPROACH `event_cell` (an orthogonally-
    adjacent tile), derived from the offline traversal graph. Empty when
    `context` is None (no verified start cell -- see
    `_build_reachability_context`), when the approach is already open with
    nothing held, or when no `VERIFIED_CAPABILITIES` combination opens it at
    all (`derive_blocked_verdict_for_event_from_starts`'s empty `minimal_sets` -- true
    geography, not a capability gate, so it is not added here)."""
    if context is None:
        return ()
    graph, capability_map, starts = context
    verdict = derive_blocked_verdict_for_event_from_starts(graph, capability_map, starts, event_cell)
    if verdict.reachable_now or not verdict.minimal_sets:
        return ()
    best = verdict.minimal_sets[0]
    return tuple(sorted(c.value for c in best))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


_STAGED_MAP_FILENAME = re.compile(r"^Map(\d+)\.pory$")


def _load_staged_map_ids(scripts_dir: Path) -> set[int]:
    """Map ids that were actually transpiled, from the transpiler's own
    output directory (`<build_dir>/scripts/Map###.pory`) -- NOT inferred
    from `transpile_unhandled.jsonl`'s contents.

    Inferring "staged" from the queue is the bug this exists to fix: a
    cleanly-transpiled map produces zero queue rows, which is
    indistinguishable from a map that was never staged at all if the queue
    is the only source consulted. `scripts_dir` is ground truth -- one
    `.pory` file per staged map, clean or not.
    """
    if not scripts_dir.exists():
        logger.warning(
            "chapter manifest: no scripts dir at %s; no map can be treated as "
            "staged, so every row's `unhandled` will be None (the safe "
            "default -- nothing can then be dispositioned cosmetic)",
            scripts_dir,
        )
        return set()
    staged: set[int] = set()
    for path in scripts_dir.iterdir():
        match = _STAGED_MAP_FILENAME.match(path.name)
        if match:
            staged.add(int(match.group(1)))
    return staged


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


def _generate_terrain_rows(
    map_id: int,
    stair_cells: list[StairCell],
    reachability_consulted: bool,
) -> list[ManifestRow]:
    """One `kind="terrain"` row per detected diagonal-stair cell.

    Takes the cells rather than the map so the caller detects once and uses
    the same answer for both halves of the absorption -- which page rows to
    skip, and which terrain rows to emit. Detection itself is
    `tileset_converter.stairs`'s job and is never re-implemented here: the
    layout converter is the single source of truth for which cells get which
    native metatile behaviour, and a second detector could disagree with it
    silently.
    """
    rows: list[ManifestRow] = []
    for cell in stair_cells:
        terrain = TerrainRef(
            x=cell.x, y=cell.y,
            behavior=BEHAVIOR_BY_SIDE[cell.side],
            source_event_id=cell.event_id,
        )
        rows.append(ManifestRow(
            row_id=terrain_row_id(map_id, "stairs", cell.x, cell.y),
            kind="terrain",
            map_id=map_id,
            content_hash=content_hash(asdict(terrain)),
            effects=(),
            terrain=terrain,
            reachability_consulted=reachability_consulted,
        ))
    return rows


def _generate_page_rows(
    map_id: int,
    map_data: dict[str, Any],
    switch_names: dict[int, str],
    var_names: dict[int, str],
    unhandled_counts: Counter[tuple[int, int, int]],
    reachability_context: ReachabilityContext | None,
    staged_map_ids: set[int],
) -> list[ManifestRow]:
    reachability_consulted = reachability_context is not None
    rows: list[ManifestRow] = []

    # Diagonal-stair events are absorbed into terrain rows (below) instead of
    # emitting an ordinary page row: the script itself is never emitted by
    # the layout converter, so a page row for it would describe output that
    # doesn't exist, and emitting both a page row and a terrain row for the
    # same cell would double-count the same traversal mechanic.
    stair_cells = detect_stair_cells(map_data)
    absorbed_event_ids = {cell.event_id for cell in stair_cells}
    rows.extend(_generate_terrain_rows(map_id, stair_cells, reachability_consulted))

    for event in map_data.get("events", []):
        event_id = event["id"]
        if event_id in absorbed_event_ids:
            continue
        event_name = event.get("name")
        event_cell = (event["x"], event["y"])
        reach_requires = _reachability_requires(reachability_context, event_cell)
        for page_idx, page in enumerate(event.get("pages", [])):
            commands = page.get("list") or []
            extracted = _extract_page(commands)
            condition = _build_condition(
                page.get("condition") or {}, switch_names, var_names)
            trigger_raw = page.get("trigger")
            trigger = _TRIGGER_NAMES.get(trigger_raw, str(trigger_raw))
            requires = tuple(sorted(set(extracted["requires"]) | set(reach_requires)))
            unhandled = (
                unhandled_counts.get((map_id, event_id, page_idx), 0)
                if map_id in staged_map_ids else None
            )
            row = ManifestRow(
                row_id=page_row_id(map_id, event_id, page_idx),
                kind="page",
                map_id=map_id,
                content_hash=content_hash(page),
                effects=extracted["effects"],
                script_heads=extracted["script_heads"],
                unrecognized_heads=extracted["unrecognized_heads"],
                other_codes=extracted["other_codes"],
                requires=requires,
                unhandled=unhandled,
                script_typed_conditions=extracted["script_typed_conditions"],
                event_id=event_id,
                event_name=event_name,
                page_idx=page_idx,
                condition=condition,
                trigger=trigger,
                reachability_consulted=reachability_consulted,
            )
            rows.append(row)
    return rows


def _generate_seam_rows(
    map_ids: set[int],
    connections: list[list[Any]],
    consulted_by_map: dict[int, bool],
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
                reachability_consulted=consulted_by_map.get(map_a, False),
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
                reachability_consulted=consulted_by_map.get(map_b, False),
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

    # Shared with the flag registry — one loader for the two sidecars (H2).
    # Anchored to the repo, not the CWD: the loader now fails loud on a missing
    # sidecar, and a CWD-relative path would turn "ran from another directory"
    # into that failure. The old CWD-relative read hid this by degrading to an
    # empty table, which is exactly the silent default §4.5 forbids.
    ref = Path(__file__).resolve().parents[3] / "reference"
    switch_names, var_names = load_label_tables(
        ref / "uranium_switches.json",
        ref / "uranium_variables.json",
    )
    unhandled_counts = _load_unhandled_counts(build_dir / "transpile_unhandled.jsonl")
    staged_map_ids = _load_staged_map_ids(build_dir / "scripts")

    conn_path = build_dir / "connections.json"
    connections = _load_json(conn_path) if conn_path.exists() else []

    rows: list[ManifestRow] = []
    consulted_by_map: dict[int, bool] = {}
    for map_id in map_ids:
        map_path = maps_dir / f"Map{map_id:03d}.json"
        if not map_path.exists():
            raise FileNotFoundError(
                f"chapter manifest: no converted map for id {map_id} at {map_path}")
        map_data = _load_json(map_path)
        reachability_context = _build_reachability_context(
            chapter_id, map_id, maps_dir, build_dir / "tilesets.json")
        consulted_by_map[map_id] = reachability_context is not None
        rows.extend(_generate_page_rows(
            map_id, map_data, switch_names, var_names, unhandled_counts,
            reachability_context, staged_map_ids))

    rows.extend(_generate_seam_rows(set(map_ids), connections, consulted_by_map))

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
