"""Tests for `rpg2gba.chapter_manifest.generator`.

Covers a synthetic golden case (exact row shape) plus the map-32 (Moki Town)
corpus regression fixture the design document characterizes in Part 6 of
`PLAYTEST_AUTHORING_IMPROVEMENT.md`. The corpus tests skip when
`output/uranium-build/` is absent, matching the pattern in
`tests/test_chapter_atlas.py`.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from rpg2gba.chapter_atlas.census import (
    COND_TYPE_SCRIPT,
    RUBY_KEYWORDS,
    _script_head,
)
from rpg2gba.chapter_manifest import generator
from rpg2gba.chapter_manifest.approach_model import GraphApproachModel
from rpg2gba.chapter_manifest.generator import (
    _extract_scripts,
    generate_chapter_manifest,
    write_manifest,
)
from rpg2gba.chapter_manifest.schema import (
    branch_row_id,
    content_hash,
    page_row_id,
    seam_row_id,
    whole_page_views,
)

OUT_DIR = Path("output/uranium-build")
CHAPTERS_PATH = Path("reference/chapters.json")


# --- synthetic fixtures ------------------------------------------------


def _write_map(path: Path, map_id: int, events: list[dict]) -> None:
    payload = {
        "map_id": map_id,
        "tileset_id": 1,
        "width": 10,
        "height": 10,
        "events": events,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _page(list_: list[dict], *, condition: dict | None = None, trigger: int = 0) -> dict:
    default_condition = {
        "switch1_valid": False, "switch1_id": 1,
        "switch2_valid": False, "switch2_id": 1,
        "variable_valid": False, "variable_id": 1, "variable_value": 0,
        "self_switch_valid": False, "self_switch_ch": "A",
    }
    if condition:
        default_condition.update(condition)
    list_ = list_ + [{"code": 0, "indent": 0, "parameters": []}]
    return {
        "condition": default_condition,
        "graphic": {}, "move_type": 0, "move_route": {"list": []},
        "trigger": trigger, "direction_fix": False, "through": False,
        "list": list_,
    }


def _cmd(code: int, parameters: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": parameters or []}


def _setup_chapter(tmp_path: Path, map_id: int, events: list[dict]) -> Path:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    _write_map(build_dir / "maps" / f"Map{map_id:03d}.json", map_id, events)
    (build_dir / "connections.json").write_text("[]", encoding="utf-8")
    # These fixtures represent a map that has been through the transpiler --
    # most of these tests assert on `unhandled`/`may_be_cosmetic`, which now
    # depend on staging status (`generator._load_staged_map_ids`). A `.pory`
    # stub is all the loader looks at.
    scripts_dir = build_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / f"Map{map_id:03d}.pory").write_text("", encoding="utf-8")
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": "CHX", "maps": [map_id]}],
    }), encoding="utf-8")
    return build_dir, chapters_path


def test_golden_single_page_text_row(tmp_path: Path) -> None:
    """A single text-only page produces the exact expected row."""
    events = [{
        "id": 1, "name": "Sign", "x": 3, "y": 4,
        "pages": [_page([_cmd(101, ["Hello"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 7, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert len(rows) == 1
    row = rows[0]
    assert row.row_id == page_row_id(7, 1, 0)
    assert row.kind == "page"
    assert row.map_id == 7
    assert row.effects == ("text",)
    assert row.script_heads == ()
    assert row.unrecognized_heads == ()
    assert row.other_codes == ()
    assert row.requires == ()
    assert row.unhandled == 0
    assert row.script_typed_conditions == 0
    assert row.event_id == 1
    assert row.event_name == "Sign"
    assert row.page_idx == 0
    assert row.condition.is_unconditional
    assert row.trigger == "action"
    assert row.may_be_cosmetic is False  # a sign you press A on (#43(b))
    assert row.is_dispositionable is True


def test_unrecognized_script_head_blocks_disposition(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Mystery", "x": 0, "y": 0,
        "pages": [_page([_cmd(355, ["pbTotallyMadeUpThing(1)"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 8, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert len(rows) == 1
    row = rows[0]
    assert row.script_heads == ("pbTotallyMadeUpThing",)
    assert row.unrecognized_heads == ("pbTotallyMadeUpThing",)
    assert row.is_dispositionable is False


def test_unrecognized_command_code_lands_in_other_codes(tmp_path: Path) -> None:
    """Code 999 has no dispatch rule and must not be silently dropped."""
    events = [{
        "id": 1, "name": "Weird", "x": 0, "y": 0,
        "pages": [_page([_cmd(999, ["whatever"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 9, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert len(rows) == 1
    row = rows[0]
    assert row.other_codes == (999,)
    assert row.effects == ()
    assert row.is_dispositionable is False


def test_assignment_head_uses_rhs_not_lhs(tmp_path: Path) -> None:
    """`trainer = createPhoneTrainer(...)` yields head `createPhoneTrainer`,
    not the bogus `trainer` (the assigned local variable name)."""
    events = [{
        "id": 3, "name": "Hiker", "x": 0, "y": 0,
        "pages": [_page([_cmd(
            355, ['trainer = createPhoneTrainer(PBTrainers::HIKER,"Larrie",0)'])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 35, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.script_heads == ("createPhoneTrainer",)
    assert row.unrecognized_heads == ()
    assert row.is_dispositionable is True


def test_plain_call_head_still_recognized(tmp_path: Path) -> None:
    """A plain (non-assignment) call line is unaffected by the assignment fix."""
    events = [{
        "id": 1, "name": "Heal", "x": 0, "y": 0,
        "pages": [_page([_cmd(355, ["pbHealAll(1,2)"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 16, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.script_heads == ("pbHealAll",)
    assert row.effects == ("heal",)


@pytest.mark.parametrize(
    "head, call, expected_effects",
    [
        ("pbSetSelfSwitch", "pbSetSelfSwitch(1,2,'A',true)", ("self_switch_write",)),
        ("pbCallBub", "pbCallBub(1,'hi')", ("bubble_ui",)),
        ("pbEraseThisEvent", "pbEraseThisEvent", ("erase_event",)),
        ("setTempSwitchOn", "setTempSwitchOn(1)", ("temp_switch_write",)),
        ("get_character", "get_character(-1)", ()),
    ],
)
def test_newly_recognized_heads_produce_expected_effects(
    tmp_path: Path, head: str, call: str, expected_effects: tuple[str, ...]
) -> None:
    events = [{
        "id": 1, "name": "X", "x": 0, "y": 0,
        "pages": [_page([_cmd(355, [call])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 17, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.script_heads == (head,)
    assert row.unrecognized_heads == (), f"{head} should be recognized via MECHANIC_BY_HEAD"
    assert row.effects == expected_effects


@pytest.mark.parametrize("code", [106, 108, 413])
def test_newly_ignored_codes_do_not_land_in_other_codes(tmp_path: Path, code: int) -> None:
    events = [{
        "id": 1, "name": "X", "x": 0, "y": 0,
        "pages": [_page([_cmd(code, [])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 18, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.other_codes == ()
    assert row.effects == ()


@pytest.mark.parametrize(
    "code, expected_tag",
    [(204, "graphic"), (208, "graphic"), (207, "animation"), (223, "screen_fx")],
)
def test_newly_mapped_codes_produce_expected_tag(
    tmp_path: Path, code: int, expected_tag: str
) -> None:
    events = [{
        "id": 1, "name": "X", "x": 0, "y": 0,
        "pages": [_page([_cmd(code, [])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 19, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.other_codes == ()
    assert row.effects == (expected_tag,)


@pytest.mark.parametrize("code", [112, 113, 115])
def test_control_flow_codes_block_cosmetic(tmp_path: Path, code: int) -> None:
    events = [{
        "id": 1, "name": "X", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["hi"]), _cmd(code, [])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 20, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert "control_flow" in row.effects
    assert row.may_be_cosmetic is False


def test_state_writing_tag_blocks_cosmetic(tmp_path: Path) -> None:
    """A `pbReceiveItem` giveitem row cannot be dispositioned cosmetic."""
    events = [{
        "id": 1, "name": "Chest", "x": 0, "y": 0,
        "pages": [_page([_cmd(355, ["Kernel.pbReceiveItem(::PBItems::POTION,1)"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 10, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.effects == ("giveitem",)
    assert row.may_be_cosmetic is False


def test_text_only_page_may_be_cosmetic(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "NPC", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["Hi there"]), _cmd(401, ["how are you"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 11, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.effects == ("text",)
    # #43(b): a talk NPC the player presses A on is observable, not decoration.
    assert row.may_be_cosmetic is False


def test_cosmetic_follows_observability_not_state_writes(tmp_path: Path) -> None:
    """#43(b), per trigger: a triggered page with any effect is observable; an
    empty triggered page and an untriggered text page stay eligible."""
    events = [
        {"id": 1, "name": "Touch", "x": 0, "y": 0,
         "pages": [_page([_cmd(101, ["Hi"])], trigger=1)]},
        {"id": 2, "name": "Empty", "x": 1, "y": 0, "pages": [_page([])]},
        {"id": 3, "name": "Ambient", "x": 2, "y": 0,
         "pages": [_page([_cmd(101, ["Hi"])], trigger=4)]},
    ]
    build_dir, chapters_path = _setup_chapter(tmp_path, 12, events)

    rows = {r.event_name: r for r in generate_chapter_manifest(
        "CHX", build_dir=build_dir, chapters_path=chapters_path)}

    assert rows["Touch"].may_be_cosmetic is False
    assert rows["Empty"].may_be_cosmetic is True
    assert rows["Ambient"].may_be_cosmetic is True


def test_unhandled_join_vetoes_cosmetic(tmp_path: Path) -> None:
    """A page joining an unhandled-queue entry may not be dispositioned cosmetic,
    even though its own effects would otherwise be cosmetic-safe."""
    events = [{
        "id": 2, "name": "NPC", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["Hi"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 12, events)
    (build_dir / "transpile_unhandled.jsonl").write_text(
        json.dumps({
            "map_id": 12, "event_id": 2, "event_name": "NPC", "page": 0,
            "line": 0, "command_code": 355, "description": "x", "reason": "x",
        }) + "\n",
        encoding="utf-8",
    )

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    row = rows[0]
    assert row.unhandled == 1
    assert row.may_be_cosmetic is False


def test_seam_rows_emitted_for_both_directions(tmp_path: Path) -> None:
    """A connection touching two chapter maps emits one seam row per side."""
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    _write_map(build_dir / "maps" / "Map001.json", 1, [])
    _write_map(build_dir / "maps" / "Map002.json", 2, [])
    (build_dir / "connections.json").write_text(
        json.dumps([[1, "E", 5, 2, "W", 0]]), encoding="utf-8")
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": "CHX", "maps": [1, 2]}],
    }), encoding="utf-8")

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    seam_rows = [r for r in rows if r.kind == "seam"]
    assert len(seam_rows) == 2
    ids = {r.row_id for r in seam_rows}
    assert ids == {seam_row_id(1, "E", 2), seam_row_id(2, "W", 1)}
    for row in seam_rows:
        assert row.effects == ("warp",)
        assert row.may_be_cosmetic is False


def test_seam_row_only_one_side_in_chapter(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    _write_map(build_dir / "maps" / "Map001.json", 1, [])
    (build_dir / "connections.json").write_text(
        json.dumps([[1, "E", 5, 99, "W", 0]]), encoding="utf-8")
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": "CHX", "maps": [1]}],
    }), encoding="utf-8")

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    seam_rows = [r for r in rows if r.kind == "seam"]
    assert len(seam_rows) == 1
    assert seam_rows[0].row_id == seam_row_id(1, "E", 99)


def test_generator_never_filters_conditional_pages(tmp_path: Path) -> None:
    """A page gated on a switch that can never be true in isolation is still
    emitted — the generator makes no satisfiability judgment (Q2ii)."""
    events = [{
        "id": 1, "name": "Gated", "x": 0, "y": 0,
        "pages": [
            _page([_cmd(101, ["a"])]),
            _page([_cmd(101, ["b"])], condition={"switch1_valid": True, "switch1_id": 999}),
        ],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 13, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert len(rows) == 2
    gated = rows[1]
    assert gated.condition.switch1_id == 999
    assert not gated.condition.is_unconditional


# --- branch-arm rows (REDERIVATION_PLAN.md §16.3 C1) ----------------------


def test_conditional_branch_without_else_yields_two_arm_rows(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Trainer", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(111, [12, "Kernel.pbTrainerBattle(1)"]),
            _cmd(101, ["You win!"], indent=1),
            _cmd(412, [], indent=0),
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 60, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    page_row = next(r for r in rows if r.kind == "page")
    branches = sorted(
        (r for r in rows if r.kind == "branch"), key=lambda r: r.branch.arm_index)
    assert len(branches) == 2
    then_row, else_row = branches
    assert then_row.row_id == branch_row_id(page_row.row_id, 0)
    assert else_row.row_id == branch_row_id(page_row.row_id, 1)
    assert then_row.parent_row_id == page_row.row_id
    assert else_row.parent_row_id == page_row.row_id

    assert then_row.branch.arm_kind == "then"
    assert then_row.branch.explicit is True
    assert then_row.branch.opener_code == 111
    assert then_row.branch.condition_type == 12
    assert then_row.branch.condition_text == "Kernel.pbTrainerBattle(1)"
    assert then_row.effects == ("text",)

    assert else_row.branch.arm_kind == "else"
    assert else_row.branch.explicit is False  # synthesized: no 411 in source
    assert else_row.branch.condition_type == 12
    assert else_row.branch.condition_text == "Kernel.pbTrainerBattle(1)"
    assert else_row.effects == ()

    # The condition text (on the opener, in the enclosing scope) counts
    # toward the PAGE row, per trunk-only extraction (C1b) -- not either arm.
    assert page_row.script_heads == ("pbTrainerBattle",)
    assert then_row.script_heads == ()
    assert else_row.script_heads == ()


def test_page_without_arms_keeps_its_pre_c1_hash(tmp_path: Path) -> None:
    """R5 invalidates hashes on branching pages only: a page with no arms is
    its own trunk, so its hash must be exactly `content_hash(page)`."""
    page = _page([_cmd(101, ["Hello"])])
    events = [{"id": 1, "name": "Sign", "x": 0, "y": 0, "pages": [page]}]
    build_dir, chapters_path = _setup_chapter(tmp_path, 62, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert [r.kind for r in rows] == ["page"]
    assert rows[0].content_hash == content_hash(page)


def test_arm_hash_tracks_its_condition_not_just_its_body(tmp_path: Path) -> None:
    """A decision on the then-arm of `pbTrainerBattle(1)` must go stale when
    the condition becomes `pbTrainerBattle(2)`, even with the body untouched."""
    def arms(condition: str) -> dict[str, str]:
        events = [{
            "id": 1, "name": "Trainer", "x": 0, "y": 0,
            "pages": [_page([
                _cmd(111, [12, condition]),
                _cmd(101, ["You win!"], indent=1),
                _cmd(412, [], indent=0),
            ])],
        }]
        root = tmp_path / condition.replace("(", "_").replace(")", "")
        root.mkdir()
        build_dir, chapters_path = _setup_chapter(root, 63, events)
        rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)
        return {r.row_id: r.content_hash for r in rows if r.kind == "branch"}

    first = arms("pbTrainerBattle(1)")
    second = arms("pbTrainerBattle(2)")
    assert first.keys() == second.keys()
    assert all(first[rid] != second[rid] for rid in first)


def test_whole_page_views_fold_arms_back_into_their_page(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Nested", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(111, [12, "pbTrainerBattle(1)"]),
            _cmd(111, [12, "pbCallBub(1)"], indent=1),
            _cmd(201, [0, 5, 1, 1, 2, 0], indent=2),
            _cmd(412, [], indent=1),
            _cmd(412, [], indent=0),
        ], trigger=3)],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 64, events)
    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)
    page = next(r for r in rows if r.kind == "page")

    view = whole_page_views(rows)[page.row_id]

    assert "warp" not in page.effects
    assert "warp" in view.effects
    assert view.script_heads == ("pbCallBub", "pbTrainerBattle")
    assert view.script_typed_conditions == 2
    assert (view.row_id, view.content_hash) == (page.row_id, page.content_hash)


def test_conditional_branch_with_else_both_arms_explicit(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Gate", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(111, [0, 1, 0]),
            _cmd(101, ["Open"], indent=1),
            _cmd(411, [], indent=0),
            _cmd(101, ["Closed"], indent=1),
            _cmd(412, [], indent=0),
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 61, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    branches = sorted(
        (r for r in rows if r.kind == "branch"), key=lambda r: r.branch.arm_index)
    assert len(branches) == 2
    then_row, else_row = branches
    assert then_row.branch.explicit is True
    assert else_row.branch.explicit is True
    assert then_row.effects == ("text",)
    assert else_row.effects == ("text",)


def test_show_choices_three_arms_and_no_cancel(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Menu", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(102, [["A", "B", "C"], 3]),
            _cmd(402, [0, "A"], indent=0),
            _cmd(101, ["chose A"], indent=1),
            _cmd(402, [1, "B"], indent=0),
            _cmd(101, ["chose B"], indent=1),
            _cmd(402, [2, "C"], indent=0),
            _cmd(101, ["chose C"], indent=1),
            _cmd(404, [], indent=0),
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 62, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    page_row = next(r for r in rows if r.kind == "page")
    branches = sorted(
        (r for r in rows if r.kind == "branch"), key=lambda r: r.branch.arm_index)
    assert len(branches) == 3
    assert [b.branch.choice_index for b in branches] == [0, 1, 2]
    assert [b.branch.choice_text for b in branches] == ["A", "B", "C"]
    assert all(b.branch.arm_kind == "choice" for b in branches)
    assert all(b.branch.opener_code == 102 for b in branches)
    assert all(b.parent_row_id == page_row.row_id for b in branches)
    for i, b in enumerate(branches):
        assert b.row_id == branch_row_id(page_row.row_id, i)
    assert [b.effects for b in branches] == [("text",)] * 3
    # No cancel arm (403) present in this fixture -- none synthesized either.
    assert not any(b.branch.arm_kind == "cancel" for b in branches)


def test_nested_conditional_inside_choice_arm_no_double_count(tmp_path: Path) -> None:
    """A 111 nested inside a choice arm contributes its condition to that
    arm's row (not the page trunk), and its own two arms become separate
    child rows with the choice arm as their `parent_row_id`. No effect is
    counted on more than one row."""
    events = [{
        "id": 1, "name": "Menu", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(102, [["Yes", "No"], 2]),
            _cmd(402, [0, "Yes"], indent=0),
            _cmd(111, [12, "Kernel.pbTrainerBattle(1)"], indent=1),
            _cmd(101, ["fight"], indent=2),
            _cmd(412, [], indent=1),
            _cmd(402, [1, "No"], indent=0),
            _cmd(101, ["never mind"], indent=1),
            _cmd(404, [], indent=0),
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 63, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    page_row = next(r for r in rows if r.kind == "page")
    by_id = {r.row_id: r for r in rows if r.kind == "branch"}
    assert len(by_id) == 4  # "Yes" choice, "No" choice, nested then, nested else

    yes_row = next(r for r in by_id.values()
                   if r.branch.arm_kind == "choice" and r.branch.choice_text == "Yes")
    no_row = next(r for r in by_id.values()
                  if r.branch.arm_kind == "choice" and r.branch.choice_text == "No")
    nested = [r for r in by_id.values() if r.parent_row_id == yes_row.row_id]
    assert len(nested) == 2  # the nested 111's then/else

    # The page trunk has no script heads at all -- pbTrainerBattle lives on
    # the "Yes" choice arm's own condition, not the page.
    assert page_row.script_heads == ()
    assert yes_row.script_heads == ("pbTrainerBattle",)
    assert no_row.effects == ("text",)

    nested_then = next(r for r in nested if r.branch.arm_kind == "then")
    nested_else = next(r for r in nested if r.branch.arm_kind == "else")
    assert nested_then.effects == ("text",)
    assert nested_else.effects == ()
    assert nested_then.branch.opener_code == 111
    assert nested_then.parent_row_id == yes_row.row_id
    assert nested_else.branch.explicit is False

    # No head/effect appears on more than one row.
    assert "pbTrainerBattle" not in no_row.script_heads
    assert "pbTrainerBattle" not in nested_then.script_heads


def test_loop_body_counted_in_enclosing_scope_not_a_branch(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Loopy", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(112, [], indent=0),
            _cmd(101, ["spin"], indent=1),
            _cmd(113, [], indent=1),  # break loop
            _cmd(413, [], indent=0),  # repeat above
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 64, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert len([r for r in rows if r.kind == "branch"]) == 0
    page_row = next(r for r in rows if r.kind == "page")
    assert "text" in page_row.effects
    assert "control_flow" in page_row.effects  # 112/113


def test_trunk_hash_changes_when_arm_added_not_when_arm_content_changes(
    tmp_path: Path,
) -> None:
    def _rows(commands: list[dict]) -> list:
        events = [{
            "id": 1, "name": "X", "x": 0, "y": 0,
            "pages": [_page(commands)],
        }]
        build_dir, chapters_path = _setup_chapter(tmp_path / "run", 65, events)
        return generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    import shutil

    base_cmds = [
        _cmd(111, [0, 1, 0]),
        _cmd(101, ["a"], indent=1),
        _cmd(412, [], indent=0),
    ]
    rows1 = _rows(base_cmds)
    page1 = next(r for r in rows1 if r.kind == "page")
    then1 = next(r for r in rows1 if r.kind == "branch" and r.branch.arm_kind == "then")

    shutil.rmtree(tmp_path / "run")

    # Change ONLY the then-arm's content -- trunk hash must not move.
    changed_arm_cmds = [
        _cmd(111, [0, 1, 0]),
        _cmd(101, ["a different line entirely"], indent=1),
        _cmd(412, [], indent=0),
    ]
    rows2 = _rows(changed_arm_cmds)
    page2 = next(r for r in rows2 if r.kind == "page")
    then2 = next(r for r in rows2 if r.kind == "branch" and r.branch.arm_kind == "then")

    assert page1.content_hash == page2.content_hash
    assert then1.content_hash != then2.content_hash

    shutil.rmtree(tmp_path / "run")

    # Add a second 111 -- trunk hash (skeleton) must move.
    added_arm_cmds = base_cmds + [
        _cmd(111, [0, 2, 0]),
        _cmd(101, ["b"], indent=1),
        _cmd(412, [], indent=0),
    ]
    rows3 = _rows(added_arm_cmds)
    page3 = next(r for r in rows3 if r.kind == "page")
    assert page3.content_hash != page1.content_hash


def test_branch_generation_is_idempotent(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Menu", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(102, [["A", "B"], 2]),
            _cmd(402, [0, "A"], indent=0),
            _cmd(111, [12, "pbSomeCheck(1)"], indent=1),
            _cmd(101, ["fight"], indent=2),
            _cmd(412, [], indent=1),
            _cmd(402, [1, "B"], indent=0),
            _cmd(101, ["never mind"], indent=1),
            _cmd(404, [], indent=0),
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 66, events)

    rows1 = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)
    rows2 = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)
    assert rows1 == rows2

    out1 = tmp_path / "m1.json"
    out2 = tmp_path / "m2.json"
    write_manifest(rows1, out1)
    write_manifest(rows2, out2)
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    from rpg2gba.chapter_manifest.schema import row_id_sort_key

    payload = json.loads(out1.read_text(encoding="utf-8"))
    row_ids = [entry["row_id"] for entry in payload]
    assert row_ids == sorted(row_ids, key=row_id_sort_key)


# --- staged-map detection (_load_staged_map_ids) --------------------------


def test_load_staged_map_ids_parses_pory_filenames(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "Map019.pory").write_text("", encoding="utf-8")
    (scripts_dir / "Map035.pory").write_text("", encoding="utf-8")
    (scripts_dir / "CommonEvents.pory").write_text("", encoding="utf-8")
    (scripts_dir / "Map019.template_fields.json").write_text("{}", encoding="utf-8")

    staged = generator._load_staged_map_ids(scripts_dir)

    assert staged == {19, 35}


def test_load_staged_map_ids_absent_dir_returns_empty_and_does_not_crash(
    tmp_path: Path,
) -> None:
    staged = generator._load_staged_map_ids(tmp_path / "no-such-scripts-dir")
    assert staged == set()


def test_unstaged_map_gets_none_unhandled_staged_map_gets_int(tmp_path: Path) -> None:
    """A page on an unstaged map cannot be measured against the transpile
    queue at all (`None`); a page on a staged map with no matching queue
    entry gets a real, measured `0`. The page is a parallel process so the
    observability rule (#43(b)) does not also veto `cosmetic` here."""
    events = [{
        "id": 1, "name": "NPC", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["Hi"])], trigger=4)],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 21, events)
    # _setup_chapter stages map 21; unstage it for this test.
    (build_dir / "scripts" / "Map021.pory").unlink()

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)
    assert rows[0].unhandled is None
    assert rows[0].may_be_cosmetic is False

    (build_dir / "scripts" / "Map021.pory").write_text("", encoding="utf-8")
    rows2 = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)
    assert rows2[0].unhandled == 0
    assert rows2[0].may_be_cosmetic is True


