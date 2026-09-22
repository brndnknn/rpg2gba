"""End-to-end tests for `rpg2gba.beat_gen.__main__` on CH05 (C6 Task 9).

This is C6_GENERATOR_PLAN.md C1's checkpoint: "CH05 regenerates and diffs
acceptably". It needs Tasks 1-8, the staged build under
`output/uranium-build/`, and (for the last test) C7 Task 1's frozen file.

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 9.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

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
    return out, cli.write_outputs(plan, out)


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
    assert len(plan.beats) == 20
    assert {e.status for e in plan.elsewhere} == {"blocked"}   # the two surf items
    assert plan.route is not None


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
    assert [p.name for p in paths] == ["ch05.generated.py", "CH05.review.md", "CH05.route.json"]
    assert all(p.parent == out and p.exists() for p in paths)


def test_rerun_is_byte_identical(plan, written, tmp_path):
    _, first = written
    second = cli.write_outputs(plan, tmp_path)
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
