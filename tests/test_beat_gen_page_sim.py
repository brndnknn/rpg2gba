"""`beat_gen/page_sim.py`: one page, one firing (REDERIVATION_PLAN.md §16.3
ruling 19, "generic_beat checks services" follow-on).

Fixtures are built by feeding small, real-shaped RMXP page dicts through
`story_state.extract.extract_map` -- the SAME extraction the production
pipeline uses -- rather than hand-building `RowState`/`ArmGuard` objects,
so a fixture can never drift from what `story_state.extract` actually
produces for that page shape.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_gen.page_sim import Firing, run_page
from rpg2gba.story_state.extract import extract_map
from rpg2gba.story_state.state import Switch, Variable

_BUILD_DIR = Path("output/uranium-build")

_NO_CONDITION = {
    "switch1_valid": False, "switch2_valid": False,
    "variable_valid": False, "self_switch_valid": False,
}


def _rows(map_id: int, event_id: int, page: dict) -> dict:
    map_data = {"events": [{"id": event_id, "pages": [page]}]}
    return extract_map(map_id, map_data, common_events=[], switch_labels={})


def _switch_write(sid: int, on: bool) -> dict:
    return {"code": 121, "indent": 1, "parameters": [sid, sid, 0 if on else 1]}


def _blank(indent: int = 1) -> dict:
    return {"code": 0, "indent": indent, "parameters": []}


# --- 1. self-switch toggle NPC (map064/ev001/p0 shape) ---------------------


def _npc_page() -> dict:
    return {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            {"code": 111, "indent": 0, "parameters": [2, "A", 1]},  # self switch A off?
            {"code": 101, "indent": 1, "parameters": ["hi"]},
            {"code": 123, "indent": 1, "parameters": ["A", 0]},  # turn A on
            _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            {"code": 101, "indent": 1, "parameters": ["welcome back"]},
            _blank(),
            {"code": 412, "indent": 0, "parameters": []},
            _blank(indent=0),
        ],
    }


def test_self_switch_npc_toggles_across_two_firings():
    page = _npc_page()
    rows = _rows(64, 1, page)
    firing = Firing(cell=None, event_cell=None)

    first = run_page("map064/ev001/p0", page, rows, {}, firing)
    assert first.taken == {"map064/ev001/p0/b0"}
    assert first.not_taken == {"map064/ev001/p0/b1"}
    assert first.undecided == frozenset()
    assert first.exact is True

    second = run_page("map064/ev001/p0", page, rows, first.state, firing)
    assert second.taken == {"map064/ev001/p0/b1"}
    assert second.not_taken == {"map064/ev001/p0/b0"}


# --- 2. choice answers ------------------------------------------------------


def _choice_page() -> dict:
    return {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            {"code": 102, "indent": 0, "parameters": [["Yes", "No"], 1]},
            {"code": 402, "indent": 0, "parameters": [0, "Yes"]},
            _switch_write(10, True), _blank(),
            {"code": 402, "indent": 0, "parameters": [1, "No"]},
            _switch_write(11, True), _blank(),
            {"code": 403, "indent": 0, "parameters": []},
            _switch_write(12, True), _blank(),
            {"code": 404, "indent": 0, "parameters": []},
        ],
    }


def test_choice_answer_selects_one_arm_others_not_taken():
    page = _choice_page()
    rows = _rows(68, 3, page)
    firing = Firing(cell=None, event_cell=None, choice_answers={0: 0})

    result = run_page("map068/ev003/p0", page, rows, {}, firing)
    assert result.taken == {"map068/ev003/p0/b0"}
    assert result.not_taken == {"map068/ev003/p0/b1", "map068/ev003/p0/b2"}
    assert result.undecided == frozenset()
    assert result.state[Switch(10)] == frozenset({True})


def test_choice_missing_answer_is_undecided_for_every_arm():
    page = _choice_page()
    rows = _rows(68, 3, page)
    firing = Firing(cell=None, event_cell=None)  # no choice_answers entry

    result = run_page("map068/ev003/p0", page, rows, {}, firing)
    assert result.taken == frozenset()
    all_arms = {"map068/ev003/p0/b0", "map068/ev003/p0/b1", "map068/ev003/p0/b2"}
    assert result.undecided == all_arms
    assert result.not_taken == frozenset()
    assert result.exact is False
    # Conservative: every arm's switch write is possible, none is certain.
    assert result.state[Switch(10)] == frozenset({False, True})
    assert result.state[Switch(11)] == frozenset({False, True})
    assert result.state[Switch(12)] == frozenset({False, True})


# --- 3. the y-loop (map032/ev074/p0 shape) ----------------------------------


def _y_loop_page() -> dict:
    def loop(test_text: str, move_code: int) -> list[dict]:
        return [
            {"code": 112, "indent": 0, "parameters": []},
            {"code": 111, "indent": 1, "parameters": [12, test_text]},
            {"code": 113, "indent": 2, "parameters": []},
            _blank(indent=2),
            {"code": 412, "indent": 1, "parameters": []},
            {"code": 209, "indent": 1,
             "parameters": [-1, {"__class__": "RPG::MoveRoute", "list": []}]},
            {"code": 509, "indent": 1,
             "parameters": [{"__class__": "RPG::MoveCommand", "code": move_code, "parameters": []}]},
            {"code": 210, "indent": 1, "parameters": []},
            {"code": 413, "indent": 0, "parameters": []},
        ]

    return {
        "trigger": 2, "condition": dict(_NO_CONDITION),
        "list": [
            *loop("$game_player.y>=15", 1),  # move down (y+1) until y>=15
            *loop("$game_player.y<=15", 4),  # move up (y-1) until y<=15
        ],
    }


PAGE_ROW = "map032/ev074/p0"
LOOP1_THEN, LOOP1_ELSE = f"{PAGE_ROW}/b0", f"{PAGE_ROW}/b1"
LOOP2_THEN, LOOP2_ELSE = f"{PAGE_ROW}/b2", f"{PAGE_ROW}/b3"


def test_y_loop_from_13_both_loop1_arms_taken_loop2_else_not_taken():
    page = _y_loop_page()
    rows = _rows(32, 74, page)
    firing = Firing(cell=(10, 13), event_cell=None)

    result = run_page(PAGE_ROW, page, rows, {}, firing)
    assert {LOOP1_THEN, LOOP1_ELSE} <= result.taken
    assert LOOP2_ELSE in result.not_taken


def test_y_loop_from_15_both_move_arms_not_taken():
    page = _y_loop_page()
    rows = _rows(32, 74, page)
    firing = Firing(cell=(10, 15), event_cell=None)

    result = run_page(PAGE_ROW, page, rows, {}, firing)
    # y is already 15: both loops break on their first iteration, so the
    # "else" arm that would fall through to the move step never runs.
    assert LOOP1_ELSE in result.not_taken
    assert LOOP2_ELSE in result.not_taken
    assert LOOP1_THEN in result.taken
    assert LOOP2_THEN in result.taken


# --- 4. input-kind script conditions ----------------------------------------


def _one_if_page(condition_text: str) -> dict:
    return {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            {"code": 111, "indent": 0, "parameters": [12, condition_text]},
            _switch_write(30, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(31, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
        ],
    }


ONE_IF_ROW = "map050/ev009/p0"
THEN, ELSE = f"{ONE_IF_ROW}/b0", f"{ONE_IF_ROW}/b1"


def test_game_player_x_equal_selects_by_cell():
    page = _one_if_page("$game_player.x==17")
    rows = _rows(50, 9, page)

    hit = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=(17, 0), event_cell=None))
    assert hit.taken == {THEN} and hit.not_taken == {ELSE}

    miss = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=(16, 0), event_cell=None))
    assert miss.taken == {ELSE} and miss.not_taken == {THEN}

    unknown = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=None, event_cell=None))
    assert unknown.undecided == {THEN, ELSE}


def test_on_event_compares_cell_to_event_cell():
    page = _one_if_page("get_character(0).onEvent?")
    rows = _rows(50, 9, page)

    equal = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=(5, 5), event_cell=(5, 5)))
    assert equal.taken == {THEN} and equal.not_taken == {ELSE}

    unequal = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=(5, 5), event_cell=(6, 6)))
    assert unequal.taken == {ELSE} and unequal.not_taken == {THEN}

    unknown = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=None, event_cell=(6, 6)))
    assert unknown.undecided == {THEN, ELSE}


def test_pb_pick_berry_always_confirms_yes():
    page = _one_if_page("pbPickBerry(PBItems::ORANBERRY,2)")
    rows = _rows(50, 9, page)

    result = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=None, event_cell=None))
    assert result.taken == {THEN} and result.not_taken == {ELSE}


# --- 5. list-index ordering: a write before a same-page test ---------------


def test_write_before_test_on_same_variable_is_seen():
    page = {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            {"code": 122, "indent": 0, "parameters": [1, 1, 0, 0, 5]},  # var1 = 5
            {"code": 111, "indent": 0, "parameters": [1, 1, 0, 0, 0]},  # var1 == 0 ?
            _switch_write(60, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(61, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
        ],
    }
    rows = _rows(50, 9, page)
    result = run_page(ONE_IF_ROW, page, rows, {}, Firing(cell=None, event_cell=None))
    # var1 is 5 (not 0) by the time the test runs -- else arm.
    assert result.taken == {ELSE} and result.not_taken == {THEN}
    assert result.state[Variable(1)] == frozenset({5})


# --- 6. undecided construct unions writes; poison stops interpretation -----


def _nonconstant_var_branch(indent: int = 0) -> dict:
    # operand_kind=1 (variable-relative) makes this un-parseable at
    # extraction time (`nonconstant_variable_condition`, a SOFT refusal):
    # arm_guard is None for both arms -- genuinely undecided, no family to
    # even try.
    return {"code": 111, "indent": indent, "parameters": [1, 5, 1, 0, 0]}


def test_undecided_construct_unions_writes_and_clears_exact():
    page = {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            _nonconstant_var_branch(),
            _switch_write(20, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(20, False), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
            _switch_write(21, True),  # trunk-level, unconditional, after the branch
            _blank(indent=0),
        ],
    }
    rows = _rows(10, 5, page)
    result = run_page("map010/ev005/p0", page, rows, {}, Firing(cell=None, event_cell=None))

    assert result.undecided == {"map010/ev005/p0/b0", "map010/ev005/p0/b1"}
    assert result.taken == frozenset() and result.not_taken == frozenset()
    assert result.exact is False
    assert result.state[Switch(20)] == frozenset({False, True})
    assert result.state[Switch(21)] == frozenset({True})  # unaffected, still certain


def test_poison_stops_interpretation_but_keeps_prior_proofs():
    page = {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            # A decided branch: switch 99 defaults to False (off), so the
            # then-arm (tests switch OFF) is certain.
            {"code": 111, "indent": 0, "parameters": [0, 99, 1]},
            _switch_write(30, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(30, False), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
            # An undecided branch whose then-arm exits the event -- poison.
            _nonconstant_var_branch(),
            {"code": 115, "indent": 1, "parameters": []},
            _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(31, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
            # A third branch, structurally unreachable once poisoned.
            {"code": 111, "indent": 0, "parameters": [0, 40, 0]},
            _switch_write(50, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(51, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
        ],
    }
    rows = _rows(20, 7, page)
    result = run_page("map020/ev007/p0", page, rows, {}, Firing(cell=None, event_cell=None))

    assert result.taken == {"map020/ev007/p0/b0"}
    assert result.not_taken == {"map020/ev007/p0/b1"}
    assert result.undecided == {
        "map020/ev007/p0/b2", "map020/ev007/p0/b3",
        "map020/ev007/p0/b4", "map020/ev007/p0/b5",
    }
    assert result.exact is False
    assert result.state[Switch(30)] == frozenset({True})  # the decided arm's write stands
    assert result.state[Switch(50)] == frozenset({False, True})  # swept in conservatively


# --- 7. partition + input immutability --------------------------------------


def test_taken_not_taken_undecided_partition_all_arms_input_untouched():
    page = _npc_page()
    rows = _rows(64, 1, page)
    input_state = {}
    result = run_page("map064/ev001/p0", page, rows, dict(input_state), Firing(cell=None, event_cell=None))

    all_arms = {rid for rid in rows if rid.rsplit("/", 1)[-1].startswith("b")}
    assert result.taken | result.not_taken | result.undecided == all_arms
    assert result.taken & result.not_taken == frozenset()
    assert result.taken & result.undecided == frozenset()
    assert result.not_taken & result.undecided == frozenset()
    assert input_state == {}  # never mutated


# --- real-data cross-check (lead amendment): map050/ev019/p0, a canlose
# trainer battle whose two arms carry different outcome kinds (b8 'always',
# b9 'fork:whiteout') -- the decision must be per-arm, not "then's tests,
# else is the negation". -----------------------------------------------------


def test_real_canlose_trainer_battle_decides_per_arm():
    if not _BUILD_DIR.exists():
        pytest.skip("output/uranium-build not present locally")
    from rpg2gba.beat_gen.__main__ import BUILD_DIR, _page_for, _row_states_for

    row_states = _row_states_for(BUILD_DIR)(50)
    page = _page_for(BUILD_DIR)("map050/ev019/p0")
    result = run_page("map050/ev019/p0", page, row_states, {}, Firing(cell=None, event_cell=None))

    assert "map050/ev019/p0/b8" in result.taken
    assert "map050/ev019/p0/b9" in result.not_taken
    assert result.state[Switch(35)] == frozenset({False})


# --- 8. player-facing conditions ([6, -1, dir]) -- escort (ruling 11) -------


def _facing_if_page(direction: int) -> dict:
    return {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            {"code": 111, "indent": 0, "parameters": [6, -1, direction]},
            _switch_write(30, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(31, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
        ],
    }


FACING_ROW = "map051/ev010/p0"
FACING_THEN, FACING_ELSE = f"{FACING_ROW}/b0", f"{FACING_ROW}/b1"


def test_player_facing_then_arm_taken_when_fired_from_south():
    page = _facing_if_page(8)  # [6, -1, 8]: "is the player facing up?"
    rows = _rows(51, 10, page)
    # Player south of the event, facing toward it -- facing up.
    result = run_page(FACING_ROW, page, rows, {}, Firing(cell=(5, 6), event_cell=(5, 5)))
    assert result.taken == {FACING_THEN} and result.not_taken == {FACING_ELSE}


def test_player_facing_else_arm_taken_from_the_east():
    page = _facing_if_page(8)
    rows = _rows(51, 10, page)
    # Player east of the event, facing toward it -- facing left, not up.
    result = run_page(FACING_ROW, page, rows, {}, Firing(cell=(6, 5), event_cell=(5, 5)))
    assert result.taken == {FACING_ELSE} and result.not_taken == {FACING_THEN}


def test_player_facing_move_route_updates_facing_before_a_second_check():
    # First [6,-1,8] check, fired from the south (facing up), takes the
    # then-arm; a move-route "move left" (code 2) then "turn right" (code
    # 18) follows; the SECOND [6,-1,8] check must see that turn (facing
    # right, not up any more), so it takes the else-arm.
    page = {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            {"code": 111, "indent": 0, "parameters": [6, -1, 8]},
            _switch_write(40, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(41, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
            {"code": 209, "indent": 0,
             "parameters": [-1, {"__class__": "RPG::MoveRoute", "list": []}]},
            {"code": 509, "indent": 0,
             "parameters": [{"__class__": "RPG::MoveCommand", "code": 2, "parameters": []}]},
            {"code": 509, "indent": 0,
             "parameters": [{"__class__": "RPG::MoveCommand", "code": 18, "parameters": []}]},
            {"code": 210, "indent": 0, "parameters": []},
            {"code": 111, "indent": 0, "parameters": [6, -1, 8]},
            _switch_write(42, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(43, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
        ],
    }
    rows = _rows(51, 11, page)
    row = "map051/ev011/p0"
    first_then, first_else = f"{row}/b0", f"{row}/b1"
    second_then, second_else = f"{row}/b2", f"{row}/b3"
    result = run_page(row, page, rows, {}, Firing(cell=(5, 6), event_cell=(5, 5)))
    assert result.taken == {first_then, second_else}
    assert result.not_taken == {first_else, second_then}


def test_player_facing_undecided_for_an_autorun_page():
    # trigger=3 (autorun): facing is never seeded from cell/event_cell.
    page = _facing_if_page(8)
    page["trigger"] = 3
    rows = _rows(51, 12, page)
    row = "map051/ev012/p0"
    result = run_page(row, page, rows, {}, Firing(cell=(5, 6), event_cell=(5, 5)))
    assert result.undecided == {f"{row}/b0", f"{row}/b1"}


def test_npc_facing_stays_undecided():
    # [6, N, dir] with N != -1 is an NPC's own facing, not the player's --
    # this interpreter never models it.
    page = {
        "trigger": 0, "condition": dict(_NO_CONDITION),
        "list": [
            {"code": 111, "indent": 0, "parameters": [6, 3, 8]},
            _switch_write(30, True), _blank(),
            {"code": 411, "indent": 0, "parameters": []},
            _switch_write(31, True), _blank(),
            {"code": 412, "indent": 0, "parameters": []},
        ],
    }
    rows = _rows(51, 13, page)
    row = "map051/ev013/p0"
    result = run_page(row, page, rows, {}, Firing(cell=(5, 6), event_cell=(5, 5)))
    assert result.undecided == {f"{row}/b0", f"{row}/b1"}