# --- diagonal-stair absorption into terrain rows ---------------------------


def _stair_page(move_codes: list[int]) -> dict:
    """A minimal player-touch stair page: a code-111 branch on the player's
    facing direction (condition kind 6, character -1), then a move-route
    command (209) targeting the player (-1) whose embedded route contains
    the given diagonal move codes. Shape matches `stairs._page_qualifies`/
    `_page_move_codes`."""
    return _page([
        _cmd(111, [6, -1, 0, 0]),
        _cmd(209, [-1, {"list": [{"code": c} for c in move_codes]}]),
    ], trigger=1)


def test_stair_event_absorbed_into_terrain_row_no_page_row(tmp_path: Path) -> None:
    """A diagonal-stair event (NW/SE axis -> RIGHT side) is skipped entirely
    as a page row and instead produces exactly one terrain row -- while a
    normal event on the same map is untouched."""
    events = [
        {
            "id": 6, "name": "Stairs", "x": 5, "y": 9,
            "pages": [_stair_page([7, 6])],  # NW, SE -> RIGHT side
        },
        {
            "id": 7, "name": "Sign", "x": 0, "y": 0,
            "pages": [_page([_cmd(101, ["Hello"])])],
        },
    ]
    build_dir, chapters_path = _setup_chapter(tmp_path, 37, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    page_rows = [r for r in rows if r.kind == "page"]
    terrain_rows = [r for r in rows if r.kind == "terrain"]

    assert all(r.event_id != 6 for r in page_rows), "stair event must not get a page row"
    assert {r.event_id for r in page_rows} == {7}

    assert len(terrain_rows) == 1
    terrain_row = terrain_rows[0]
    assert terrain_row.terrain.x == 5
    assert terrain_row.terrain.y == 9
    assert terrain_row.terrain.behavior == "MB_SIDEWAYS_STAIRS_RIGHT_SIDE"
    assert terrain_row.terrain.source_event_id == 6
    assert terrain_row.may_be_cosmetic is False
    assert terrain_row.unhandled is None


def test_idempotence(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "NPC", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(101, ["Hi"]),
            _cmd(355, ["Kernel.pbReceiveItem(::PBItems::POTION,1)"]),
            _cmd(121, [1, 1, 0]),
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 14, events)

    rows1 = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)
    rows2 = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert rows1 == rows2

    out1 = tmp_path / "manifest1.json"
    out2 = tmp_path / "manifest2.json"
    write_manifest(rows1, out1)
    write_manifest(rows2, out2)
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
    assert out1.read_text(encoding="utf-8").endswith("\n")


