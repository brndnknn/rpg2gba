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

import functools
import itertools
import json
import logging
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rpg2gba.chapter_atlas.census import (
    CODE_CONDITIONAL,
    CODE_SCRIPT,
    CODE_SCRIPT_CONT,
    COND_TYPE_SCRIPT,
    MECHANIC_BY_HEAD,
    RUBY_KEYWORDS,
    _script_head,
)
from rpg2gba.chapter_manifest.conditions import classify_condition
from rpg2gba.chapter_manifest.derivation import derive_entry
from rpg2gba.chapter_manifest.schema import (
    BranchRef,
    ManifestRow,
    PageCondition,
    SeamRef,
    TerrainRef,
    branch_row_id,
    content_hash,
    page_row_id,
    row_id_sort_key,
    row_to_dict,
    seam_row_id,
    terrain_row_id,
)
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.conversion_agent.transpiler import (
    CONDITIONAL_BRANCH,
    SHOW_CHOICES,
    SHOW_TEXT_CONT,
    ChoiceNode,
    IfNode,
    LoopNode,
    Node,
    TextRun,
    parse_tree,
)
from rpg2gba.tileset_converter.stairs import (
    BEHAVIOR_BY_SIDE,
    StairCell,
    detect_stair_cells,
)
from rpg2gba.traversal.capabilities import CapabilityMap, build_capability_map
from rpg2gba.traversal.graph import MapGraph, build_map_graph
from rpg2gba.traversal.reachability import derive_blocked_verdict_for_event_from_starts

if TYPE_CHECKING:
    # Protocols only -- `generator.py` must not import `checker` at runtime
    # (same layering discipline `checker.py` itself uses for the packages
    # its own Protocol seams stand in for).
    from rpg2gba.chapter_manifest.checker import BeatModel, BoundaryModel

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
    # Set Event Location (202) -> `setobjectxy` (+ `turnobject` when the
    # command also sets a facing). Grouped with the move-route pair: all
    # three reposition an object and write no game state, so the same
    # cosmetic-safe reading applies.
    202: "move_route",
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
    # The four codes below were `other_codes` purely because this table
    # never named them, not because the transpiler cannot emit them
    # (REDERIVATION_PLAN.md 15.1 item 1). Tags follow what it actually
    # emits: 104 is stripped outright (`_STRIP_CODES`), 116 becomes
    # `removeobject`, and the 221/222 transition pair becomes
    # `fadescreen`.
    104: "text",  # Change Text Options — stripped; display-only
    116: "erase_event",  # Erase Event -> removeobject (persistent)
    221: "screen_fx",  # Prepare for Transition -> fadescreen(FADE_TO_BLACK)
    222: "screen_fx",  # Execute Transition -> fadescreen(FADE_FROM_BLACK)
    # Loop (112) / Break Loop (113) / Exit Event Processing (115): not
    # cosmetic-safe. 115 in particular terminates the remainder of a page's
    # command list, so a page carrying it cannot honestly be called decoration
    # — see schema.py's comment on COSMETIC_SAFE_TAGS.
    112: "control_flow",
    113: "control_flow",
    115: "control_flow",
    # Label (118) / Jump to Label (119): the transpiler dispatches both
    # (`transpiler.py` LABEL/JUMP_TO_LABEL -> `goto`), so leaving them out
    # of this table put a understood command into `other_codes`, which
    # reads as "we do not know what this is". Tagged `control_flow` with
    # 112/113 rather than filed under `_CODE_BRANCH`: that set is the
    # if/else family the extractor walks into, while these are jumps, the
    # same shape as Loop and Break Loop.
    118: "control_flow",
    119: "control_flow",
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
    # White-out respawn anchor, not `heal` — see schema.py's COSMETIC_SAFE_TAGS
    # comment (P8b item 3, REDERIVATION_PLAN.md §15.2/§15.6).
    "pbSetPokemonCenter": "respawn_write",
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
# tile(s) the player can actually be entering this map on -- for the offline
# reachability flood to start from. That used to be a hand-kept table
# (a table keyed by chapter and map, requiring a citation per entry,
# registered chapter by chapter). A5 (C6_GENERATOR_PLAN.md) replaced it: `_start_cells`
# below derives the same shape from source data via
# `beat_gen.reach.chapter_entry_cells` -- the engine spawn plus every landing
# a reachable warp/seam/connection puts the player on, flooded over the
# chapter's own chain (itself and its predecessors). A (chapter, map) pair
# with no derivable entry (nothing in the chain reaches it) still gets no
# reachability-derived requires -- `_HEAD_REQUIRES` alone keeps covering it,
# same graceful degrade as before.
@functools.cache
def _chapter_entry_cells(chapter_id: str, build_dir: Path) -> dict[int, frozenset[tuple[int, int]]]:
    """The derived `{map_id: entry_cells}` for `chapter_id`'s own maps (A5),
    computed once per (chapter_id, build_dir) -- building the graphs/world
    this needs is slow, and the generator calls this once per row's map.

    No NPC occupancy: `requires[]` answers "which field move opens this", and
    a story NPC standing in a door (CH03's Grott-Hole) is not a field move.
    The route solver and `beat_gen`'s geography pass do treat NPCs as walls;
    that is where a story-blocked map is deferred.

    Fails loud: an unknown chapter or a build missing the chain's map data
    is a real fault (§4.5). A synthetic test build patches `_start_cells`.

    Imports the routing/beat_gen/chapter_atlas pieces lazily to avoid an
    import cycle (`chapter_manifest` is imported from lower in the stack than
    `routing`)."""
    from rpg2gba.beat_gen.reach import chapter_entry_cells
    from rpg2gba.chapter_atlas.binding import load_binding
    from rpg2gba.routing.__main__ import _build_graphs_and_overlays, _build_world

    binding = load_binding(Path("reference/chapters.json"))
    chapter = binding.chapter(chapter_id)
    chain: list[int] = list(chapter.maps)
    predecessor = chapter.predecessor
    while predecessor is not None:
        pred_chapter = binding.chapter(predecessor)
        chain = list(pred_chapter.maps) + chain
        predecessor = pred_chapter.predecessor

    graphs, _ = _build_graphs_and_overlays(chain, build_dir)
    return chapter_entry_cells(frozenset(chapter.maps), frozenset(chain), graphs,
                               _build_world(build_dir))


