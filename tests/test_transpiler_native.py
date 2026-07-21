"""Unit tests for the native-bucket queue-clearing pass (2026-07-05 slice
review): six shapes checked against a fork-native analog and converted from
queue entries to deterministic emission where a clean, narrow mapping exists.

Covers (see the matching module-level comment block in ``transpiler.py``,
just above ``_ROCK_SMASH_RE``, for the fork/corpus evidence each shape cites):

1. ``Kernel.pbRockSmash`` type-12 conditional -> ``goto(EventScript_RockSmash)``
   (``_ROCK_SMASH_RE`` / ``_emit_rock_smash_idiom``), both arms dropped.
2. Cave-entrance choreography subsumed by the native warp: ``pbCaveEntrance``
   script-call strip (``_CAVE_ENTRANCE_STRIP_RE``), the code-204 fog tuple
   strip (``_CAVE_FOG_204_PARAMS`` / ``_emit_change_map_settings``), and the
   code-12 "step forward" 209 route strip (``_is_cave_step_forward_route``).
3. ``pbTrainerPC`` -> ``goto(EventScript_PC)`` (``_TRAINER_PC_RE``).
4. ``pbShowMap`` -> ``special(FieldShowRegionMap)`` (``_SHOW_MAP_RE``).
5. ``$PokemonGlobal.runningShoes=true`` -> ``setflag(FLAG_SYS_B_DASH)``
   (``_RUNNING_SHOES_ON_RE``).
6. ``pbHasSpecies?(::PBSpecies::X)`` -> ``checkspecies(SPECIES_X)`` +
   ``if (var(VAR_RESULT) == TRUE)`` (``_HAS_SPECIES_RE`` /
   ``_emit_has_species_idiom``), gated through ``ctx.staged_species`` (only
   the six staged starter species emit; any other id-mapped-but-unstaged
   species, e.g. SPECIES_URAYNE, still queues — a regression test pins that
   the gate can't silently widen).

Builders mirror ``tests/test_transpiler_strips.py`` / ``test_transpiler_idioms.py``
(local per file-ownership convention): an event is
``{id, name, x, y, pages:[...]}``, each page ``{trigger, list, ...}`` with
``list`` a sequence of ``{code, indent, parameters}`` commands.
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, self_switch_flag_name

# ----------------------------------------------------------------------------
# builders
# ----------------------------------------------------------------------------


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds: list[list[dict]], trigger: int = 0, id: int = 5, name: str = "npc",
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


def _route(steps: list[dict], repeat: bool = False) -> dict:
    return {"list": [*steps, {"code": 0}], "repeat": repeat}


def _branch(
    condition: str,
    then_body: list[dict],
    else_body: list[dict] | None = None,
) -> list[dict]:
    cmds = [cmd(T.CONDITIONAL_BRANCH, [12, condition], indent=0)]
    cmds += [dict(c, indent=1) for c in then_body]
    if else_body is not None:
        cmds.append(cmd(T.ELSE_BRANCH, indent=0))
        cmds += [dict(c, indent=1) for c in else_body]
    cmds.append(cmd(T.BRANCH_END, indent=0))
    return cmds


@pytest.fixture()
def ctx() -> T.TranspileContext:
    return T.TranspileContext(registry=FlagRegistry())


def run_event(
    ctx: T.TranspileContext,
    pages_cmds: list[list[dict]],
    trigger: int = 0,
    map_id: int = 32,
    event_id: int = 14,
    name: str = "npc",
) -> T.TranspiledEvent:
    ev = make_event(pages_cmds, trigger=trigger, id=event_id, name=name)
    return T.transpile_event(map_id, ev, ctx)


# ----------------------------------------------------------------------------
# Shape 1 — Kernel.pbRockSmash
# ----------------------------------------------------------------------------


def test_rock_smash_strips_both_arms_and_gotos_native(ctx: T.TranspileContext) -> None:
    then_body = [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])]
    else_body = [cmd(T.CONTROL_SELF_SWITCH, ["B", 0])]
    commands = _branch("Kernel.pbRockSmash", then_body, else_body)
    res = run_event(ctx, [commands], map_id=32, event_id=14)
    assert res.unhandled == []
    assert "goto(EventScript_RockSmash)" in res.text
    assert "# rock smash" in res.text
    # neither arm's content emits — the branch is fully superseded, not just
    # un-taken.
    a_flag = self_switch_flag_name(32, 14, "A")
    b_flag = self_switch_flag_name(32, 14, "B")
    assert a_flag not in res.text
    assert b_flag not in res.text


def test_rock_smash_bare_variant_matches(ctx: T.TranspileContext) -> None:
    commands = _branch("pbRockSmash", [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands])
    assert res.unhandled == []
    assert "goto(EventScript_RockSmash)" in res.text


def test_rock_smash_near_miss_still_queues(ctx: T.TranspileContext) -> None:
    commands = _branch("Kernel.pbRockSmashFoo", [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "goto(EventScript_RockSmash)" not in res.text


def test_rock_smash_records_smashable_rock_trait(ctx: T.TranspileContext) -> None:
    """Upstream signal for the downstream FLAG_TEMP_* respawn-flag fix
    (porymap ships smashable rocks with a null "flag": "0", so the fix needs
    to know which (map, event) pairs are rocks — see ctx.traits)."""
    commands = _branch("Kernel.pbRockSmash", [cmd(T.CONTROL_SELF_SWITCH, ["A", 0])])
    run_event(ctx, [commands], map_id=32, event_id=14)
    assert ctx.traits == {(32, 14): {"smashable_rock"}}


def test_non_rock_event_records_no_trait(ctx: T.TranspileContext) -> None:
    run_event(ctx, [[cmd(T.WAIT, [1])]], map_id=32, event_id=14)
    assert ctx.traits == {}


# ----------------------------------------------------------------------------
# Shape 2a — pbCaveEntrance script-call strip
# ----------------------------------------------------------------------------


def test_cave_entrance_strips_with_breadcrumb(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbCaveEntrance"])]])
    assert res.unhandled == []
    assert "# cave transition: pbCaveEntrance subsumed by native warp fade" in res.text


def test_cave_entrance_kernel_prefix_variant(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["Kernel.pbCaveEntrance"])]])
    assert res.unhandled == []
    assert "# cave transition: pbCaveEntrance subsumed by native warp fade" in res.text


def test_cave_entrance_near_miss_with_args_still_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbCaveEntrance(1)"])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SCRIPT
    assert "# cave transition" not in res.text


# ----------------------------------------------------------------------------
# Shape 2b — code-204 cave fog tuple strip
# ----------------------------------------------------------------------------

_CAVE_FOG_PARAMS = [1, "004-Shade02", 0, 60, 0, 250, 0, 0]


def test_cave_fog_204_exact_match_strips(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.CHANGE_MAP_SETTINGS, list(_CAVE_FOG_PARAMS))]])
    assert res.unhandled == []
    assert "# cave transition: fog settings" in res.text


def test_cave_fog_204_near_miss_different_opacity_still_queues(
    ctx: T.TranspileContext,
) -> None:
    bad_params = [1, "004-Shade02", 0, 61, 0, 250, 0, 0]  # opacity 61, not 60
    res = run_event(ctx, [[cmd(T.CHANGE_MAP_SETTINGS, bad_params)]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CHANGE_MAP_SETTINGS
    assert "# cave transition" not in res.text


def test_cave_fog_204_near_miss_different_subtype_still_queues(
    ctx: T.TranspileContext,
) -> None:
    panorama_params = [0, "004-Shade02", 0]  # subtype 0 = panorama, not fog
    res = run_event(ctx, [[cmd(T.CHANGE_MAP_SETTINGS, panorama_params)]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CHANGE_MAP_SETTINGS


# ----------------------------------------------------------------------------
# Shape 2c — code-209 single-step "step forward" (code 12) route strip
# ----------------------------------------------------------------------------


def test_cave_step_forward_route_strips(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 12, "parameters": []}])
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [-1, route])]])
    assert res.unhandled == []
    assert "step-forward route" in res.text
    assert "applymovement" not in res.text


def test_cave_step_forward_neutralizes_paired_210(ctx: T.TranspileContext) -> None:
    route = _route([{"code": 12, "parameters": []}])
    res = run_event(
        ctx, [[cmd(T.SET_MOVE_ROUTE, [-1, route]), cmd(T.WAIT_MOVE_COMPLETION, [])]],
    )
    assert res.unhandled == []
    assert "waitmovement" not in res.text  # the 210 is neutralized, like a queued route


def test_cave_step_forward_near_miss_extra_step_still_queues(
    ctx: T.TranspileContext,
) -> None:
    route = _route([{"code": 12, "parameters": []}, {"code": 13, "parameters": []}])
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [-1, route])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SET_MOVE_ROUTE
    assert "step-forward route" not in res.text


def test_cave_step_forward_near_miss_non_player_target_still_queues(
    ctx: T.TranspileContext,
) -> None:
    route = _route([{"code": 12, "parameters": []}])
    res = run_event(ctx, [[cmd(T.SET_MOVE_ROUTE, [3, route])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SET_MOVE_ROUTE
    assert "step-forward route" not in res.text


# ----------------------------------------------------------------------------
# Shape 3 — pbTrainerPC
# ----------------------------------------------------------------------------


def test_trainer_pc_gotos_native(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbTrainerPC"])]])
    assert res.unhandled == []
    assert "goto(EventScript_PC)" in res.text


def test_trainer_pc_near_miss_still_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbTrainerPCFoo"])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SCRIPT
    assert "goto(EventScript_PC)" not in res.text


# ----------------------------------------------------------------------------
# Shape 4 — pbShowMap
# ----------------------------------------------------------------------------


def test_show_map_emits_special_and_keeps_preceding_dialogue(
    ctx: T.TranspileContext,
) -> None:
    res = run_event(
        ctx, [[cmd(T.SHOW_TEXT, ["Wall map text."]), cmd(T.SCRIPT, ["pbShowMap"])]],
    )
    assert res.unhandled == []
    assert "special(FieldShowRegionMap)" in res.text
    assert "Wall map text." in res.text
    assert "waitstate" not in res.text  # implicit via the assembler macro


def test_show_map_near_miss_still_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbShowMapX"])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SCRIPT
    assert "special(FieldShowRegionMap)" not in res.text


# ----------------------------------------------------------------------------
# Shape 5 — $PokemonGlobal.runningShoes=true
# ----------------------------------------------------------------------------


def test_running_shoes_true_sets_flag(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$PokemonGlobal.runningShoes=true"])]])
    assert res.unhandled == []
    assert "setflag(FLAG_SYS_B_DASH)" in res.text


def test_running_shoes_whitespace_variant_matches(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$PokemonGlobal.runningShoes = true"])]])
    assert res.unhandled == []
    assert "setflag(FLAG_SYS_B_DASH)" in res.text


def test_running_shoes_false_near_miss_still_queues(ctx: T.TranspileContext) -> None:
    res = run_event(ctx, [[cmd(T.SCRIPT, ["$PokemonGlobal.runningShoes=false"])]])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SCRIPT
    assert "setflag(FLAG_SYS_B_DASH)" not in res.text


# ----------------------------------------------------------------------------
# Shape 6 — pbHasSpecies?(::PBSpecies::X) -> checkspecies(SPECIES_X)
# ----------------------------------------------------------------------------


@pytest.fixture()
def ctx_with_starters() -> T.TranspileContext:
    """A context with the id map + staged-species manifest populated the way
    ``transpile_driver._load_species_id_map``/``_load_staged_species`` would,
    for the six W5 starter-line species. URAYNE is deliberately id-mapped but
    NOT staged — it's the regression fixture for the unstaged-species test."""
    return T.TranspileContext(
        registry=FlagRegistry(),
        species={
            "ORCHYNX": "SPECIES_ORCHYNX",
            "METALYNX": "SPECIES_METALYNX",
            "RAPTORCH": "SPECIES_RAPTORCH",
            "ARCHILLES": "SPECIES_ARCHILLES",
            "ELETUX": "SPECIES_ELETUX",
            "ELECTRUXO": "SPECIES_ELECTRUXO",
            "URAYNE": "SPECIES_URAYNE",
        },
        staged_species=frozenset({
            "SPECIES_ORCHYNX", "SPECIES_METALYNX", "SPECIES_RAPTORCH",
            "SPECIES_ARCHILLES", "SPECIES_ELETUX", "SPECIES_ELECTRUXO",
        }),
    )