def test_write_manifest_sorted_by_row_id(tmp_path: Path) -> None:
    events = [{
        "id": 5, "name": "B", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["x"])]), _page([_cmd(101, ["y"])])],
    }, {
        "id": 2, "name": "A", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["z"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 15, events)
    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    out = tmp_path / "manifest.json"
    write_manifest(rows, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    row_ids = [r["row_id"] for r in payload]
    assert row_ids == sorted(row_ids)


# --- reachability-derived requires (second `requires[]` source) ----------
#
# `_CHAPTER_MAP_START_CELLS` only holds real, verified start cells (currently
# just CH04/map035), so these tests monkeypatch it with a synthetic
# (chapter, map) start cell rather than fighting real map geometry -- the
# wiring being tested is generic over the table's contents.


def _write_traversable_map(
    path: Path, map_id: int, width: int, height: int, events: list[dict],
    wall_cells: set[tuple[int, int]],
) -> None:
    """A minimal map with a full "tiles" block so `traversal.graph`/
    `traversal.capabilities` can build a real `MapGraph`/`CapabilityMap` from
    it: tile id 1 (passable) everywhere except `wall_cells` (tile id 2,
    blocked)."""
    layer0 = [
        2 if (x, y) in wall_cells else 1
        for y in range(height) for x in range(width)
    ]
    empty_layer = [0] * (width * height)
    payload = {
        "map_id": map_id,
        "tileset_id": 1,
        "width": width,
        "height": height,
        "tiles": {"xsize": width, "ysize": height, "zsize": 3,
                  "data": layer0 + empty_layer + empty_layer},
        "events": events,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_tilesets(path: Path) -> None:
    # passage 0 = passable, 0x0F = fully blocked (tile_map.PASSAGE_BLOCK_MASK).
    path.write_text(json.dumps({
        "1": {"passages": [0, 0, 0x0F], "priorities": [0, 0, 0], "terrain_tags": [0, 0, 0]},
    }), encoding="utf-8")


def _setup_reachability_chapter(
    tmp_path: Path, chapter_id: str, map_id: int, width: int, height: int,
    events: list[dict], wall_cells: set[tuple[int, int]],
) -> tuple[Path, Path]:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    _write_traversable_map(
        build_dir / "maps" / f"Map{map_id:03d}.json", map_id, width, height, events, wall_cells)
    _write_tilesets(build_dir / "tilesets.json")
    (build_dir / "connections.json").write_text("[]", encoding="utf-8")
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": chapter_id, "maps": [map_id]}],
    }), encoding="utf-8")
    return build_dir, chapters_path


