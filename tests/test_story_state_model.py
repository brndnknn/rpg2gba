"""Tests for `rpg2gba.story_state.model` (REDERIVATION_PLAN.md §16.3 C2b).

Synthetic fixtures reuse `test_chapter_manifest_generator.py`'s `_page`/`_cmd`
builders (CLAUDE.md §4.3, same pattern `test_story_state_extract.py` uses).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.schema import branch_row_id, page_row_id
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.story_state.extract import extract_map, extract_triggered_common_events
from rpg2gba.story_state.model import (
    VARIABLE_TOP,
    OrderDependentEndState,
    _check_refused_pseudo_rows,
    _undetermined_detail,
    build_chapter_stories,
    certain,
    compute_end_state,
    compute_enabled_by,
    compute_killed_by,
    model_intro,
    possible,
    saturate,
)
from rpg2gba.story_state.state import Switch, Test, Variable
from tests.test_chapter_manifest_generator import _cmd, _page

OUT_DIR = Path("output/uranium-build")
CHAPTERS_PATH = Path("reference/chapters.json")


def _write_metadata_header(
    build_dir: Path, *, map_id: int = 49, x: int = 7, y: int = 7, direction: int = 2,
    encounter_maps: tuple[int, ...] = (),
) -> None:
    """A minimal `metadata.h` fixture (`heal_locations.initial_anchor`'s
    input shape) -- `model_intro` now reads this to seed `RESPAWN_MAP`
    (REDERIVATION_PLAN.md §16.3 C3). Also writes `wild_encounters.json` with a
    land table on each of `encounter_maps` (ruling 15's losable-battle check
    reads it)."""
    enc_dir = build_dir / "intermediate"
    enc_dir.mkdir(parents=True, exist_ok=True)
    land = {"encounter_rate": 5, "mons": [{"species": "SPECIES_X", "min_level": 2, "max_level": 2}]}
    (enc_dir / "wild_encounters.json").write_text(json.dumps({
        "maps": {str(m): {"land_mons": land} for m in encounter_maps},
    }), encoding="utf-8")
    header_dir = build_dir / "include" / "constants"
    header_dir.mkdir(parents=True, exist_ok=True)
    (header_dir / "metadata.h").write_text(
        f"#define URANIUM_START_MAP {map_id}\n"
        f"#define URANIUM_START_X {x}\n"
        f"#define URANIUM_START_Y {y}\n"
        f"#define URANIUM_START_DIR {direction}\n",
        encoding="utf-8",
    )


def _event(event_id: int, pages: list[dict], *, x: int = 0, y: int = 0) -> dict:
    return {"id": event_id, "name": None, "x": x, "y": y, "pages": pages}


def _map(events: list[dict], map_id: int = 999) -> dict:
    return {"map_id": map_id, "tileset_id": 1, "width": 10, "height": 10, "events": events}


def _rows(events: list[dict], map_id: int = 999) -> dict:
    return extract_map(map_id, _map(events, map_id), common_events=[], switch_labels={})


def _order(rows: dict) -> list[str]:
    from rpg2gba.chapter_manifest.schema import row_id_sort_key
    return sorted(rows, key=row_id_sort_key)


def _structural_refusals(rows: dict) -> dict:
    from rpg2gba.story_state.model import _structural_refusal
    cache: dict = {}
    return {rid: _structural_refusal(rid, rows, cache) for rid in rows}


# --- highest-live-page rule -------------------------------------------


def test_certainly_set_higher_page_kills_lower_page() -> None:
    p0 = _page([_cmd(101, ["p0"])])
    p1 = _page([_cmd(101, ["p1"])], condition={"self_switch_valid": True, "self_switch_ch": "A"})
    rows = _rows([_event(1, [p0, p1])])
    from rpg2gba.story_state.model import _live_status
    from rpg2gba.story_state.state import SelfSwitch

    p0_id = page_row_id(999, 1, 0)
    certain_state = {SelfSwitch(999, 1, "A"): frozenset({True})}
    live, _ = _live_status(p0_id, rows, certain_state, {})
    assert live is False


def test_merely_possible_higher_page_does_not_kill_lower_page() -> None:
    p0 = _page([_cmd(101, ["p0"])])
    p1 = _page([_cmd(101, ["p1"])], condition={"self_switch_valid": True, "self_switch_ch": "A"})
    rows = _rows([_event(1, [p0, p1])])
    from rpg2gba.story_state.model import _live_status
    from rpg2gba.story_state.state import SelfSwitch

    p0_id = page_row_id(999, 1, 0)
    possible_only_state = {SelfSwitch(999, 1, "A"): frozenset({True, False})}
    live, _ = _live_status(p0_id, rows, possible_only_state, {})
    assert live is True


# --- refusal inheritance -------------------------------------------------


def test_arm_inherits_parent_refusal() -> None:
    page = _page([
        _cmd(111, [1, 3, 1, 4, 1], indent=0),  # malformed: operand_kind 1
        _cmd(111, [0, 5, 0], indent=1),        # nested, well-formed
        _cmd(101, ["inner then"], indent=2),
        _cmd(412, [], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = _rows([_event(1, [page])])
    refusals = _structural_refusals(rows)

    page_id = page_row_id(999, 1, 0)
    outer_then = branch_row_id(page_id, 0)
    inner_then = branch_row_id(page_id, 2)

    assert refusals[outer_then] is not None
    assert refusals[outer_then][0] == "nonconstant_variable_condition"
    # The nested arm's parent is the refused outer arm -- inherits.
    assert rows[inner_then].parent_row_id == outer_then
    assert refusals[inner_then] == refusals[outer_then]


def test_unmodelled_outcome_refuses() -> None:
    page = _page([
        _cmd(111, [12, "pbPhoneBattleCount(1)>=3"], indent=0),
        _cmd(101, ["then"], indent=1),
        _cmd(412, [], indent=0),
    ])
    rows = _rows([_event(1, [page])])
    refusals = _structural_refusals(rows)
    then_id = branch_row_id(page_row_id(999, 1, 0), 0)
    assert refusals[then_id] is not None
    assert refusals[then_id][0].startswith("unmodelled_outcome:")


# --- saturation stages and enabled_by -----------------------------------


def test_saturation_stage_and_enabled_by_two_step_chain() -> None:
    setter_page = _page([_cmd(121, [10, 10, 0])], trigger=3)  # autorun, switch 10 ON
    gated_page = _page(
        [_cmd(101, ["gated"])], condition={"switch1_valid": True, "switch1_id": 10})
    rows = _rows([_event(1, [setter_page]), _event(2, [gated_page])])
    order = _order(rows)
    structural_refusal = _structural_refusals(rows)

    result = saturate({}, rows, order, already_owned={}, structural_refusal=structural_refusal)

    setter_id = page_row_id(999, 1, 0)
    gated_id = page_row_id(999, 2, 0)
    assert result.newly_owned[setter_id] == 0
    assert result.newly_owned[gated_id] == 1

    enabled = compute_enabled_by(gated_id, rows, {}, {r: None for r in result.newly_owned})
    assert enabled == ((setter_id,),)


# --- killed_by ------------------------------------------------------------


def test_killed_by_case_a_writer_falsifies_own_test() -> None:
    guarded_page = _page(
        [_cmd(101, ["x"])], condition={"switch1_valid": True, "switch1_id": 5})
    killer_page = _page([_cmd(121, [5, 5, 1])])  # switch 5 OFF
    rows = _rows([_event(1, [guarded_page]), _event(2, [killer_page])])
    guarded_id = page_row_id(999, 1, 0)
    killer_id = page_row_id(999, 2, 0)

    killed_by = compute_killed_by(guarded_id, rows, set(rows), {})
    assert killer_id in killed_by


def test_killed_by_case_b_writer_satisfies_higher_page() -> None:
    p0 = _page([_cmd(101, ["p0"])])
    p1 = _page([_cmd(101, ["p1"])], condition={"switch1_valid": True, "switch1_id": 7})
    other_event = _event(2, [_page([_cmd(121, [7, 7, 0])])])  # switch 7 ON
    rows = _rows([_event(1, [p0, p1]), other_event])

    p0_id = page_row_id(999, 1, 0)
    killer_id = page_row_id(999, 2, 0)
    killed_by = compute_killed_by(p0_id, rows, set(rows), {})
    assert killer_id in killed_by


# --- end state -------------------------------------------------------------


def test_end_state_ordered_toggle_resolves_deterministically() -> None:
    setter_page = _page([_cmd(121, [1, 1, 0])], trigger=3)  # switch 1 ON, autorun
    clearer_page = _page(
        [_cmd(121, [1, 1, 1])],  # switch 1 OFF
        condition={"switch1_valid": True, "switch1_id": 1}, trigger=4,
    )
    rows = _rows([_event(1, [setter_page]), _event(2, [clearer_page])])
    order = _order(rows)
    structural_refusal = _structural_refusals(rows)
    result = saturate({}, rows, order, already_owned={}, structural_refusal=structural_refusal)

    owned = set(result.newly_owned)
    enabled_by_of = {
        rid: () if result.newly_owned[rid] == 0
        else compute_enabled_by(rid, rows, {}, {r: None for r in owned})
        for rid in owned
    }
    end_state, order_dependent = compute_end_state({}, owned, rows, enabled_by_of)
    assert end_state[Switch(1)] == frozenset({False})
    assert order_dependent == ()


def test_order_dependent_writers_join_and_are_recorded_not_raised() -> None:
    """Lead ruling 2026-09-16: a genuine cross-page order dependence (two
    unrelated events, no precedence edge) is NOT a raise any more -- C2
    joins (sound over-approximation) and records an `OrderDependentKey` for
    C6's route to actually resolve."""
    a = _event(1, [_page([_cmd(121, [2, 2, 0])])])  # switch 2 ON, no guard
    b = _event(2, [_page([_cmd(121, [2, 2, 1])])])  # switch 2 OFF, no guard, unordered
    rows = _rows([a, b])
    owned = set(rows)
    enabled_by_of = {rid: () for rid in owned}
    end_state, order_dependent = compute_end_state({}, owned, rows, enabled_by_of)

    assert end_state[Switch(2)] == frozenset({False, True})
    assert len(order_dependent) == 1
    odk = order_dependent[0]
    assert odk.key == "switch:2"
    assert odk.writers == (page_row_id(999, 1, 0), page_row_id(999, 2, 0))
    assert odk.values == (False, True)


