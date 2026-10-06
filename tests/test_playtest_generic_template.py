"""Tests for `rpg2gba.playtest.archetypes.generic` (C6 Task 7).

What these can check offline: which kinds the body claims to execute, the
pure step list, and what each registration function REGISTERS (rows,
declared assertions, location). What they can't: whether a step handler
drives the emulator correctly. That is P11's boot gate.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 7.
"""
from __future__ import annotations

import typing

import pytest

from rpg2gba.beat_floor.assertion import (
    AssertionKind,
    FloorAssertion,
    FloorRefusal,
    RowFloor,
    make_params,
)
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.playtest.archetypes import declare_assertions, generic
from rpg2gba.playtest.chapter import ChapterBuilder

NPC = "map037/ev005/p0"                  # CH05's Revive NPC: no archetype claims it
NPC_ARMS = (f"{NPC}/b0", f"{NPC}/b1")
ROW_LEVEL = {"seam_crossing", "stair_crossing", "blocked_obstacle"}


def _builder() -> ChapterBuilder:
    return ChapterBuilder("TEST", doc="generic template test")


def _a(akind: str, list_index: int, row: str = NPC, **params) -> FloorAssertion:
    return FloorAssertion(row_id=row, kind=akind, list_index=list_index,
                          code=None if list_index < 0 else 101, params=make_params(**params))


def _floor(*assertions: FloorAssertion, refused: bool = False, row: str = NPC) -> RowFloor:
    refusals = (FloorRefusal(row, "text_unnormalizable", 0, 101, "x"),) if refused else ()
    return RowFloor(row_id=row, trigger="action", assertions=frozenset(assertions),
                    refusals=refusals)


# --- the honesty contract -------------------------------------------------------

def test_executed_kinds_cover_the_minimum():
    assert {"trigger", "completes", "text"} <= generic.GENERIC_EXECUTED_KINDS


def test_every_executed_kind_has_a_handler_and_nothing_else_does():
    assert set(generic.STEP_HANDLERS) == generic.GENERIC_EXECUTED_KINDS


def test_executed_kinds_are_real_floor_kinds_and_not_row_level():
    assert generic.GENERIC_EXECUTED_KINDS <= set(typing.get_args(AssertionKind))
    assert not (generic.GENERIC_EXECUTED_KINDS & ROW_LEVEL)


# --- steps_for ------------------------------------------------------------------

def test_steps_trigger_first_completes_last_rest_by_list_index():
    floor = _floor(_a("completes", -1), _a("text", 5, index=1, text="b"),
                   _a("trigger", -1, trigger="action"), _a("text", 2, index=0, text="a"))
    kinds = [(s.kind, s.list_index) for s in generic.steps_for(floor)]
    assert kinds == [("trigger", -1), ("text", 2), ("text", 5), ("completes", -1)]


def test_steps_drop_kinds_the_body_does_not_execute():
    floor = _floor(_a("trigger", -1, trigger="action"), _a("completes", -1),
                   _a("audio", 3, code=241, name="PU-Lab"))
    assert "audio" not in generic.GENERIC_EXECUTED_KINDS
    assert "audio" not in {s.kind for s in generic.steps_for(floor)}


def test_steps_refuse_a_refused_floor():
    with pytest.raises(ValueError, match=NPC):
        generic.steps_for(_floor(refused=True))


def test_steps_are_deterministic():
    floor = _floor(_a("trigger", -1, trigger="action"), _a("text", 2, index=0, text="a"),
                   _a("completes", -1))
    assert generic.steps_for(floor) == generic.steps_for(floor)


# --- ChapterBuilder.claimed_rows (you add it) --------------------------------------

def test_builder_reports_claimed_rows():
    b = _builder()
    b.beat("X", "x", map_constant="MAP_PASSAGE_CAVE_2F", at=(1, 1), rows=(NPC,))(lambda emu: None)
    assert b.claimed_rows() == frozenset({NPC})


# --- generic_beat ---------------------------------------------------------------

def test_generic_beat_registers_rows_and_honest_assertions():
    rows = (NPC, *NPC_ARMS)
    b = _builder()
    generic.generic_beat(b, chapter_id="CH05", beat_name="m037e005p0", rows=rows)
    (beat,) = b.build().beats
    assert beat.name == "m037e005p0"
    assert beat.rows == rows
    assert beat.archetype is None
    assert beat.assertions == declare_assertions(
        rows, executed_kinds=generic.GENERIC_EXECUTED_KINDS, template="generic")
    assert beat.locations[0].map_constant == "MAP_PASSAGE_CAVE_2F"


def test_generic_beat_location_is_the_page_approach_cell():
    from rpg2gba.playtest.archetypes import load_chapter_rows
    from rpg2gba.routing.locations import cell_for_row
    (page,) = [r for r in load_chapter_rows("CH05") if r.row_id == NPC]
    cell = cell_for_row(page)
    b = _builder()
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=NPC_ARMS)  # arms only
    (beat,) = b.build().beats
    loc = beat.locations[0]
    assert (loc.x, loc.y) == (cell.x, cell.y)


def test_generic_beat_skip_claimed():
    b = _builder()
    b.beat("X", "x", map_constant="MAP_PASSAGE_CAVE_2F", at=(1, 1),
           rows=(NPC_ARMS[0],))(lambda emu: None)
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=(NPC, *NPC_ARMS),
                         skip_claimed=True)
    beats = b.build().beats
    assert [x.name for x in beats] == ["X", "n"]
    assert beats[1].rows == (NPC, NPC_ARMS[1])