def test_has_species_conditional_emits_checkspecies(
    ctx_with_starters: T.TranspileContext,
) -> None:
    """SPECIES_RAPTORCH is one of the six W5 starter-line species staged into
    the fork by ``species_converter.stage`` (STARTER_SPECIES_PLAN.md §W5), so
    the fork's native party-species check (``checkspecies``,
    engine/asm/macros/event.inc:2541, ``Scrcmd_checkspecies`` ->
    ``CheckPartyHasSpecies``, engine/src/scrcmd.c:3139) can be emitted
    directly: a preamble ``checkspecies(...)`` command plus an ``if`` over
    the ``VAR_RESULT`` it writes (the command-not-inline-expression shape
    documented on ``_emit_has_species_idiom``). Closes SLICE1_TODO #2, the
    last live queue entry (Auntie's dialogue branch, Map049 EV001)."""
    commands = _branch(
        "pbHasSpecies?(::PBSpecies::RAPTORCH)",
        [cmd(T.EXIT_EVENT)],
    )
    res = run_event(ctx_with_starters, [commands])
    assert res.unhandled == []
    assert "checkspecies(SPECIES_RAPTORCH)" in res.text
    assert "if (var(VAR_RESULT) == TRUE) {" in res.text


def test_has_species_conditional_unstaged_species_still_queues(
    ctx_with_starters: T.TranspileContext,
) -> None:
    """URAYNE resolves fine through the id map (like any of the ~166
    ``needs_engine`` species) but was never staged into the fork by W5 — its
    SPECIES_URAYNE constant does not exist in the fork's headers. This is
    the important regression: an id-map hit alone must NOT be enough to
    emit a species constant, or a future change could silently widen the
    gate to invented symbols the fork doesn't define."""
    commands = _branch(
        "pbHasSpecies?(::PBSpecies::URAYNE)",
        [cmd(T.CONTROL_SWITCHES, [185, 185, 1])],
    )
    res = run_event(ctx_with_starters, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "SPECIES_URAYNE" not in res.text


def test_has_species_conditional_no_species_wiring_still_queues(
    ctx: T.TranspileContext,
) -> None:
    """The plain ``ctx`` fixture has no species/staged_species wiring at all
    (the disposition before the driver populates them) — must still queue,
    not raise, and must not emit a bare SPECIES_* guess."""
    commands = _branch(
        "pbHasSpecies?(::PBSpecies::RAPTORCH)",
        [cmd(T.CONTROL_SWITCHES, [185, 185, 1])],
    )
    res = run_event(ctx, [commands])
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.CONDITIONAL_BRANCH
    assert "SPECIES_RAPTORCH" not in res.text
