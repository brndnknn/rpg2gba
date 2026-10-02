"""The state vocabulary: keys, tests, writes and refusals (REDERIVATION_PLAN.md
§16.3 C2a / C2 design, "Package story_state:" paragraph).

Everything here is a frozen dataclass. This module is the contract C2b's
liveness/ordering pass is built on, so it stays small and exact -- no
behaviour, no I/O, just shapes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

# --- keys --------------------------------------------------------------

# `Switch`/`Variable` model RMXP global switches/variables ($game_switches,
# $game_variables). `SelfSwitch` models a specific event's self-switch
# ($game_self_switches[[map_id, event_id, letter]]). `TempSwitch` models
# Uranium's Game_Event#tempSwitches -- an in-memory hash reset in
# Game_Event#initialize on every map load (022_Game_Event_v17.rb), so it
# behaves like per-visit input rather than persisted state: never carried
# across a map transition, only within the current visit.


@dataclass(frozen=True)
class Switch:
    id: int


@dataclass(frozen=True)
class Variable:
    id: int


@dataclass(frozen=True)
class SelfSwitch:
    map_id: int
    event_id: int
    letter: str


@dataclass(frozen=True)
class TempSwitch:
    map_id: int
    event_id: int
    letter: str


@dataclass(frozen=True)
class EngineKey:
    """Engine-held state no RMXP switch/variable carries, but which an engine
    transition reads (REDERIVATION_PLAN.md §16.3 C3). Integer-valued, like a
    Variable. The one key today is `RESPAWN_MAP`: `$PokemonGlobal.
    pokecenterMapId`, written by `Kernel.pbSetPokemonCenter` and read by
    `Kernel.pbStartOver` (`101__PField_Field.rb:1666-1676,1920-1948`)."""

    name: str


RESPAWN_MAP = EngineKey("respawn_map")


@dataclass(frozen=True)
class BagHas:
    """Boolean: the player's bag holds at least one of KEY item `item` (the
    item's internal symbol, e.g. ``"BIKEWHEEL"``). Switch-like: seeded False at
    new game, set True by a literal grant, havoc'd by anything else that
    touches the item (`story_state.bag`). Key items only -- ordinary items can
    arrive by channels a script scan cannot see."""

    item: str


Key = Switch | Variable | SelfSwitch | TempSwitch | EngineKey | BagHas

CompareOp = Literal["==", "!=", ">=", "<=", ">", "<"]


@dataclass(frozen=True)
class Test(object):
    """A read: `key` compared to `value` with `op`.

    `value` is `bool` for a switch-like key (Switch/SelfSwitch/TempSwitch)
    and `int` for a Variable -- the two key families never share a Test's
    `value` type, so a reader can dispatch on `isinstance(key, Variable)`
    rather than re-deriving it from `value`.
    """

    # Stops pytest from trying to collect this dataclass as a test class
    # merely because its name starts with `Test` -- it is a data shape named
    # for what it models (a boolean test), not a test case.
    __test__: ClassVar[bool] = False

    key: Key
    op: CompareOp
    value: bool | int


# --- writes --------------------------------------------------------------


@dataclass(frozen=True)
class Assign(object):
    """A write that sets `key` to exactly one of `values`.

    A plain 121/123 set or a 122 constant assignment has a single-element
    `values`; a 122 random-range assignment (op 0, operand_kind 2, lo..hi)
    carries the whole range, because under RMXP's actual RNG every value in
    it is a live possibility -- C2's ruling (d) treats every random outcome
    as live and checked offline.

    `conditional` is True when this write was reached only through a branch
    arm of an INLINED common event (a 117 call) -- the write is not
    guaranteed on every execution of the calling row, only on the arm's own
    path. `source` is a short human citation, e.g. ``"code 121 @list[4]"`` or
    ``"script @list[7]: pbSetSelfSwitch(18, \"A\", true)"``.

    `list_index` is this write's position in its OWNING PAGE's raw command
    list (`page["list"]`), REGARDLESS of which row (trunk or a nested arm)
    the write's own row belongs to (REDERIVATION_PLAN.md §16.3 C2b handback,
    FIX 1: a page trunk and its descendant arms are one execution, ordered by
    list position, not unordered sibling rows). For a write attributed
    through an inlined common event (a 117 call), `list_index` is the index
    of the 117 CALL ITSELF in the calling page -- not the write's position
    inside the common event's own body -- since that is where the calling
    page's own execution order places the inlined effect. Defaults to `-1`
    ("unpopulated") only so hand-built test fixtures that don't care about
    ordering don't have to pass it; every real extraction populates it.
    """

    key: Key
    values: frozenset[bool | int]
    conditional: bool
    source: str
    list_index: int = -1


@dataclass(frozen=True)
class Adjust(object):
    """A 122 add/sub/mul/div/mod of `key` by the constant `amount`.

    `op` is one of ``"+"``, ``"-"``, ``"*"``, ``"/"``, ``"%"`` (RMXP
    operations 1-5). Only ever targets a Variable -- switches/self-switches
    have no arithmetic write form. Unlike `Assign`, the resulting value set
    is not computable without knowing the key's current value, so C2b (not
    this module) is responsible for folding an `Adjust` into a value set once
    it has one to adjust.
    """

    key: Variable
    op: Literal["+", "-", "*", "/", "%"]
    amount: int
    conditional: bool
    source: str
    list_index: int = -1  # see Assign.list_index


Write = Assign | Adjust


@dataclass(frozen=True)
class Refusal(object):
    """A row (or one of its writes) that extraction could not model.

    `code` is a stable snake_case identifier (grep-able, stable across runs);
    `detail` is a precise, human-readable citation of what could not be
    parsed and why -- CLAUDE.md §4.5's "fail loud" applied to state
    extraction: an un-modelled write or read is recorded, never silently
    dropped or defaulted.
    """

    code: str
    detail: str