def _rock_and_sign_events() -> list[dict]:
    """A 3x3 pocket: start (1,0), a rock (event 1) at the only chokepoint
    (1,1), walls at (0,1)/(2,1), and a plain sign (event 2) at (1,2) reachable
    only by crossing the rock's cell."""
    return [
        {
            "id": 1, "name": "Rock", "x": 1, "y": 1,
            "pages": [_page([_cmd(355, ["Kernel.pbRockSmash(1)"])])],
        },
        {
            "id": 2, "name": "Sign", "x": 1, "y": 2,
            "pages": [_page([_cmd(101, ["Beyond the rock"])])],
        },
    ]


def test_reachability_requires_approach_gated_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A row with no gating script head of its own still picks up
    `rock_smash` in `requires` when its only approach crosses a rock-obstacle
    cell -- the 24-row (approach-gated) half of the CH04 split."""
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHR", 99), frozenset({(1, 0)}))
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})

    rows = generate_chapter_manifest("CHR", build_dir=build_dir, chapters_path=chapters_path)

    sign_row = next(r for r in rows if r.event_id == 2)
    assert sign_row.requires == ("rock_smash",)
    assert sign_row.script_heads == ()  # no head of its own -- reachability only
    assert sign_row.reachability_consulted is True


def test_reachability_requires_does_not_duplicate_head_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rock event's own row already gets `rock_smash` from `_HEAD_REQUIRES`
    (interaction-gated); its APPROACH is open (the start cell is adjacent to
    it), so the reachability source contributes nothing extra -- no duplicate,
    no spurious requirement."""
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHR", 99), frozenset({(1, 0)}))
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})

    rows = generate_chapter_manifest("CHR", build_dir=build_dir, chapters_path=chapters_path)

    rock_row = next(r for r in rows if r.event_id == 1)
    assert rock_row.requires == ("rock_smash",)