def test_generic_beat_skip_claimed_with_nothing_left_registers_nothing():
    b = _builder()
    b.beat("X", "x", map_constant="MAP_PASSAGE_CAVE_2F", at=(1, 1),
           rows=NPC_ARMS)(lambda emu: None)
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=NPC_ARMS, skip_claimed=True)
    assert [x.name for x in b.build().beats] == ["X"]


def test_generic_beat_refused_floor_fails_loud():
    def lookup(row_id: str) -> RowFloor:
        return _floor(refused=True, row=row_id)

    with pytest.raises(ValueError, match=NPC):
        generic.generic_beat(_builder(), chapter_id="CH05", beat_name="n", rows=(NPC,),
                             floor_lookup=lookup)


class _SilentEmu:
    """A field that never shows a lock: the script ran inside one frame."""

    def __init__(self) -> None:
        self.pos = (0, 0)
        self.required: list[bool] = []

    def walk_to(self, x: int, y: int, **_kw) -> None:
        self.pos = (x, y)

    def face(self, direction: str) -> None:
        pass

    def player_pos(self) -> tuple[int, int]:
        return self.pos

    def interact(self, frame_budget: int = 30, *, require_script: bool = True) -> bool:
        self.required.append(require_script)
        return False

    def advance_dialog(self) -> None:
        pass

    def field_locked(self) -> bool:
        return False


def test_generic_beat_does_not_demand_a_visible_script_for_a_silent_arm(monkeypatch):
    # ROM run 44: the lab PC's not-facing-up arm is lock/faceplayer/compare/
    # release -- done inside one frame, so no poll ever sees it lock.
    from rpg2gba.playtest import assertions
    monkeypatch.setattr(assertions, "require_map", lambda *a, **k: None)
    emu = _SilentEmu()
    b = _builder()
    generic.generic_beat(b, chapter_id="CH01", beat_name="m050e026p0_face_north_east_west",
                         rows=("map050/ev026/p0/b1",), approach_prefer="north")
    (beat,) = b.build().beats
    beat.run(emu)
    assert emu.required == [False]


# --- obstacle_beat --------------------------------------------------------------

ROCKS = ("map032/ev014/p0", "map032/ev015/p0")


def _rock_lookup(capability: str = "rock_smash"):
    def lookup(row_id: str) -> RowFloor:
        x, y = (65, 45) if row_id == ROCKS[0] else (66, 46)   # the real rocks' cells
        return _floor(_a("trigger", -1, row=row_id, trigger="action"),
                      _a("blocked_obstacle", -1, row=row_id, x=x, y=y, capability=capability),
                      row=row_id)
    return lookup


def test_obstacle_beat_declares_every_obstacle():
    b = _builder()
    generic.obstacle_beat(b, chapter_id="CH01", beat_name="m032obstacle_rock_smash",
                          rows=ROCKS, capability="rock_smash", floor_lookup=_rock_lookup())
    (beat,) = b.build().beats
    assert beat.rows == ROCKS
    assert {a.kind for a in beat.assertions} == {"blocked_obstacle"}
    assert {a.row_id for a in beat.assertions} == set(ROCKS)
    assert beat.locations[0].map_constant == "MAP_MOKI_TOWN"


class _RockEmu:
    """Pressing A opens the rock's message and locks the field until
    `advance_dialog` closes it."""

    def __init__(self) -> None:
        self.pos = (0, 0)
        self.locked = False
        self.stepped_while_locked = False

    def walk_to(self, x: int, y: int, **_kw) -> None:
        assert not self.locked, "walked with the rock's message still open"
        self.pos = (x, y)

    def face(self, direction: str) -> None:
        pass

    def player_pos(self) -> tuple[int, int]:
        return self.pos

    def interact(self) -> bool:
        self.locked = True
        return True

    def advance_dialog(self) -> None:
        self.locked = False

    def field_locked(self) -> bool:
        return self.locked


def test_obstacle_beat_closes_the_message_before_stepping(monkeypatch):
    # ROM run 43: the "rugged rock" box stayed open, so the step was a
    # vacuous no-op and the walk to the next rock stalled behind it.
    from rpg2gba.playtest import assertions
    emu = _RockEmu()

    def try_step(e, facing):
        e.stepped_while_locked |= e.locked
        return False

    monkeypatch.setattr(assertions, "require_map", lambda *a, **k: None)
    monkeypatch.setattr(assertions, "try_step", try_step)
    b = _builder()
    generic.obstacle_beat(b, chapter_id="CH01", beat_name="m032obstacle_rock_smash",
                          rows=ROCKS, capability="rock_smash", floor_lookup=_rock_lookup())
    (beat,) = b.build().beats
    beat.run(emu)
    assert not emu.stepped_while_locked


def test_obstacle_beat_capability_mismatch_fails_loud():
    with pytest.raises(ValueError, match="strength"):
        generic.obstacle_beat(_builder(), chapter_id="CH01", beat_name="o", rows=ROCKS,
                              capability="strength", floor_lookup=_rock_lookup())


def test_obstacle_beat_row_without_obstacle_fails_loud():
    def lookup(row_id: str) -> RowFloor:
        return _floor(_a("trigger", -1, row=row_id, trigger="action"), row=row_id)

    with pytest.raises(ValueError, match="map032/ev014/p0"):
        generic.obstacle_beat(_builder(), chapter_id="CH01", beat_name="o", rows=ROCKS,
                              capability="rock_smash", floor_lookup=lookup)


# --- stair_beat / seam_beat (real floors) -----------------------------------------