def _start_cells(
    chapter_id: str, map_id: int, build_dir: Path,
) -> frozenset[tuple[int, int]] | None:
    """The derived entry cells for `(chapter_id, map_id)` (A5), or None when
    the set is empty -- nothing in the chapter's chain reaches this map, or
    the derivation itself could not run (see `_chapter_entry_cells`).
    Replaces the hand-kept per-chapter start-cell table (A5)."""
    cells = _chapter_entry_cells(chapter_id, build_dir).get(map_id)
    return cells if cells else None


ReachabilityContext = tuple[MapGraph, CapabilityMap, frozenset[tuple[int, int]]]


def _build_reachability_context(
    chapter_id: str,
    map_id: int,
    maps_dir: Path,
    tilesets_json: Path,
) -> ReachabilityContext | None:
    """The (graph, capability_map, start_cells) triple for reachability-
    derived requires on `map_id`, or None if `map_id` has no derivable start
    cells for `chapter_id` (see `_start_cells`).

    `start_cells` is a frozenset, not a single cell, because one map can hold
    several disconnected walkable components each entered by its own door
    (e.g. Kevlar's building strip); the reachability flood unions all of them
    via `reachability.derive_blocked_verdict_for_event_from_starts`.

    `maps_dir`/`tilesets_json` are threaded through from the same `build_dir`
    the generator itself reads (never the traversal package's own defaults),
    so a chapter built against a non-default `build_dir` (e.g. a test
    fixture) doesn't silently fall back to reading the real corpus."""
    starts = _start_cells(chapter_id, map_id, maps_dir.parent)
    if starts is None:
        logger.warning(
            "chapter manifest: %s map %03d has no derivable entry cell -- the "
            "offline reachability source was NOT consulted for this map. "
            "Terrain-gated capabilities (surf, waterfall) cannot appear in "
            "requires[] for ANY row on this map as a result, and _HEAD_REQUIRES "
            "structurally cannot express them either -- an absence of requires "
            "entries here is not evidence the map has no capability gates. "
            "No reachable warp/seam/connection lands on this map from the "
            "engine spawn over this chapter's chain.",
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
    """Capabilities needed to actually GET PAST `event_cell` -- reach an
    orthogonally-adjacent tile AND, if the event is itself an obstacle
    (a Rock Smash rock, a Strength boulder), clear it -- derived from the
    offline traversal graph via `require_clearing=True` (backlog #95: the
    approach-only question used to answer `reachable_now=True` for a rock
    reachable from either side even though the rock itself was never
    cleared, which silently dropped 5 of CH04's hand-authored
    `blocked:rock_smash` rows). Empty when `context` is None (no verified
    start cell -- see `_build_reachability_context`), when the event is
    already clear with nothing held, or when no `VERIFIED_CAPABILITIES`
    combination opens it at all (`derive_blocked_verdict_for_event_from_starts`'s
    empty `minimal_sets` -- true geography, not a capability gate, so it is
    not added here).

    `ManifestRow.requires` stays a flat `tuple[str, ...]` (schema change out
    of scope for this function); it reports ONE minimal set -- the smallest,
    per `_minimal_sets_for_predicate`'s ordering -- even when the verdict
    carries several independent alternatives. The full disjunction is not
    lost: the disposition layer (`BlockedVerdict.as_disposition`,
    `schema.parse_blocked_argument`) carries every minimal set. When more
    than one exists here, the narrowing is logged so it stays legible in the
    build log rather than silently discarding the alternatives."""
    if context is None:
        return ()
    graph, capability_map, starts = context
    # `require_clearing=True`: this populates `requires[]`, which is asking
    # what the player needs to actually GET PAST this event, not merely
    # stand next to it -- for a Rock Smash rock or Strength boulder that
    # means the obstacle's own capability, not just an open approach tile
    # (backlog #95; see `reachability.derive_blocked_verdict_for_event`'s
    # docstring for the two-question distinction and the CH04 evidence).
    verdict = derive_blocked_verdict_for_event_from_starts(
        graph, capability_map, starts, event_cell, require_clearing=True,
    )
    if verdict.reachable_now or not verdict.minimal_sets:
        return ()
    best = verdict.minimal_sets[0]
    if len(verdict.minimal_sets) > 1:
        alternatives = verdict.minimal_sets[1:]
        logger.warning(
            "event cell %s has %d independent minimal capability sets; "
            "requires[] keeps only %s -- alternative(s) %s are dropped from "
            "the manifest row and survive only in the disposition layer",
            event_cell,
            len(verdict.minimal_sets),
            "+".join(sorted(c.value for c in best)),
            ", ".join("+".join(sorted(c.value for c in s)) for s in alternatives),
        )
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
    """Count queue entries per `(map_id, event_id, page)`.

    The `page` key is **0-based**, matching the `pN` component of the
    manifest `row_id` this counter is looked up with (`page_row_id`).
    That agreement was the #98 bug: the queue writer emitted 1-based
    pages while this table is queried with a 0-based `page_idx`, so a
    page's `unhandled` count silently came from its neighbour. Fixed on
    the writer side (`conversion_agent/transpiler.py`) so `row_id`s did
    not have to move. Script block labels stay 1-based and are
    deliberately a separate numbering -- see the note at the writer.
    """
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
    # The condition text itself, captured rather than discarded (see the
    # module-level note below and REDERIVATION_PLAN.md §14.6, Ruling 2). A
    # page can carry more than one code-111/type-12 branch (nested or
    # sequential conditionals), so this is a list, not a single string.
    script_condition_texts: list[str] = []

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
                    script_condition_texts.append(params[1])
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
    # this shape (census.py's note, reused verbatim by the brief). This reads
    # `script_condition_texts`, captured above, rather than re-walking
    # `commands` a second time -- the two loops used to derive the same
    # information independently (REDERIVATION_PLAN.md §14.6), which is also
    # what let the condition text itself go unclassified for so long: the
    # walk that had it in hand only ever asked "what's the head," never "does
    # this whole text match a known idiom."
    condition_families: set[str] = set()
    condition_unclassified: set[str] = set()
    for text in script_condition_texts:
        head = _script_head(text)
        if head and head not in RUBY_KEYWORDS:
            _record_head(head)
        family = classify_condition(text)
        if family is not None:
            condition_families.add(family.name)
        else:
            condition_unclassified.add(" ".join(text.split()))

    return {
        "effects": tuple(sorted(effects)),
        "other_codes": tuple(sorted(other_codes)),
        "script_heads": tuple(sorted(script_heads)),
        "unrecognized_heads": tuple(sorted(unrecognized_heads)),
        "requires": tuple(sorted(requires)),
        "script_typed_conditions": script_typed_conditions,
        "condition_families": tuple(sorted(condition_families)),
        "condition_unclassified": tuple(sorted(condition_unclassified)),
    }


def _flatten_scope(nodes: list[Node], commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The raw commands one scope owns, per REDERIVATION_PLAN.md §16.3 C1b:
    a `Leaf`/`TextRun` contributes its own raw command(s); a `LoopNode`
    (code 112) is transparent -- its body belongs to the ENCLOSING scope,
    not a branch of its own -- so its opener plus its flattened children are
    both included; an `IfNode`/`ChoiceNode` contributes only its OPENER
    command (the 111 with its condition text, the 102 with its choice list)
    -- its arm bodies are each a separate scope, walked by `_walk_branches`,
    never flattened in here. That is what keeps an arm's effects counted
    exactly once: the opener line the arm's own condition/choice-list lives
    on is trunk (or the enclosing arm's) content; the arm's body commands
    only ever appear in `_flatten_scope` when `_walk_branches` calls this
    function again for that arm's own `children` list.

    A `TextRun`'s trailing 401 continuations are not stored as their own
    nodes (`parse_tree` merges them into `TextRun.text`), so they are
    re-collected here by scanning forward from the node's own index --
    the same adjacency `parse_tree` itself walked, replayed against the
    same `commands` list so the two never disagree.
    """
    out: list[dict[str, Any]] = []
    for node in nodes:
        if isinstance(node, TextRun):
            idx = node.index
            out.append(commands[idx])
            j = idx + 1
            while j < len(commands) and commands[j].get("code") == SHOW_TEXT_CONT:
                out.append(commands[j])
                j += 1
        elif isinstance(node, LoopNode):
            out.append(node.cmd)
            out.extend(_flatten_scope(node.children, commands))
        elif isinstance(node, (IfNode, ChoiceNode)):
            out.append(node.cmd)
        else:  # Leaf
            out.append(node.cmd)
    return out


def _arms_skeleton(nodes: list[Node]) -> list[dict[str, Any]]:
    """A structural (not content) summary of every branch construct directly
    owned by `nodes`' scope -- used only inside a row's `content_hash`
    payload (REDERIVATION_PLAN.md §16.3 C1b): "the trunk hash must still
    change if an arm's structure changes ... hash the trunk commands plus a
    skeleton of the arms." `_flatten_scope` above already includes each
    opener's raw command (condition text / choice list) in the scope's own
    hash input, but NOT whether a 111 had a real 411 in the source -- that
    fact only lives in `IfNode.otherwise is None` vs `[]`, which is
    otherwise invisible to a bare command dump. This closes that gap.

    Recurses through `LoopNode` (transparent, same as `_flatten_scope`) but
    stops at `IfNode`/`ChoiceNode` -- a nested branch's OWN skeleton is that
    arm's concern (via its own `content_hash`), not this scope's.
    """
    out: list[dict[str, Any]] = []
    for node in nodes:
        if isinstance(node, IfNode):
            out.append({"kind": "if", "index": node.index, "has_else": node.otherwise is not None})
        elif isinstance(node, ChoiceNode):
            out.append({
                "kind": "choice",
                "index": node.index,
                "arms": [[ci, ct] for ci, ct, _ in node.arms],
            })
        elif isinstance(node, LoopNode):
            out.extend(_arms_skeleton(node.children))
    return out


@dataclass
class PageScope:
    """One scope on a page -- the trunk, or one branch arm -- with the id,
    parent and `BranchRef` it would own as a manifest row, plus its own flat
    command list and direct child nodes (REDERIVATION_PLAN.md §16.3 C2a
    item 1: single source for row scopes).

    `row_id`/`parent_row_id`/`branch` are exactly what `_generate_page_rows`
    used to compute inline per arm; `iter_page_scopes` is now the one place
    that walk happens, so `story_state.extract` (which needs the same ids
    without re-deriving them) and the manifest generator both consume it
    rather than each carrying their own copy of the arm-numbering walk.

    The trunk scope (`branch is None`, `parent_row_id is None`) is always
    first; every branch-arm scope follows in the same flat `bN` source order
    `branch_row_id` expects (arm openers in source order, depth-first).
    """

    row_id: str
    parent_row_id: str | None
    branch: BranchRef | None
    commands: list[dict[str, Any]]
    nodes: list[Node]


def _walk_scopes(
    nodes: list[Node],
    parent_row_id: str,
    page_row_id_: str,
    commands: list[dict[str, Any]],
    counter: Iterator[int],
    out: list[PageScope],
) -> None:
    """Depth-first walk assigning flat `bN` ids in source order of arm
    openers (REDERIVATION_PLAN.md §16.3 C1c). A plain recursive pre-order
    walk produces exactly that order: every nested node's flat `index` sits
    strictly between its parent opener's index and the parent's next
    sibling, so visiting a node's own arms immediately (before moving to the
    next sibling in `nodes`) is equivalent to a global sort of every
    branch-construct by `.index`.

    `LoopNode` is transparent here too (ruling: "Code 112 loops are NOT
    branches"): its children are walked at the SAME `parent_row_id`, not
    given a scope of their own.
    """
    for node in nodes:
        if isinstance(node, IfNode):
            params = node.cmd.get("parameters") or []
            condition_type = params[0] if len(params) >= 1 else None
            condition_text = params[1] if len(params) >= 2 and isinstance(params[1], str) else None

            then_index = next(counter)
            then_row_id = branch_row_id(page_row_id_, then_index)
            then_branch = BranchRef(
                arm_index=then_index, arm_kind="then",
                opener_code=CONDITIONAL_BRANCH, opener_index=node.index,
                choice_index=None, choice_text=None,
                condition_type=condition_type, condition_text=condition_text,
                explicit=True,
            )
            out.append(PageScope(
                row_id=then_row_id, parent_row_id=parent_row_id, branch=then_branch,
                commands=_flatten_scope(node.then, commands), nodes=node.then,
            ))
            _walk_scopes(node.then, then_row_id, page_row_id_, commands, counter, out)

            else_children = node.otherwise if node.otherwise is not None else []
            else_index = next(counter)
            else_row_id = branch_row_id(page_row_id_, else_index)
            else_branch = BranchRef(
                arm_index=else_index, arm_kind="else",
                opener_code=CONDITIONAL_BRANCH, opener_index=node.index,
                choice_index=None, choice_text=None,
                condition_type=condition_type, condition_text=condition_text,
                explicit=node.otherwise is not None,
            )
            out.append(PageScope(
                row_id=else_row_id, parent_row_id=parent_row_id, branch=else_branch,
                commands=_flatten_scope(else_children, commands), nodes=else_children,
            ))
            _walk_scopes(else_children, else_row_id, page_row_id_, commands, counter, out)

        elif isinstance(node, ChoiceNode):
            for choice_index, choice_text, children in node.arms:
                arm_kind = "cancel" if choice_index is None else "choice"
                arm_index = next(counter)
                row_id = branch_row_id(page_row_id_, arm_index)
                branch = BranchRef(
                    arm_index=arm_index, arm_kind=arm_kind,  # type: ignore[arg-type]
                    opener_code=SHOW_CHOICES, opener_index=node.index,
                    choice_index=choice_index, choice_text=choice_text,
                    condition_type=None, condition_text=None,
                    explicit=True,
                )
                out.append(PageScope(
                    row_id=row_id, parent_row_id=parent_row_id, branch=branch,
                    commands=_flatten_scope(children, commands), nodes=children,
                ))
                _walk_scopes(children, row_id, page_row_id_, commands, counter, out)

        elif isinstance(node, LoopNode):
            _walk_scopes(node.children, parent_row_id, page_row_id_, commands, counter, out)

        # Leaf / TextRun: no nested branch structure possible.


def iter_page_scopes(
    map_id: int, event: dict[str, Any], page_idx: int, page: dict[str, Any],
) -> list[PageScope]:
    """Every scope on one event page: the trunk first, then each branch arm
    in flat `bN` source order (REDERIVATION_PLAN.md §16.3 C2a item 1).

    The single implementation of "what scope does each row own" -- arm
    numbering, parent linkage, and `BranchRef` construction all happen here
    exactly once; `_generate_page_rows` (this module) and
    `story_state.extract` both consume this instead of each walking
    `parse_tree`'s output themselves.
    """
    commands = page.get("list") or []
    tree = parse_tree(commands)
    row_id = page_row_id(map_id, event["id"], page_idx)
    scopes: list[PageScope] = [PageScope(
        row_id=row_id, parent_row_id=None, branch=None,
        commands=_flatten_scope(tree, commands), nodes=tree,
    )]
    _walk_scopes(tree, row_id, row_id, commands, itertools.count(), scopes)
    return scopes


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
            condition = _build_condition(
                page.get("condition") or {}, switch_names, var_names)
            trigger_raw = page.get("trigger")
            trigger = _TRIGGER_NAMES.get(trigger_raw, str(trigger_raw))
            unhandled = (
                unhandled_counts.get((map_id, event_id, page_idx), 0)
                if map_id in staged_map_ids else None
            )

            scopes = iter_page_scopes(map_id, event, page_idx, page)
            for scope in scopes:
                extracted = _extract_page(scope.commands)
                skeleton = _arms_skeleton(scope.nodes)
                requires = tuple(sorted(set(extracted["requires"]) | set(reach_requires)))
                if scope.branch is None:
                    # Trunk-only hash (REDERIVATION_PLAN.md §16.3 C1b): every
                    # page-level, non-command field (condition/graphic/
                    # trigger/move_route/...) still goes in, same as the old
                    # `content_hash(page)`; only `"list"` is swapped for the
                    # trunk-only command dump, plus an explicit arm skeleton
                    # so the hash still changes when an arm is added/removed
                    # even though its CONTENTS live in that arm row's own
                    # hash, not here. A page with no arms hashes exactly as
                    # it did before C1 -- its trunk IS its list -- so R5
                    # invalidates branching pages only.
                    payload = (
                        {**page, "list": scope.commands, "arms_skeleton": skeleton}
                        if skeleton else page
                    )
                    kind = "page"
                    branch = None
                else:
                    # The BranchRef (condition text / choice text) goes in
                    # too: an arm's meaning depends on what selects it, so a
                    # decision on the then-arm of `pbTrainerBattle(A)` must
                    # go stale when the condition becomes
                    # `pbTrainerBattle(B)`, even with the arm body untouched.
                    payload = {
                        "commands": scope.commands,
                        "arms_skeleton": skeleton,
                        "branch": asdict(scope.branch),
                    }
                    kind = "branch"
                    branch = scope.branch
                rows.append(ManifestRow(
                    row_id=scope.row_id,
                    kind=kind,  # type: ignore[arg-type]
                    map_id=map_id,
                    content_hash=content_hash(payload),
                    effects=extracted["effects"],
                    script_heads=extracted["script_heads"],
                    unrecognized_heads=extracted["unrecognized_heads"],
                    other_codes=extracted["other_codes"],
                    requires=requires,
                    unhandled=unhandled,
                    script_typed_conditions=extracted["script_typed_conditions"],
                    condition_families=extracted["condition_families"],
                    condition_unclassified=extracted["condition_unclassified"],
                    event_id=event_id,
                    event_name=event_name,
                    page_idx=page_idx,
                    condition=condition,
                    trigger=trigger,
                    reachability_consulted=reachability_consulted,
                    branch=branch,
                    parent_row_id=scope.parent_row_id,
                ))
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

    rows.sort(key=lambda r: row_id_sort_key(r.row_id))
    return rows


def write_manifest(rows: list[ManifestRow], path: Path) -> None:
    """Serializes `rows` to JSON deterministically: sorted by row_id, indent
    2, trailing newline, non-ASCII left as-is. Idempotence (CLAUDE.md §4.2)
    depends on this being the only writer and on every field within a row
    already being pre-sorted by the generator."""
    ordered = sorted(rows, key=lambda r: row_id_sort_key(r.row_id))
    payload = [row_to_dict(row) for row in ordered]
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")


def write_derived(
    rows: list[ManifestRow],
    path: Path,
    *,
    beat_model: "BeatModel | None" = None,
    boundary_model: "BoundaryModel | None" = None,
) -> None:
    """Writes the machine-derived sidecar (format v2, `REDERIVATION_PLAN.md`
    §15.2 item 1, narrowed by the 2026-09-14 four-verdict ruling).

    Every row `derivation.derive_entry` resolves to a `DerivedEntry` gets a
    sidecar entry -- `{"disposition": ..., "derived_hash": ...}`, with
    `"proposed": true` present only on a `blocked:` proposal. `derived_hash`
    is the row's `content_hash` at generation time, the same value
    `checker.py` compares an authored disposition's `affirmed_hash` against,
    so a later content change invalidates a sidecar entry exactly the way it
    invalidates a human affirmation.

    `checker.check_chapter` never trusts this file's judgment at check
    time -- it independently recomputes `derive_entry` for every row rather
    than trusting whatever this function wrote earlier (CLAUDE.md §4.5:
    never trust a stored claim's mere presence), so drift between "what the
    generator derived when it wrote this" and "what the checker derives now"
    is caught, not silently inherited. `beat_model`/`boundary_model` are
    threaded through for the same reason `check_cmd` builds them: without
    them, `derive_entry` can still resolve `blocked:`/`cosmetic` but never
    `beat:`/`boundary`.

    This module's single-writer invariant for the AUTHORED dispositions file
    (see the package docstring) is unaffected: this function writes only the
    sidecar, never `CHnn.dispositions.json`, and a `blocked:` entry here is
    explicitly a proposal, not a disposition -- a human must copy it into
    the dispositions file with an `affirmed_hash` before it counts as one
    (`checker.RULE_DERIVED_UNAFFIRMED`).
    """
    entries = {
        row.row_id: entry
        for row in sorted(rows, key=lambda r: row_id_sort_key(r.row_id))
        for entry in (derive_entry(row, beat_model=beat_model, boundary_model=boundary_model),)
        if entry is not None
    }
    payload: dict[str, Any] = {}
    for row_id in sorted(entries):
        entry = entries[row_id]
        obj: dict[str, Any] = {
            "disposition": entry.disposition,
            "derived_hash": entry.derived_hash,
        }
        if entry.proposed:
            obj["proposed"] = True
        payload[row_id] = obj
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")