def test_reachability_requires_absent_without_verified_start_cell(tmp_path: Path) -> None:
    """No entry in `_CHAPTER_MAP_START_CELLS` for this (chapter, map) -- the
    generator degrades gracefully (empty reachability half) rather than
    raising, and `_HEAD_REQUIRES` alone still applies."""
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR_UNREGISTERED", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})

    rows = generate_chapter_manifest(
        "CHR_UNREGISTERED", build_dir=build_dir, chapters_path=chapters_path)

    sign_row = next(r for r in rows if r.event_id == 2)
    assert sign_row.requires == ()
    assert sign_row.reachability_consulted is False
    rock_row = next(r for r in rows if r.event_id == 1)
    assert rock_row.requires == ("rock_smash",)  # _HEAD_REQUIRES still applies
    assert rock_row.reachability_consulted is False


def test_reachability_requires_logs_narrowing_when_multiple_minimal_sets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`_reachability_requires` keeps only the smallest minimal set in the
    flat `requires` tuple (the manifest row schema doesn't change), but when
    `BlockedVerdict.minimal_sets` carries more than one independent
    alternative, dropping the rest must be visible in the build log rather
    than silent -- CLAUDE.md §4.5. Geometry: two disjoint corridors through
    row y=1 (a rock at x=1, water at x=3) both feed the fully-open row y=2,
    so either rock_smash alone or surf alone opens the approach to the event
    at (2, 2) -- the same shape as
    `test_two_independent_alternative_routes_yield_two_minimal_sets` in
    `test_traversal_reachability.py`."""
    from rpg2gba.traversal.capabilities import Capability, CapabilityMap, Obstacle
    from rpg2gba.traversal.graph import MapGraph

    walls = {(0, 1), (2, 1), (3, 1), (4, 1)}
    graph = MapGraph(
        map_id=1, width=5, height=3, tileset_id=0,
        blocked={(x, y): (x, y) in walls for x in range(5) for y in range(3)},
    )
    capability_map = CapabilityMap(map_id=1, obstacles={
        (1, 1): Obstacle(cell=(1, 1), capability=Capability.ROCK_SMASH,
                          source="event", detail="1:Rock", event_id=1),
        (3, 1): Obstacle(cell=(3, 1), capability=Capability.SURF,
                          source="terrain", detail="7", event_id=None),
    })
    context = (graph, capability_map, frozenset({(0, 0)}))

    with caplog.at_level("WARNING", logger="rpg2gba.chapter_manifest.generator"):
        requires = generator._reachability_requires(context, (2, 2))

    assert requires == ("rock_smash",)
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "(2, 2)" in message
    assert "rock_smash" in message
    assert "surf" in message


def test_reachability_consulted_propagates_to_seam_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seam rows carry the same per-map fact as page rows on that map --
    there is no separate per-map metadata structure, so the flag lives on
    every row sharing a `map_id`, seams included."""
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHR", 99), frozenset({(1, 0)}))
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})
    (build_dir / "connections.json").write_text(
        json.dumps([[99, "E", 0, 100, "W", 0]]), encoding="utf-8")

    rows = generate_chapter_manifest("CHR", build_dir=build_dir, chapters_path=chapters_path)

    seam_row = next(r for r in rows if r.kind == "seam")
    assert seam_row.map_id == 99
    assert seam_row.reachability_consulted is True