STAIRS = ("map037/terrain/stairs/11,9", "map037/terrain/stairs/11,10")


def test_stair_beat_declares_stair_crossings():
    b = _builder()
    generic.stair_beat(b, chapter_id="CH05", beat_name="m037stair11x9", rows=STAIRS)
    (beat,) = b.build().beats
    expected = {a for r in STAIRS for a in floor_for_row(r).assertions
                if a.kind == "stair_crossing"}
    assert expected and beat.assertions == frozenset(expected)
    assert beat.locations[0].map_constant == "MAP_PASSAGE_CAVE_2F"


def _crossing(row: str, d: str, a: tuple[int, int], e: tuple[int, int],
              cell: tuple[int, int]) -> generic.StairCrossing:
    return generic.StairCrossing(row, d, a, e, cell)


# Map033's x=57 column (ROM run 52): two lanes, each crossed both ways.
_M033 = (
    _crossing("57,9", "RIGHT", (56, 9), (58, 10), (57, 9)),
    _crossing("57,10", "LEFT", (58, 10), (56, 9), (57, 10)),
    _crossing("57,10", "RIGHT", (56, 10), (58, 11), (57, 10)),
    _crossing("57,11", "LEFT", (58, 11), (56, 10), (57, 11)),
)


def test_order_stair_crossings_chains_and_returns_to_the_reached_side():
    order = generic.order_stair_crossings(_M033, prefer="east", beat_name="b")
    assert [(c.direction, c.approach) for c in order] == [
        ("LEFT", (58, 10)), ("RIGHT", (56, 9)),     # lane 1 there and back
        ("LEFT", (58, 11)), ("RIGHT", (56, 10)),    # same-side hop, lane 2
    ]
    assert order[-1].exit == (58, 11)


def test_order_stair_crossings_west_start():
    order = generic.order_stair_crossings(_M033, prefer="west", beat_name="b")
    assert order[0].approach == (56, 9)
    assert order[-1].side_of(order[-1].exit) == -1


def test_order_stair_crossings_refuses_a_one_way_walk():
    with pytest.raises(ValueError, match="end across the staircase"):
        generic.order_stair_crossings(_M033[1:2], prefer="east", beat_name="b")


def test_order_stair_crossings_refuses_an_unreached_preferred_side():
    with pytest.raises(ValueError, match="no crossing starts on the north side"):
        generic.order_stair_crossings(_M033, prefer="north", beat_name="b")


SEAM ="map031/seam/N/map035"


def test_seam_beat_declares_the_crossing(monkeypatch):
    # seam_warps.json is empty since 2026-10-06 (31<->35 is a real connection);
    # the arrow-warp mechanism is exercised with an injected seam entry.
    import rpg2gba.playtest.cells as cells_mod

    monkeypatch.setattr(cells_mod, "_SEAM_WARPS_CACHE", [
        {"id": "synthetic", "map_a": 31, "map_b": 35,
         "cells_a": [[31, 0], [32, 0]], "cells_b": [[20, 56], [21, 56]]}])
    b = _builder()
    generic.seam_beat(b, chapter_id="CH03", beat_name="m031seamN035", rows=(SEAM,))
    (beat,) = b.build().beats
    assert {a.kind for a in beat.assertions} == {"seam_crossing"}
    assert beat.rows == (SEAM,)


def test_seam_beat_takes_exactly_one_row():
    with pytest.raises(ValueError):
        generic.seam_beat(_builder(), chapter_id="CH04", beat_name="s",
                          rows=("map035/seam/N/map040", "map035/seam/S/map031"))


# --- item_grant (2026-09-25) ------------------------------------------------


class _BagEmu:
    def __init__(self, qty: int) -> None:
        self.qty = qty

    def bag_item_quantity(self, const: str) -> int:
        return self.qty

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def test_item_grant_handler_checks_the_bag_total():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step
    from rpg2gba.playtest.errors import ScenarioError

    handler = STEP_HANDLERS["item_grant"]
    floor_params = (("item", "POKeBALL"), ("quantity", 5))
    # A bare floor step is a misuse: the body must add the before-quantity.
    with pytest.raises(ScenarioError, match="after the page completes"):
        handler(_BagEmu(5), "B1", Step("map032/ev009/p2", "item_grant", 160, floor_params))
    checked = Step("map032/ev009/p2", "item_grant", 160,
                   floor_params + (("const", "ITEM_POKE_BALL"), ("expected_total", 5)))
    handler(_BagEmu(5), "B1", checked)
    with pytest.raises(ScenarioError, match="bag holds 0 ITEM_POKE_BALL, expected 5"):
        handler(_BagEmu(0), "B1", checked)


# --- pokemon_grant + gift ceremonies (2026-09-29, ROM run 27) -------------------


