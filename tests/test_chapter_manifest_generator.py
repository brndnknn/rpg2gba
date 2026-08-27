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
from rpg2gba.chapter_manifest.generator import (
    _extract_scripts,
    generate_chapter_manifest,
    write_manifest,
)
from rpg2gba.chapter_manifest.schema import page_row_id, seam_row_id

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
    assert row.may_be_cosmetic is True
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
    assert row.may_be_cosmetic is True


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
    pbEraseThisEvent) and a page-1 gated on self-switch A."""
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
        for head in ("pbRockSmash", "pbRockSmashRandomEncounter",
                     "isRockSmashSoftlocked", "pbEraseThisEvent"):
            assert head in page0.script_heads, (
                f"event {event_id} page0 missing expected head {head}")
        assert page1.condition.self_switch_ch == "A"
        assert page1.condition.is_unconditional is False


@_needs_map32
def test_map32_recognized_and_unrecognized_heads_match_document() -> None:
    """Table in PLAYTEST_AUTHORING_IMPROVEMENT.md §6.3: six of eleven heads
    found on map 32 are unrecognized against `MECHANIC_BY_HEAD`."""
    rows = _map32_rows()
    all_unrecognized: set[str] = set()
    all_recognized: set[str] = set()
    for row in rows:
        if row.kind != "page":
            continue
        all_unrecognized.update(row.unrecognized_heads)
        all_recognized.update(h for h in row.script_heads if h not in row.unrecognized_heads)

    # `isRockSmashSoftlocked` remains unrecognized: it is not one of the six
    # gaps the CH04 resolution closed (2026-08-22).
    expected_unrecognized = {
        "isRockSmashSoftlocked",
    }
    expected_recognized = {
        "pbRockSmashRandomEncounter", "pbReceiveItem", "pbRockSmash",
        "pbCaveEntrance", "pbPhoneRegisterNPC",
        "pbCallBub", "get_character", "setTempSwitchOn",
        "pbEraseThisEvent", "pbSetSelfSwitch",
    }
    assert expected_unrecognized <= all_unrecognized
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
