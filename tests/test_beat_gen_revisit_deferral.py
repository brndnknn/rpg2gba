"""Re-offer deferred rows (operator ruling 2026-10-14): `beat_gen.seed.deferred_rows`
and `build_chapter_stories(deferred_for=...)`."""
from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.beat_gen.seed import deferred_loader, deferred_rows
from rpg2gba.chapter_manifest.schema import page_row_id
from rpg2gba.story_state.model import build_chapter_stories
from tests.test_chapter_manifest_generator import _cmd, _page
from tests.test_story_state_model import _event, _map, _write_metadata_header

TEMPLATE_MANIFEST = Path("reference/manifests/CH04.manifest.json")


# --- loader -------------------------------------------------------------


def _entry(template: dict, row_id: str, requires: list[str]) -> dict:
    return {**template, "row_id": row_id, "requires": requires, "parent_row_id": None}


def _write_loader_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    chapters = tmp_path / "chapters.json"
    chapters.write_text(json.dumps({
        "schema": 1,
        "acts": [{"id": "A1", "title": "Act 1", "chapters": ["CHA"]}],
        "chapters": [{"id": "CHA", "act": "A1", "title": "Alpha", "maps": [901]}],
    }), encoding="utf-8")
    template = json.loads(TEMPLATE_MANIFEST.read_text(encoding="utf-8"))[0]
    rows = [
        # ev003: capability-blocked, unclaimed, unlisted -> rule (b)
        _entry(template, "map901/ev003/p0", ["rock_smash"]),
        _entry(template, "map901/ev003/p0/b0", []),
        # ev004: capability-blocked but claimed by a beat -> not deferred
        _entry(template, "map901/ev004/p0", ["rock_smash"]),
        # ev005: capability-blocked but listed (refused) -> not deferred
        _entry(template, "map901/ev005/p0", ["rock_smash"]),
        # ev006: no requires, not listed -> not deferred
        _entry(template, "map901/ev006/p0", []),
        # ev001 page is bare-later; its branch follows the page
        _entry(template, "map901/ev001/p0", []),
        _entry(template, "map901/ev001/p0/b1", []),
    ]
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "CHA.manifest.json").write_text(json.dumps(rows), encoding="utf-8")
    module_dir = tmp_path / "gen"
    module_dir.mkdir()
    (module_dir / "cha.py").write_text(
        "from types import SimpleNamespace as NS\n"
        "CHAPTER = NS(beats=[NS(name='b', rows=['map901/ev004/p0'])])\n"
        "ELSEWHERE = {\n"
        "    'map901/ev001/p0': 'later',\n"
        "    'map901/ev002/p0': 'later: CH05: its event crosses out',\n"
        "    'map901/ev008/p0': 'unreachable',\n"
        "    'map901/ev009/p0': 'later: CH06',\n"
        "}\n"
        "REFUSED = {'map901/ev005/p0': 'x'}\n",
        encoding="utf-8")
    return chapters, manifest_dir, module_dir


def test_loader_rules_a_and_b_and_exclusions(tmp_path: Path) -> None:
    chapters, manifest_dir, module_dir = _write_loader_fixture(tmp_path)
    got = deferred_rows("CHA", module_dir, chapters_path=chapters, manifest_dir=manifest_dir)
    assert got == frozenset({
        "map901/ev001/p0", "map901/ev001/p0/b1",   # (a) + branch closure
        "map901/ev009/p0",                         # (a) owner-only `later: CHnn`
        "map901/ev003/p0", "map901/ev003/p0/b0",   # (b) + branch closure
    })
    assert "map901/ev002/p0" not in got  # boundary crossing: inbound mechanism's


def test_loader_fails_loud_without_module(tmp_path: Path) -> None:
    chapters, manifest_dir, module_dir = _write_loader_fixture(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="no generated module"):
        deferred_rows("CHZ", module_dir, chapters_path=chapters, manifest_dir=manifest_dir)


def test_loader_never_reads_the_chapter_being_generated(tmp_path: Path) -> None:
    _, _, module_dir = _write_loader_fixture(tmp_path)
    assert deferred_loader("CHA", module_dir)("CHA") == frozenset()


# --- story model --------------------------------------------------------

DEFERRED_ROW = page_row_id(901, 2, 0)
GATED_ROW = page_row_id(902, 1, 0)
LOCAL_ROW = page_row_id(901, 1, 0)


