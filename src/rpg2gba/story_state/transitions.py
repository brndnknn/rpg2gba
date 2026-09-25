"""Engine transitions and engine obligations (REDERIVATION_PLAN.md §16.2 R9,
§16.3 C3).

An **engine transition** is a state change the engine makes on its own, outside
any event page: white-out is the first. R9 models each one as a
precondition-gated fork -- snapshot, apply the transition, walk what it makes
live, restore -- so its writes never reach a chapter's end state.

An **engine obligation** is Uranium behaviour that runs as a triggered common
event in RMXP but that the ROM must implement in engine C (ruling (e): CE 51's
day/night switches from the real-time clock). The story-state model already
treats it as modelled pseudo-rows; the engine audit checks the ROM owes nothing.

Declarations only -- no behaviour. `model.py` consumes `TRANSITIONS`;
`engine_audit.py` consumes all three tables.
"""
from __future__ import annotations

from dataclasses import dataclass

from rpg2gba.story_state.state import RESPAWN_MAP, Assign, EngineKey, Switch, Test


@dataclass(frozen=True)
class EngineWrite:
    """A state write the fenced engine code must perform: `call` is the C
    call name (`FlagSet` / `FlagClear` / `VarSet`), `constant` the emitted
    registry name, `function` the C function it must sit inside."""

    call: str
    constant: str
    function: str


@dataclass(frozen=True)
class EngineTransition:
    name: str
    # Every test must be possible in a chapter's end state for the fork to run.
    precondition: tuple[Test, ...]
    # Applied as OVERWRITES on a copy of the chapter end state.
    writes: tuple[Assign, ...]
    # The fork lands on every map id this key possibly holds; forced rows
    # elsewhere cannot fire before the landing handler restores state.
    lands_on: EngineKey
    engine_writes: tuple[EngineWrite, ...]
    source: str
    # The fork also needs the chapter to hold a battle that can white out
    # (`losable.losable_battle_evidence`; REDERIVATION_PLAN.md §16.3 ruling 15).
    requires_losable_battle: bool = False


@dataclass(frozen=True)
class EngineObligation:
    name: str
    # Triggered-common-event pseudo-row trunk the ROM must implement.
    pseudo_row_id: str
    # Uranium switch/variable ids the engine must write.
    switch_ids: tuple[int, ...]
    source: str


@dataclass(frozen=True)
class HarnessOnlyWrite:
    """A fenced engine write that is test-harness scaffolding, not Uranium
    behaviour -- declared so the audit can tell it from an undeclared write."""

    write: EngineWrite
    reason: str


WHITEOUT = EngineTransition(
    name="whiteout",
    # Switch 2 "Got Pokemon" (FLAG_RECEIVED_STARTER): a held party, R9's
    # precondition. Set only by the starter choice, map050/ev019.
    precondition=(Test(key=Switch(2), op="==", value=True),),
    # Kernel.pbStartOver sets STARTING_OVER_SWITCH (5) on both the Pokémon
    # Center and the MetadataHome path (101__PField_Field.rb:1942,1966).
    writes=(
        Assign(key=Switch(5), values=frozenset({True}), conditional=False,
               source="Kernel.pbStartOver: $game_switches[STARTING_OVER_SWITCH]=true"),
    ),
    lands_on=RESPAWN_MAP,
    engine_writes=(EngineWrite("FlagSet", "FLAG_STARTING_OVER", "DoWhiteOut"),),
    source="reference/scripts_dump/101__PField_Field.rb:1920-1978",
    # pbStartOver follows only a battle that was not allowed to be lost.
    requires_losable_battle=True,
)

TRANSITIONS: tuple[EngineTransition, ...] = (WHITEOUT,)

DAY_NIGHT = EngineObligation(
    name="day_night",
    pseudo_row_id="common/ce051",
    switch_ids=(105, 106),
    source="common event 51 (parallel on switch 51 GAME RUNNING); "
           "REDERIVATION_PLAN.md §16.3 C2 ruling (e)",
)

OBLIGATIONS: tuple[EngineObligation, ...] = (DAY_NIGHT,)

HARNESS_ONLY: tuple[HarnessOnlyWrite, ...] = (
    HarnessOnlyWrite(
        EngineWrite("FlagSet", "FLAG_BADGE03_GET", "CB2_StartUraniumSlice"),
        reason="standing boot harness: enables Rock Smash from a fresh boot",
    ),
)