class _GiftEmu:
    """The transpiler's gift flow: an "obtained" line, then a nickname
    yes/no that B answers NO and A would answer YES."""

    def __init__(self, text: str | None = "RED obtained Luxi!") -> None:
        self.text = text
        self.prompt = True
        self.taps: list[str] = []
        self.cleared = False

    def wait_for_field_message(self, frame_budget: int = 180) -> str | None:
        return self.text

    def yesno_prompt_up(self) -> bool:
        return self.prompt

    def advance_dialog(self, key: str = "A", stop=None, **_: object) -> int:
        self.taps.append(f"advance:{key}")
        return 0

    def tap(self, key: str) -> None:
        self.taps.append(key)
        if key == "B":
            self.prompt = False

    def run(self, frames: int) -> None:
        pass

    def clear_field_message(self) -> None:
        self.cleared = True

    def resolve_constant(self, name: str) -> int:
        return {"SPECIES_LUXI": 7}[name]

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def test_pokemon_grant_answers_the_nickname_no_and_checks_the_party(monkeypatch):
    from rpg2gba.playtest import assertions
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step
    from rpg2gba.playtest.errors import ScenarioError

    handler = STEP_HANDLERS["pokemon_grant"]
    step = Step("map031/ev050/p0", "pokemon_grant", 4,
                (("species", "LUXI"), ("level", 5), ("const", "SPECIES_LUXI")))
    monkeypatch.setattr(assertions, "party_has_species", lambda emu, sid: sid == 7)
    emu = _GiftEmu()
    handler(emu, "B1", step)
    assert emu.taps == ["advance:B", "B"] and emu.cleared and not emu.prompt
    monkeypatch.setattr(assertions, "party_has_species", lambda emu, sid: False)
    with pytest.raises(ScenarioError, match="SPECIES_LUXI is not in the party"):
        handler(_GiftEmu(), "B1", step)
    with pytest.raises(ScenarioError, match="obtained"):
        handler(_GiftEmu(text="Something else"), "B1", step)


def test_generic_beat_resolves_a_gift_species_and_declares_it():
    gift = _a("pokemon_grant", 4, species="LUXI", level=5)
    lookup = {NPC: _floor(_a("trigger", -1, trigger="action"), _a("completes", -1), gift)}
    b = _builder()
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=(NPC,),
                         floor_lookup=lookup.__getitem__)
    (beat,) = b.build().beats
    assert "pokemon_grant" in {a.kind for a in beat.assertions}


def test_gift_ceremony_runs_where_the_refused_arm_gives(monkeypatch):
    """The starter page: its give arm (b1, index 9) is refused, but its
    ceremony comes up before Theo's first line (index 29)."""
    from rpg2gba.playtest import assertions

    b = _builder()
    generic.generic_beat(b, chapter_id="CH01", beat_name="m050e019p0", rows=RIVAL,
                         gift_ceremonies=(9,))
    (beat,) = b.build().beats
    assert "map050/ev019/p0/b1" not in beat.rows

    calls: list[str] = []
    monkeypatch.setattr(assertions, "require_map", lambda *a: None)
    monkeypatch.setattr(assertions, "damage_lead", lambda *a: None)
    monkeypatch.setattr(generic, "_gift_ceremony", lambda emu, name, row: calls.append("gift"))
    for kind in generic.STEP_HANDLERS:
        monkeypatch.setitem(generic.STEP_HANDLERS, kind,
                            lambda emu, name, step: calls.append(step.kind))
    beat.run(_AnyEmu())
    assert calls.count("gift") == 1
    assert calls.index("gift") < calls.index("text")


# --- item grants' obtain boxes come up in place (ROM run 48) --------------------


class _BoxEmu:
    """Shows `boxes` one at a time; `dismiss_message` moves to the next."""

    def __init__(self, boxes: list[str]) -> None:
        self.boxes = list(boxes)
        self.dismissed = 0

    def wait_for_field_message(self, frame_budget: int = 180) -> str | None:
        return self.boxes[0] if self.boxes else None

    def clear_field_message(self) -> None:
        pass

    def dismiss_message(self) -> None:
        self.dismissed += 1
        self.boxes.pop(0)

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def test_item_boxes_get_through_obtain_and_pocket_lines():
    emu = _BoxEmu(["Obtained 5 Poké Balls!",
                   "RED put away the Poké Balls\\nin the POKé BALLS POCKET.",
                   "Poké Balls are necessary for catching Pokémon"])
    generic._item_boxes(emu, "B1", "map032/ev009/p2")
    assert emu.dismissed == 2
    assert emu.boxes == ["Poké Balls are necessary for catching Pokémon"]


def test_item_boxes_read_the_native_berry_trees_longer_flow():
    """ROM run 56: the berry tree's pocket line is its 3rd box, and the pick
    prompt can be read twice while its yes/no is up -- the 4th read must
    still be checked (the old loop read it and never looked)."""
    emu = _BoxEmu(["You found 2 ORAN BERRIES!\\pDo you want to pick them?",
                   "You found 2 ORAN BERRIES!\\pDo you want to pick them?",
                   "RED picked the 2 ORAN BERRIES.",
                   "RED put away the ORAN BERRIES\\nin the BAG’s BERRIES POCKET."
                   "\\pThe soil returned to its soft and\\nloamy state.",
                   "next"])
    generic._item_boxes(emu, "B1", "map033/ev102/p0")
    assert emu.boxes == ["next"]


def test_item_boxes_fail_loud_when_the_pocket_line_never_comes():
    from rpg2gba.playtest.errors import ScenarioError
    emu = _BoxEmu(["Obtained a POTION!"] + ["more"] * 10)
    with pytest.raises(ScenarioError, match=r"never came in 5 boxes"):
        generic._item_boxes(emu, "B1", "r")


class _BerryEmu:
    """Reads a native berry tree's pick state; any flag read is a bug."""

    def __init__(self, picked: bool) -> None:
        self.picked = picked
        self.trees: list[int] = []

    def berry_tree_picked(self, tree_id: int) -> bool:
        self.trees.append(tree_id)
        return self.picked

    def flag(self, name: str) -> bool:
        raise AssertionError(f"read {name}; a native berry tree has no self-switch")

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


_BERRY_SSA = generic.Step("map033/ev102/p0/b0", "self_switch_write", 1,
                          (("event_id", 102), ("letter", "A"), ("value", True)))


