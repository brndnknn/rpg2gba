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
    # C6 part two): the warp, its arrival nudge and the nudge's arms. Plus
    # 2 transits since one-way warps (2026-09-28 ruling): each reverse warp
    # ends on its destination for the arrival nudge there, then walks back.
    assert len(plan.beats) == 25
    assert sum(b.template == "transit" for b in plan.beats) == 2
    inbound = [b for b in plan.beats if dict(b.kwargs).get("manifest_chapter_id") == "CH04"]
    assert [b.name for b in inbound] == [
        "m035e001_warp", "m035e001_arrival_nudge", "m035e001_arrival_nudge_arms"]
    # The two surf items, the full-bag/white-out arms (ruling 19 step 1), and
    # the nudges' `onEvent?` else arms: the walk lands on the nudge tile
    # (steps 4-5, `state_arms`).
    assert {e.status for e in plan.elsewhere} == {"blocked", "unselected_arm"}
    assert sorted(e.row_id for e in plan.elsewhere
                  if e.detail.startswith("not taken on the walk")) == [
        "map035/ev001/p1/b1", "map036/ev002/p1/b1"]
    assert plan.route is not None


def test_every_beat_starts_on_the_map_the_player_is_on(plan):
    """The continuity pass's contract, re-checked from the outside: walking
    the warps' legs from the route's entry, every non-warp beat is on the
    player's current map."""
    from rpg2gba.beat_gen.__main__ import BUILD_DIR, _warp_dest
    from rpg2gba.beat_floor.walk import floor_for_chapter
    from rpg2gba.playtest.archetypes import map_uranium_id

    floors = {**floor_for_chapter("CH04", build_dir=BUILD_DIR),
              **floor_for_chapter("CH05", build_dir=BUILD_DIR)}
    cur = plan.route.nodes[0].map_id
    for beat in plan.beats:
        kw = dict(beat.kwargs)
        if beat.template == "warp" and not kw.get("boundary"):
            sides = {"origin": beat.map_id, "dest": _warp_dest(beat, floors)}
            assert cur == sides[kw["start_side"]], beat.name
            cur = sides[kw["end_side"]]
        elif beat.template == "transit":
            assert cur == beat.map_id, beat.name
            cur = map_uranium_id(kw["hops"][-1][4])
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
    # A GENERATED module declares -- except a transit, which claims no rows
    # and is only the way between two beats (`generic.transit_beat`).
    transits = {b.name for b in plan.beats if b.template == "transit"}
    assert all(b.assertions is not None for b in own if b.name not in transits)


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


# --- _cell_fn: which cells get re-sided as warps --------------------------------

class _OpenGraph:
    """Every cell walkable except `walls`; no warp tiles."""
    def __init__(self, walls=()):
        self.walls = set(walls)
        self.warp_exits = frozenset()

    def is_walkable(self, cell):
        return cell not in self.walls


def _page_row(row_id="map031/ev049/p0", trigger="action"):
    from rpg2gba.chapter_manifest.schema import ManifestRow
    return ManifestRow(row_id=row_id, kind="page", map_id=31, content_hash="x",
                       event_id=49, page_idx=0, trigger=trigger)


def test_action_warp_keeps_its_event_relative_sides(monkeypatch):
    """Regression (C9 regen, Kevlar Center door): an action-button warp's
    cell is already the APPROACH cell with the event's sides. Re-siding it
    as a warp named sides of the approach cell -- `east` of (21,14) -- which
    the runtime resolves against the event, (22,13), a wall."""
    from rpg2gba.routing.locations import ApproachCandidate, RowCell
    row = _page_row()
    sides = (ApproachCandidate(21, 14, "south", "s"), ApproachCandidate(20, 13, "west", "w"))
    cell = RowCell(row.row_id, "MAP_KEVLAR_TOWN", 21, 14, "approach_to", sides)
    monkeypatch.setattr(cli, "cell_for_row", lambda r: cell)
    fn = cli._cell_fn(frozenset({row.row_id}), {31: _OpenGraph()}, lambda m: ())
    assert fn(row).approach_candidates == sides


def test_touch_warp_on_its_event_cell_is_sided_around_the_event(monkeypatch):
    from rpg2gba.routing.locations import RowCell
    row = _page_row(trigger="player_touch")
    cell = RowCell(row.row_id, "MAP_KEVLAR_TOWN", 21, 13, "event_cell")
    monkeypatch.setattr(cli, "cell_for_row", lambda r: cell)
    fn = cli._cell_fn(frozenset({row.row_id}), {31: _OpenGraph(walls={(22, 13)})},
                      lambda m: ())
    got = {(c.side, c.x, c.y) for c in fn(row).approach_candidates}
    assert got == {("north", 21, 12), ("south", 21, 14), ("west", 20, 13)}


def test_obstacle_on_walkable_terrain_is_sided_around_the_object(monkeypatch):
    """Regression (C9, Kevlar Strength boulders map031/ev001, ev037): the
    boulder's tile is walkable terrain under the boulder object. Without its
    sides the reach pass floods to the occupied tile itself and drops the row
    as `later -- owner None`."""
    from rpg2gba.routing.locations import RowCell
    row = _page_row(row_id="map031/ev001/p0", trigger="player_touch")
    cell = RowCell(row.row_id, "MAP_KEVLAR_TOWN", 10, 16, "event_cell")
    monkeypatch.setattr(cli, "cell_for_row", lambda r: cell)
    graph = _OpenGraph(walls={(9, 16), (11, 16), (10, 15)})
    fn = cli._cell_fn(frozenset(), {31: graph}, lambda m: (),
                      obstacle_rows=frozenset({row.row_id}))
    got = {(c.side, c.x, c.y) for c in fn(row).approach_candidates}
    assert got == {("south", 10, 17)}


def test_non_obstacle_touch_event_on_walkable_tile_stays_on_its_cell(monkeypatch):
    from rpg2gba.routing.locations import RowCell
    row = _page_row(row_id="map031/ev001/p0", trigger="player_touch")
    cell = RowCell(row.row_id, "MAP_KEVLAR_TOWN", 10, 16, "event_cell")
    monkeypatch.setattr(cli, "cell_for_row", lambda r: cell)
    fn = cli._cell_fn(frozenset(), {31: _OpenGraph()}, lambda m: ())
    assert fn(row).approach_candidates == ()


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


def test_a_trainer_battle_in_an_arm_is_not_a_trainer_match():
    """Mawuli (map068/ev014) fights in the "Wanna fight? -> Yes" arm: the
    page goes to the generic template, which answers the menu per arm."""
    from rpg2gba.beat_floor.lookup import floor_for_row
    from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch

    def match(page):
        return ArchetypeMatch("trainer", 0, 0, {}, {page: "battle"}, {page: "beat"})

    arm_battle, page_battle = "map068/ev014/p0", "map033/ev053/p0"
    floors = {r: floor_for_row(r) for r in (arm_battle, page_battle)}
    assert not cli._battle_on_page(match(arm_battle), floors)
    assert cli._battle_on_page(match(page_battle), floors)


def test_a_randomized_flavour_npc_goes_to_the_generic_template():
    from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch

    def flavour(variant):
        return ArchetypeMatch("flavour_npc", 48, 11, {"variant": variant},
                              {"map048/ev011/p0": "talk"}, {"map048/ev011/p0": "beat"})

    assert cli._generic_reads_it_better(flavour("randomized"), {})
    assert not cli._generic_reads_it_better(flavour("plain"), {})
