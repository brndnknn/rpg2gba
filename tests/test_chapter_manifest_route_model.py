"""`chapter_manifest.route_model` -- the concrete `checker.RouteModel`.

The adapter joins the two halves `RULE_ROUTE_ORDER` compares: the planned
order, from `reference/routes/<chapter>.route.json`, and the registered
order, from the chapter's own playtest module. Its interesting behaviour is
the degrade path -- a chapter that has not been routed yet must leave the
rule unenforced rather than fail, while a route file that exists but is
corrupt must raise (CLAUDE.md §4.5).

Chapter modules are faked into `sys.modules` the way
`tests/test_chapter_predecessor.py` does, so no real chapter module (and no
ROM) is needed.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.checker import (
    RULE_FLOOR_MODEL_UNENFORCED,
    RULE_ROUTE_APPROACH,
    check_chapter,
)
from rpg2gba.chapter_manifest.route_model import PlanRouteModel, build_route_model
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.routing.plan import (
    PrecedenceEdge,
    RoutePlanError,
    RouteLeg,
    RouteNode,
    RoutePlan,
    RouteSegment,
    write_plan,
)

PKG = "rpg2gba.playtest.chapters_gen"  # the default suite since 2026-10-03
# A route plan only ever approves a HAND-suite walk: `build_route_model`
# returns None for a generated chapter (PROJECT_TODO #124), so the tests that
# exercise the rule's mechanics install their chapters in the hand package.
HAND_PKG = "rpg2gba.playtest.chapters"


def _install_chapter(name: str, group_ids: list[str], pkg: str = PKG) -> None:
    """Fake a chapter module whose beats register the given groups, in order."""
    builder = ChapterBuilder(name, f"{name} test chapter")
    for group_id in group_ids:
        def _run(emu: object) -> None:  # pragma: no cover - never executed
            raise AssertionError("beat body must not run in this test")

        builder.beat(
            group_id, f"{group_id} description",
            map_constant="MAP_G1", at=(1, 1), group=group_id,
        )(_run)

    module = types.ModuleType(f"{pkg}.{name}")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    sys.modules[f"{pkg}.{name}"] = module


def _install_chapter_with_predecessor(
    name: str, predecessor: str, group_ids: list[str], pkg: str = PKG,
) -> None:
    """Like `_install_chapter`, but goes through
    `ChapterBuilder(predecessor=...)` so the built chapter's `groups()`
    genuinely contains inherited `<predecessor>:<group>` ids via the real
    `_prefix_beat` path, not a hand-fabricated `":"`-containing id."""
    suite = "gen" if pkg == PKG else "hand"
    builder = ChapterBuilder(name, f"{name} test chapter", predecessor=predecessor, suite=suite)
    for group_id in group_ids:
        def _run(emu: object) -> None:  # pragma: no cover - never executed
            raise AssertionError("beat body must not run in this test")

        builder.beat(
            group_id, f"{group_id} description",
            map_constant="MAP_G1", at=(1, 1), group=group_id,
        )(_run)

    module = types.ModuleType(f"{pkg}.{name}")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    sys.modules[f"{pkg}.{name}"] = module


def _cleanup_chapter(name: str, pkg: str = PKG) -> None:
    sys.modules.pop(f"{pkg}.{name}", None)


def _install_chapter_at(name: str, beats: list[tuple[str, tuple[int, int]]]) -> None:
    """Like `_install_chapter`, but each beat gets its own `at=` cell --
    needed to exercise `declared_beat_cell`, which `_install_chapter`'s
    uniform `at=(1, 1)` can't distinguish between beats."""
    builder = ChapterBuilder(name, f"{name} test chapter")
    for group_id, cell in beats:
        def _run(emu: object) -> None:  # pragma: no cover - never executed
            raise AssertionError("beat body must not run in this test")

        builder.beat(
            group_id, f"{group_id} description",
            map_constant="MAP_G1", at=cell, group=group_id,
        )(_run)

    module = types.ModuleType(f"{PKG}.{name}")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    sys.modules[f"{PKG}.{name}"] = module