def test_native_berry_tree_state_is_the_self_switch_write():
    """Operator ruling 2026-10-01 (ROM run 57): the pick blanking tree 97 is
    the RMXP page's self-switch-A write."""
    emu = _BerryEmu(picked=True)
    generic._handle_self_switch_write(emu, "B1", _BERRY_SSA)
    assert emu.trees == [97]


def test_an_unpicked_native_berry_tree_fails_the_write():
    from rpg2gba.playtest.errors import ScenarioError
    with pytest.raises(ScenarioError, match="berry tree 97 picked reads False"):
        generic._handle_self_switch_write(_BerryEmu(picked=False), "B1", _BERRY_SSA)


def test_item_boxes_fail_loud_without_an_obtain_line():
    from rpg2gba.playtest.errors import ScenarioError
    with pytest.raises(ScenarioError, match="obtain line"):
        generic._item_boxes(_BoxEmu(["Poké Balls are necessary"]), "B1", "r")


def test_the_professors_poke_balls_come_up_before_the_arms_first_line(monkeypatch):
    # The grant is the trunk's `pbReceiveItem` condition (list[160]); arm
    # b16's first line is list[162].
    from rpg2gba.playtest import assertions

    rows = ("map032/ev009/p2", "map032/ev009/p2/b16")
    b = _builder()
    generic.generic_beat(b, chapter_id="CH01", beat_name="m032e009p2", rows=rows,
                         approach_prefer="south")
    (beat,) = b.build().beats
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(assertions, "require_map", lambda *a: None)
    monkeypatch.setattr(generic, "_item_boxes", lambda emu, name, row: calls.append(("boxes", -1)))
    for kind in generic.STEP_HANDLERS:
        monkeypatch.setitem(generic.STEP_HANDLERS, kind,
                            lambda emu, name, step: calls.append((step.kind, step.list_index)))
    beat.run(_AnyEmu())
    spoken = [c for c in calls if c[0] in ("text", "boxes")]
    at = spoken.index(("boxes", -1))
    assert spoken[at - 1] == ("text", 155) and spoken[at + 1] == ("text", 162)


# --- heal_party waits for the heal to land (ROM run 31) -------------------------


class _HealEmu:
    """Lead at 1/19 HP; the script's heal lands after `heal_at` frames."""

    def __init__(self, heal_at: int | None) -> None:
        self.heal_at, self.frame = heal_at, 0

    def run(self, frames: int) -> None:
        self.frame += frames

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def test_heal_party_waits_for_the_heal_behind_a_fade(monkeypatch):
    from rpg2gba.playtest import assertions
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step
    from rpg2gba.playtest.errors import ScenarioError

    monkeypatch.setattr(assertions, "read_lead_hp", lambda emu: (
        (19, 19) if emu.heal_at is not None and emu.frame >= emu.heal_at else (1, 19)))
    step = Step("map050/ev019/p0/b8", "heal_party", 129, ())
    STEP_HANDLERS["heal_party"](_HealEmu(heal_at=40), "B1", step)
    with pytest.raises(ScenarioError, match="lead HP is 1/19 after the heal"):
        STEP_HANDLERS["heal_party"](_HealEmu(heal_at=None), "B1", step)


# --- choice (ruling 19) -------------------------------------------------------


class _MenuEmu:
    """A menu already up; each tap decides what the script receives."""

    def __init__(self, *, yesno: bool, results: dict[str, int]) -> None:
        self.symbols = {"gSpecialVar_Result": 0x2000}
        self.result = 0xFF
        self._yesno, self._results, self.taps = yesno, results, []

    def yesno_prompt_up(self) -> bool:
        return self._yesno

    def u16(self, addr: int) -> int:
        return self.result

    def run(self, frames: int) -> None:
        pass

    def tap(self, key: str) -> None:
        self.taps.append(key)
        if key in self._results:
            self.result = self._results[key]

    def resolve_constant(self, name: str) -> int:
        return 127

    def screenshot(self, name: str) -> str:
        return f"{name}.png"


def _choice_step(options, answer):
    from rpg2gba.playtest.archetypes.generic import Step

    return Step("map031/ev014/p0", "choice", 3, (("options", options), ("answer", answer)))


def test_choice_handler_answers_a_yesno_and_reads_it_back():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS

    yes = _MenuEmu(yesno=True, results={"A": 1, "B": 0})
    STEP_HANDLERS["choice"](yes, "B1", _choice_step(("Yes", "No"), 0))
    assert yes.taps == ["A"]
    no = _MenuEmu(yesno=True, results={"A": 1, "B": 0})
    STEP_HANDLERS["choice"](no, "B1", _choice_step(("Yes", "No"), 1))
    assert no.taps == ["B"]


def test_choice_handler_moves_the_cursor_for_a_multichoice():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS

    emu = _MenuEmu(yesno=False, results={"A": 2})
    STEP_HANDLERS["choice"](emu, "B1", _choice_step(("Orchynx", "Raptorch", "Eletux"), 2))
    assert emu.taps == ["DOWN", "DOWN", "A"]


def test_choice_handler_catches_a_wrong_answer_reaching_the_script():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS
    from rpg2gba.playtest.errors import ScenarioError

    emu = _MenuEmu(yesno=True, results={"A": 0})  # YES pressed, script got NO
    with pytest.raises(ScenarioError, match="script received 0, expected 1"):
        STEP_HANDLERS["choice"](emu, "B1", _choice_step(("Yes", "No"), 0))