def test_unverified_start_cell_warns_with_actionable_message(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An unregistered (chapter, map) pair is a visible WARNING, not a
    DEBUG-level whisper -- an unconsulted map must not be indistinguishable
    from "no capability gates here"."""
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR_LOUD", 42, 3, 3, events, wall_cells={(0, 1), (2, 1)})

    with caplog.at_level("WARNING", logger="rpg2gba.chapter_manifest.generator"):
        generate_chapter_manifest("CHR_LOUD", build_dir=build_dir, chapters_path=chapters_path)

    warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "verified start cell" in r.getMessage()
    ]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "not consulted" in message.lower() or "NOT consulted" in message
    assert "surf" in message and "waterfall" in message
    assert "_HEAD_REQUIRES" in message


# --- GraphApproachModel (concrete checker.ApproachModel) -----------------


def test_approach_model_true_when_start_itself_is_an_approach_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rock's own approach cell set includes (1,0), the start cell
    itself -- trivially reachable with nothing held, so `reachable_now` is
    True even though the rock is an uncleared rock_smash obstacle."""
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHR", 99), frozenset({(1, 0)}))
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})

    model = GraphApproachModel(
        "CHR", maps_dir=build_dir / "maps", tilesets_json=build_dir / "tilesets.json")
    rows = generate_chapter_manifest("CHR", build_dir=build_dir, chapters_path=chapters_path)

    rock_row = next(r for r in rows if r.event_id == 1)
    assert model.has_walkable_approach(rock_row) is True