def test_order_dependent_key_lands_the_route_winner() -> None:
    """C6 seed recompute: a route pick lands the last writer's value in the
    end state (the next chapter's seed); the key is still recorded, joined."""
    a = _event(1, [_page([_cmd(121, [2, 2, 0])])])  # switch 2 ON
    b = _event(2, [_page([_cmd(121, [2, 2, 1])])])  # switch 2 OFF
    rows = _rows([a, b])
    owned = set(rows)
    seen: list[tuple[str, ...]] = []

    def pick(writers: tuple[str, ...]) -> str:
        seen.append(writers)
        return page_row_id(999, 1, 0)                 # the route visits the ON last

    end_state, order_dependent = compute_end_state(
        {}, owned, rows, {rid: () for rid in owned}, pick)
    assert seen == [(page_row_id(999, 1, 0), page_row_id(999, 2, 0))]
    assert end_state[Switch(2)] == frozenset({True})
    assert order_dependent[0].values == (False, True)


def test_order_dependent_key_without_a_pick_stays_joined() -> None:
    a = _event(1, [_page([_cmd(121, [2, 2, 0])])])
    b = _event(2, [_page([_cmd(121, [2, 2, 1])])])
    rows = _rows([a, b])
    owned = set(rows)
    end_state, _ = compute_end_state({}, owned, rows, {rid: () for rid in owned},
                                     lambda _writers: None)
    assert end_state[Switch(2)] == frozenset({False, True})


