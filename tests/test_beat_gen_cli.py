"""End-to-end tests for `rpg2gba.beat_gen.__main__` on CH05 (C6 Task 9).

This is C6_GENERATOR_PLAN.md C1's checkpoint: "CH05 regenerates and diffs
acceptably". It needs Tasks 1-8, the staged build under
`output/uranium-build/`, and (for the last test) C7 Task 1's frozen file.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 9.
"""
from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path

import pytest
from click.testing import CliRunner

from rpg2gba.beat_gen import __main__ as cli
from rpg2gba.chapter_manifest.schema import parse_row_id
from rpg2gba.playtest.chapter import Chapter


FROZEN = Path("reference/frozen/hand_beats_ch01-ch05.json")


@pytest.fixture(scope="module")
def plan():
    return cli.build_plan("CH05")


@pytest.fixture(scope="module")
def written(plan, tmp_path_factory):
    out = tmp_path_factory.mktemp("beats")
    module_dir = tmp_path_factory.mktemp("chapters_gen")
    return out, cli.write_outputs(plan, out, module_dir=module_dir)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("ch05_generated", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the plan -------------------------------------------------------------------

def test_ch05_is_green(plan):
    assert plan.refusals == ()        # C6 plan B2: CH05 is the one that must be green


def test_ch05_plan_shape(plan):
    assert plan.chapter_id == "CH05" and plan.predecessor == "CH04"
    # 20 own beats + 3 successor claims on CH04's cave mouth (§10 R2/R3,
    # C6 part two): the warp, its arrival nudge and the nudge's arms.
    assert len(plan.beats) == 23
    inbound = [b for b in plan.beats if dict(b.kwargs).get("manifest_chapter_id") == "CH04"]
    assert [b.name for b in inbound] == [
        "m035e001_warp", "m035e001_arrival_nudge", "m035e001_arrival_nudge_arms"]
    assert {e.status for e in plan.elsewhere} == {"blocked"}   # the two surf items
    assert plan.route is not None


def test_every_beat_starts_on_the_map_the_player_is_on(plan):
    """The continuity pass's contract, re-checked from the outside: walking
    the warps' legs from the route's entry, every non-warp beat is on the
    player's current map."""
    from rpg2gba.beat_gen.__main__ import BUILD_DIR, _warp_dest
    from rpg2gba.beat_floor.walk import floor_for_chapter

    floors = {**floor_for_chapter("CH04", build_dir=BUILD_DIR),
              **floor_for_chapter("CH05", build_dir=BUILD_DIR)}
    cur = plan.route.nodes[0].map_id
    for beat in plan.beats:
        kw = dict(beat.kwargs)
        if beat.template == "warp" and not kw.get("boundary"):
            sides = {"origin": beat.map_id, "dest": _warp_dest(beat, floors)}
            assert cur == sides[kw["start_side"]], beat.name
            cur = sides[kw["end_side"]]
        else:
            assert cur == beat.map_id, beat.name


def test_groups_are_contiguous_in_route_order(plan):
    seen: list[str] = []
    for beat in plan.beats:
        if not seen or seen[-1] != beat.group:
            assert beat.group not in seen, f"group {beat.group} split"
            seen.append(beat.group)
    route_groups = [n.group for n in plan.route.nodes if n.kind == "group"]
    assert seen == route_groups


def test_every_warp_has_a_press_direction(plan):
    for beat in plan.beats:
        if beat.template == "warp":
            assert dict(beat.kwargs).get("direction") in {"UP", "DOWN", "LEFT", "RIGHT"}, beat


def test_build_plan_is_deterministic(plan):
    assert cli.build_plan("CH05") == plan


# --- the artifacts --------------------------------------------------------------

def test_three_artifacts_in_fixed_order(written):
    out, paths = written
    assert [p.name for p in paths] == ["ch05.py", "CH05.review.md", "CH05.route.json"]
    module_path, review_path, route_path = paths
    assert module_path.exists()
    assert review_path.parent == out and review_path.exists()
    assert route_path.parent == out and route_path.exists()


def test_rerun_is_byte_identical(plan, written, tmp_path):
    _, first = written
    second_module_dir = tmp_path / "module"
    second = cli.write_outputs(plan, tmp_path, module_dir=second_module_dir)
    for a, b in zip(first, second):
        assert a.read_bytes() == b.read_bytes(), a.name


def test_generated_module_imports_and_claims_every_owned_row(plan, written):
    _, paths = written
    chapter = _load(paths[0]).CHAPTER
    assert isinstance(chapter, Chapter)
    own = [b for b in chapter.beats if ":" not in b.name]
    claimed = {r for b in own for r in b.rows}
    planned = {r for b in plan.beats for r in b.rows}
    assert planned <= claimed
    assert all(b.assertions is not None for b in own)   # a GENERATED module declares


def test_route_artifact_is_a_loadable_plan(written):
    from rpg2gba.routing.plan import load_plan
    _, paths = written
    assert load_plan(paths[2]).chapter_id == "CH05"


# --- grading against the C7 freeze (R12 amended) -------------------------------

def test_frozen_rows_on_ch05_maps_are_claimed(written):
    if not FROZEN.exists():
        pytest.skip("C7 Task 1's freeze file isn't written yet")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    hand_rows = {r for beat in frozen["chapters"]["CH05"] for r in beat["rows"]}
    own_maps = {36, 37}
    on_maps = {r for r in hand_rows if parse_row_id(r).map_id in own_maps}
    _, paths = written
    chapter = _load(paths[0]).CHAPTER
    claimed = {r for b in chapter.beats if ":" not in b.name for r in b.rows}
    assert on_maps - claimed == set()


# --- never_fires (C9 ruling 3) --------------------------------------------------

def test_dead_arrival_nudge_group_yields_never_fires_elsewhere_not_refusal():
    from rpg2gba.beat_gen.plan import Elsewhere, PlannedBeat, make_kwargs

    beat = PlannedBeat(name="m068e012p1", template="arrival_nudge", map_id=68,
                        rows=("map068/ev012/p1",), group="m068e012",
                        kwargs=make_kwargs())
    arm = PlannedBeat(name="m068e012p1b0", template="arrival_nudge_arms", map_id=68,
                       rows=("map068/ev012/p1/b0",), group="m068e012",
                       kwargs=make_kwargs())
    detail = ("archetype_kwargs: map068/ev012/p1: no warp lands on this arrival "
              "autorun's cell (5,6) on map 68 -- it never fires")
    dead_groups = {"m068e012": detail}

    result = cli._never_fires_elsewhere((beat, arm), dead_groups)

    assert result == (
        Elsewhere("map068/ev012/p1", "never_fires", detail=detail),
        Elsewhere("map068/ev012/p1/b0", "never_fires", detail=detail))


def test_never_fires_elsewhere_skips_beats_outside_dead_groups():
    from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs

    live = PlannedBeat(name="m036e002p1", template="arrival_nudge", map_id=36,
                        rows=("map036/ev002/p1",), group="m036e002",
                        kwargs=make_kwargs())
    assert cli._never_fires_elsewhere((live,), {}) == ()


# --- --module-dir CLI wiring (mocked: no staged corpus needed) -----------------

def test_generate_cli_threads_out_dir_and_module_dir(tmp_path, monkeypatch):
    """`generate` must pass its `--out-dir`/`--module-dir` options straight
    through to `build_plan`/`write_outputs`, and default `--module-dir` to
    `DEFAULT_MODULE_DIR` (`playtest/chapters_gen/`) when omitted. Mocked so
    this doesn't need a staged `output/uranium-build/` corpus."""
    calls = {}

    def fake_build_plan(chapter_id, *, build_dir=cli.BUILD_DIR,
                        out_dir=cli.DEFAULT_OUT_DIR, module_dir=cli.DEFAULT_MODULE_DIR):
        calls["build_plan"] = (chapter_id, out_dir, module_dir)
        return types.SimpleNamespace(refusals=())

    def fake_write_outputs(plan, out_dir, *, module_dir=None, build_dir=cli.BUILD_DIR):
        calls["write_outputs"] = (out_dir, module_dir)
        return [module_dir / "ch05.py", out_dir / "CH05.review.md", out_dir / "CH05.route.json"]

    monkeypatch.setattr(cli, "build_plan", fake_build_plan)
    monkeypatch.setattr(cli, "write_outputs", fake_write_outputs)

    out_dir = tmp_path / "out"
    module_dir = tmp_path / "modules"
    runner = CliRunner()
    result = runner.invoke(cli.cli, [
        "generate", "--chapter", "CH05",
        "--out-dir", str(out_dir), "--module-dir", str(module_dir),
    ])

    assert result.exit_code == 0, result.output
    assert calls["build_plan"] == ("CH05", out_dir, module_dir)
    assert calls["write_outputs"] == (out_dir, module_dir)


def test_generate_cli_module_dir_defaults_to_chapters_gen(tmp_path, monkeypatch):
    calls = {}

    def fake_build_plan(chapter_id, *, build_dir=cli.BUILD_DIR,
                        out_dir=cli.DEFAULT_OUT_DIR, module_dir=cli.DEFAULT_MODULE_DIR):
        calls["module_dir"] = module_dir
        return types.SimpleNamespace(refusals=())

    def fake_write_outputs(plan, out_dir, *, module_dir=None, build_dir=cli.BUILD_DIR):
        return [module_dir / "ch05.py", out_dir / "CH05.review.md", out_dir / "CH05.route.json"]

    monkeypatch.setattr(cli, "build_plan", fake_build_plan)
    monkeypatch.setattr(cli, "write_outputs", fake_write_outputs)

    runner = CliRunner()
    result = runner.invoke(cli.cli, [
        "generate", "--chapter", "CH05", "--out-dir", str(tmp_path / "out"),
    ])

    assert result.exit_code == 0, result.output
    assert calls["module_dir"] == cli.DEFAULT_MODULE_DIR
