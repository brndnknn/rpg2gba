"""Tests for the `generate` subcommand of `rpg2gba.chapter_manifest`'s CLI.

Uses Click's CliRunner with `--build-dir`/`--chapters`/`--manifest` pointed at
synthetic fixtures under `tmp_path`, following the fixture style in
`tests/test_chapter_manifest_generator.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rpg2gba.chapter_manifest.__main__ import cli


def _write_map(path: Path, map_id: int, events: list[dict]) -> None:
    payload = {
        "map_id": map_id,
        "tileset_id": 1,
        "width": 10,
        "height": 10,
        "events": events,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _page(list_: list[dict]) -> dict:
    condition = {
        "switch1_valid": False, "switch1_id": 1,
        "switch2_valid": False, "switch2_id": 1,
        "variable_valid": False, "variable_id": 1, "variable_value": 0,
        "self_switch_valid": False, "self_switch_ch": "A",
    }
    list_ = list_ + [{"code": 0, "indent": 0, "parameters": []}]
    return {
        "condition": condition,
        "graphic": {}, "move_type": 0, "move_route": {"list": []},
        "trigger": 0, "direction_fix": False, "through": False,
        "list": list_,
    }


def _cmd(code: int, parameters: list | None = None) -> dict:
    return {"code": code, "indent": 0, "parameters": parameters or []}


def _setup_chapter(tmp_path: Path, chapter_id: str, map_id: int, events: list[dict]) -> tuple[Path, Path]:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    _write_map(build_dir / "maps" / f"Map{map_id:03d}.json", map_id, events)
    (build_dir / "connections.json").write_text("[]", encoding="utf-8")
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": chapter_id, "maps": [map_id]}],
    }), encoding="utf-8")
    return build_dir, chapters_path


def test_generate_writes_default_path_and_reports_count(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Sign", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["Hello"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, "CH04", 7, events)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, [
            "generate", "--chapter", "CH04",
            "--build-dir", str(build_dir),
            "--chapters", str(chapters_path),
        ])

        assert result.exit_code == 0, result.output
        expected_path = Path("reference") / "manifests" / "CH04.manifest.json"
        assert expected_path.exists()
        payload = json.loads(expected_path.read_text(encoding="utf-8"))
        assert len(payload) == 1
        assert "1 rows" in result.output
        assert "wrote" in result.output


def test_generate_twice_is_byte_identical(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "NPC", "x": 0, "y": 0,
        "pages": [_page([
            _cmd(101, ["Hi"]),
            _cmd(355, ["Kernel.pbReceiveItem(::PBItems::POTION,1)"]),
        ])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, "CH04", 8, events)
    manifest_path = tmp_path / "out.manifest.json"

    runner = CliRunner()
    args = [
        "generate", "--chapter", "CH04",
        "--manifest", str(manifest_path),
        "--build-dir", str(build_dir),
        "--chapters", str(chapters_path),
    ]

    result1 = runner.invoke(cli, args)
    assert result1.exit_code == 0, result1.output
    text1 = manifest_path.read_text(encoding="utf-8")

    result2 = runner.invoke(cli, args)
    assert result2.exit_code == 0, result2.output
    text2 = manifest_path.read_text(encoding="utf-8")

    assert text1 == text2


def test_generate_unknown_chapter_fails_loud(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Sign", "x": 0, "y": 0,
        "pages": [_page([_cmd(101, ["Hello"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, "CH04", 9, events)
    manifest_path = tmp_path / "out.manifest.json"

    runner = CliRunner()
    result = runner.invoke(cli, [
        "generate", "--chapter", "CHNOPE",
        "--manifest", str(manifest_path),
        "--build-dir", str(build_dir),
        "--chapters", str(chapters_path),
    ])

    assert result.exit_code != 0
    assert not manifest_path.exists()


# --- `check` subcommand: GraphApproachModel wiring -------------------------
#
# A 3x3 chokepoint map (start (1,0), a rock at the chokepoint (1,1), walls at
# (0,1)/(2,1) forcing everything through the rock, a sign beyond it) --
# mirrors the fixture in `test_chapter_manifest_generator.py`'s reachability
# tests, duplicated locally rather than imported (this file's own convention:
# `_write_map`/`_page`/`_cmd` are already independently duplicated there).


def _write_traversable_map(
    path: Path, map_id: int, width: int, height: int, events: list[dict],
    wall_cells: set[tuple[int, int]],
) -> None:
    layer0 = [2 if (x, y) in wall_cells else 1 for y in range(height) for x in range(width)]
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
    path.write_text(json.dumps({
        "1": {"passages": [0, 0, 0x0F], "priorities": [0, 0, 0], "terrain_tags": [0, 0, 0]},
    }), encoding="utf-8")


def _setup_chokepoint_chapter(tmp_path: Path, chapter_id: str, map_id: int) -> tuple[Path, Path]:
    events = [
        {
            "id": 1, "name": "Rock", "x": 1, "y": 1,
            "pages": [_page([_cmd(355, ["Kernel.pbRockSmash(1)"])])],
        },
        {
            "id": 2, "name": "Sign", "x": 1, "y": 2,
            "pages": [_page([_cmd(101, ["Beyond the rock"])])],
        },
    ]
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    _write_traversable_map(
        build_dir / "maps" / f"Map{map_id:03d}.json", map_id, 3, 3, events,
        wall_cells={(0, 1), (2, 1)})
    _write_tilesets(build_dir / "tilesets.json")
    (build_dir / "connections.json").write_text("[]", encoding="utf-8")
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": chapter_id, "maps": [map_id]}],
    }), encoding="utf-8")
    return build_dir, chapters_path


def test_check_fires_missed_assertion_with_no_negative_beat(tmp_path: Path, monkeypatch) -> None:
    """End to end through the CLI: a registered start cell, a `blocked:`
    disposition with no `negative_beat`, and a genuinely walkable approach
    (the rock's own north neighbour is the start tile) -- the rule that
    could never fire with no approach model supplied now fires for real."""
    from rpg2gba.chapter_manifest import generator
    monkeypatch.setitem(generator._CHAPTER_MAP_START_CELLS, ("CHK", 50), frozenset({(1, 0)}))

    build_dir, chapters_path = _setup_chokepoint_chapter(tmp_path, "CHK", 50)
    manifest_path = tmp_path / "CHK.manifest.json"
    dispositions_path = tmp_path / "CHK.dispositions.json"

    runner = CliRunner()
    gen = runner.invoke(cli, [
        "generate", "--chapter", "CHK",
        "--manifest", str(manifest_path),
        "--build-dir", str(build_dir),
        "--chapters", str(chapters_path),
    ])
    assert gen.exit_code == 0, gen.output

    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {r["row_id"]: r["content_hash"] for r in rows}
    rock_row_id = "map050/ev001/p0"
    sign_row_id = "map050/ev002/p0"
    dispositions_path.write_text(json.dumps({
        rock_row_id: {"disposition": "blocked:rock_smash", "affirmed_hash": hashes[rock_row_id]},
        sign_row_id: {
            "disposition": "blocked:rock_smash", "affirmed_hash": hashes[sign_row_id],
            "assertable": True, "negative_beat": "B1",
        },
    }), encoding="utf-8")

    result = runner.invoke(cli, [
        "check", "--chapter", "CHK",
        "--manifest", str(manifest_path),
        "--dispositions", str(dispositions_path),
        "--build-dir", str(build_dir),
    ])

    assert f"{rock_row_id} (blocked_missed_assertion)" in result.output
    assert f"{sign_row_id} (blocked_missed_assertion)" not in result.output
    assert f"{rock_row_id} (approach_model_unenforced)" not in result.output
    assert f"{sign_row_id} (approach_model_unenforced)" not in result.output


def test_check_unregistered_map_falls_back_to_unenforced(tmp_path: Path) -> None:
    """No entry in `_CHAPTER_MAP_START_CELLS` for this chapter/map -- the
    concrete model answers None for every row, same as no model at all."""
    build_dir, chapters_path = _setup_chokepoint_chapter(tmp_path, "CHK_UNREG", 51)
    manifest_path = tmp_path / "CHK_UNREG.manifest.json"
    dispositions_path = tmp_path / "CHK_UNREG.dispositions.json"

    runner = CliRunner()
    gen = runner.invoke(cli, [
        "generate", "--chapter", "CHK_UNREG",
        "--manifest", str(manifest_path),
        "--build-dir", str(build_dir),
        "--chapters", str(chapters_path),
    ])
    assert gen.exit_code == 0, gen.output

    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {r["row_id"]: r["content_hash"] for r in rows}
    rock_row_id = "map051/ev001/p0"
    dispositions_path.write_text(json.dumps({
        rock_row_id: {"disposition": "blocked:rock_smash", "affirmed_hash": hashes[rock_row_id]},
        "map051/ev002/p0": {"disposition": "cosmetic", "affirmed_hash": hashes["map051/ev002/p0"]},
    }), encoding="utf-8")

    result = runner.invoke(cli, [
        "check", "--chapter", "CHK_UNREG",
        "--manifest", str(manifest_path),
        "--dispositions", str(dispositions_path),
        "--build-dir", str(build_dir),
    ])

    assert f"{rock_row_id} (approach_model_unenforced)" in result.output
    assert f"{rock_row_id} (blocked_missed_assertion)" not in result.output


# --- `check` subcommand: boundary model wiring (PROJECT_TODO #72/#73) -----
#
# No synthetic fixture path for `build_boundary_model` -- it reads the real
# `reference/chapters.json` chain and the real `output/uranium-build/`
# corpus by design (same as `build_beat_model`/`build_archetype_model`), so
# these run against CH04's real, committed manifest and a scratch copy of
# its real dispositions.


def test_check_flags_a_boundary_disposition_that_is_not_a_real_crossing(
    tmp_path: Path,
) -> None:
    """`map035/ev001/p1` is CH04's arrival-nudge autorun, not itself a
    code-201 transfer -- `is_forward_crossing` is False for it (pinned in
    `test_chapter_manifest_boundary_model.py`). Switching its real
    disposition from `beat:B8` to `boundary` should be caught as a false
    crossing claim, wired all the way through the CLI's real
    `build_boundary_model`."""
    dispositions_path = Path("reference/manifests/CH04.dispositions.json")
    dispositions = json.loads(dispositions_path.read_text(encoding="utf-8"))
    row_id = "map035/ev001/p1"
    dispositions[row_id] = {
        "disposition": "boundary",
        "affirmed_hash": dispositions[row_id]["affirmed_hash"],
    }

    scratch = tmp_path / "CH04.dispositions.json"
    scratch.write_text(json.dumps(dispositions), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "check", "--chapter", "CH04",
        "--dispositions", str(scratch),
    ])

    assert f"{row_id} (boundary_not_crossing)" in result.output


def test_check_real_ch04_carries_no_boundary_dispositions_yet() -> None:
    """Baseline: CH04's real, committed dispositions carry no `boundary`
    verdict at all today (PROJECT_TODO #72/#73's enforcement landed before
    any row was switched to it), so wiring in the real boundary model must
    not manufacture a finding out of nothing."""
    runner = CliRunner()
    result = runner.invoke(cli, ["check", "--chapter", "CH04"])

    assert "boundary_not_crossing" not in result.output
    assert "boundary_unclaimed" not in result.output
