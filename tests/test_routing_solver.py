"""Tests for `rpg2gba.routing.solver`.

Geometry is built directly (no `output/`/`engine/` dependency), following the
style of `tests/test_routing_pathing.py` and `tests/test_traversal_reachability
.py`: `MapGraph`/`TriggerOverlay`/`WorldGraph` constructed by hand, `Chapter`
built via `ChapterBuilder` as `tests/test_chapter_predecessor.py` does, and a
fake map-constant registry (`map_ids=`) instead of the real persisted state.

Most scenarios use small "corridor" maps whose only job is to realize an
exact, hand-picked tile cost between two points -- `_corridor` below builds a
straight open N-tile map plus the four warp edges needed to traverse it in
either direction, optionally with a foreign trigger cell partway along it.
This lets a cost MATRIX be dialed in directly rather than reverse-engineered
from realistic geography, which is what the 2-opt and precedence tests need.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from rpg2gba.chapter_manifest.schema import ManifestRow, PageCondition
from rpg2gba.playtest.chapter import Beat, BeatLocation, Chapter, ChapterBuilder
from rpg2gba.traversal.graph import MapGraph
from rpg2gba.traversal.triggers import Certainty, TriggerKind, TriggerOverlay, TriggerRef
from rpg2gba.traversal.world import WorldEdge, WorldGraph

from rpg2gba.routing.plan import PrecedenceEdge, RoutePlan, plan_from_dict, plan_to_dict, write_plan
from rpg2gba.routing.solver import RouteSolverError, solve_route


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _trivial_graph(map_id: int) -> MapGraph:
    return MapGraph(map_id=map_id, width=1, height=1, tileset_id=0, blocked={(0, 0): False})


def _empty_overlay(map_id: int) -> TriggerOverlay:
    return TriggerOverlay(map_id=map_id, tiles={})


def _corridor_graph(map_id: int, length: int) -> MapGraph:
    return MapGraph(
        map_id=map_id, width=length + 1, height=1, tileset_id=0,
        blocked={(x, 0): False for x in range(length + 1)},
    )


def _foreign_ref(script: str) -> TriggerRef:
    return TriggerRef(
        kind=TriggerKind.COORD_EVENT, script=script, certainty=Certainty.CERTAIN,
        owner_xy=None, detail="unconditional",
    )


def _corridor(
    a_map: int, b_map: int, corridor_map: int, length: int, *, foreign_script: str | None = None,
) -> tuple[list[WorldEdge], MapGraph, TriggerOverlay]:
    """A straight `length`-tile corridor between two 1-cell "home" maps,
    traversable in either direction, at exactly `length` tiles of cost.
    `foreign_script`, if given, flags the corridor's midpoint cell as a
    foreign trigger (so any traversal of it -- there is no detour on a
    straight corridor -- is a forced crossing)."""
    graph = _corridor_graph(corridor_map, length)
    if foreign_script is not None:
        mid = length // 2
        overlay = TriggerOverlay(map_id=corridor_map, tiles={(mid, 0): [_foreign_ref(foreign_script)]})
    else:
        overlay = _empty_overlay(corridor_map)
    edges = [
        WorldEdge(src_map=a_map, dst_map=corridor_map, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=corridor_map * 10 + 1),
        WorldEdge(src_map=corridor_map, dst_map=b_map, kind="warp",
                  src_cell=(length, 0), dst_cell=(0, 0), event_id=corridor_map * 10 + 2),
        WorldEdge(src_map=b_map, dst_map=corridor_map, kind="warp",
                  src_cell=(0, 0), dst_cell=(length, 0), event_id=corridor_map * 10 + 3),
        WorldEdge(src_map=corridor_map, dst_map=a_map, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=corridor_map * 10 + 4),
    ]
    return edges, graph, overlay


def _world(edges: list[WorldEdge], map_ids: set[int]) -> WorldGraph:
    return WorldGraph(
        edges=edges, names={m: f"Map{m:03d}" for m in map_ids}, map_ids=frozenset(map_ids),
        maps_without_info=frozenset(), infos_without_map=frozenset(),
        variable_warp_count=0, variable_warp_maps={},
    )


class _World:
    """Accumulates corridor edges/graphs/overlays across several `add()` calls
    so a test can describe a whole cost matrix declaratively."""

    def __init__(self) -> None:
        self.edges: list[WorldEdge] = []
        self.graphs: dict[int, MapGraph] = {}
        self.overlays: dict[int, TriggerOverlay] = {}
        self.map_ids: set[int] = set()

    def home(self, map_id: int) -> None:
        self.graphs[map_id] = _trivial_graph(map_id)
        self.overlays[map_id] = _empty_overlay(map_id)
        self.map_ids.add(map_id)

    def add(
        self, a_map: int, b_map: int, corridor_map: int, length: int, *,
        foreign_script: str | None = None,
    ) -> None:
        edges, graph, overlay = _corridor(a_map, b_map, corridor_map, length, foreign_script=foreign_script)
        self.edges.extend(edges)
        self.graphs[corridor_map] = graph
        self.overlays[corridor_map] = overlay
        self.map_ids.add(corridor_map)

    def build(self) -> WorldGraph:
        return _world(self.edges, self.map_ids)


def _chapter_with_groups(*group_specs: tuple[str, str, int]) -> tuple[Chapter, dict[str, int]]:
    """Build a chapter with one beat per `(group_id, map_constant, dummy_id)`
    spec, each beat's own group. Returns the chapter and a `map_ids` table
    mapping each map_constant to its dummy uranium id."""
    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")
    map_ids: dict[str, int] = {}
    for group_id, map_constant, uranium_id in group_specs:
        map_ids[map_constant] = uranium_id

        def make_beat(mc: str) -> None:
            @builder.beat(group_id, f"beat for {group_id}", map_constant=mc, at=(0, 0),
                          group=group_id)
            def _run(emu) -> None:  # noqa: ANN001
                pass

        make_beat(map_constant)
    return builder.build(), map_ids


_PLAYTEST_CHAPTERS_PKG = "rpg2gba.playtest.chapters"


def _install_chapter_module(name: str, chapter: Chapter) -> None:
    """Register `chapter` as `rpg2gba.playtest.chapters.<name>`'s CHAPTER, the
    sys.modules-faking technique `tests/test_chapter_predecessor.py` uses --
    `ChapterBuilder(predecessor=...)`'s `build()` resolves a predecessor via
    `load_chapter`, which is just `importlib.import_module` + `getattr(...,
    "CHAPTER")`."""
    module = types.ModuleType(f"{_PLAYTEST_CHAPTERS_PKG}.{name}")
    module.CHAPTER = chapter
    sys.modules[f"{_PLAYTEST_CHAPTERS_PKG}.{name}"] = module


def _uninstall_chapter_module(name: str) -> None:
    sys.modules.pop(f"{_PLAYTEST_CHAPTERS_PKG}.{name}", None)


# ---------------------------------------------------------------------------
# precedence derivation + enforcement
# ---------------------------------------------------------------------------


def _self_switch_rows() -> tuple[ManifestRow, ManifestRow]:
    writer = ManifestRow(
        row_id="map010/ev001/p0", kind="page", map_id=10, content_hash="w",
        event_id=1, page_idx=0, effects=("self_switch_write",),
    )
    dependent = ManifestRow(
        row_id="map010/ev001/p1", kind="page", map_id=10, content_hash="d",
        event_id=1, page_idx=1, condition=PageCondition(self_switch_ch="A"),
    )
    return writer, dependent


def test_precedence_edge_derived_and_constrains_chosen_order() -> None:
    writer, dependent = _self_switch_rows()

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("G1", "group 1", map_constant="MAP_G1", at=(0, 0), group="G1",
                  rows=(dependent.row_id,))
    def g1(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("G2", "group 2", map_constant="MAP_G2", at=(0, 0), group="G2",
                  rows=(writer.row_id,))
    def g2(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()

    w = _World()
    w.home(100)  # entry
    w.home(101)  # G1
    w.home(102)  # G2
    w.home(103)  # exit
    w.add(100, 101, 201, 1)    # entry -> G1: cheap
    w.add(100, 102, 202, 5)    # entry -> G2: expensive
    w.add(101, 102, 203, 1)    # G1 <-> G2: cheap
    w.add(101, 103, 204, 5)    # G1 -> exit: expensive
    w.add(102, 103, 205, 1)    # G2 -> exit: cheap

    map_ids = {"MAP_G1": 101, "MAP_G2": 102}

    route = solve_route(
        chapter, "TESTCH",
        manifest_rows=[writer, dependent],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(103, (0, 0)),
        map_ids=map_ids,
    )

    assert route.precedence == (
        PrecedenceEdge(before="G2", after="G1", reason="self_switch:A map010/ev001"),
    )

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["G2", "G1"]
    # forced order costs 5 (entry->G2) + 1 (G2->G1) + 5 (G1->exit) = 11, even
    # though entry->G1->G2->exit (1+1+1=3) is far cheaper -- precedence wins.
    assert route.tile_cost == 11


def test_precedence_skips_silently_when_neither_side_is_claimed() -> None:
    writer, dependent = _self_switch_rows()
    chapter, map_ids = _chapter_with_groups(("G1", "MAP_G1", 101))

    w = _World()
    w.home(100)
    w.home(101)
    w.home(103)
    w.add(100, 101, 201, 1)
    w.add(101, 103, 202, 1)

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[writer, dependent],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )
    assert route.precedence == ()


# ---------------------------------------------------------------------------
# 2-opt improvement
# ---------------------------------------------------------------------------


def test_two_opt_improves_a_bad_greedy_seed() -> None:
    chapter, map_ids = _chapter_with_groups(
        ("P1", "MAP_P1", 101), ("P2", "MAP_P2", 102), ("P3", "MAP_P3", 103),
    )

    w = _World()
    for mid in (100, 101, 102, 103, 104):  # entry, P1, P2, P3, exit
        w.home(mid)

    # Cost matrix engineered so greedy nearest-neighbour (E->P1->P3->P2->exit,
    # cost 2+3+2+10=17) is beaten by E->P1->P2->P3->exit (2+10+2+2=16), a move
    # 2-opt reaches by reversing the [P3, P2] tail of the greedy seed.
    w.add(100, 101, 201, 2)   # E-P1
    w.add(100, 102, 202, 3)   # E-P2
    w.add(100, 103, 203, 10)  # E-P3
    w.add(101, 102, 204, 10)  # P1-P2
    w.add(101, 103, 205, 3)   # P1-P3
    w.add(102, 103, 206, 2)   # P2-P3
    w.add(101, 104, 207, 10)  # P1-exit
    w.add(102, 104, 208, 10)  # P2-exit
    w.add(103, 104, 209, 2)   # P3-exit

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(104, (0, 0)), map_ids=map_ids,
    )

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["P1", "P2", "P3"]
    assert route.tile_cost == 16
    assert route.solver_method == "greedy+2opt"


# ---------------------------------------------------------------------------
# trigger crossing preference / unavoidability
# ---------------------------------------------------------------------------


def test_prefers_crossing_free_order_over_a_shorter_crossing_order() -> None:
    chapter, map_ids = _chapter_with_groups(("A", "MAP_A", 101), ("B", "MAP_B", 102))

    w = _World()
    w.home(100)  # entry
    w.home(101)  # A
    w.home(102)  # B
    w.home(103)  # exit

    w.add(100, 101, 201, 6)  # entry -> A: long way around, no crossing
    w.add(100, 102, 202, 2, foreign_script="map099/someone_elses_event")  # entry -> B: short, crosses
    w.add(101, 102, 203, 1)  # A -> B: cheap
    w.add(102, 103, 204, 1)  # B -> exit: cheap

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["A", "B"]
    assert route.tile_cost == 6 + 1 + 1
    assert all(s.crossed_foreign_triggers == () for s in route.segments)


def test_returns_a_plan_with_crossing_recorded_when_unavoidable() -> None:
    chapter, map_ids = _chapter_with_groups(("B", "MAP_B", 102))

    w = _World()
    w.home(100)  # entry
    w.home(102)  # B
    w.home(103)  # exit
    w.add(100, 102, 202, 2, foreign_script="map099/someone_elses_event")
    w.add(102, 103, 204, 1)

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )

    assert route.tile_cost == 3
    first_segment = route.segments[0]
    assert len(first_segment.crossed_foreign_triggers) == 1
    crossing = first_segment.crossed_foreign_triggers[0]
    assert crossing.script == "map099/someone_elses_event"
    assert crossing.certainty == "certain"


# ---------------------------------------------------------------------------
# fail-loud paths
# ---------------------------------------------------------------------------


def test_group_with_no_location_fails_loud() -> None:
    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("G1", "no location", group="G1")
    def g1(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()

    w = _World()
    w.home(100)
    w.home(103)
    w.add(100, 103, 201, 1)

    with pytest.raises(RouteSolverError, match="G1"):
        solve_route(
            chapter, "TESTCH", manifest_rows=[],
            graphs=w.graphs, overlays=w.overlays, world=w.build(),
            entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids={},
        )


def test_unroutable_pair_fails_loud() -> None:
    chapter, map_ids = _chapter_with_groups(("Lost", "MAP_LOST", 999))

    w = _World()
    w.home(100)  # entry
    w.home(999)  # "Lost" -- deliberately no edges connect it to anything
    w.home(103)  # exit

    with pytest.raises(RouteSolverError, match="dead-end"):
        solve_route(
            chapter, "TESTCH", manifest_rows=[],
            graphs=w.graphs, overlays=w.overlays, world=w.build(),
            entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
        )


# ---------------------------------------------------------------------------
# default entry/exit derivation
# ---------------------------------------------------------------------------


def test_default_entry_and_exit_derived_from_first_and_last_beat() -> None:
    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("Start", "chapter start", map_constant="MAP_E", at=(0, 0))
    def start(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("Finish", "chapter end", map_constant="MAP_EX", at=(0, 0))
    def finish(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_E": 100, "MAP_EX": 103}

    w = _World()
    w.home(100)
    w.home(103)
    w.add(100, 103, 201, 4)

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(), map_ids=map_ids,
    )

    assert route.nodes[0].kind == "entry"
    assert (route.nodes[0].map_id, route.nodes[0].cell) == (100, (0, 0))
    assert route.nodes[-1].kind == "exit"
    assert (route.nodes[-1].map_id, route.nodes[-1].cell) == (103, (0, 0))


# ---------------------------------------------------------------------------
# round trip / idempotence
# ---------------------------------------------------------------------------


def _simple_route() -> RoutePlan:
    chapter, map_ids = _chapter_with_groups(("A", "MAP_A", 101))
    w = _World()
    w.home(100)
    w.home(101)
    w.home(103)
    w.add(100, 101, 201, 2)
    w.add(101, 103, 202, 2)
    return solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )


def test_plan_round_trips_through_to_dict_and_from_dict() -> None:
    route = _simple_route()
    assert plan_from_dict(plan_to_dict(route)) == route


def test_solving_twice_yields_byte_identical_written_output(tmp_path) -> None:  # noqa: ANN001
    route1 = _simple_route()
    route2 = _simple_route()

    path1 = tmp_path / "one.json"
    path2 = tmp_path / "two.json"
    write_plan(route1, path1)
    write_plan(route2, path2)

    assert path1.read_text(encoding="utf-8") == path2.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# predecessor chaining: inherited beats/groups must never be routed
# ---------------------------------------------------------------------------


def test_inherited_groups_excluded_and_entry_exit_use_own_beats() -> None:
    predecessor_builder = ChapterBuilder("predch", doc="reference/chapters/00-pred.md")

    @predecessor_builder.beat("B1", "predecessor's own beat",
                              map_constant="MAP_PRED", at=(0, 0))
    def pred_b1(emu) -> None:  # noqa: ANN001
        pass

    predecessor = predecessor_builder.build()
    _install_chapter_module("predch", predecessor)
    try:
        builder = ChapterBuilder("childch", doc="reference/chapters/00-child.md",
                                  predecessor="predch")

        @builder.beat("Start", "child's own first beat", map_constant="MAP_START", at=(0, 0))
        def start(emu) -> None:  # noqa: ANN001
            pass

        @builder.beat("G1", "child's own group", map_constant="MAP_G1", at=(0, 0), group="G1")
        def g1(emu) -> None:  # noqa: ANN001
            pass

        chapter = builder.build()
        # sanity: predecessor chaining did prepend an inherited beat, so this
        # test is actually exercising the filter, not a no-op chapter.
        assert [b.name for b in chapter.beats] == ["predch:B1", "Start", "G1"]

        map_ids = {"MAP_PRED": 999, "MAP_START": 100, "MAP_G1": 101}

        w = _World()
        w.home(999)  # predecessor's map -- must never be touched by routing
        w.home(100)  # Start (own entry)
        w.home(101)  # G1 (own group / exit)
        w.add(100, 101, 201, 3)

        route = solve_route(
            chapter, "CHILDCH", manifest_rows=[],
            graphs=w.graphs, overlays=w.overlays, world=w.build(), map_ids=map_ids,
        )

        group_ids = [n.group for n in route.nodes if n.kind == "group"]
        assert "predch:B1" not in group_ids
        assert group_ids == ["Start", "G1"]

        # Entry comes from the CHILD's own first beat (map 100), never the
        # predecessor's (map 999).
        assert route.nodes[0].kind == "entry"
        assert route.nodes[0].map_id == 100
        # Exit comes from the child's own last beat (G1, map 101).
        assert route.nodes[-1].kind == "exit"
        assert route.nodes[-1].map_id == 101

        assert route.tile_cost == 3
    finally:
        _uninstall_chapter_module("predch")


def test_chapter_with_only_inherited_beats_fails_loud() -> None:
    # A chapter can never legitimately have zero of its own beats
    # (`ChapterBuilder.build()` itself rejects that), so this simulates the
    # "only inherited content" case the same way an already-prefixed beat
    # would appear post-predecessor-chaining: one beat whose name already
    # carries the `<owner>:<name>` shape, so `_own_beats`/the group filter
    # treats it as not-this-chapter's.
    builder = ChapterBuilder("onlyinherited", doc="reference/chapters/00-x.md")

    @builder.beat("predch:B1", "looks inherited", map_constant="MAP_PRED", at=(0, 0),
                  group="predch:B1")
    def b1(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()

    w = _World()
    w.home(999)
    w.home(998)
    w.add(999, 998, 201, 1)

    with pytest.raises(RouteSolverError, match="no own groups"):
        solve_route(
            chapter, "ONLYINHERITED", manifest_rows=[],
            graphs=w.graphs, overlays=w.overlays, world=w.build(),
            entry=(999, (0, 0)), exit_=(998, (0, 0)), map_ids={"MAP_PRED": 999},
        )
