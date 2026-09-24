"""Tests for `rpg2gba.beat_floor.walk` (REDERIVATION_PLAN.md §16.3 C4).

Unit tests that need script/condition behaviour monkeypatch
`walk.extract_script`/`walk.extract_condition` so they exercise the walker
alone; `test_beat_floor_script_condition.py` covers the real extractors.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_floor import walk
from rpg2gba.beat_floor.assertion import ExtractContext, FloorAssertion

MAP_ID = 1
EVENT_ID = 1
PAGE_IDX = 0
ROW_ID = "map001/ev001/p0"


def _map_data(commands: list[dict], *, trigger: int = 0) -> dict:
    return {
        "events": [
            {
                "id": EVENT_ID,
                "pages": [
                    {
                        "trigger": trigger,
                        "condition": {},
                        "list": commands,
                    }
                ],
            }
        ]
    }


def _floor(commands: list[dict], *, trigger: int = 0, common_events: list[dict] | None = None,
           door_cells: dict[int, frozenset[tuple[int, int]]] | None = None):
    map_data = _map_data(commands, trigger=trigger)
    return walk.floor_for_map(
        MAP_ID, map_data, common_events=common_events or [], switch_labels={},
        door_cells=door_cells if door_cells is not None else {},
    )


def _row(commands: list[dict], **kwargs):
    rows = _floor(commands, **kwargs)
    return rows[ROW_ID]


def _kinds(row) -> set[str]:
    return {a.kind for a in row.assertions}


def _only(row, kind: str) -> FloorAssertion:
    matches = [a for a in row.assertions if a.kind == kind]
    assert len(matches) == 1, matches
    return matches[0]


# --- base shape --------------------------------------------------------

def test_every_row_gets_trigger_and_completes():
    row = _row([], trigger=3)
    assert row.trigger == "autorun"
    trig = _only(row, "trigger")
    assert trig.param("trigger") == "autorun"
    _only(row, "completes")
    assert not row.refused


# --- text grouping -------------------------------------------------------

def test_text_grouping_joins_101_and_401():
    commands = [
        {"code": 101, "parameters": ["Hello,"]},
        {"code": 401, "parameters": ["world!"]},
    ]
    row = _row(commands)
    text_a = _only(row, "text")
    assert text_a.param("index") == 0
    assert text_a.list_index == 0
    assert "Hello" in text_a.param("text")
    assert "world" in text_a.param("text")
    assert not row.refused
    assert row.offline_eligible


def test_two_consecutive_text_boxes_get_separate_indices():
    commands = [
        {"code": 101, "parameters": ["First"]},
        {"code": 101, "parameters": ["Second"]},
    ]
    row = _row(commands)
    texts = sorted((a for a in row.assertions if a.kind == "text"), key=lambda a: a.param("index"))
    assert [t.param("index") for t in texts] == [0, 1]
    assert texts[0].param("text") != texts[1].param("text")


def test_text_unnormalizable_refuses_row():
    commands = [{"code": 101, "parameters": ["bad \\v[1] code"]}]
    row = _row(commands)
    assert row.refused
    assert any(r.reason == "text_unnormalizable" for r in row.refusals)


def test_text_gets_stagings_char_substitutions():
    """Regression (#109 follow-up): the floor's text path must apply the same
    straight-quote and `*` substitutions `text_source.page_messages` does --
    it had its own copy of the pipeline and kept refusing `"` and `*`."""
    commands = [{"code": 101, "parameters": ['He said "hi" *wink*']}]
    row = _row(commands)
    assert not row.refused, row.refusals
    text = _only(row, "text").param("text")
    assert '"' not in text and "*" not in text


# --- choice --------------------------------------------------------------

def test_choice_normalizes_options():
    commands = [{"code": 102, "parameters": [["Yes", "No"], 0]}]
    row = _row(commands)
    choice = _only(row, "choice")
    assert choice.param("options") == ("Yes", "No")


# --- warp ------------------------------------------------------------------

def test_warp_direct_target():
    commands = [{"code": 201, "parameters": [0, 5, 10, 12, 2, 0]}]
    row = _row(commands)
    w = _only(row, "warp")
    assert w.param("map_id") == 5
    assert w.param("x") == 10
    assert w.param("y") == 12
    assert w.param("direction") == 2
    assert w.param("arrives_on_door") is False
    assert not row.refused


def test_warp_arrives_on_door_reads_emitted_door_cells():
    """`arrives_on_door` is True exactly when the emitted layout stamps the
    arrival cell (on the DESTINATION map) as a door tile -- the same cell on
    another map, or a neighbouring cell, does not count."""
    commands = [{"code": 201, "parameters": [0, 5, 10, 12, 0, 0]}]
    on_door = _only(_row(commands, door_cells={5: frozenset({(10, 12)})}), "warp")
    assert on_door.param("arrives_on_door") is True
    other_map = _only(_row(commands, door_cells={6: frozenset({(10, 12)})}), "warp")
    assert other_map.param("arrives_on_door") is False
    neighbour = _only(_row(commands, door_cells={5: frozenset({(10, 13)})}), "warp")
    assert neighbour.param("arrives_on_door") is False


def test_warp_without_door_cells_fails_loud():
    """An ExtractContext built without door cells cannot answer
    arrives_on_door -- the extractor raises rather than guess plain floor."""
    ctx = ExtractContext(1, 1, 0, "map001/ev001/p0", {}, {}, {})
    with pytest.raises(ValueError, match="door cells"):
        walk._extract_warp({"code": 201, "parameters": [0, 5, 10, 12, 2, 0]}, 0, ctx)


def test_warp_variable_target_refuses():
    commands = [{"code": 201, "parameters": [1, 0, 0, 0, 0, 0]}]
    row = _row(commands)
    assert row.refused
    assert any(r.reason == "warp_variable_target" for r in row.refusals)


# --- event position --------------------------------------------------------

def test_event_position_direct():
    commands = [{"code": 202, "parameters": [3, 0, 4, 5, 1]}]
    row = _row(commands)
    pos = _only(row, "event_position")
    assert pos.param("target") == 3
    assert pos.param("x") == 4
    assert pos.param("y") == 5


def test_event_position_variable_refuses():
    commands = [{"code": 202, "parameters": [3, 1, 0, 0, 0]}]
    row = _row(commands)
    assert row.refused
    assert any(r.reason == "event_position_variable_target" for r in row.refusals)


# --- 115 stops the walk ------------------------------------------------

def test_exit_event_processing_stops_walk():
    commands = [
        {"code": 116, "parameters": []},
        {"code": 115, "parameters": []},
        {"code": 201, "parameters": [0, 5, 1, 1, 2, 0]},
    ]
    row = _row(commands)
    assert _kinds(row) >= {"erase_event"}
    assert "warp" not in _kinds(row)
    assert not row.refused


# --- 117 inlining ------------------------------------------------------

def test_common_event_call_inlines_body_attributed_to_call_site():
    ce = {"id": 9, "list": [{"code": 116, "parameters": []}]}
    commands = [
        {"code": 106, "parameters": []},           # list_index 0 (visual)
        {"code": 117, "parameters": [9]},           # list_index 1 (the call)
    ]
    row = _row(commands, common_events=[ce])
    erase = _only(row, "erase_event")
    assert erase.list_index == 1
    assert not row.refused


def test_common_event_cycle_refuses():
    ce = {"id": 9, "list": [{"code": 117, "parameters": [9]}]}
    commands = [{"code": 117, "parameters": [9]}]
    row = _row(commands, common_events=[ce])
    assert row.refused
    cycle = [r for r in row.refusals if r.reason == "common_event_cycle"]
    assert len(cycle) == 1
    assert cycle[0].list_index == 0  # attributed to the outer call site


def test_missing_common_event_refuses():
    commands = [{"code": 117, "parameters": [404]}]
    row = _row(commands, common_events=[])
    assert row.refused
    assert any(r.reason == "missing_common_event" for r in row.refusals)


# --- unknown code --------------------------------------------------------

def test_unknown_code_refuses():
    commands = [{"code": 9999, "parameters": []}]
    row = _row(commands)
    assert row.refused
    assert any(r.reason == "no_extractor" for r in row.refusals)


# --- audio / visual tagging ------------------------------------------------

def test_audio_tagged_and_offline_eligible():
    commands = [{"code": 241, "parameters": [{"name": "Theme1"}]}]
    row = _row(commands)
    a = _only(row, "audio")
    assert a.tag == "audio"
    assert a.param("name") == "Theme1"
    assert a.offline  # audio is in OFFLINE_KINDS
    assert row.offline_eligible


def test_visual_tagged_and_offline_eligible():
    commands = [{"code": 106, "parameters": []}]
    row = _row(commands)
    v = _only(row, "visual")
    assert v.tag == "visual"
    assert v.offline
    assert row.offline_eligible


# --- story_state write merge --------------------------------------------

def test_switch_write_merged_from_story_state():
    commands = [{"code": 121, "parameters": [5, 5, 0]}]  # switch 5 ON
    row = _row(commands)
    sw = _only(row, "switch_write")
    assert sw.param("switch_id") == 5
    assert sw.param("value") is True
    assert sw.list_index == 0
    assert sw.tag == "state"
    # var_write/battle/displacement/event_position are ROM-only, but
    # switch_write is offline-checkable (assertion.OFFLINE_KINDS).
    assert row.offline_eligible


def test_var_write_merged_and_not_offline_eligible():
    commands = [{"code": 122, "parameters": [10, 10, 0, 0, 7]}]  # var 10 = 7
    row = _row(commands)
    vw = _only(row, "var_write")
    assert vw.param("var_id") == 10
    assert vw.param("op") == "="
    assert vw.param("value") == 7
    # var_write is ROM-only (R11's own example)
    assert not row.offline_eligible


def test_self_switch_write_merged():
    commands = [{"code": 123, "parameters": ["A", 0]}]
    row = _row(commands)
    ssw = _only(row, "self_switch_write")
    assert ssw.param("event_id") == EVENT_ID
    assert ssw.param("letter") == "A"
    assert ssw.param("value") is True


def test_leaf_extractor_emits_nothing_for_switch_write():
    # walk.py's own CODE_EXTRACTORS[121] contributes nothing -- the
    # switch_write assertion above comes entirely from the story_state
    # merge, per R11 C4 design ("state writes are not re-derived").
    result = walk.CODE_EXTRACTORS[121]({"code": 121, "parameters": [5, 5, 0]}, 0,
                                        ExtractContext(1, 1, 0, "x", {}, {}, {}))
    assert result == ((), ())


# --- condition family (111 type 12) via monkeypatched sibling -------------

def test_condition_type_12_dispatches_to_extract_condition(monkeypatch):
    calls = []

    def fake_extract_condition(text, list_index, ctx):
        calls.append((text, list_index, ctx.row_id))
        return (
            (FloorAssertion(row_id=ctx.row_id, kind="var_write", list_index=list_index,
                             code=111, params=(("stub", True),), tag="state"),),
            (),
        )

    monkeypatch.setattr(walk, "extract_condition", fake_extract_condition)
    commands = [{"code": 111, "parameters": [12, "some_condition_call()"]}]
    row = _row(commands)
    assert calls == [("some_condition_call()", 0, ROW_ID)]
    assert any(a.kind == "var_write" and a.param("stub") for a in row.assertions)


def test_condition_type_0_contributes_nothing():
    # Plain switch condition (type 0) is a story_state guard, not a floor
    # extraction target -- R11 C4 shape.
    commands = [{"code": 111, "parameters": [0, 5, 0]}]
    row = _row(commands)
    assert not row.refused
    assert _kinds(row) == {"trigger", "completes"}


# --- script grouping via monkeypatched sibling -----------------------------

def test_script_block_grouped_and_dispatched(monkeypatch):
    calls = []

    def fake_extract_script(text, list_index, ctx):
        calls.append((text, list_index))
        return (), ()

    monkeypatch.setattr(walk, "extract_script", fake_extract_script)
    # A call the interpreter's builtin table declares: C8 stage 4 put real
    # story-state extraction behind this row, so an INVENTED name here would
    # refuse (`ruby_unknown_call`) and mask what this test is about, which is
    # only that a 355 + its 655 continuations arrive as ONE joined block.
    commands = [
        {"code": 355, "parameters": ["pbCallBub("]},
        {"code": 655, "parameters": ["1, 2)"]},
    ]
    row = _row(commands)
    assert calls == [("pbCallBub(\n1, 2)", 0)]
    assert not row.refused


# --- move route (real module) ----------------------------------------------

def test_move_route_dispatches_to_real_module():
    commands = [{
        "code": 209,
        "parameters": [-1, {"list": [{"code": 1, "parameters": []}, {"code": 0}]}],
    }]
    row = _row(commands)
    d = _only(row, "displacement")
    assert d.param("dx") == 0
    assert d.param("dy") == 1


# --- idempotence -----------------------------------------------------------

def test_idempotent_across_runs():
    commands = [
        {"code": 101, "parameters": ["Hi"]},
        {"code": 121, "parameters": [1, 1, 0]},
        {"code": 201, "parameters": [0, 2, 3, 4, 0, 0]},
    ]
    a = _row(commands)
    b = _row(commands)
    assert a == b


# --- real corpus (skipped if the build isn't present) ----------------------

_BUILD_DIR = Path("output/uranium-build")


@pytest.mark.parametrize("chapter", ["CH01", "CH02", "CH03", "CH04", "CH05"])
def test_real_chapter_has_no_unextracted_codes(chapter):
    if not (_BUILD_DIR / "maps").exists():
        pytest.skip("no converted map corpus at output/uranium-build/maps")

    rows = walk.floor_for_chapter(chapter, build_dir=_BUILD_DIR)
    assert rows, f"{chapter}: no rows produced"
    no_extractor = [
        (rid, r) for rid, row in rows.items() for r in row.refusals
        if r.reason == "no_extractor"
    ]
    assert not no_extractor, f"{chapter}: unhandled command codes: {no_extractor[:10]}"


@pytest.mark.parametrize("chapter", ["CH01", "CH02", "CH03", "CH04", "CH05"])
def test_real_chapter_floor_rows_match_manifest_rows(chapter):
    # The floor covers exactly every manifest row -- page, branch, seam, and
    # terrain (beat_floor.terrain gives seam/terrain rows a row-level floor
    # too, REDERIVATION_PLAN.md §16.3 C5), not just the event rows.
    import json

    if not (_BUILD_DIR / "maps").exists():
        pytest.skip("no converted map corpus at output/uranium-build/maps")
    manifest = json.loads(
        Path(f"reference/manifests/{chapter}.manifest.json").read_text(encoding="utf-8"))
    rows = manifest["rows"] if isinstance(manifest, dict) else manifest
    manifest_row_ids = {r["row_id"] for r in rows}
    floor_row_ids = set(walk.floor_for_chapter(chapter, build_dir=_BUILD_DIR))
    assert floor_row_ids == manifest_row_ids