def test_order_dependent_pick_must_be_a_writer() -> None:
    a = _event(1, [_page([_cmd(121, [2, 2, 0])])])
    b = _event(2, [_page([_cmd(121, [2, 2, 1])])])
    rows = _rows([a, b])
    owned = set(rows)
    with pytest.raises(ValueError, match="not one of its writers"):
        compute_end_state({}, owned, rows, {rid: () for rid in owned},
                          lambda _writers: "map999/ev009/p0")


# --- chaining ---------------------------------------------------------


def _write_chain_fixture(tmp_path: Path) -> tuple[Path, Path]:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)

    # CHA/map901: an unconditional autorun page (event 1, owned by CHA at
    # stage 0), plus a SECOND event on the same CHA map guarded on switch 99
    # -- nothing in CHA ever sets it, so this row is never live in CHA
    # itself; it becomes live only once CHB writes switch 99 (a `later:CHB`
    # row on CHA's own map, per R8 backtracking).
    map_a = _map([
        _event(1, [_page([_cmd(121, [50, 50, 0])], trigger=3)]),
        _event(2, [_page([_cmd(101, ["later"])], condition={
            "switch1_valid": True, "switch1_id": 99})]),
    ], map_id=901)
    (build_dir / "maps" / "Map901.json").write_text(json.dumps(map_a), encoding="utf-8")

    # CHB/map902: one page only live once switch 50 is set (owned by CHB,
    # since CHA's own maps never satisfy it and CHA's saturation only sees
    # map901/map903), plus an autorun page setting switch 99 -- the write
    # that redeems map901/ev002's row above as `later:CHB`.
    map_b = _map([
        _event(1, [_page([_cmd(101, ["b"])], condition={
            "switch1_valid": True, "switch1_id": 50})]),
        _event(2, [_page([_cmd(121, [99, 99, 0])], trigger=3)]),
    ], map_id=902)
    (build_dir / "maps" / "Map902.json").write_text(json.dumps(map_b), encoding="utf-8")

    # map903: never live anywhere in the chain (guarded on a switch nothing sets).
    map_c = _map(
        [_event(1, [_page([_cmd(101, ["c"])], condition={
            "switch1_valid": True, "switch1_id": 77})])],
        map_id=903,
    )
    (build_dir / "maps" / "Map903.json").write_text(json.dumps(map_c), encoding="utf-8")

    (build_dir / "common_events.json").write_text("[]", encoding="utf-8")
    (build_dir / "system.json").write_text(json.dumps({"start_map_id": 901}), encoding="utf-8")
    _write_metadata_header(build_dir)

    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "schema": 1,
        "acts": [{"id": "A1", "title": "Act 1", "chapters": ["CHA", "CHB"]}],
        "chapters": [
            {"id": "CHA", "act": "A1", "title": "Alpha", "maps": [901, 903]},
            {"id": "CHB", "act": "A1", "title": "Beta", "maps": [902],
             "predecessor": "CHA"},
        ],
    }), encoding="utf-8")
    return build_dir, chapters_path