class _InlineMenuEmu(_MenuEmu):
    """`_MenuEmu` plus the game var the inline choice copies its pick into."""

    def __init__(self, *, var_after: int, **kw) -> None:
        super().__init__(**kw)
        self._var_after = var_after

    def var(self, name: str) -> int:
        assert name == "VAR_TEMP_MOVE_CHOICE"
        return self._var_after


def _inline_step(options, answer, if_cancel=0):
    from rpg2gba.playtest.archetypes.generic import Step

    return Step("map050/ev005/p0/b2", "choice", 57, (
        ("answer", answer), ("if_cancel", if_cancel), ("inline", True),
        ("options", options), ("var_id", 2)))


def test_inline_two_option_choice_is_a_multichoice_and_reads_its_var(monkeypatch):
    from rpg2gba.playtest.archetypes import generic

    class _Reg:
        def get_var(self, var_id):
            return "VAR_TEMP_MOVE_CHOICE" if var_id == 2 else None

    monkeypatch.setattr(generic, "_flag_registry", lambda: _Reg())
    emu = _InlineMenuEmu(yesno=False, results={"A": 1}, var_after=1)
    generic.STEP_HANDLERS["choice"](emu, "B1", _inline_step(("A", "B"), 1))
    assert emu.taps == ["DOWN", "A"]   # never the yes/no path, despite two options
    wrong = _InlineMenuEmu(yesno=False, results={"A": 1}, var_after=0)
    from rpg2gba.playtest.errors import ScenarioError
    with pytest.raises(ScenarioError, match="VAR_TEMP_MOVE_CHOICE reads 0, expected 1"):
        generic.STEP_HANDLERS["choice"](wrong, "B1", _inline_step(("A", "B"), 1))


def test_inline_choice_that_ignores_b_has_no_cancel_arm():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS
    from rpg2gba.playtest.errors import ScenarioError

    emu = _InlineMenuEmu(yesno=False, results={}, var_after=0)
    with pytest.raises(ScenarioError, match="ignores B"):
        STEP_HANDLERS["choice"](emu, "B1", _inline_step(("A", "B", "C"), -1))


# --- service (ruling 20) ------------------------------------------------------


class _ServiceEmu:
    def __init__(self, *, mart=(), registered=False):
        self.symbols = {"gSpecialVar_Result": 0x2000}
        self.mem = {0x2000: 0}
        self._mart, self._registered, self.taps = list(mart), registered, []

    def u16(self, addr):
        return self.mem.get(addr, 0)

    def write_u16(self, addr, value):
        self.mem[addr] = value

    def advance_dialog(self, key, stop=None):
        self.mem[0x2000] = 0xFF          # the PC menu comes up

    def tap(self, key):
        self.taps.append(key)
        if key == "B" and self.mem[0x2000] == 0xFF:
            self.mem[0x2000] = 127       # MULTI_B_PRESSED

    def resolve_constant(self, name):
        return {"MULTI_B_PRESSED": 127, "ITEM_POKE_BALL": 4, "ITEM_POTION": 13}[name]

    def mart_items(self):
        return self._mart

    def match_call_registered(self, trainer):
        return self._registered

    def screenshot(self, name):
        return f"{name}.png"


def _service_step(**params):
    from rpg2gba.playtest.archetypes.generic import Step

    return Step("map068/ev007/p0", "service", 0, tuple(sorted(params.items())))


def test_service_pc_reaches_the_menu_and_backs_out():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS

    emu = _ServiceEmu()
    STEP_HANDLERS["service"](emu, "B1", _service_step(name="pc"))
    assert emu.taps == ["B"]


def test_service_mart_checks_the_stock():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS
    from rpg2gba.playtest.errors import ScenarioError

    step = _service_step(name="mart", consts=("ITEM_POKE_BALL", "ITEM_POTION"))
    STEP_HANDLERS["service"](_ServiceEmu(mart=[4, 13]), "B1", step)
    with pytest.raises(ScenarioError, match=r"sells \[4\], expected \[4, 13\]"):
        STEP_HANDLERS["service"](_ServiceEmu(mart=[4]), "B1", step)


class _StarterEmu(_ServiceEmu):
    """Shows `messages` one per A press (ROM run 21: the transpiled reveal is
    speech, then the scene's reveal line -- never a mon pic). Like the real
    `advance_dialog`, wipes the message buffer on exit (ROM run 22)."""

    def __init__(self, messages):
        super().__init__()
        self._messages, self._at = list(messages), 0
        self._cleared = False

    def current_field_message_text(self):
        if self._cleared or self._at >= len(self._messages):
            return None
        return self._messages[self._at]

    def advance_dialog(self, key, stop=None):
        while self._at < len(self._messages) and not (stop and stop()):
            self._at += 1
        self._cleared = True

    def dismiss_message(self):
        self._at += 1
        self._cleared = False


def test_service_starter_select_stops_on_a_reveal_line_not_a_mon_pic():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS

    emu = _StarterEmu(["RED...", "You seem to be a Trainer who likes\\nto play it safe.",
                       "Orchynx is the\\nbest pick!", "Go ahead and take it, RED."])
    STEP_HANDLERS["service"](emu, "B1", _service_step(name="starter_select"))
    # Stopped on the reveal and dismissed it: the next text step reads the
    # line after it (ROM run 23).
    assert emu.current_field_message_text() == "Go ahead and take it, RED."


def test_service_starter_select_fails_loud_when_no_reveal_shows():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS
    from rpg2gba.playtest.errors import ScenarioError

    emu = _StarterEmu(["RED, are you ready to take the\\nTrainer Aptitude Test?"])
    with pytest.raises(ScenarioError, match="no starter reveal line"):
        STEP_HANDLERS["service"](emu, "B1", _service_step(name="starter_select"))