def _write_chain(tmp_path: Path) -> tuple[Path, Path]:
    """CHA(901) -> CHB(902) -> CHC(901, a revisit); INTRO starts on empty map 903. 901/ev2 is an autorun that
    sets switch 60; 902/ev1 is gated on switch 60."""
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    map_a = _map([
        _event(1, [_page([_cmd(121, [50, 50, 0])], trigger=3)]),
        _event(2, [_page([_cmd(121, [60, 60, 0])], trigger=3)]),
    ], map_id=901)
    map_b = _map([_event(1, [_page([_cmd(101, ["b"])], condition={
        "switch1_valid": True, "switch1_id": 60})])], map_id=902)
    (build_dir / "maps" / "Map901.json").write_text(json.dumps(map_a), encoding="utf-8")
    (build_dir / "maps" / "Map902.json").write_text(json.dumps(map_b), encoding="utf-8")
    # INTRO starts on an empty map outside the chain, so it owns none of the rows.
    (build_dir / "maps" / "Map903.json").write_text(
        json.dumps(_map([], map_id=903)), encoding="utf-8")
    (build_dir / "common_events.json").write_text("[]", encoding="utf-8")
    (build_dir / "system.json").write_text(json.dumps({"start_map_id": 903}), encoding="utf-8")
    _write_metadata_header(build_dir)
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "schema": 1,
        "acts": [{"id": "A1", "title": "Act 1", "chapters": ["CHA", "CHB", "CHC"]}],
        "chapters": [
            {"id": "CHA", "act": "A1", "title": "Alpha", "maps": [901]},
            {"id": "CHB", "act": "A1", "title": "Beta", "maps": [902], "predecessor": "CHA"},
            {"id": "CHC", "act": "A1", "title": "Gamma", "maps": [901], "predecessor": "CHB"},
        ],
    }), encoding="utf-8")
    return build_dir, chapters_path


def _row(story, row_id: str):  # noqa: ANN001
    return next(r for r in story.rows if r.row_id == row_id)


def test_deferred_row_is_owned_by_the_first_chapter_with_its_map(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_chain(tmp_path)
    calls: list[str] = []

    def deferred_for(cid: str) -> frozenset[str]:
        calls.append(cid)
        return frozenset({DEFERRED_ROW}) if cid == "CHA" else frozenset()

    stories = build_chapter_stories(
        ["CHA", "CHB", "CHC"], build_dir=build_dir, chapters_path=chapters_path,
        deferred_for=deferred_for)
    assert "CHC" not in calls  # the chapter being generated has no module
    assert _row(stories["CHA"], LOCAL_ROW).owner == "CHA"
    cha = _row(stories["CHA"], DEFERRED_ROW)
    assert (cha.status, cha.owner) == ("later", "CHC")
    # CHB lacks the map, so the hidden row's write (switch 60) never reaches
    # CHB: the row gated on it stays unowned there and is picked up by CHC.
    gated = _row(stories["CHB"], GATED_ROW)
    assert gated.status == "later" and gated.owner == "CHC"
    assert not any(r.row_id == DEFERRED_ROW and r.owner == "CHB" for r in stories["CHB"].rows)
    assert dict(stories["CHA"].end_state) != dict(stories["CHC"].end_state)


def test_without_deferral_first_live_chapter_owns_it(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_chain(tmp_path)
    stories = build_chapter_stories(
        ["CHA", "CHB", "CHC"], build_dir=build_dir, chapters_path=chapters_path)
    assert _row(stories["CHA"], DEFERRED_ROW).owner == "CHA"
    assert _row(stories["CHB"], GATED_ROW).owner == "CHB"
    explicit_none = build_chapter_stories(
        ["CHA", "CHB", "CHC"], build_dir=build_dir, chapters_path=chapters_path,
        deferred_for=None)
    assert explicit_none == stories


def test_empty_deferral_matches_default(tmp_path: Path) -> None:
    build_dir, chapters_path = _write_chain(tmp_path)
    base = build_chapter_stories(
        ["CHA", "CHB", "CHC"], build_dir=build_dir, chapters_path=chapters_path)
    empty = build_chapter_stories(
        ["CHA", "CHB", "CHC"], build_dir=build_dir, chapters_path=chapters_path,
        deferred_for=lambda cid: frozenset())
    assert empty == base