def test_chaining_later_and_unreachable(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_chain_fixture(tmp_path)
    stories = build_chapter_stories(
        ["CHA", "CHB"], build_dir=build_dir, chapters_path=chapters_path)

    cha = stories["CHA"]
    row_901 = next(r for r in cha.rows if r.row_id.startswith("map901"))
    assert row_901.status == "live"
    assert row_901.owner == "CHA"

    row_903 = next(r for r in cha.rows if r.row_id.startswith("map903"))
    assert row_903.status == "unreachable"

    chb = stories["CHB"]
    row_902 = next(r for r in chb.rows if r.row_id.startswith("map902"))
    assert row_902.status == "live"
    assert row_902.owner == "CHB"
    assert row_902.stage == 0  # already possible from CHA's end state (the seed)


def test_chaining_marks_row_owned_by_a_later_chapter_as_later(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_chain_fixture(tmp_path)
    stories = build_chapter_stories(
        ["CHA", "CHB"], build_dir=build_dir, chapters_path=chapters_path)

    cha = stories["CHA"]
    row = next(r for r in cha.rows if r.row_id == page_row_id(901, 2, 0))
    assert row.status == "later"
    assert row.owner == "CHB"
    assert row.detail == "later:CHB"


# --- intro pseudo-chapter --------------------------------------------


def test_intro_follows_a_direct_transfer(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)

    start_map = _map([_event(1, [_page(
        [_cmd(201, [0, 52, 1, 1, 0, 0])], trigger=3,  # autorun, direct transfer to map52
    )])], map_id=51)
    (build_dir / "maps" / "Map051.json").write_text(json.dumps(start_map), encoding="utf-8")

    second_map = _map([_event(1, [_page([_cmd(121, [1, 1, 0])], trigger=3)])], map_id=52)
    (build_dir / "maps" / "Map052.json").write_text(json.dumps(second_map), encoding="utf-8")

    (build_dir / "system.json").write_text(json.dumps({"start_map_id": 51}), encoding="utf-8")
    _write_metadata_header(build_dir)

    story, end_state, intro_maps, refusals, pseudo_owned = model_intro(
        build_dir, common_events=[], switch_labels={}, bound_map_ids=set())

    assert intro_maps == [51, 52]
    assert refusals == []
    assert end_state[Switch(1)] == frozenset({True})
    row_ids = {r.row_id for r in story.rows}
    assert page_row_id(51, 1, 0) in row_ids
    assert page_row_id(52, 1, 0) in row_ids


# --- possible/certain sanity -----------------------------------------


def test_possible_and_certain_over_variable_range() -> None:
    state = {Variable(9): frozenset({1, 2, 3})}
    assert possible(Test(Variable(9), "==", 2), state) is True
    assert certain(Test(Variable(9), "==", 2), state) is False
    assert certain(Test(Variable(9), ">=", 1), state) is True


# --- triggered common events (pseudo-rows, REDERIVATION_PLAN.md §16.3 C2
# ruling (e)) --------------------------------------------------------------


def _write_pseudo_row_fixture(tmp_path: Path) -> tuple[Path, Path]:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)

    # An INTRO-only start map with no data file (never read) -- distinct
    # from CHZ's own map, so the intro chain does NOT already satisfy the
    # CE's gate before CHZ is even modelled.
    (build_dir / "system.json").write_text(json.dumps({"start_map_id": 1}), encoding="utf-8")

    # One map, one autorun row setting switch 50 -- the CE below is gated on
    # it, so the CE's writes should only become possible AFTER this row.
    map_a = _map(
        [_event(1, [_page([_cmd(121, [50, 50, 0])], trigger=3)])], map_id=904,
    )
    (build_dir / "maps" / "Map904.json").write_text(json.dumps(map_a), encoding="utf-8")

    ce = {
        "id": 60, "name": "Gated CE", "trigger": 2, "switch_id": 50,
        "list": [{"code": 122, "parameters": [70, 70, 0, 0, 7], "indent": 0}],  # var 70 = 7
    }
    (build_dir / "common_events.json").write_text(json.dumps([ce]), encoding="utf-8")
    _write_metadata_header(build_dir)

    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "schema": 1,
        "acts": [{"id": "A1", "title": "Act 1", "chapters": ["CHZ"]}],
        "chapters": [{"id": "CHZ", "act": "A1", "title": "Zeta", "maps": [904]}],
    }), encoding="utf-8")
    return build_dir, chapters_path


def test_triggered_common_event_becomes_live_only_after_its_gate_row(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_pseudo_row_fixture(tmp_path)
    stories = build_chapter_stories(["CHZ"], build_dir=build_dir, chapters_path=chapters_path)

    chz = stories["CHZ"]
    ce_row = next(r for r in chz.common_events if r.row_id == "common/ce060")
    assert ce_row.status == "live"
    assert ce_row.owner == "CHZ"
    assert ce_row.stage == 1  # not stage 0 -- only live once switch 50 is set
    setter_id = page_row_id(904, 1, 0)
    assert ce_row.enabled_by == ((setter_id,),)

    # It never shows up in the map-scoped `rows` list.
    assert all(r.row_id != "common/ce060" for r in chz.rows)

    end_state = dict(chz.end_state)
    assert end_state["var:70"] == (7,)


# --- engine-transition forks (REDERIVATION_PLAN.md §16.3 C3, ruling R9) ----


def _write_whiteout_fixture(
    tmp_path: Path, *, got_pokemon: bool = True, losable: bool = True,
) -> tuple[Path, Path]:
    """One chapter CHW over four synthetic maps, shaped after the real
    map049/map068 white-out pattern (R9): map500 optionally sets Switch(2)
    "Got Pokemon" (the precondition); map501 has a bare `pbSetPokemonCenter`
    call (moving the respawn anchor away from the default) AND a forced
    handler gated on Switch(5) "Starting Over" (only live via the fork);
    map502 has an identically-shaped handler that must NOT be fork-owned
    (it isn't on the landing map); map503 has an always-live control row to
    confirm a main-path row is never reattributed to the fork. `losable`
    puts a wild encounter table on map503 (ruling 15: no losable battle, no
    white-out)."""
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)

    events_500 = (
        [_event(1, [_page([_cmd(121, [2, 2, 0])], trigger=3)])]  # switch 2 ON, autorun
        if got_pokemon
        else [_event(1, [_page([_cmd(101, ["noop"])])])]
    )
    map_500 = _map(events_500, map_id=500)
    (build_dir / "maps" / "Map500.json").write_text(json.dumps(map_500), encoding="utf-8")

    map_501 = _map([
        _event(1, [_page([_cmd(355, ["pbSetPokemonCenter"])], trigger=3)]),
        _event(2, [_page([_cmd(101, ["handler"])], condition={
            "switch1_valid": True, "switch1_id": 5}, trigger=3)]),
    ], map_id=501)
    (build_dir / "maps" / "Map501.json").write_text(json.dumps(map_501), encoding="utf-8")

    map_502 = _map([
        _event(1, [_page([_cmd(101, ["other handler"])], condition={
            "switch1_valid": True, "switch1_id": 5}, trigger=3)]),
    ], map_id=502)
    (build_dir / "maps" / "Map502.json").write_text(json.dumps(map_502), encoding="utf-8")

    map_503 = _map([_event(1, [_page([_cmd(101, ["always"])], trigger=3)])], map_id=503)
    (build_dir / "maps" / "Map503.json").write_text(json.dumps(map_503), encoding="utf-8")

    (build_dir / "common_events.json").write_text("[]", encoding="utf-8")
    (build_dir / "system.json").write_text(json.dumps({"start_map_id": 500}), encoding="utf-8")
    _write_metadata_header(  # anchor distinct from 500-503
        build_dir, map_id=49, encounter_maps=(503,) if losable else ())

    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "schema": 1,
        "acts": [{"id": "A1", "title": "Act 1", "chapters": ["CHW"]}],
        "chapters": [{"id": "CHW", "act": "A1", "title": "Whiteout",
                      "maps": [500, 501, 502, 503]}],
    }), encoding="utf-8")
    return build_dir, chapters_path


