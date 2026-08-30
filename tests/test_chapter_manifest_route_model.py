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

import sys
import types
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.checker import check_chapter
from rpg2gba.chapter_manifest.route_model import PlanRouteModel, build_route_model
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.routing.plan import (
    PrecedenceEdge,
    RouteLeg,
    RouteNode,
    RoutePlan,
    RouteSegment,
    write_plan,
)

PKG = "rpg2gba.playtest.chapters"


def _install_chapter(name: str, group_ids: list[str]) -> None:
    """Fake a chapter module whose beats register the given groups, in order."""
    builder = ChapterBuilder(name, f"{name} test chapter")
    for group_id in group_ids:
        def _run(emu: object) -> None:  # pragma: no cover - never executed
            raise AssertionError("beat body must not run in this test")

        builder.beat(
            group_id, f"{group_id} description",
            map_constant="MAP_G1", at=(1, 1), group=group_id,
        )(_run)

    module = types.ModuleType(f"{PKG}.{name}")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    sys.modules[f"{PKG}.{name}"] = module


def _install_chapter_with_predecessor(
    name: str, predecessor: str, group_ids: list[str],
) -> None:
    """Like `_install_chapter`, but goes through
    `ChapterBuilder(predecessor=...)` so the built chapter's `groups()`
    genuinely contains inherited `<predecessor>:<group>` ids via the real
    `_prefix_beat` path, not a hand-fabricated `":"`-containing id."""
    builder = ChapterBuilder(name, f"{name} test chapter", predecessor=predecessor)
    for group_id in group_ids:
        def _run(emu: object) -> None:  # pragma: no cover - never executed
            raise AssertionError("beat body must not run in this test")

        builder.beat(
            group_id, f"{group_id} description",
            map_constant="MAP_G1", at=(1, 1), group=group_id,
        )(_run)

    module = types.ModuleType(f"{PKG}.{name}")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    sys.modules[f"{PKG}.{name}"] = module


def _cleanup_chapter(name: str) -> None:
    sys.modules.pop(f"{PKG}.{name}", None)


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


def test_registered_group_order_excludes_inherited_predecessor_groups(
    tmp_path: Path,
) -> None:
    """Regression for the CH04 bug: a chapter with a predecessor inherits
    that predecessor's beats/groups, renamed `<owner>:<name>`
    (`playtest.chapter._prefix_beat`). `build_route_model` must drop those
    from `registered_group_order()` -- same filter the solver applies
    (`routing.solver._solvable_groups`) -- or every inherited group reads as
    "registered but never planned"."""
    _install_chapter("predecessor_place", ["P1", "P2"])
    try:
        _install_chapter_with_predecessor(
            "successor_place", "predecessor_place", ["G1", "G2"])
        try:
            # Sanity check the fixture actually goes through real prefixing
            # before trusting the filtered assertion below.
            chapter = sys.modules[f"{PKG}.successor_place"].CHAPTER
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
            _cleanup_chapter("successor_place")
    finally:
        _cleanup_chapter("predecessor_place")


def test_rule_route_order_is_clean_despite_predecessor_when_plan_matches(
    tmp_path: Path,
) -> None:
    """Consequence at the rule level: with a plan that matches the
    chapter's own groups, `RULE_ROUTE_ORDER` produces zero findings even
    though the chapter has a predecessor -- before the fix, the 60+
    inherited groups each surfaced as a spurious `registered_only` error."""
    _install_chapter("predecessor_place2", ["P1", "P2"])
    try:
        _install_chapter_with_predecessor(
            "successor_place2", "predecessor_place2", ["G1", "G2"])
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
            assert findings == []
        finally:
            _cleanup_chapter("successor_place2")
    finally:
        _cleanup_chapter("predecessor_place2")
