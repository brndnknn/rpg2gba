"""Tests for `python -m rpg2gba.routing`'s CLI (`plan` / `show`).

Follows `tests/test_chapter_manifest_cli.py`'s style (CliRunner, tmp_path
fixtures for `--build-dir`/`--chapters`/`--manifest`) and the chapter-module-
faking technique from `tests/test_chapter_predecessor.py` (a fake module
dropped into `sys.modules` under `rpg2gba.playtest.chapters_gen.<name>`, since
`load_chapter` is just `importlib.import_module` + `getattr(..., "CHAPTER")`).

`build_map_graph`/`build_trigger_overlay`/`build_world_graph`/`build_occupancy`
are monkey-patched at the point `rpg2gba.routing.__main__` imported them, so
these tests
never touch `output/`/`engine/` -- only a single trivial 1x1 map is needed
since the test chapter's one group sits on the same map as its (default)
entry/exit, so every segment is a same-map, zero-tile hop and the world
graph is never actually queried.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from click.testing import CliRunner

from rpg2gba.playtest.chapter import Chapter, ChapterBuilder
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.triggers import TriggerOverlay
from rpg2gba.traversal.world import WorldGraph

from rpg2gba.routing.occupancy import MapOccupancy

from rpg2gba.chapter_manifest.dispositions import Disposition, write_dispositions
from rpg2gba.chapter_manifest.schema import ManifestRow, row_to_dict

from rpg2gba.routing.__main__ import cli
from rpg2gba.routing.plan import load_plan
import rpg2gba.routing.__main__ as routing_main

PKG = "rpg2gba.playtest.chapters_gen"  # the default suite since 2026-10-03
MAP_ID = 101


def _install_chapter(name: str) -> Chapter:
    builder = ChapterBuilder(name, doc="reference/chapters/00-test.md")

    @builder.beat("G1", "the only beat", map_constant="MAP_G1", at=(0, 0), group="G1")
    def g1(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    module = types.ModuleType(f"{PKG}.{name}")
    module.CHAPTER = chapter
    sys.modules[f"{PKG}.{name}"] = module
    return chapter


def _fake_build_map_graph(map_id: int, **kwargs) -> MapGraph:  # noqa: ANN003
    return MapGraph(map_id=map_id, width=1, height=1, tileset_id=0, blocked={(0, 0): False})


def _fake_build_trigger_overlay(map_id: int, **kwargs) -> TriggerOverlay:  # noqa: ANN003
    return TriggerOverlay(map_id=map_id, tiles={})


def _fake_build_world_graph(**kwargs) -> WorldGraph:  # noqa: ANN003
    return WorldGraph(
        edges=[], names={}, map_ids=frozenset(), maps_without_info=frozenset(),
        infos_without_map=frozenset(), variable_warp_count=0, variable_warp_maps={},
    )


def _fake_build_occupancy(map_id: int, **kwargs) -> MapOccupancy:  # noqa: ANN003
    return MapOccupancy(map_id=map_id, tiles=())


def _write_fixtures(tmp_path: Path, chapter: str) -> tuple[Path, Path, Path]:
    build_dir = tmp_path / "build"
    (build_dir / "porymap").mkdir(parents=True)
    (build_dir / "porymap" / "map_constants.json").write_text(json.dumps({
        str(MAP_ID): {
            "uranium_id": MAP_ID, "map_const": "MAP_G1", "alias_const": "MAP_URANIUM_101",
            "layout_const": "LAYOUT_G1", "mapsec_const": "MAPSEC_G1",
            "dir_name": "G1", "display_name": "G1",
        },
    }), encoding="utf-8")

    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": chapter, "maps": [MAP_ID]}],
    }), encoding="utf-8")

    manifest_path = tmp_path / f"{chapter}.manifest.json"
    manifest_path.write_text("[]", encoding="utf-8")

    return build_dir, chapters_path, manifest_path


def _patch_builders(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(routing_main, "build_map_graph", _fake_build_map_graph)
    monkeypatch.setattr(routing_main, "build_trigger_overlay", _fake_build_trigger_overlay)
    monkeypatch.setattr(routing_main, "build_world_graph", _fake_build_world_graph)
    monkeypatch.setattr(routing_main, "build_occupancy", _fake_build_occupancy)


def _cleanup_chapter(name: str) -> None:
    sys.modules.pop(f"{PKG}.{name}", None)


def test_plan_dry_run_prints_summary_and_writes_nothing(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    chapter = "dryrunch"
    _install_chapter(chapter)
    try:
        _patch_builders(monkeypatch)
        build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "plan", "--chapter", chapter, "--module", chapter, "--dry-run",
                "--manifest", str(manifest_path),
                "--build-dir", str(build_dir),
                "--chapters", str(chapters_path),
            ])

            assert result.exit_code == 0, result.output
            assert "group 'G1'" in result.output
            assert "greedy+2opt" in result.output
            assert not (Path("reference") / "routes" / f"{chapter}.route.json").exists()
    finally:
        _cleanup_chapter(chapter)


def test_plan_writes_route_file(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    chapter = "writech"
    _install_chapter(chapter)
    try:
        _patch_builders(monkeypatch)
        build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            out_path = Path("out.route.json")
            result = runner.invoke(cli, [
                "plan", "--chapter", chapter, "--module", chapter,
                "--out", str(out_path),
                "--manifest", str(manifest_path),
                "--build-dir", str(build_dir),
                "--chapters", str(chapters_path),
            ])

            assert result.exit_code == 0, result.output
            assert out_path.exists()
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            assert payload["chapter"] == chapter
            assert len(payload["nodes"]) == 3  # entry, G1, exit
    finally:
        _cleanup_chapter(chapter)


def test_show_prints_summary_from_written_file(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    chapter = "showch"
    _install_chapter(chapter)
    try:
        _patch_builders(monkeypatch)
        build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            route_path = Path("route.json")
            plan_result = runner.invoke(cli, [
                "plan", "--chapter", chapter, "--module", chapter, "--out", str(route_path),
                "--manifest", str(manifest_path),
                "--build-dir", str(build_dir),
                "--chapters", str(chapters_path),
            ])
            assert plan_result.exit_code == 0, plan_result.output

            show_result = runner.invoke(cli, ["show", "--chapter", chapter, "--route", str(route_path)])
            assert show_result.exit_code == 0, show_result.output
            assert "precedence:" in show_result.output
            assert "segments:" in show_result.output

            json_result = runner.invoke(
                cli, ["show", "--chapter", chapter, "--route", str(route_path), "--json"],
            )
            assert json_result.exit_code == 0, json_result.output
            payload = json.loads(json_result.output)
            assert payload["chapter"] == chapter
    finally:
        _cleanup_chapter(chapter)


def test_show_missing_route_file_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["show", "--chapter", "nope", "--route", "missing.json"])
        assert result.exit_code != 0
        assert "does not exist" in result.output


def test_show_default_route_path_missing_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["show", "--chapter", "nope"])
        assert result.exit_code != 0
        assert "route plan not found" in result.output


def test_plan_unknown_chapter_module_errors(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    chapter = "totallyunknownchapter"
    _patch_builders(monkeypatch)
    build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, [
            "plan", "--chapter", chapter, "--module", chapter,
            "--manifest", str(manifest_path),
            "--build-dir", str(build_dir),
            "--chapters", str(chapters_path),
        ])
        assert result.exit_code != 0
        assert "no chapter" in result.output


def test_plan_chapter_id_and_module_are_distinct_names(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """`--chapter` keys the artifacts, `--module` names the scenario module.

    The real corpus now has these agree by default: CH04 is Route 2, whose
    playtest module is `ch04.py`. This test pins that they are still allowed
    to DIFFER -- the CLI accepts an explicit `--module` that is not the
    chapter id, and records it on the plan for downstream consumers to
    recover.
    """
    chapter_id = "CH99"
    module = "someplace"
    _install_chapter(module)
    try:
        _patch_builders(monkeypatch)
        build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter_id)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            route_path = Path("out.route.json")
            result = runner.invoke(cli, [
                "plan", "--chapter", chapter_id, "--module", module,
                "--out", str(route_path),
                "--manifest", str(manifest_path),
                "--build-dir", str(build_dir),
                "--chapters", str(chapters_path),
            ])

            assert result.exit_code == 0, result.output
            written = load_plan(route_path)
            assert written.chapter_id == chapter_id
            assert written.chapter_module == module
    finally:
        _cleanup_chapter(module)


# --- RULE_TRIGGER_OVERLAY_VACUOUS: PROJECT_TODO #75 / REDERIVATION_PLAN P1 --
#
# The ROUTE step (`plan_cmd`) must refuse to let a route across a map with a
# dispositioned trainer row read as clean when the trigger overlay it was
# solved against found zero TRAINER_SIGHT tiles there -- see
# `chapter_manifest.checker.TriggerOverlayModel`'s docstring for the CH05
# incident (a clean 155-tile route reported before the object events the
# overlay needed even existed).


def _write_trainer_manifest(manifest_path: Path, map_id: int) -> str:
    """Writes a one-row manifest whose row is a `trainer` archetype match on
    `map_id`, and returns that row's `row_id`."""
    row = ManifestRow(
        row_id=f"map{map_id:03d}/ev001/p0", kind="page", map_id=map_id,
        content_hash="th0", event_id=1, page_idx=0,
        script_heads=("pbTrainerBattle",), effects=(),
        trigger="action button", reachability_consulted=True,
    )
    manifest_path.write_text(json.dumps([row_to_dict(row)]), encoding="utf-8")
    return row.row_id


