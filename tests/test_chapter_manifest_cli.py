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