def test_service_phone_register_checks_the_match_call_flag():
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS
    from rpg2gba.playtest.errors import ScenarioError

    step = _service_step(name="phone_register", trainer="TRAINER_RICHEY")
    STEP_HANDLERS["service"](_ServiceEmu(registered=True), "B1", step)
    with pytest.raises(ScenarioError, match="not registered for match call"):
        STEP_HANDLERS["service"](_ServiceEmu(registered=False), "B1", step)


# --- battle: trainer half only ----------------------------------------------


class _BattleEmu:
    """A battle already running against `opponent`; winning sets `flag_after`."""

    def __init__(self, *, opponent=7, trainer=True, flag_after=True):
        self.opponent, self.trainer, self.flag_after = opponent, trainer, flag_after
        self.won = False
        self.cleared_after_win = False

    def clear_field_message(self):
        # ROM run 30: the battle's defeat line must not reach the next text step.
        self.cleared_after_win = self.won

    def is_trainer_battle(self):
        return self.trainer

    def opponent_trainer_id(self):
        return self.opponent

    def resolve_constant(self, name):
        return {"TRAINER_FLAGS_START": 0x500, "TRAINER_RICHEY": 7, "TRAINER_THEO_2": 9}[name]

    def flag(self, flag_id):
        return self.won and self.flag_after and flag_id == 0x500 + self.opponent

    def run(self, frames):
        pass

    def screenshot(self, name):
        return f"{name}.png"


def _battle(monkeypatch, emu, consts=("TRAINER_RICHEY",)):
    from rpg2gba.playtest import battle
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step

    monkeypatch.setattr(battle, "in_battle", lambda e: not e.won)

    def win(e, *, finish_script=True):
        # The generic template checks the post-battle script's own text, so it
        # must not have the helper press through it (ROM run 29).
        assert finish_script is False
        e.won = True
    monkeypatch.setattr(battle, "win_battle", win)
    params = (("kind", "trainer"), ("name", "Richey"), ("trainer_type", "YOUNGSTER"))
    if consts is not None:
        params += (("consts", consts),)
    STEP_HANDLERS["battle"](emu, "B1", Step("map033/ev053/p0", "battle", 12, params))


def test_battle_handler_checks_the_trainer_wins_and_reads_the_defeat_flag(monkeypatch):
    emu = _BattleEmu()
    _battle(monkeypatch, emu)
    assert emu.cleared_after_win
    assert emu.won


def test_battle_handler_accepts_any_party_of_the_named_trainer(monkeypatch):
    _battle(monkeypatch, _BattleEmu(opponent=9), consts=("TRAINER_RICHEY", "TRAINER_THEO_2"))


def test_battle_handler_rejects_the_wrong_trainer_a_wild_battle_and_no_flag(monkeypatch):
    from rpg2gba.playtest.errors import ScenarioError

    with pytest.raises(ScenarioError, match="fought trainer id 9"):
        _battle(monkeypatch, _BattleEmu(opponent=9))
    with pytest.raises(ScenarioError, match="not a trainer battle"):
        _battle(monkeypatch, _BattleEmu(trainer=False))
    with pytest.raises(ScenarioError, match="defeat flag is not set"):
        _battle(monkeypatch, _BattleEmu(flag_after=False))
    with pytest.raises(ScenarioError, match="no resolved trainer consts"):
        _battle(monkeypatch, _BattleEmu(), consts=None)


RICHEY = ("map033/ev053/p0", "map033/ev053/p0/b0")
RIVAL = ("map050/ev019/p0", "map050/ev019/p0/b7", "map050/ev019/p0/b8")


def test_generic_beat_declares_a_trainer_battle():
    b = _builder()
    generic.generic_beat(b, chapter_id="CH02", beat_name="m033e053p0", rows=RICHEY)
    (beat,) = b.build().beats
    battles = [a for a in beat.assertions if a.kind == "battle"]
    assert [(a.row_id, a.param("name")) for a in battles] == [(RICHEY[0], "Richey")]


def test_battle_consts_are_only_the_staged_parties(monkeypatch):
    """ROM run 28: trainers.json has every Theo party in the corpus; the
    early-rival battle can only be one the ROM was built with."""
    from rpg2gba.beat_gen import adapt
    from rpg2gba.playtest.archetypes.generic import Step, _battle_consts

    monkeypatch.setattr(adapt, "trainer_consts_for",
                        lambda name, cls, row_id: ("TRAINER_THEO_10", "TRAINER_THEO_12",
                                                   "TRAINER_THEO_9"))
    monkeypatch.setattr(generic, "_staged_trainer_consts",
                        lambda: frozenset({"TRAINER_THEO_9", "TRAINER_THEO_10"}))
    step = Step(RIVAL[0], "battle", 106, (("kind", "trainer"), ("name", "Theo"),
                                          ("trainer_type", "RIVAL")))
    assert _battle_consts(step, "b") == ("TRAINER_THEO_10", "TRAINER_THEO_9")
    monkeypatch.setattr(generic, "_staged_trainer_consts", lambda: frozenset())
    with pytest.raises(ValueError, match="none of .* is staged"):
        _battle_consts(step, "b")


def test_generic_beat_leaves_a_wild_battle_undeclared():
    wild = _a("battle", 3, kind="wild", species="PIDGEY")
    lookup = {NPC: _floor(_a("trigger", -1, trigger="action"), _a("completes", -1), wild)}
    b = _builder()
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=(NPC,),
                         floor_lookup=lookup.__getitem__)
    (beat,) = b.build().beats
    assert "battle" not in {a.kind for a in beat.assertions}