def _write_trainer_disposition(row_id: str, chapter: str) -> None:
    """Writes `reference/manifests/<chapter>.dispositions.json` (the default
    path `_check_trigger_overlay_or_raise` reads) relative to the CURRENT
    working directory -- callers must be inside a
    `runner.isolated_filesystem(...)` block already."""
    path = Path("reference") / "manifests" / f"{chapter}.dispositions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_dispositions({row_id: Disposition(row_id=row_id, verdict="beat", argument="B1")}, path)


def _fake_build_trigger_overlay_with_sight(sight_map_id: int):
    """A `build_trigger_overlay` fake that plants one TRAINER_SIGHT tile on
    `sight_map_id` and leaves every other map vacuous, same shape as
    `_fake_build_trigger_overlay` otherwise."""
    from rpg2gba.traversal.triggers import Certainty, TriggerKind, TriggerRef

    def _build(map_id: int, **kwargs) -> TriggerOverlay:  # noqa: ANN003
        if map_id != sight_map_id:
            return TriggerOverlay(map_id=map_id, tiles={})
        return TriggerOverlay(
            map_id=map_id,
            tiles={
                (0, 1): [
                    TriggerRef(
                        kind=TriggerKind.TRAINER_SIGHT, script="EventScript_Trainer",
                        certainty=Certainty.CERTAIN, owner_xy=(0, 0), detail="sight range 1 facing SOUTH",
                    )
                ]
            },
        )

    return _build


