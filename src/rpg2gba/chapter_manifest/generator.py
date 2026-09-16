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
#
# CH01/CH02/CH03's 15 maps were registered as one batch on 2026-09-09
# (REDERIVATION_PLAN.md P6b) under a DERIVED rule, which is worth stating
# precisely because the paragraphs above ask for a boot-walk citation and
# this is a different kind of evidence:
#
#   For each (chapter, map), take every literal code-201 destination that
#   targets that map from a source map in the current slice, drop self-warps,
#   and drop destinations that are not walkable. Register what remains.
#
# The dropped-unwalkable step matters and is not hygiene: Map031's (23,28),
# (32,28), (35,6), (37,28) and Map033's (39,18) are shop-exit DOOR tiles --
# blocked metatiles the warp lands you on and steps you off. As reachability
# starts they flood nothing, so registering one would produce exactly the
# confident-wrong-answer the paragraph above warns about.
#
# WHY A DERIVED SET IS SOUND HERE, when a single guessed cell would not be.
# This set is a SUPERSET of "the cell the player first arrives on" -- it is
# every cell they can arrive on. That would be dangerous if it could
# over-report reachability, i.e. if some registered cell sat in a component
# the chapter cannot actually reach. It cannot, on 14 of these 15 maps:
# every registered cell on them lies in ONE connected component (verified
# 2026-09-09 via `graph.connected_components()`), so the flood is provably
# identical whichever cell is chosen, and the exact first-arrival is
# unobservable for this table's purpose. The proof is monotone in
# capabilities: two cells sharing a no-capability component remain in the
# same component under any capability that is later added, since adding a
# capability only ever merges components. Map 73 is the sole exception -- its
# four cells are four components -- and there all four ARE genuinely entered
# during CH03 (ch03.py carries BOUTIQUE_ARRIVAL, BIKE_SHOP_ARRIVAL,
# MAURY_ARRIVAL and COUPLE_ARRIVAL, each position-verified across CH03's
# green gate), so the set is exact rather than a superset.
#
# This is emphatically NOT a licence to guess a cell on a future map. It is
# the narrow case where the answer does not depend on the guess, and it comes
# with the check that establishes that. A map whose arrival cells span more
# than one component gets no such pass: register every genuinely-used door
# (map 73) or leave it out.
#
# CH01/49 (7,7) is the one entry here that is NOT derived from a warp: CH01
# begins there on a fresh save via this fork's own new-game spawn override
# (`engine/src/new_game.c:174`, "Map049 @ 7,7, URANIUM_START_MAP"), so the
# engine source is the citation. It shares component 0 with that map's two
# warp arrivals, so it does not change the flood -- it is registered because
# it is the true first-arrival and the table should say so where it can.
_CHAPTER_MAP_START_CELLS: dict[tuple[str, int], frozenset[tuple[int, int]]] = {
    # -- CH01 Moki Town ------------------------------------------------
    # (7,7) engine spawn override; (10,9) <- Map032 ev005 (front door);
    # (11,3) <- Map048 ev002 (stairs down).
    ("CH01", 49): frozenset({(7, 7), (10, 9), (11, 3)}),
    # (4,3) <- Map049 ev003, (4,6) <- Map049 ev021 -- the two staircases.
    ("CH01", 48): frozenset({(4, 3), (4, 6)}),
    # The town square. (28,31) <- Map049 ev002 is CH01's true first arrival
    # (leaving the player's house); the rest are returns from the lab
    # (17,11), houses (43,31)/(24,42), Theo's (56,42), and Route 1 (8,43).
    ("CH01", 32): frozenset({
        (8, 43), (17, 11), (24, 42), (28, 31), (43, 31), (56, 42),
    }),
    # (14,18) <- Map032 ev003 (the lab door); (14,7) <- Map032 ev078, a
    # scripted event-touch cutscene warp rather than a normal door.
    ("CH01", 50): frozenset({(14, 7), (14, 18)}),
    ("CH01", 64): frozenset({(9, 12)}),   # <- Map032 ev006
    ("CH01", 65): frozenset({(9, 12)}),   # <- Map032 ev007
    # Theo's house. (10,10) <- Map032 ev017 (door); (11,3) <- Map089 ev002
    # (stairs down from 2F).
    ("CH01", 172): frozenset({(10, 10), (11, 3)}),
    ("CH01", 89): frozenset({(4, 3)}),    # <- Map172 ev003 (stairs up)
    # -- CH02 Route 1 --------------------------------------------------
    # (70,11) <- Map032 ev023/ev036/ev037, the three-tile Moki exit strip,
    # all agreeing on one destination -- CH02's first arrival, and the cell
    # ch02.py's B1_ARRIVAL already position-asserts. (15,7)/(16,7) are
    # the Kevlar returns (Map031 ev023/ev035).
    ("CH02", 33): frozenset({(15, 7), (16, 7), (70, 11)}),
    ("CH02", 81): frozenset({(9, 12)}),   # <- Map033 ev027 (old rod house)
    # -- CH03 Kevlar Town ----------------------------------------------
    # (15,42)/(16,42) <- Map033 ev045/ev046, the two-tile Route 1 seam and
    # CH03's first arrival -- ch03.py's B27 position-asserts (16,42) with
    # tolerance=0. The rest are returns: cave (13,7), Center (20,12),
    # Mart (37,14).
    ("CH03", 31): frozenset({(13, 7), (15, 42), (16, 42), (20, 12), (37, 14)}),
    ("CH03", 67): frozenset({(10, 10)}),  # <- Map031 ev002 (Mart)
    # <- Map031 ev003 and ev049, two door tiles agreeing on one destination.
    ("CH03", 68): frozenset({(8, 18)}),
    # The four-shop strip -- four doors, four components, all four used in
    # CH03. Map031 ev004 boutique, ev012 bike shop, ev013 Maury, ev041 couple.
    ("CH03", 73): frozenset({(5, 11), (24, 12), (44, 12), (64, 12)}),
    ("CH03", 19): frozenset({(11, 29)}),  # <- Map031 ev034 (Grott-Hole cave)
    # -- CH04 / CH05 (registered during their own builds) ---------------
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
class _BranchWalkContext:
    """Fields every branch-arm row copies verbatim from its page row
    (REDERIVATION_PLAN.md §16.3 C1), plus what `_walk_branches` needs to
    build one."""

    map_id: int
    event_id: int
    event_name: str | None
    page_idx: int
    condition: PageCondition
    trigger: str
    unhandled: int | None
    reachability_consulted: bool
    reach_requires: tuple[str, ...]
    page_row_id: str
    commands: list[dict[str, Any]]


def _make_branch_row(
    ctx: "_BranchWalkContext",
    *,
    arm_index: int,
    arm_kind: str,
    opener_code: int,
    opener_index: int,
    choice_index: int | None,
    choice_text: str | None,
    condition_type: int | None,
    condition_text: str | None,
    explicit: bool,
    parent_row_id: str,
    children: list[Node],
) -> ManifestRow:
    scope_commands = _flatten_scope(children, ctx.commands)
    skeleton = _arms_skeleton(children)
    extracted = _extract_page(scope_commands)
    requires = tuple(sorted(set(extracted["requires"]) | set(ctx.reach_requires)))
    row_id = branch_row_id(ctx.page_row_id, arm_index)
    branch = BranchRef(
        arm_index=arm_index,
        arm_kind=arm_kind,  # type: ignore[arg-type]
        opener_code=opener_code,
        opener_index=opener_index,
        choice_index=choice_index,
        choice_text=choice_text,
        condition_type=condition_type,
        condition_text=condition_text,
        explicit=explicit,
    )
    return ManifestRow(
        row_id=row_id,
        kind="branch",
        map_id=ctx.map_id,
        # The BranchRef (condition text / choice text) goes in too: an arm's
        # meaning depends on what selects it, so a decision on the then-arm
        # of `pbTrainerBattle(A)` must go stale when the condition becomes
        # `pbTrainerBattle(B)`, even with the arm body untouched.
        content_hash=content_hash({
            "commands": scope_commands,
            "arms_skeleton": skeleton,
            "branch": asdict(branch),
        }),
        effects=extracted["effects"],
        script_heads=extracted["script_heads"],
        unrecognized_heads=extracted["unrecognized_heads"],
        other_codes=extracted["other_codes"],
        requires=requires,
        unhandled=ctx.unhandled,
        script_typed_conditions=extracted["script_typed_conditions"],
        condition_families=extracted["condition_families"],
        condition_unclassified=extracted["condition_unclassified"],
        event_id=ctx.event_id,
        event_name=ctx.event_name,
        page_idx=ctx.page_idx,
        condition=ctx.condition,
        trigger=ctx.trigger,
        reachability_consulted=ctx.reachability_consulted,
        branch=branch,
        parent_row_id=parent_row_id,
    )


def _walk_branches(
    nodes: list[Node],
    ctx: "_BranchWalkContext",
    parent_row_id: str,
    counter: Iterator[int],
    out: list[ManifestRow],
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
            then_row = _make_branch_row(
                ctx, arm_index=then_index, arm_kind="then",
                opener_code=CONDITIONAL_BRANCH, opener_index=node.index,
                choice_index=None, choice_text=None,
                condition_type=condition_type, condition_text=condition_text,
                explicit=True, parent_row_id=parent_row_id, children=node.then,
            )
            out.append(then_row)
            _walk_branches(node.then, ctx, then_row.row_id, counter, out)

            else_children = node.otherwise if node.otherwise is not None else []
            else_index = next(counter)
            else_row = _make_branch_row(
                ctx, arm_index=else_index, arm_kind="else",
                opener_code=CONDITIONAL_BRANCH, opener_index=node.index,
                choice_index=None, choice_text=None,
                condition_type=condition_type, condition_text=condition_text,
                explicit=node.otherwise is not None,
                parent_row_id=parent_row_id, children=else_children,
            )
            out.append(else_row)
            _walk_branches(else_children, ctx, else_row.row_id, counter, out)

        elif isinstance(node, ChoiceNode):
            for choice_index, choice_text, children in node.arms:
                arm_kind = "cancel" if choice_index is None else "choice"
                arm_index = next(counter)
                arm_row = _make_branch_row(
                    ctx, arm_index=arm_index, arm_kind=arm_kind,
                    opener_code=SHOW_CHOICES, opener_index=node.index,
                    choice_index=choice_index, choice_text=choice_text,
                    condition_type=None, condition_text=None,
                    explicit=True, parent_row_id=parent_row_id, children=children,
                )
                out.append(arm_row)
                _walk_branches(children, ctx, arm_row.row_id, counter, out)

        elif isinstance(node, LoopNode):
            _walk_branches(node.children, ctx, parent_row_id, counter, out)

        # Leaf / TextRun: no nested branch structure possible.


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
            tree = parse_tree(commands)
            trunk_commands = _flatten_scope(tree, commands)
            trunk_skeleton = _arms_skeleton(tree)
            extracted = _extract_page(trunk_commands)
            condition = _build_condition(
                page.get("condition") or {}, switch_names, var_names)
            trigger_raw = page.get("trigger")
            trigger = _TRIGGER_NAMES.get(trigger_raw, str(trigger_raw))
            requires = tuple(sorted(set(extracted["requires"]) | set(reach_requires)))
            unhandled = (
                unhandled_counts.get((map_id, event_id, page_idx), 0)
                if map_id in staged_map_ids else None
            )
            # Trunk-only hash (REDERIVATION_PLAN.md §16.3 C1b): every
            # page-level, non-command field (condition/graphic/trigger/
            # move_route/...) still goes in, same as the old `content_hash
            # (page)`; only `"list"` is swapped for the trunk-only command
            # dump, plus an explicit arm skeleton so the hash still changes
            # when an arm is added/removed even though its CONTENTS live in
            # that arm row's own hash, not here.
            # A page with no arms hashes exactly as it did before C1 -- its
            # trunk IS its list -- so R5 invalidates branching pages only.
            trunk_payload = (
                {**page, "list": trunk_commands, "arms_skeleton": trunk_skeleton}
                if trunk_skeleton else page
            )
            row_id = page_row_id(map_id, event_id, page_idx)
            row = ManifestRow(
                row_id=row_id,
                kind="page",
                map_id=map_id,
                content_hash=content_hash(trunk_payload),
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
            )
            rows.append(row)

            branch_ctx = _BranchWalkContext(
                map_id=map_id, event_id=event_id, event_name=event_name,
                page_idx=page_idx, condition=condition, trigger=trigger,
                unhandled=unhandled, reachability_consulted=reachability_consulted,
                reach_requires=reach_requires, page_row_id=row_id, commands=commands,
            )
            branch_rows: list[ManifestRow] = []
            _walk_branches(tree, branch_ctx, row_id, itertools.count(), branch_rows)
            rows.extend(branch_rows)
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