def test_approach_model_closes_the_sibling_obstacle_blind_spot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prior version of this model asked a purely LOCAL collision question
    and answered True here: the sign's north neighbour (1,1) is
    collision-open floor, so a plain walkability read cannot see that a
    rock event occupies it. The reachability-from-entry version closes that
    blind spot: (1,1) is the only way from the start (1,0) into row y=2 (the
    walls at (0,1)/(2,1) seal the other columns), (1,1) is an uncleared
    rock_smash obstacle, and nothing is held -- so the sign has NO reachable
    approach cell right now. Verified empirically, not assumed: this fixture
    is exactly the shape that exposed the old bug."""
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHR", 99), frozenset({(1, 0)}))
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})

    model = GraphApproachModel(
        "CHR", maps_dir=build_dir / "maps", tilesets_json=build_dir / "tilesets.json")
    rows = generate_chapter_manifest("CHR", build_dir=build_dir, chapters_path=chapters_path)

    sign_row = next(r for r in rows if r.event_id == 2)
    assert model.has_walkable_approach(sign_row) is False


def test_approach_model_none_for_seam_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHR", 99), frozenset({(1, 0)}))
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})
    (build_dir / "connections.json").write_text(
        json.dumps([[99, "E", 0, 100, "W", 0]]), encoding="utf-8")

    model = GraphApproachModel(
        "CHR", maps_dir=build_dir / "maps", tilesets_json=build_dir / "tilesets.json")
    rows = generate_chapter_manifest("CHR", build_dir=build_dir, chapters_path=chapters_path)

    seam_row = next(r for r in rows if r.kind == "seam")
    assert model.has_walkable_approach(seam_row) is None


def test_approach_model_none_for_unregistered_map(tmp_path: Path) -> None:
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR_UNREGISTERED", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})

    model = GraphApproachModel(
        "CHR_UNREGISTERED", maps_dir=build_dir / "maps", tilesets_json=build_dir / "tilesets.json")
    rows = generate_chapter_manifest(
        "CHR_UNREGISTERED", build_dir=build_dir, chapters_path=chapters_path)

    rock_row = next(r for r in rows if r.event_id == 1)
    assert model.has_walkable_approach(rock_row) is None


def test_approach_model_none_for_vanished_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row whose event no longer exists in the decoded map data (deleted,
    renumbered) cannot be answered, not silently answered False."""
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHR", 99), frozenset({(1, 0)}))
    events = _rock_and_sign_events()
    build_dir, chapters_path = _setup_reachability_chapter(
        tmp_path, "CHR", 99, 3, 3, events, wall_cells={(0, 1), (2, 1)})
    rows = generate_chapter_manifest("CHR", build_dir=build_dir, chapters_path=chapters_path)
    rock_row = next(r for r in rows if r.event_id == 1)

    # Now remove the event from the decoded map data, simulating drift.
    _write_traversable_map(
        build_dir / "maps" / "Map099.json", 99, 3, 3,
        [e for e in events if e["id"] != 1], wall_cells={(0, 1), (2, 1)})

    model = GraphApproachModel(
        "CHR", maps_dir=build_dir / "maps", tilesets_json=build_dir / "tilesets.json")
    assert model.has_walkable_approach(rock_row) is None


# --- map 32 (Moki Town) corpus regression fixture -----------------------


_needs_map32 = pytest.mark.skipif(
    not (OUT_DIR / "maps" / "Map032.json").exists(),
    reason="output/uranium-build/maps/Map032.json not present",
)


def _map32_rows():
    rows = generate_chapter_manifest(
        "CH01", build_dir=OUT_DIR, chapters_path=CHAPTERS_PATH)
    return [r for r in rows if r.map_id == 32]


def _map32_raw_head_blocks() -> Counter:
    """Recomputes script-head frequency as independent *blocks* (a 355 command
    plus any immediately-following 655 continuations), across every page of
    map 32 — the same unit `generator._extract_scripts` produces, but tallied
    globally rather than deduplicated per page/row. This is the methodology
    that reproduces the document's Part 6.3 table: a head occurring twice on
    one page (map 32's boulder events call `pbEraseThisEvent` once per branch
    arm) counts twice here, where `ManifestRow.script_heads` — a per-row set,
    correct for its own dispositioning purpose — would only count it once.
    """
    data = json.loads((OUT_DIR / "maps" / "Map032.json").read_text(encoding="utf-8"))
    counts: Counter = Counter()
    for event in data["events"]:
        for page in event["pages"]:
            commands = page.get("list") or []
            for block in _extract_scripts(commands):
                head = _script_head(block)
                if not head or head in RUBY_KEYWORDS:
                    continue
                counts[head] += 1
            # Script-typed (params[0] == 12) code-111 conditionals also carry
            # a head, in `parameters[1]`, not inside a 355/655 block —
            # `pbRockSmash` and `isRockSmashSoftlocked` in the boulder chain
            # live here, as does `pbReceiveItem`'s gate on EV027/EV009.
            for cmd in commands:
                if cmd.get("code") != 111:
                    continue
                params = cmd.get("parameters") or []
                if (len(params) >= 2 and params[0] == COND_TYPE_SCRIPT
                        and isinstance(params[1], str)):
                    head = _script_head(params[1])
                    if not head or head in RUBY_KEYWORDS:
                        continue
                    counts[head] += 1
    return counts