def test_plan_fails_on_vacuous_overlay_for_dispositioned_trainer_map(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    chapter = "vacuousch"
    _install_chapter(chapter)
    try:
        _patch_builders(monkeypatch)  # default fake overlay is always empty/vacuous
        build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter)
        row_id = _write_trainer_manifest(manifest_path, MAP_ID)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _write_trainer_disposition(row_id, chapter)
            result = runner.invoke(cli, [
                "plan", "--chapter", chapter, "--module", chapter, "--dry-run",
                "--manifest", str(manifest_path),
                "--build-dir", str(build_dir),
                "--chapters", str(chapters_path),
            ])

            assert result.exit_code != 0, result.output
            assert "trigger_overlay_vacuous" in result.output
            assert f"map{MAP_ID:03d}" in result.output
    finally:
        _cleanup_chapter(chapter)


def test_plan_succeeds_when_overlay_actually_sees_trainer_sight(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    chapter = "sightseench"
    _install_chapter(chapter)
    try:
        _patch_builders(monkeypatch)
        monkeypatch.setattr(
            routing_main, "build_trigger_overlay",
            _fake_build_trigger_overlay_with_sight(MAP_ID),
        )
        build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter)
        row_id = _write_trainer_manifest(manifest_path, MAP_ID)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _write_trainer_disposition(row_id, chapter)
            result = runner.invoke(cli, [
                "plan", "--chapter", chapter, "--module", chapter, "--dry-run",
                "--manifest", str(manifest_path),
                "--build-dir", str(build_dir),
                "--chapters", str(chapters_path),
            ])

            assert result.exit_code == 0, result.output
    finally:
        _cleanup_chapter(chapter)


def test_plan_skips_trigger_overlay_check_without_dispositions_file(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """No dispositions file on disk at all -- the check has nothing to
    classify as a "dispositioned trainer row" and must not block routing a
    chapter that hasn't reached the disposition step yet (that absence is
    `chapter_manifest check`'s own RULE_UNDISPOSITIONED's job, not this
    rule's)."""
    chapter = "nodispch"
    _install_chapter(chapter)
    try:
        _patch_builders(monkeypatch)  # vacuous overlay, but no dispositions file either
        build_dir, chapters_path, manifest_path = _write_fixtures(tmp_path, chapter)
        _write_trainer_manifest(manifest_path, MAP_ID)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "plan", "--chapter", chapter, "--module", chapter, "--dry-run",
                "--manifest", str(manifest_path),
                "--build-dir", str(build_dir),
                "--chapters", str(chapters_path),
            ])

            assert result.exit_code == 0, result.output
    finally:
        _cleanup_chapter(chapter)