class _AnyEmu:
    def __getattr__(self, name):
        return lambda *a, **k: 0


def test_a_heal_after_a_battle_damages_the_lead_after_the_battle(monkeypatch):
    from rpg2gba.playtest import assertions

    b = _builder()
    generic.generic_beat(b, chapter_id="CH01", beat_name="m050e019p0", rows=RIVAL)
    (beat,) = b.build().beats
    assert {"battle", "heal_party", "switch_write"} <= {a.kind for a in beat.assertions}

    calls: list[str] = []
    monkeypatch.setattr(assertions, "require_map", lambda *a: None)
    monkeypatch.setattr(assertions, "damage_lead", lambda *a: calls.append("damage"))
    for kind in generic.STEP_HANDLERS:
        monkeypatch.setitem(generic.STEP_HANDLERS, kind,
                            lambda emu, name, step: calls.append(step.kind))
    beat.run(_AnyEmu())
    assert calls.index("battle") < calls.index("damage") < calls.index("heal_party")
    assert calls.count("damage") == 1


# --- state writes: an assign is value-checked, a multi-valued one by set ------


class _StateEmu:
    def __init__(self, value):
        self.value = value

    def var(self, name):
        return self.value

    def flag(self, name):
        return self.value

    def screenshot(self, name):
        return f"{name}.png"


class _Registry:
    def get_var(self, var_id):
        return "VAR_TEST"

    def get_flag(self, switch_id):
        return "FLAG_TEST"


def test_var_write_assign_is_checked_against_every_possible_value(monkeypatch):
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step
    from rpg2gba.playtest.errors import ScenarioError

    monkeypatch.setattr(generic, "_flag_registry", lambda: _Registry())
    roll = Step("map048/ev011/p0", "var_write", 0,
                (("op", "="), ("value", (0, 1, 2)), ("var_id", 1)))
    STEP_HANDLERS["var_write"](_StateEmu(2), "B1", roll)
    with pytest.raises(ScenarioError, match="reads 3, expected one of"):
        STEP_HANDLERS["var_write"](_StateEmu(3), "B1", roll)
    single = Step("map048/ev011/p0", "var_write", 0,
                  (("op", "="), ("value", 5), ("var_id", 1)))
    with pytest.raises(ScenarioError, match="reads 4"):
        STEP_HANDLERS["var_write"](_StateEmu(4), "B1", single)


def test_switch_write_with_both_values_possible_accepts_either(monkeypatch):
    from rpg2gba.playtest.archetypes.generic import STEP_HANDLERS, Step
    from rpg2gba.playtest.errors import ScenarioError

    monkeypatch.setattr(generic, "_flag_registry", lambda: _Registry())
    both = Step("map050/ev019/p0", "switch_write", 0,
                (("switch_id", 35), ("value", (False, True))))
    STEP_HANDLERS["switch_write"](_StateEmu(False), "B1", both)
    STEP_HANDLERS["switch_write"](_StateEmu(True), "B1", both)
    on = Step("map050/ev019/p0", "switch_write", 0, (("switch_id", 35), ("value", True)))
    with pytest.raises(ScenarioError, match="reads False"):
        STEP_HANDLERS["switch_write"](_StateEmu(False), "B1", on)


# --- a stuck approach walk: tolerated only for a walking NPC --------------------

class _StuckWalkEmu(_AnyEmu):
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def walk_to(self, x, y, **_kw):
        raise self.exc


def _stuck_beat(monkeypatch, moves: bool, talks: list[tuple]):
    from rpg2gba.playtest import assertions

    monkeypatch.setattr(generic, "event_page_moves", lambda mc, ev, pg: moves)
    monkeypatch.setattr(generic, "event_is_sight_trainer", lambda mc, ev: False)
    monkeypatch.setattr(generic, "local_id", lambda mc, ev: 7)
    monkeypatch.setattr(generic, "custom_route_loop", lambda mc, ev: None)
    monkeypatch.setattr(generic, "_item_boxes", lambda emu, name, row: None)
    monkeypatch.setattr(assertions, "require_map", lambda *a, **k: None)
    monkeypatch.setattr(assertions, "talk_to_moving_npc",
                        lambda emu, beat, lid, **kw: talks.append((beat, lid)))
    for kind in generic.STEP_HANDLERS:
        monkeypatch.setitem(generic.STEP_HANDLERS, kind, lambda emu, name, step: None)
    b = _builder()
    generic.generic_beat(b, chapter_id="CH05", beat_name="n", rows=(NPC,))
    (beat,) = b.build().beats
    return beat


STUCK = "stuck after 8 step-aside attempts at (1, 1)"


def test_a_stuck_approach_walk_falls_through_to_the_live_talk_for_a_walking_npc(monkeypatch):
    from rpg2gba.playtest.errors import ScenarioError

    talks: list[tuple] = []
    beat = _stuck_beat(monkeypatch, True, talks)
    beat.run(_StuckWalkEmu(ScenarioError(STUCK)))
    assert talks == [("n", 7)]


def test_a_stuck_approach_walk_still_fails_for_a_non_moving_target(monkeypatch):
    from rpg2gba.playtest.errors import ScenarioError

    talks: list[tuple] = []
    beat = _stuck_beat(monkeypatch, False, talks)
    with pytest.raises(ScenarioError, match="stuck after 8"):
        beat.run(_StuckWalkEmu(ScenarioError(STUCK)))
    assert talks == []