@_needs_map32
def test_map32_event_and_page_counts() -> None:
    rows = _map32_rows()
    page_rows = [r for r in rows if r.kind == "page"]
    events = {r.event_id for r in page_rows}
    assert len(events) == 52
    assert len(page_rows) == 90


@_needs_map32
def test_map32_no_code_201_warp_to_59_but_seam_row_present() -> None:
    """The doc's §6.2 finding: map 32 -> Route 3 is an overland seam, not a
    code-201 warp event, and an event-only manifest would miss it entirely."""
    data = json.loads((OUT_DIR / "maps" / "Map032.json").read_text(encoding="utf-8"))
    for event in data["events"]:
        for page in event["pages"]:
            for cmd in page.get("list") or []:
                if cmd.get("code") == 201:
                    params = cmd.get("parameters") or []
                    assert not (len(params) >= 2 and params[1] == 59), (
                        "expected no code-201 warp from map 32 to map 59")

    rows = _map32_rows()
    seam_rows = [r for r in rows if r.kind == "seam"]
    assert seam_row_id(32, "E", 59) in {r.row_id for r in seam_rows}


@_needs_map32
def test_map32_boulder_events_page0_chain_and_page1_self_switch() -> None:
    """Events 14, 15, 33 are all named `Rock` with the documented page-0 chain
    (pbRockSmash -> pbRockSmashRandomEncounter -> isRockSmashSoftlocked ->
    pbEraseThisEvent) and a page-1 gated on self-switch A.

    Post-C1 (REDERIVATION_PLAN.md §16.3): page0's own top-level 111
    (`pbRockSmash`) is trunk, but the chain's other three heads live inside
    that 111's `then`/nested-`else` branch-arm rows, not on the page row
    itself -- trunk-only extraction means a page row's `script_heads` no
    longer merges its arms' content. This test now gathers heads across the
    page row AND every branch-arm row descending from it (row ids prefixed
    `<page_row_id>/b`), which is exactly the population C1b moved the heads
    into."""
    rows = _map32_rows()
    by_event: dict[int, list] = {}
    for row in rows:
        if row.kind == "page" and row.event_id in (14, 15, 33):
            by_event.setdefault(row.event_id, []).append(row)

    assert set(by_event) == {14, 15, 33}
    for event_id, event_rows in by_event.items():
        event_rows.sort(key=lambda r: r.page_idx)
        assert len(event_rows) == 2
        page0, page1 = event_rows
        assert page0.event_name == "Rock"
        branch_rows = [
            r for r in rows
            if r.kind == "branch" and r.row_id.startswith(page0.row_id + "/b")
        ]
        chain_heads = set(page0.script_heads)
        for br in branch_rows:
            chain_heads.update(br.script_heads)
        for head in ("pbRockSmash", "pbRockSmashRandomEncounter",
                     "isRockSmashSoftlocked", "pbEraseThisEvent"):
            assert head in chain_heads, (
                f"event {event_id} page0's trunk+arms missing expected head {head}")
        assert page1.condition.self_switch_ch == "A"
        assert page1.condition.is_unconditional is False


@_needs_map32
def test_map32_recognized_and_unrecognized_heads_match_document() -> None:
    """Table in PLAYTEST_AUTHORING_IMPROVEMENT.md §6.3: six of eleven heads
    found on map 32 are unrecognized against `MECHANIC_BY_HEAD`.

    Post-C1: heads that used to live on a page row alone can now live on a
    branch-arm row instead (trunk-only extraction), so both kinds are
    scanned -- the document's per-map head census is unaffected by WHICH
    row a head landed on, only by whether it was found at all."""
    rows = _map32_rows()
    all_unrecognized: set[str] = set()
    all_recognized: set[str] = set()
    for row in rows:
        if row.kind not in ("page", "branch"):
            continue
        all_unrecognized.update(row.unrecognized_heads)
        all_recognized.update(h for h in row.script_heads if h not in row.unrecognized_heads)

    # `isRockSmashSoftlocked` was the last unrecognized head here after the
    # CH04 resolution (2026-08-22). It became recognized 2026-09-13, once its
    # static strip (REDERIVATION_PLAN.md §15.1 item 2) got its missing
    # MECHANIC_BY_HEAD entry, so map 32 now has no unrecognized heads at all.
    expected_recognized = {
        "pbRockSmashRandomEncounter", "pbReceiveItem", "pbRockSmash",
        "pbCaveEntrance", "pbPhoneRegisterNPC",
        "pbCallBub", "get_character", "setTempSwitchOn",
        "pbEraseThisEvent", "pbSetSelfSwitch", "isRockSmashSoftlocked",
    }
    assert all_unrecognized == set()
    assert expected_recognized <= all_recognized
    assert all_recognized.isdisjoint(all_unrecognized)


@_needs_map32
def test_map32_script_head_block_frequencies_match_document() -> None:
    """The raw per-block frequency table from §6.3, reproduced independently
    of `ManifestRow` (see `_map32_raw_head_blocks`'s docstring for why the
    counting unit differs from `script_heads`)."""
    expected = {
        "pbCallBub": 41,
        "get_character": 8,
        "setTempSwitchOn": 8,
        "pbEraseThisEvent": 6,
        "pbRockSmashRandomEncounter": 6,
        "pbReceiveItem": 3,
        "pbRockSmash": 3,
        "isRockSmashSoftlocked": 3,
        "pbCaveEntrance": 3,
        "pbSetSelfSwitch": 3,
        "pbPhoneRegisterNPC": 1,
    }
    counts = _map32_raw_head_blocks()
    for head, expected_count in expected.items():
        assert counts[head] == expected_count, (
            f"{head}: expected {expected_count} blocks, generator found {counts[head]}")