def _inject_chosen_approaches(
    path: Path, approaches: dict[int, dict[str, str] | None],
) -> None:
    """Patch `chosen_approach` onto specific node indices of an
    already-written plan file.

    `routing.plan.RouteNode`/`write_plan` don't carry this field yet -- it's
    landing there alongside the route-solver work this test suite must not
    block on (see the task brief: "write your code and tests against
    synthetic fixtures you construct yourself ... do not block on the real
    artifact"). Patching the JSON directly after `write_plan` lets these
    tests exercise the agreed on-disk shape (`{"side": ..., "resolver":
    ...}` on a group node) without needing that dataclass change landed
    first."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for node in data["nodes"]:
        if node["index"] in approaches:
            node["chosen_approach"] = approaches[node["index"]]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _plan(chapter_id: str, module: str, group_ids: list[str],
          precedence: tuple[PrecedenceEdge, ...] = ()) -> RoutePlan:
    nodes = [RouteNode(index=0, kind="entry", map_id=1, cell=(0, 0))]
    for i, group_id in enumerate(group_ids, start=1):
        nodes.append(RouteNode(
            index=i, kind="group", map_id=1, cell=(i, 0),
            group=group_id, beats=(group_id,),
        ))
    nodes.append(RouteNode(index=len(nodes), kind="exit", map_id=1, cell=(0, 0)))

    segments = tuple(
        RouteSegment(
            from_index=i, to_index=i + 1,
            legs=(RouteLeg(map_id=1, tiles=((i, 0), (i + 1, 0))),),
            tile_count=1,
        )
        for i in range(len(nodes) - 1)
    )
    return RoutePlan(
        chapter_id=chapter_id, chapter_module=module,
        nodes=tuple(nodes), segments=segments, precedence=precedence,
        tile_cost=len(segments), solver_method="greedy+2opt",
    )


def test_returns_none_when_no_route_plan_exists(tmp_path: Path) -> None:
    """The ordinary state of an unrouted chapter -- unenforced, not an error."""
    routes = tmp_path / "routes"
    routes.mkdir()
    assert build_route_model("CH99", root=routes) is None


def test_returns_none_when_the_named_module_does_not_load(tmp_path: Path) -> None:
    routes = tmp_path / "routes"
    routes.mkdir(parents=True)
    write_plan(_plan("CH99", "nosuchmodule", ["G1"]), routes / "CH99.route.json")

    assert build_route_model("CH99", root=routes) is None


def test_corrupt_route_plan_raises_rather_than_degrading(tmp_path: Path) -> None:
    routes = tmp_path / "routes"
    routes.mkdir(parents=True)
    (routes / "CH99.route.json").write_text('{"schema": 1}', encoding="utf-8")

    with pytest.raises(Exception):
        build_route_model("CH99", root=routes)


def test_reports_planned_and_registered_orders(tmp_path: Path) -> None:
    _install_chapter("someplace", ["G1", "G2", "G3"])
    try:
        routes = tmp_path / "routes"
        routes.mkdir(parents=True)
        write_plan(
            _plan("CH99", "someplace", ["G2", "G1", "G3"]),
            routes / "CH99.route.json",
        )

        model = build_route_model("CH99", root=routes)
        assert isinstance(model, PlanRouteModel)
        assert model.planned_group_order() == ("G2", "G1", "G3")
        assert model.registered_group_order() == ("G1", "G2", "G3")
    finally:
        _cleanup_chapter("someplace")


def test_translates_precedence_edges(tmp_path: Path) -> None:
    _install_chapter("someplace", ["G1", "G2"])
    try:
        routes = tmp_path / "routes"
        routes.mkdir(parents=True)
        write_plan(
            _plan("CH99", "someplace", ["G1", "G2"],
                  precedence=(PrecedenceEdge(
                      before="G1", after="G2",
                      reason="self_switch:A map035/ev014"),)),
            routes / "CH99.route.json",
        )

        model = build_route_model("CH99", root=routes)
        assert model is not None
        edges = model.precedence_edges()
        assert len(edges) == 1
        assert (edges[0].before, edges[0].after) == ("G1", "G2")
        assert edges[0].reason == "self_switch:A map035/ev014"
    finally:
        _cleanup_chapter("someplace")


def test_explicit_route_path_overrides_the_default_location(tmp_path: Path) -> None:
    _install_chapter("someplace", ["G1"])
    try:
        elsewhere = tmp_path / "elsewhere.route.json"
        write_plan(_plan("CH99", "someplace", ["G1"]), elsewhere)

        model = build_route_model("CH99", route=elsewhere, root=tmp_path)
        assert model is not None
        assert model.planned_group_order() == ("G1",)
    finally:
        _cleanup_chapter("someplace")


def test_a_generated_chapter_is_never_checked_against_a_route_plan(
    tmp_path: Path,
) -> None:
    """PROJECT_TODO #124: a gen suite loads no route plan (the runner's
    ruling), so the checker must not compare one either -- a plan on disk
    approved the deleted hand walk, and every regenerated group read as
    unplanned (CH05: 27 `route_order` errors). The rule degrades to its
    unenforced warning, exactly as for an unrouted chapter."""
    _install_chapter("gen_predecessor", ["P1"])
    try:
        _install_chapter_with_predecessor("gen_successor", "gen_predecessor", ["G1", "G2"])
        try:
            routes = tmp_path / "routes"
            routes.mkdir(parents=True)
            write_plan(_plan("CH99", "gen_successor", ["G1", "G2"]), routes / "CH99.route.json")
            assert build_route_model("CH99", root=routes) is None
        finally:
            _cleanup_chapter("gen_successor")
    finally:
        _cleanup_chapter("gen_predecessor")


def test_registered_group_order_excludes_inherited_predecessor_groups(
    tmp_path: Path,
) -> None:
    """Regression for the CH04 bug: a chapter with a predecessor inherits
    that predecessor's beats/groups, renamed `<owner>:<name>`
    (`playtest.chapter._prefix_beat`). `build_route_model` must drop those
    from `registered_group_order()` -- same filter the solver applies
    (`routing.solver._solvable_groups`) -- or every inherited group reads as
    "registered but never planned"."""
    _install_chapter("predecessor_place", ["P1", "P2"], pkg=HAND_PKG)
    try:
        _install_chapter_with_predecessor(
            "successor_place", "predecessor_place", ["G1", "G2"],
            pkg=HAND_PKG)
        try:
            # Sanity check the fixture actually goes through real prefixing
            # before trusting the filtered assertion below.
            chapter = sys.modules[f"{HAND_PKG}.successor_place"].CHAPTER
            all_group_ids = [g.group_id for g in chapter.groups()]
            assert all_group_ids == [
                "predecessor_place:P1", "predecessor_place:P2", "G1", "G2"]

            routes = tmp_path / "routes"
            routes.mkdir(parents=True)
            write_plan(
                _plan("CH99", "successor_place", ["G1", "G2"]),
                routes / "CH99.route.json",
            )

            model = build_route_model("CH99", root=routes)
            assert model is not None
            assert model.registered_group_order() == ("G1", "G2")
        finally:
            _cleanup_chapter("successor_place", pkg=HAND_PKG)
    finally:
        _cleanup_chapter("predecessor_place", pkg=HAND_PKG)


def test_rule_route_order_is_clean_despite_predecessor_when_plan_matches(
    tmp_path: Path,
) -> None:
    """Consequence at the rule level: with a plan that matches the
    chapter's own groups, `RULE_ROUTE_ORDER` produces zero findings even
    though the chapter has a predecessor -- before the fix, the 60+
    inherited groups each surfaced as a spurious `registered_only` error."""
    _install_chapter("predecessor_place2", ["P1", "P2"], pkg=HAND_PKG)
    try:
        _install_chapter_with_predecessor(
            "successor_place2", "predecessor_place2", ["G1", "G2"],
            pkg=HAND_PKG)
        try:
            routes = tmp_path / "routes"
            routes.mkdir(parents=True)
            write_plan(
                _plan("CH99", "successor_place2", ["G1", "G2"]),
                routes / "CH99.route.json",
            )

            model = build_route_model("CH99", root=routes)
            assert model is not None
            findings = check_chapter([], {}, route=model)
            # Filter the C5 floor rule's unenforced warning -- this test
            # supplies no `floor_coverage=` and is about route order, not
            # floor coverage.
            relevant = [f for f in findings if f.rule != RULE_FLOOR_MODEL_UNENFORCED]
            assert relevant == []
        finally:
            _cleanup_chapter("successor_place2", pkg=HAND_PKG)
    finally:
        _cleanup_chapter("predecessor_place2", pkg=HAND_PKG)


# --- chosen_approach: does the beat's declared cell match the plan's? ------


def test_planned_approaches_empty_when_plan_carries_no_chosen_approach(
    tmp_path: Path,
) -> None:
    """An older plan artifact, or one with no side-sensitive stops --
    `planned_approaches()` must report nothing to check, not raise and not
    fabricate an entry."""
    _install_chapter_at("approach_place1", [("G1", (1, 0))])
    try:
        routes = tmp_path / "routes"
        routes.mkdir(parents=True)
        write_plan(_plan("CH99", "approach_place1", ["G1"]),
                   routes / "CH99.route.json")

        model = build_route_model("CH99", root=routes)
        assert model is not None
        assert model.planned_approaches() == ()
    finally:
        _cleanup_chapter("approach_place1")


def test_rule_route_approach_clean_when_declared_cell_matches_plan(
    tmp_path: Path,
) -> None:
    _install_chapter_at("approach_place2", [("G1", (1, 0))])
    try:
        routes = tmp_path / "routes"
        routes.mkdir(parents=True)
        path = routes / "CH99.route.json"
        write_plan(_plan("CH99", "approach_place2", ["G1"]), path)
        _inject_chosen_approaches(path, {
            1: {"side": "east", "resolver": "approach_to(MAP_G1, ev1, "
                                              "prefer=\"east\")"},
        })

        model = build_route_model("CH99", root=routes)
        assert model is not None
        approaches = model.planned_approaches()
        assert len(approaches) == 1
        assert approaches[0].side == "east"
        assert approaches[0].cell == (1, 0)
        assert model.declared_beat_cell("G1") == (1, 0)

        findings = check_chapter([], {}, route=model)
        assert all(f.rule != RULE_ROUTE_APPROACH for f in findings)
    finally:
        _cleanup_chapter("approach_place2")


def test_rule_route_approach_errors_when_declared_cell_disagrees_with_plan(
    tmp_path: Path,
) -> None:
    _install_chapter_at("approach_place3", [("G1", (9, 9))])
    try:
        routes = tmp_path / "routes"
        routes.mkdir(parents=True)
        path = routes / "CH99.route.json"
        write_plan(_plan("CH99", "approach_place3", ["G1"]), path)
        _inject_chosen_approaches(path, {
            1: {"side": "east", "resolver": "approach_to(MAP_G1, ev1, "
                                              "prefer=\"east\")"},
        })

        model = build_route_model("CH99", root=routes)
        assert model is not None

        findings = check_chapter([], {}, route=model)
        approach_findings = [f for f in findings if f.rule == RULE_ROUTE_APPROACH]
        assert len(approach_findings) == 1
        finding = approach_findings[0]
        assert finding.severity == "error"
        assert "'G1'" in finding.message
        assert "(1, 0)" in finding.message  # the plan's cell for node 1
        assert "(9, 9)" in finding.message  # G1's declared cell
        assert "'east'" in finding.message
        assert 'approach_to(MAP_G1, ev1, prefer="east")' in finding.message
    finally:
        _cleanup_chapter("approach_place3")


def test_declared_beat_cell_none_when_beat_has_no_location(
    tmp_path: Path,
) -> None:
    """A registered beat with no `at=`/`locations=` at all -- the ordinary
    "not enforceable for this beat" case, not a mismatch."""
    builder = ChapterBuilder("approach_place4", "test chapter")

    def _run(emu: object) -> None:  # pragma: no cover - never executed
        raise AssertionError("beat body must not run in this test")

    builder.beat("G1", "G1 description", group="G1")(_run)
    module = types.ModuleType(f"{PKG}.approach_place4")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    sys.modules[f"{PKG}.approach_place4"] = module
    try:
        routes = tmp_path / "routes"
        routes.mkdir(parents=True)
        path = routes / "CH99.route.json"
        write_plan(_plan("CH99", "approach_place4", ["G1"]), path)
        _inject_chosen_approaches(path, {
            1: {"side": "east", "resolver": "approach_to(MAP_G1, ev1, "
                                              "prefer=\"east\")"},
        })

        model = build_route_model("CH99", root=routes)
        assert model is not None
        assert model.declared_beat_cell("G1") is None
    finally:
        _cleanup_chapter("approach_place4")


def test_malformed_chosen_approach_raises_rather_than_degrading(
    tmp_path: Path,
) -> None:
    """A `chosen_approach` that IS present but missing/extra keys is a real
    fault in the artifact (CLAUDE.md §4.5) -- not "the field doesn't exist
    yet", which degrades quietly instead."""
    _install_chapter_at("approach_place5", [("G1", (1, 0))])
    try:
        routes = tmp_path / "routes"
        routes.mkdir(parents=True)
        path = routes / "CH99.route.json"
        write_plan(_plan("CH99", "approach_place5", ["G1"]), path)
        _inject_chosen_approaches(path, {1: {"side": "east"}})  # missing resolver

        with pytest.raises(RoutePlanError):
            build_route_model("CH99", root=routes)
    finally:
        _cleanup_chapter("approach_place5")