def test_fork_does_not_run_when_precondition_is_impossible(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_whiteout_fixture(tmp_path, got_pokemon=False)
    stories = build_chapter_stories(["CHW"], build_dir=build_dir, chapters_path=chapters_path)
    chw = stories["CHW"]

    assert chw.forks == ()
    handler = next(r for r in chw.rows if r.row_id == page_row_id(501, 2, 0))
    assert handler.status in ("unreachable", "undetermined")
    assert handler.owner is None


def test_fork_does_not_run_without_a_losable_battle(tmp_path: Path) -> None:
    # Ruling 15: a held party is not enough; something has to be able to
    # beat it. No encounter table and no battle call on CHW's maps.
    build_dir, chapters_path = _write_whiteout_fixture(tmp_path, got_pokemon=True, losable=False)
    stories = build_chapter_stories(["CHW"], build_dir=build_dir, chapters_path=chapters_path)
    chw = stories["CHW"]

    assert chw.forks == ()
    handler = next(r for r in chw.rows if r.row_id == page_row_id(501, 2, 0))
    assert handler.owner is None


def test_whiteout_fork_owns_forced_handler_on_landing_map_only(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_whiteout_fixture(tmp_path, got_pokemon=True)
    stories = build_chapter_stories(["CHW"], build_dir=build_dir, chapters_path=chapters_path)
    chw = stories["CHW"]

    assert len(chw.forks) == 1
    fork = chw.forks[0]
    assert fork.transition == "whiteout"
    # The bare `pbSetPokemonCenter` call on map501 moves the respawn anchor,
    # but a white-out BEFORE that call still lands on the seed's anchor (map
    # 49, from the metadata-header fixture): the fork reads every value the
    # anchor held during the chapter, not just the refined end state.
    assert fork.landing_maps == (49, 501)

    landing_handler_id = page_row_id(501, 2, 0)
    assert landing_handler_id in fork.owned_row_ids
    handler = next(r for r in chw.rows if r.row_id == landing_handler_id)
    assert handler.status == "live"
    assert handler.owner == "CHW"
    assert handler.blockers[0] == "fork:whiteout"
    # Ruling 16: after the engine marker, the real enablers -- here only the
    # pbSetPokemonCenter row that moved the anchor onto this landing map.
    # Got Pokemon needs no group: map500 is the fixture's start map, so INTRO
    # already set it and CHW's seed satisfies the precondition.
    assert handler.enabled_by == (("engine:whiteout",), (page_row_id(501, 1, 0),))

    # The identically-shaped handler on map502 is NOT on the landing map, so
    # the fork never walks it -- it stays unreachable/undetermined.
    other_handler_id = page_row_id(502, 1, 0)
    assert other_handler_id not in fork.owned_row_ids
    other = next(r for r in chw.rows if r.row_id == other_handler_id)
    assert other.status in ("unreachable", "undetermined")
    assert other.owner is None


def test_whiteout_fork_writes_never_reach_end_state(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_whiteout_fixture(tmp_path, got_pokemon=True)
    stories = build_chapter_stories(["CHW"], build_dir=build_dir, chapters_path=chapters_path)
    chw = stories["CHW"]

    end_state = dict(chw.end_state)
    # WHITEOUT sets Switch(5) inside the fork only -- nothing on CHW's own
    # main path ever writes it, so it must never appear in the reported
    # end state (R9: never on the main path).
    assert "switch:5" not in end_state
    assert chw.order_dependent == ()


def test_main_path_row_is_never_reattributed_to_a_fork(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_whiteout_fixture(tmp_path, got_pokemon=True)
    stories = build_chapter_stories(["CHW"], build_dir=build_dir, chapters_path=chapters_path)
    chw = stories["CHW"]

    always_id = page_row_id(503, 1, 0)
    always = next(r for r in chw.rows if r.row_id == always_id)
    assert always.status == "live"
    assert always.owner == "CHW"
    # No fork blocker -- this row was already owned by the main path before
    # the fork ever ran.
    assert always.blockers == ()


def test_sibling_input_arms_join_instead_of_conflicting() -> None:
    """CE 51's own shape: two arms of ONE input-gated branch both write the
    same key to opposite values -- the joined end state is {False, True},
    never `OrderDependentEndState` (REDERIVATION_PLAN.md §16.3 C2b handback,
    sibling-arm join rule)."""
    page = _page([
        _cmd(111, [12, "Input.trigger?(Input::C)"], indent=0),  # input, both arms
        _cmd(121, [9, 9, 0], indent=1),   # then: switch 9 ON
        _cmd(411, [], indent=0),
        _cmd(121, [9, 9, 1], indent=1),   # else: switch 9 OFF
        _cmd(412, [], indent=0),
    ])
    rows = _rows([_event(1, [page])])
    owned = set(rows)
    enabled_by_of = {rid: () for rid in owned}
    end_state, order_dependent = compute_end_state({}, owned, rows, enabled_by_of)
    assert end_state[Switch(9)] == frozenset({False, True})
    # Sibling arms of ONE branch construct are alternatives, not an order
    # dependence -- no OrderDependentKey recorded for this join.
    assert order_dependent == ()


def test_refused_pseudo_row_with_live_gate_fails_loud() -> None:
    ce = {
        "id": 70, "name": "Unclassified CE", "trigger": 1, "switch_id": 80,
        "list": [
            _cmd(111, [12, "someTotallyUnrecognizedCustomMethod(1,2,3)"], indent=0),
            _cmd(101, ["then"], indent=1),
            _cmd(412, [], indent=0),
        ],
    }
    pseudo_rows = extract_triggered_common_events([ce], switch_labels={})
    arm_id = "common/ce070/b0"
    assert pseudo_rows[arm_id].refusals  # sanity: extraction itself refused this arm

    structural_refusal = {
        rid: (tuple(r.code for r in row.refusals) or None)
        if row.parent_row_id is None
        else (tuple(r.code for r in row.refusals) or None)
        for rid, row in pseudo_rows.items()
    }
    # Only the arm is refused; the trunk's own page_tests are fine.
    structural_refusal["common/ce070"] = None

    state = {Switch(80): frozenset({True})}
    with pytest.raises(ValueError, match="possible True"):
        _check_refused_pseudo_rows(pseudo_rows, structural_refusal, "CHZ", state)


# --- FIX 1: per-page net writes (a trunk + its arms are ONE execution) ----


def test_map081_shape_trunk_on_arms_off_ends_off_no_raise() -> None:
    """Synthetic copy of the real map081/Switch(185) shape that used to
    raise `OrderDependentEndState`: TWO events, each a page trunk that sets
    a switch ON at list[0], then an unconditional 111/412 branch whose BOTH
    arms set it back OFF later. Net per page: OFF (the trunk's ON is
    shadowed by list_index); net across the two pages: OFF, OFF -- agree,
    no raise (REDERIVATION_PLAN.md §16.3 C2b handback FIX 1)."""
    def _page_shape() -> dict:
        return _page([
            _cmd(121, [185, 185, 0], indent=0),   # ON, list[0]
            _cmd(111, [0, 1, 0], indent=0),       # branch on switch 1, list[1]
            _cmd(121, [185, 185, 1], indent=1),   # then: OFF, list[2]
            _cmd(411, [], indent=0),              # list[3]
            _cmd(121, [185, 185, 1], indent=1),   # else: OFF, list[4]
            _cmd(412, [], indent=0),              # list[5]
        ])

    rows = _rows([_event(1, [_page_shape()]), _event(2, [_page_shape()])])
    owned = set(rows)
    enabled_by_of = {rid: () for rid in owned}
    end_state, order_dependent = compute_end_state({}, owned, rows, enabled_by_of)
    assert end_state[Switch(185)] == frozenset({False})
    # Both pages agree (OFF, OFF) once shadowed -- no order dependence at all.
    assert order_dependent == ()


def test_intra_page_shadowing_is_page_scoped_not_global() -> None:
    """FIX 1's shadowing only ever compares writes WITHIN one page -- two
    unrelated pages disagreeing with no shadowing involved still join AND
    get recorded as order-dependent (lead ruling 2026-09-16), never
    silently collapsed to one page's value by an unscoped shadow rule."""
    a = _event(1, [_page([_cmd(121, [2, 2, 0])])])  # switch 2 ON, unconditional
    b = _event(2, [_page([_cmd(121, [2, 2, 1])])])  # switch 2 OFF, unconditional, unordered
    rows = _rows([a, b])
    owned = set(rows)
    enabled_by_of = {rid: () for rid in owned}
    end_state, order_dependent = compute_end_state({}, owned, rows, enabled_by_of)
    assert end_state[Switch(2)] == frozenset({False, True})
    assert len(order_dependent) == 1


# --- FIX 2a: a guard-refused row is still possibly live ---------------------


def test_guard_refused_row_stays_possibly_live_and_propagates_its_writes() -> None:
    setter_page = _page([
        _cmd(111, [12, "someTotallyUnrecognizedGuard(1)"], indent=0),  # unclassified
        _cmd(121, [50, 50, 0], indent=1),   # then: switch 50 ON
        _cmd(412, [], indent=0),
    ], trigger=3)  # autorun -- the trunk itself is unconditionally live
    gated_page = _page(
        [_cmd(101, ["gated"])], condition={"switch1_valid": True, "switch1_id": 50})
    rows = _rows([_event(1, [setter_page]), _event(2, [gated_page])])
    order = _order(rows)
    structural_refusal = _structural_refusals(rows)

    refused_arm_id = branch_row_id(page_row_id(999, 1, 0), 0)
    assert structural_refusal[refused_arm_id] is not None
    assert structural_refusal[refused_arm_id][0] == "unclassified_condition"

    result = saturate({}, rows, order, already_owned={}, structural_refusal=structural_refusal)

    # The refused row is still possibly live -- its write joined the state...
    assert refused_arm_id in result.newly_owned
    # ...which is what let the downstream gated row become live too.
    gated_id = page_row_id(999, 2, 0)
    assert gated_id in result.newly_owned


# --- FIX 2b: an unparsed write havocs its keys, not the whole row ----------


def test_unparsed_write_with_a_named_key_havocs_that_variable() -> None:
    page = _page([_cmd(355, ["$game_variables[7] = someExpression"])], trigger=3)
    rows = _rows([_event(1, [page])])
    row = rows[page_row_id(999, 1, 0)]
    assert row.writes == ()
    # C8 stage 4: the catch-all `unparsed_state_write` is gone -- the
    # interpreter says precisely WHY it could not put a value to the write.
    # The FIX 2b behaviour this test is really about is unchanged: the key
    # the script visibly assigns is havoc'd by name, not globally.
    assert row.refusals[0].code == "ruby_unknown_call:someExpression"
    assert row.havoc_keys == (Variable(7),)
    assert row.havoc_global is False

    order = _order(rows)
    structural_refusal = _structural_refusals(rows)
    result = saturate({}, rows, order, already_owned={}, structural_refusal=structural_refusal)
    assert VARIABLE_TOP in result.end_state[Variable(7)]
    # TOP is possible against ANY test on that variable.
    assert possible(Test(Variable(7), ">=", 999), result.end_state) is True
    assert certain(Test(Variable(7), ">=", 999), result.end_state) is False


def test_unparsed_write_with_no_recognizable_key_is_havoc_global() -> None:
    page = _page([_cmd(355, ["$game_self_switches[weirdThing] = true"])])
    rows = _rows([_event(1, [page])])
    row = rows[page_row_id(999, 1, 0)]
    assert row.havoc_keys == ()
    assert row.havoc_global is True


# --- FIX 2c: undetermined vs unreachable ------------------------------------


def test_undetermined_when_a_possibly_live_row_has_havoc_global() -> None:
    havoc_page = _page(
        [_cmd(355, ["$game_self_switches[weirdThing] = true"])], trigger=3)  # autorun, live
    never_page = _page(
        [_cmd(101, ["x"])], condition={"switch1_valid": True, "switch1_id": 77})  # nothing sets 77
    rows = _rows([_event(1, [havoc_page]), _event(2, [never_page])])
    order = _order(rows)
    structural_refusal = _structural_refusals(rows)
    result = saturate({}, rows, order, already_owned={}, structural_refusal=structural_refusal)

    havoc_row_id = page_row_id(999, 1, 0)
    never_row_id = page_row_id(999, 2, 0)
    assert havoc_row_id in result.newly_owned
    assert never_row_id not in result.newly_owned

    detail = _undetermined_detail(never_row_id, rows, set(result.newly_owned))
    assert detail is not None
    assert detail.startswith("havoc_global:")
    assert havoc_row_id in detail


def test_unreachable_when_nothing_in_scope_havocs_anything() -> None:
    never_page = _page(
        [_cmd(101, ["x"])], condition={"switch1_valid": True, "switch1_id": 77})
    rows = _rows([_event(1, [never_page])])
    order = _order(rows)
    structural_refusal = _structural_refusals(rows)
    result = saturate({}, rows, order, already_owned={}, structural_refusal=structural_refusal)

    row_id = page_row_id(999, 1, 0)
    assert row_id not in result.newly_owned
    assert _undetermined_detail(row_id, rows, set(result.newly_owned)) is None


def test_undetermined_when_a_specific_havoc_key_matches_this_rows_own_gate() -> None:
    havoc_page = _page(
        [_cmd(355, ["$game_variables[9] = someExpression"])], trigger=3)  # autorun, live
    gated_page = _page(
        [_cmd(101, ["x"])],
        condition={"variable_valid": True, "variable_id": 9, "variable_value": 3})
    rows = _rows([_event(1, [havoc_page]), _event(2, [gated_page])])
    order = _order(rows)
    structural_refusal = _structural_refusals(rows)
    result = saturate({}, rows, order, already_owned={}, structural_refusal=structural_refusal)

    havoc_row_id = page_row_id(999, 1, 0)
    gated_row_id = page_row_id(999, 2, 0)
    # Variable(9) is TOP -- >= 3 is possible, so the gated page IS live here
    # (a live row, not undetermined) -- this pins the OTHER half of FIX 2c:
    # a havoc'd key doesn't just excuse non-liveness, it can also grant it.
    assert gated_row_id in result.newly_owned
    assert havoc_row_id in result.newly_owned


# --- C8 stage 4: the resolver fixpoint around saturation ----------------


def _resolved(rows: dict, seed: dict | None = None) -> dict:
    from rpg2gba.story_state.model import resolve_computed_rows
    order = _order(rows)
    return resolve_computed_rows(
        seed or {}, rows, order,
        already_owned={}, structural_refusal=_structural_refusals(rows),
    )


def test_computed_row_resolves_against_saturated_state() -> None:
    """A row whose script reads a variable another row writes cannot be
    resolved at extraction time; the fixpoint resolves it against the
    saturated value set (REDERIVATION_PLAN.md §16.3, "Stages 3-4 refined").
    """
    writer = _event(1, [_page([_cmd(122, [151, 151, 0, 0, 2])])])  # var151 = 2
    reader = _event(2, [_page([_cmd(355, ["$game_switches[60]=(pbGet(151)==2)"])])])
    rows = _rows([writer, reader])

    reader_id = page_row_id(999, 2, 0)
    assert rows[reader_id].computed is not None, "reader should be computed at extraction"
    assert rows[reader_id].writes == ()

    resolved = _resolved(rows)
    row = resolved[reader_id]
    assert row.computed is None or row.writes, "the fixpoint should have resolved it"
    assign = next(w for w in row.writes if w.key == Switch(60))
    # var151's SATURATED set is {0, 2}: saturation unions a write into the
    # key's prior values, and Variable's default is 0. The resolved switch
    # is therefore genuinely both -- the fixpoint resolves against what the
    # key may be, not against one chosen execution.
    assert assign.values == frozenset({False, True})
    assert row.havoc_global is False
    assert not any(r.code == "unparsed_state_write" for r in row.refusals)
    assert row.witnesses, "a resolved row carries its input vector"


def test_computed_row_reading_a_top_value_refuses_by_name() -> None:
    """"Could be anything" cannot be enumerated -- the row keeps its havoc
    and refuses under its own code rather than inventing a value."""
    from rpg2gba.story_state.model import _resolve_computed_row

    reader = _event(2, [_page([_cmd(355, ["$game_switches[60]=(pbGet(151)==2)"])])])
    rows = _rows([reader])
    reader_id = page_row_id(999, 2, 0)
    assert rows[reader_id].computed is not None

    row = _resolve_computed_row(rows[reader_id], {Variable(151): frozenset({VARIABLE_TOP})})
    assert [r.code for r in row.refusals] == ["computed_row_top_read"]
    assert row.writes == ()
    # The write is still carried, just without a value: the key the script
    # can be SEEN to assign is havoc'd by name (model.py FIX 2b), so the
    # row does not have to claim it touches everything.
    assert row.havoc_keys == (Switch(60),)
    assert row.havoc_global is False


def test_resolution_survives_a_chapter_with_no_computed_rows() -> None:
    rows = _rows([_event(1, [_page([_cmd(121, [4, 4, 0])])])])
    assert _resolved(rows) is rows


# --- real-data test (CH01-CH05) ----------------------------------------


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(), reason="no converted corpus on disk")
def test_model_runs_for_ch01_through_ch05() -> None:
    """No more xfail (REDERIVATION_PLAN.md §16.3 C2b handback, lead ruling
    2026-09-16): `OrderDependentEndState` is reserved for a genuine
    precedence cycle now, not a plain cross-page disagreement, so the real
    CH01-CH05 corpus completes end to end."""
    chapter_ids = ["CH01", "CH02", "CH03", "CH04", "CH05"]
    stories = build_chapter_stories(
        chapter_ids, build_dir=OUT_DIR, chapters_path=CHAPTERS_PATH)

    for cid in chapter_ids:
        story = stories[cid]
        assert story.chapter_id == cid
        assert story.rows


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(), reason="no converted corpus on disk")
def test_fresh_game_takes_full_intro_so_auntie_gates_the_door() -> None:
    """Ruling 14 (REDERIVATION_PLAN.md §16.3): `$skipGameIntro` is statically
    false, so Map051's skip arm (the only INTRO writer of switch 52 "Mum")
    is dead. Auntie's goodbye becomes the sole writer, the door's
    "say goodbye first" page is live on arrival, and the exit page follows
    Auntie."""
    stories = build_chapter_stories(["CH01"], build_dir=OUT_DIR, chapters_path=CHAPTERS_PATH)
    assert "switch:52" not in {str(k) for k, _ in stories["INTRO"].end_state}
    intro = {r.row_id: r for r in stories["INTRO"].rows}
    assert intro["map051/ev002/p0/b0"].status != "live"
    assert intro["map051/ev002/p0/b1"].status == "live"

    rows = {r.row_id: r for r in stories["CH01"].rows}
    assert rows["map049/ev002/p0"].status == "live"
    assert rows["map049/ev002/p0"].stage == 0
    door_exit = rows["map049/ev002/p1"]
    assert door_exit.status == "live"
    assert door_exit.stage == 1
    assert door_exit.enabled_by == (("map049/ev001/p0",),)
