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

from rpg2gba.routing.occupancy import MapOccupancy, OccupiedTile
from rpg2gba.routing.plan import (
    ChosenApproach, PrecedenceEdge, RoutePlan, plan_from_dict, plan_to_dict, write_plan,
)
from rpg2gba.routing.solver import RouteCandidate, RouteSolverError, solve_route


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _trivial_graph(map_id: int) -> MapGraph:
    return MapGraph(map_id=map_id, width=1, height=1, tileset_id=0, blocked={(0, 0): False})


def _empty_overlay(map_id: int) -> TriggerOverlay:
    return TriggerOverlay(map_id=map_id, tiles={})


def _open_square_graph(map_id: int, size: int) -> MapGraph:
    """A fully-open `size`x`size` grid -- every cell walkable, no walls --
    so BFS distance between any two cells is exactly their Manhattan
    distance. Used for the candidate-DP tests below, where the whole point
    is to engineer a case where the cheapest ARRIVAL side is not the
    cheapest TOTAL (arrival + departure) side, which needs real geometry
    rather than the single-cell/corridor helpers above."""
    return MapGraph(
        map_id=map_id, width=size, height=size, tileset_id=0,
        blocked={(x, y): False for x in range(size) for y in range(size)},
    )


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


def _warp_row(row_id: str, map_id: int, event_id: int) -> ManifestRow:
    return ManifestRow(
        row_id=row_id, kind="page", map_id=map_id, content_hash="w",
        event_id=event_id, effects=("warp",),
    )


# ---------------------------------------------------------------------------
# warp-topology precedence
# ---------------------------------------------------------------------------


def test_warp_topology_orders_far_side_beat_after_its_introducing_warp() -> None:
    """A far-side beat must never be ordered before the warp beat that first
    reaches that map -- CH05_TODO.md's filed defect (B9 on 2F ordered before
    B8, the 1F->2F warp). Cost matrix is engineered so the UNCONSTRAINED
    cost-optimal order visits the far-side beat first (a cheap direct
    shortcut from entry bypasses the introducing map entirely), which is
    exactly the bug this precedence must override.
    """
    intro_row = _warp_row("map101/ev005/p0", map_id=101, event_id=5)

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("Wintro", "introduces the far map", map_constant="MAP_WINTRO", at=(0, 0),
                  group="Wintro", rows=(intro_row.row_id,))
    def wintro(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("Bfar", "far-side beat", map_constant="MAP_BFAR", at=(0, 0), group="Bfar")
    def bfar(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_WINTRO": 101, "MAP_BFAR": 102}

    w = _World()
    w.home(100)  # entry
    w.home(101)  # Wintro
    w.home(102)  # Bfar
    w.home(103)  # exit
    w.add(100, 101, 201, 5)   # entry <-> Wintro: expensive
    w.add(100, 102, 202, 1)   # entry <-> Bfar: cheap shortcut (the trap)
    w.add(101, 103, 204, 1)   # Wintro <-> exit: cheap
    w.add(102, 103, 205, 5)   # Bfar <-> exit: expensive

    edges = w.edges + [
        WorldEdge(src_map=101, dst_map=102, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=5),
        WorldEdge(src_map=102, dst_map=101, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=6),
    ]
    world = _world(edges, w.map_ids)

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[intro_row],
        graphs=w.graphs, overlays=w.overlays, world=world,
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )

    assert PrecedenceEdge(
        before="Wintro", after="Bfar", reason="warp_topology:map102",
    ) in route.precedence

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["Wintro", "Bfar"]
    # forced order costs 5 (entry->Wintro) + 0 (Wintro->Bfar direct warp) + 5
    # (Bfar->exit) = 10, even though the unconstrained-cheapest order
    # (entry->Bfar->Wintro->exit, 1+0+1=2) puts Bfar first.
    assert route.tile_cost == 10


def test_single_outbound_boundary_group_ordered_last_and_becomes_exit() -> None:
    """A single group owning a warp that leaves the chapter's own maps must
    be ordered last, and the route's exit point becomes that group's own
    cell -- not `_default_exit_location`'s pick."""
    boundary_row = _warp_row("map102/ev009/p0", map_id=102, event_id=9)

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("A", "ordinary beat", map_constant="MAP_A", at=(0, 0), group="A")
    def a(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("T", "terminal beat", map_constant="MAP_T", at=(0, 0), group="T",
                  rows=(boundary_row.row_id,))
    def t(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_A": 101, "MAP_T": 102}

    w = _World()
    w.home(100)  # entry
    w.home(101)  # A
    w.home(102)  # T (terminal)
    w.add(100, 101, 201, 5)  # entry <-> A: expensive
    w.add(100, 102, 202, 1)  # entry <-> T: cheap (would tempt T first)
    w.add(101, 102, 203, 1)  # A <-> T: cheap

    edges = w.edges + [
        WorldEdge(src_map=102, dst_map=999, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=9),
    ]
    world = _world(edges, w.map_ids | {999})

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[boundary_row],
        graphs=w.graphs, overlays=w.overlays, world=world,
        entry=(100, (0, 0)), map_ids=map_ids,
    )

    assert PrecedenceEdge(
        before="A", after="T", reason="warp_boundary:map999",
    ) in route.precedence

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["A", "T"]
    assert route.nodes[-1].kind == "exit"
    assert (route.nodes[-1].map_id, route.nodes[-1].cell) == (102, (0, 0))
    # forced order: entry->A (5) + A->T (1) + T->exit (0, same cell) = 6.
    assert route.tile_cost == 6


def test_entry_warp_is_never_treated_as_terminal() -> None:
    """The chapter's own entry warp destination lies outside the chapter's
    map set by definition (it points back at the predecessor map), but it
    must never be mistaken for the outbound boundary group -- the entry
    group is excluded from rule 2's candidates."""
    entry_warp_row = _warp_row("map101/ev003/p0", map_id=101, event_id=3)

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("Start", "chapter start", map_constant="MAP_START", at=(0, 0),
                  group="Start", rows=(entry_warp_row.row_id,))
    def start(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("Other", "chapter end", map_constant="MAP_OTHER", at=(0, 0),
                  group="Other")
    def other(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_START": 101, "MAP_OTHER": 102}

    w = _World()
    w.home(101)  # Start (== entry, by default derivation)
    w.home(102)  # Other
    w.add(101, 102, 201, 3)

    edges = w.edges + [
        WorldEdge(src_map=101, dst_map=999, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=3),
    ]
    world = _world(edges, w.map_ids | {999})

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[entry_warp_row],
        graphs=w.graphs, overlays=w.overlays, world=world, map_ids=map_ids,
    )

    assert not any(e.reason.startswith("warp_boundary") for e in route.precedence)
    # No terminal override fired, so the exit falls back to the default:
    # the last own beat's last location (Other, map 102).
    assert route.nodes[-1].kind == "exit"
    assert route.nodes[-1].map_id == 102


def test_two_outbound_boundary_candidates_raise_unless_exit_given() -> None:
    row_t1 = _warp_row("map101/ev009/p0", map_id=101, event_id=9)
    row_t2 = _warp_row("map102/ev011/p0", map_id=102, event_id=11)

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("T1", "candidate 1", map_constant="MAP_T1", at=(0, 0), group="T1",
                  rows=(row_t1.row_id,))
    def t1(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("T2", "candidate 2", map_constant="MAP_T2", at=(0, 0), group="T2",
                  rows=(row_t2.row_id,))
    def t2(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_T1": 101, "MAP_T2": 102}

    w = _World()
    w.home(100)  # entry
    w.home(101)  # T1
    w.home(102)  # T2
    w.add(100, 101, 201, 1)
    w.add(100, 102, 202, 1)

    edges = w.edges + [
        WorldEdge(src_map=101, dst_map=997, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=9),
        WorldEdge(src_map=102, dst_map=998, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=11),
    ]
    world = _world(edges, w.map_ids | {997, 998})

    with pytest.raises(RouteSolverError, match="terminal group"):
        solve_route(
            chapter, "TESTCH", manifest_rows=[row_t1, row_t2],
            graphs=w.graphs, overlays=w.overlays, world=world,
            entry=(100, (0, 0)), map_ids=map_ids,
        )

    # An explicit exit_= disambiguates: no raise, and the caller's own exit
    # point is honoured over anything rule 2 might have derived.
    route = solve_route(
        chapter, "TESTCH", manifest_rows=[row_t1, row_t2],
        graphs=w.graphs, overlays=w.overlays, world=world,
        entry=(100, (0, 0)), exit_=(102, (0, 0)), map_ids=map_ids,
    )
    assert route.nodes[-1].kind == "exit"
    assert (route.nodes[-1].map_id, route.nodes[-1].cell) == (102, (0, 0))
    assert not any(e.reason.startswith("warp_boundary") for e in route.precedence)


def test_world_none_derives_no_warp_precedence() -> None:
    """With `world=None`, no warp precedence is derivable at all -- the
    manifest carries a warp row that WOULD trigger rule 2 if a world graph
    were supplied, but `_derive_warp_precedence` must short-circuit on
    `world is None` before ever looking at it. Everything lives on one map so
    the segments themselves route fine without a `WorldGraph`."""
    boundary_row = _warp_row("map102/ev009/p0", map_id=102, event_id=9)

    chapter, map_ids = _chapter_with_groups(("A", "MAP_A", 100))

    graph = _corridor_graph(100, 4)
    graphs = {100: graph}
    overlays = {100: _empty_overlay(100)}

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[boundary_row],
        graphs=graphs, overlays=overlays, world=None,
        entry=(100, (0, 0)), exit_=(100, (4, 0)), map_ids=map_ids,
    )

    assert route.precedence == ()


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
# candidate-site DP: breaking the approach-side circularity
# ---------------------------------------------------------------------------
#
# `M` sits at the centre of a 5x5 open grid; its beat carries two candidate
# sides, "north" (2, 1) and "south" (2, 3) -- north listed first, so it is
# the side a resolver's own N/S/E/W tiebreak would have picked with no
# `candidates=` at all. Entry lands EXACTLY on the south candidate and exit
# sits due west, equidistant (Manhattan) from both candidates, so:
#   - arrival cost:   north=2, south=0   (south is the cheap ARRIVAL side)
#   - departure cost: north=3, south=3   (tied)
#   - total:          north=5, south=3   -- south wins on total despite
#     losing nothing (in fact winning) on arrival too; the real regression
#     this guards is a per-step-greedy solver picking the ARRIVAL-cheapest
#     side without accounting for what comes after. See
#     `test_candidate_dp_beats_a_scheme_that_only_looks_at_arrival_cost`
#     below for a case where arrival-cheapest and total-cheapest actively
#     disagree.


def _multiside_setup() -> tuple[Chapter, dict[str, int], dict[int, MapGraph],
                                dict[int, TriggerOverlay]]:
    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("M", "multi-side beat", map_constant="MAP_M", at=(2, 1), group="M")
    def m(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_M": 100}
    graph = _open_square_graph(100, 5)
    graphs = {100: graph}
    overlays = {100: _empty_overlay(100)}
    return chapter, map_ids, graphs, overlays


def _multiside_candidates() -> dict[str, tuple[RouteCandidate, ...]]:
    return {
        "M": (
            RouteCandidate(x=2, y=1, side="north",
                          resolver='approach_to(MAP_M, ev1, prefer="north")'),
            RouteCandidate(x=2, y=3, side="south",
                          resolver='approach_to(MAP_M, ev1, prefer="south")'),
        ),
    }


def test_candidate_dp_prefers_non_default_side_when_cheaper_overall() -> None:
    """The DP must pick the SOUTH candidate (cheaper total) over the N/S/E/W
    default (NORTH), and record the chosen side on the node -- proof this
    isn't a per-step greedy pick, which a naive port of the old resolver
    tiebreak would still get right here by accident (south also happens to
    be cheapest on arrival alone) -- see the disagreement case below."""
    chapter, map_ids, graphs, overlays = _multiside_setup()

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=graphs, overlays=overlays, world=None,
        entry=(100, (2, 3)), exit_=(100, (0, 2)), map_ids=map_ids,
        candidates=_multiside_candidates(),
    )

    group_node = next(n for n in route.nodes if n.kind == "group")
    assert group_node.cell == (2, 3)
    assert group_node.chosen_approach == ChosenApproach(
        side="south", resolver='approach_to(MAP_M, ev1, prefer="south")')
    assert route.tile_cost == 3  # 0 (already at south) + 3 (south -> exit)


def test_candidate_dp_beats_a_scheme_that_only_looks_at_arrival_cost() -> None:
    """Here the ARRIVAL-cheapest side ("north", at (3, 0)) is NOT the
    TOTAL-cheapest side ("south", at (2, 3)):

      dist(entry, north) = 1   dist(entry, south) = 3   -- north is arrival-cheap
      dist(north, exit)  = 5   dist(south, exit)  = 1    -- south is departure-cheap
      total north = 6         total south = 4            -- south wins overall

    North is off the entry-exit axis just enough that its cheap arrival is
    swamped by an expensive departure detour -- exactly the shape a per-step
    greedy candidate pick (minimize distance from whatever was placed
    immediately before, ignoring what comes after) gets wrong: it would lock
    in north for its cheap arrival and never revisit that choice once it
    sees the expensive departure. The DP must pick south."""
    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("M", "multi-side beat", map_constant="MAP_M", at=(3, 0), group="M")
    def m(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_M": 100}
    graphs = {100: _open_square_graph(100, 5)}
    overlays = {100: _empty_overlay(100)}
    candidates = {
        "M": (
            RouteCandidate(x=3, y=0, side="north",
                          resolver='approach_to(MAP_M, ev1, prefer="north")'),
            RouteCandidate(x=2, y=3, side="south",
                          resolver='approach_to(MAP_M, ev1, prefer="south")'),
        ),
    }

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=graphs, overlays=overlays, world=None,
        entry=(100, (2, 0)), exit_=(100, (2, 4)), map_ids=map_ids,
        candidates=candidates,
    )

    group_node = next(n for n in route.nodes if n.kind == "group")
    assert group_node.chosen_approach.side == "south"
    assert group_node.cell == (2, 3)
    assert route.tile_cost == 4  # 3 (entry->south) + 1 (south->exit)


def test_candidate_occupancy_drops_blocked_candidates() -> None:
    """A candidate cell occupied by a stationary NPC is dropped before
    solving -- the group must route on its only remaining (unblocked) side,
    never silently through the NPC."""
    chapter, map_ids, graphs, overlays = _multiside_setup()
    occupancy = {
        100: MapOccupancy(map_id=100, tiles=(
            OccupiedTile(cell=(2, 3), script="Map100_NPC", movement_type="MOVEMENT_TYPE_NONE"),
        )),
    }

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=graphs, overlays=overlays, world=None,
        entry=(100, (2, 0)), exit_=(100, (0, 2)), map_ids=map_ids,
        candidates=_multiside_candidates(), occupancy=occupancy,
    )

    group_node = next(n for n in route.nodes if n.kind == "group")
    assert group_node.cell == (2, 1)
    assert group_node.chosen_approach.side == "north"


def test_candidate_all_sides_occupied_fails_loud_naming_the_npcs() -> None:
    chapter, map_ids, graphs, overlays = _multiside_setup()
    occupancy = {
        100: MapOccupancy(map_id=100, tiles=(
            OccupiedTile(cell=(2, 1), script="Map100_NPC_N", movement_type="MOVEMENT_TYPE_NONE"),
            OccupiedTile(cell=(2, 3), script="Map100_NPC_S", movement_type="MOVEMENT_TYPE_NONE"),
        )),
    }

    with pytest.raises(RouteSolverError, match="M") as exc_info:
        solve_route(
            chapter, "TESTCH", manifest_rows=[],
            graphs=graphs, overlays=overlays, world=None,
            entry=(100, (2, 3)), exit_=(100, (0, 2)), map_ids=map_ids,
            candidates=_multiside_candidates(), occupancy=occupancy,
        )
    message = str(exc_info.value)
    assert "Map100_NPC_N" in message
    assert "Map100_NPC_S" in message


def test_candidate_solve_is_deterministic_across_repeated_runs() -> None:
    chapter, map_ids, graphs, overlays = _multiside_setup()
    kwargs = dict(
        chapter=chapter, chapter_id="TESTCH", manifest_rows=[],
        graphs=graphs, overlays=overlays, world=None,
        entry=(100, (2, 3)), exit_=(100, (0, 2)), map_ids=map_ids,
        candidates=_multiside_candidates(),
    )
    route1 = solve_route(**kwargs)
    route2 = solve_route(**kwargs)
    assert route1 == route2


def test_empty_candidate_mapping_reproduces_default_behaviour() -> None:
    """`candidates=None` (the default) and `candidates={}` must both
    reproduce exactly today's single-cell-per-group behaviour: the group's
    own resolved cell, with no `chosen_approach` recorded."""
    chapter, map_ids, graphs, overlays = _multiside_setup()

    baseline = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=graphs, overlays=overlays, world=None,
        entry=(100, (2, 3)), exit_=(100, (0, 2)), map_ids=map_ids,
    )
    explicit_empty = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=graphs, overlays=overlays, world=None,
        entry=(100, (2, 3)), exit_=(100, (0, 2)), map_ids=map_ids,
        candidates={},
    )

    assert baseline == explicit_empty
    group_node = next(n for n in baseline.nodes if n.kind == "group")
    assert group_node.cell == (2, 1)  # the beat's own literal `at=` cell
    assert group_node.chosen_approach is None


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
# PROJECT_TODO #76 -- per-destination trigger safety
# ---------------------------------------------------------------------------


def test_approaching_a_beat_does_not_count_its_own_trigger_as_a_crossing() -> None:
    """The only route to B's beat crosses B's own trigger tile (its sight
    cone / coord-event, converted from `map202/ev007/p0`). That tile is not
    foreign on the segment whose destination IS B -- it must solve with no
    crossing recorded at all."""
    own_script = "Map202_EV007_Page1"

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("B", "beat for B", map_constant="MAP_B", at=(0, 0), group="B",
                  rows=("map202/ev007/p0",))
    def b(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_B": 102}

    w = _World()
    w.home(100)  # entry
    w.home(102)  # B
    w.home(103)  # exit
    w.add(100, 102, 202, 2, foreign_script=own_script)  # entry -> B: crosses B's own tile
    w.add(102, 103, 204, 1)  # B -> exit: clean

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )

    assert route.tile_cost == 2 + 1
    assert all(s.crossed_foreign_triggers == () for s in route.segments)


def test_approaching_a_different_beat_still_counts_that_beats_trigger_as_a_crossing() -> None:
    """The converse of the above, and the regression that matters: a trigger
    tile crossed on the way to A, but OWNED by B (a different beat/group),
    must stay a foreign crossing. Guards against a fix that unions every
    group's own scripts into one chapter-wide safe set instead of gating the
    exemption by the segment's actual destination -- exactly the "B3's
    trainer must not be excused for firing during an approach to B8" case
    `resolved_trigger_scripts`'s docstring calls out, now expressed at the
    per-segment level.

    Order is NOT forced by corridor topology -- a corridor chain lets the
    solver reach B by first passing through A's cell regardless of which
    group is "visited" first, and #76's exemption makes reordering to
    B-first strictly cheaper under the solver's crossing-averse search (it
    erases the recorded crossing entirely, which is worth far more to the
    search than the extra backtracking tiles cost -- see `_CROSSING_PENALTY`
    in solver.py). Without a real constraint forcing A first, the solver
    reorders to B, A and this regression guard never fires. So the order is
    forced the same way `test_warp_topology_orders_far_side_beat_after_its_
    introducing_warp` forces its order: A's beat owns the only warp landing
    on B's map, deriving a `warp_topology` precedence edge that 2-opt must
    respect regardless of cost.
    """
    a_intro_row = _warp_row("map101/ev007/p0", map_id=101, event_id=7)
    b_script = "Map202_EV007_Page1"

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("A", "beat for A", map_constant="MAP_A", at=(0, 0), group="A",
                  rows=(a_intro_row.row_id,))
    def a(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("B", "beat for B", map_constant="MAP_B", at=(0, 0), group="B",
                  rows=("map202/ev007/p0",))
    def b(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_A": 101, "MAP_B": 102}

    w = _World()
    w.home(100)  # entry
    w.home(101)  # A
    w.home(102)  # B
    w.home(103)  # exit
    # entry -> A crosses B's own trigger tile.
    w.add(100, 101, 201, 2, foreign_script=b_script)
    w.add(102, 103, 204, 1)  # B -> exit: clean

    edges = w.edges + [
        # A's introducing warp onto B's map -- also the only A <-> B path,
        # so this segment costs 0 tiles (a direct warp), same as the
        # warp-topology precedence test above.
        WorldEdge(src_map=101, dst_map=102, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=7),
        WorldEdge(src_map=102, dst_map=101, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=8),
    ]
    world = _world(edges, w.map_ids)

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[a_intro_row],
        graphs=w.graphs, overlays=w.overlays, world=world,
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )

    assert PrecedenceEdge(
        before="A", after="B", reason="warp_topology:map102",
    ) in route.precedence

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["A", "B"]
    # entry->A (2, corridor) + A->B (0, direct warp) + B->exit (1, corridor).
    assert route.tile_cost == 2 + 0 + 1

    first_segment = route.segments[0]
    assert len(first_segment.crossed_foreign_triggers) == 1
    assert first_segment.crossed_foreign_triggers[0].script == b_script
    assert all(s.crossed_foreign_triggers == () for s in route.segments[1:])


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


def test_entry_landing_map_needs_no_introducing_warp() -> None:
    """A chapter that STARTS on a warp does not have to let itself in.

    The introducing-warp rule skips `entry_map`, because a chapter obviously
    reaches the map it begins on. For the map its entry warp LANDS on, it
    must not credit a group whose warp only lands there from DEEPER in -- a
    first-entry warp is one whose source is reachable without passing
    through the map (since 2026-09-27; this used to be a blanket exemption
    for entry landing maps, which also hid gated doors).

    CH05 is the case: it enters the Passage Cave from Route 02, and its entry
    beat claims the cave's OUTBOUND event (the only row that seam gives the
    arriving chapter), so it does not look like a way *in*. The rule credited
    the 1F<->2F staircase instead and emitted `stairs -> entry`: use the
    stairs before entering the cave. Not a worse ordering -- an impossible
    one, and it forced the whole floor to be swept backwards.

    Here `Wentry` is the chapter's entry beat, standing on map 101 having
    arrived from map 100, and `Wstairs` owns a warp that also lands on 101.
    Nothing may be ordered before `Wentry` on account of map 101.
    """
    entry_row = _warp_row("map101/ev005/p0", map_id=101, event_id=5)
    stairs_row = _warp_row("map102/ev006/p0", map_id=102, event_id=6)

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("Wentry", "the chapter's own entry crossing",
                  map_constant="MAP_ENTRY_SIDE", at=(0, 0), group="Wentry",
                  rows=(entry_row.row_id,))
    def wentry(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("Wstairs", "a second warp that also lands on map 101",
                  map_constant="MAP_STAIRS", at=(0, 0), group="Wstairs",
                  rows=(stairs_row.row_id,))
    def wstairs(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_ENTRY_SIDE": 101, "MAP_STAIRS": 102}

    w = _World()
    w.home(100)  # entry map -- the chapter starts here
    w.home(101)
    w.home(102)
    w.home(103)  # exit
    w.add(100, 101, 201, 1)
    w.add(101, 102, 202, 1)
    w.add(102, 103, 203, 1)

    edges = w.edges + [
        # the chapter's entry warp: map100 (0,0) -> map101
        WorldEdge(src_map=100, dst_map=101, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=1),
        # the entry beat's own claimed row points back OUT to map 100
        WorldEdge(src_map=101, dst_map=100, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=5),
        # the stairs land on 101 too -- the tempting false "introducer"
        WorldEdge(src_map=102, dst_map=101, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=6),
    ]
    world = _world(edges, w.map_ids)

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[entry_row, stairs_row],
        graphs=w.graphs, overlays=w.overlays, world=world,
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
    )

    assert not [
        e for e in route.precedence
        if e.after == "Wentry" and e.reason == "warp_topology:map101"
    ], (
        "nothing may be required before the chapter's own entry beat on "
        f"account of the map it enters into: {route.precedence}"
    )


# --- story precedence (REDERIVATION_PLAN.md §16.3 ruling 16) --------------


def test_story_precedence_edges_from_single_writer_groups():
    from rpg2gba.routing.solver import _derive_story_precedence

    group_by_row = {"map049/ev001/p0": "auntie", "map049/ev002/p1": "door",
                    "map050/ev019/p0": "starter", "map049/ev022/p0": "whiteout",
                    "map010/ev001/p0": "a", "map010/ev002/p0": "b"}
    enabled_by = {
        # One writer in another group: an edge.
        "map049/ev002/p1": (("map049/ev001/p0",),),
        # The engine marker constrains nothing; the real writer does.
        "map049/ev022/p0": (("engine:whiteout",), ("map050/ev019/p0",)),
        # Two alternative writers, one unclaimed (map011's, dropped): the
        # claimed one alone is an edge.
        "map010/ev002/p0": (("map010/ev001/p0", "map011/ev001/p0"),),
        # A writer no group claims (another chapter's): no edge.
        "map010/ev001/p0": (("map099/ev001/p0",),),
    }
    edges, any_of = _derive_story_precedence(enabled_by, group_by_row)
    assert [(e.before, e.after) for e in edges] == [
        ("a", "b"), ("auntie", "door"), ("starter", "whiteout")]
    assert edges[1].reason == "story:map049/ev001/p0->map049/ev002/p1"
    assert any_of == ()


def test_story_precedence_several_writers_is_any_of():
    """CH01's Auntie heal page: var 101 >= 2 is written by any of three rows,
    so it comes after at least one of them. (2026-09-27 demanded all three;
    2026-09-28 found that held CH01's lab exit -- same var, one writer in
    the lab -- shut until Theo's house.)"""
    from rpg2gba.routing.solver import _AnyOf, _derive_story_precedence

    group_by_row = {"map032/ev009/p2": "ceremony", "map050/ev019/p0": "starter",
                    "map172/ev004/p0": "pokepod", "map049/ev001/p3": "heal"}
    edges, any_of = _derive_story_precedence(
        {"map049/ev001/p3": (("map032/ev009/p2", "map050/ev019/p0", "map172/ev004/p0"),)},
        group_by_row)
    assert edges == ()
    assert any_of == (_AnyOf(after="heal", befores=("ceremony", "pokepod", "starter"),
                             reason="story_any:map049/ev001/p3"),)


def test_any_of_drops_alternatives_that_close_a_cycle():
    from rpg2gba.routing.plan import PrecedenceEdge
    from rpg2gba.routing.solver import _AnyOf, _feasible_any_of

    hard = (PrecedenceEdge(before="x", after="a", reason="t"),)
    # a must come after x, so "a" can't be x's enabler; y alone is left -> edge.
    edges, kept = _feasible_any_of(hard, (_AnyOf(after="x", befores=("a", "y"), reason="r"),))
    assert [(e.before, e.after) for e in edges] == [("y", "x")] and kept == ()
    # Every alternative after it: dropped.
    edges, kept = _feasible_any_of(hard, (_AnyOf(after="x", befores=("a",) * 2, reason="r"),))
    assert edges == () and kept == ()


def test_story_precedence_ignores_a_writer_in_the_same_group():
    from rpg2gba.routing.solver import _derive_story_precedence

    group_by_row = {"map001/ev001/p0": "g", "map001/ev001/p1": "g"}
    assert _derive_story_precedence(
        {"map001/ev001/p1": (("map001/ev001/p0",),)}, group_by_row) == ((), ())


def test_story_edge_that_closes_a_cycle_is_skipped():
    """CH01's map050/ev005 shape: page 0's group enables page 2's, and page
    2's arm enables an arm back in page 0's group. The first story edge in
    sorted order is kept; the one closing the cycle is dropped. A hard edge
    is never dropped, even when a story edge disagrees with it."""
    from rpg2gba.routing.plan import PrecedenceEdge
    from rpg2gba.routing.solver import _acyclic_story_edges

    p0_to_p2 = PrecedenceEdge(before="p0", after="p2", reason="story:a")
    p2_to_p0 = PrecedenceEdge(before="p2", after="p0", reason="story:b")
    assert _acyclic_story_edges((), (p2_to_p0, p0_to_p2)) == (p0_to_p2,)

    hard = (PrecedenceEdge(before="p2", after="p0", reason="warp_topology:x"),)
    assert _acyclic_story_edges(hard, (p0_to_p2,)) == ()


def test_warp_topology_counts_only_first_entry_warps() -> None:
    """CH01's shape (2026-09-27 ROM run): the house (entry, map 100) opens
    onto the town (102) through one door; the town's interior (103) also has
    an exit landing on 102. The interior is only reachable through the town,
    so its exit is not an introducer, and the house door alone orders every
    town group -- before the fix, two "introducers" meant no edge at all."""
    from rpg2gba.routing.solver import _derive_warp_precedence, _GroupPoint

    rows = [
        _warp_row("map100/ev001/p1", map_id=100, event_id=1),   # house door -> town
        _warp_row("map102/ev002/p0", map_id=102, event_id=2),   # town door -> interior
        _warp_row("map103/ev001/p0", map_id=103, event_id=1),   # interior exit -> town
    ]
    group_by_row = {"map100/ev001/p1": "HouseDoor", "map102/ev002/p0": "TownDoor",
                    "map103/ev001/p0": "InteriorExit"}
    points = [
        _GroupPoint("HouseDoor", ("HouseDoor",), ("map100/ev001/p1",), 100, (0, 0)),
        _GroupPoint("TownBeat", ("TownBeat",), (), 102, (1, 0)),
        _GroupPoint("TownDoor", ("TownDoor",), ("map102/ev002/p0",), 102, (2, 0)),
        _GroupPoint("InteriorExit", ("InteriorExit",), ("map103/ev001/p0",), 103, (0, 0)),
    ]
    world = _world([
        WorldEdge(src_map=100, dst_map=102, kind="warp", src_cell=(0, 0), dst_cell=(0, 0),
                  event_id=1),
        WorldEdge(src_map=102, dst_map=103, kind="warp", src_cell=(2, 0), dst_cell=(0, 0),
                  event_id=2),
        WorldEdge(src_map=103, dst_map=102, kind="warp", src_cell=(0, 0), dst_cell=(2, 0),
                  event_id=1),
    ], {100, 102, 103})

    edges, _ = _derive_warp_precedence(
        rows, group_by_row, points, world, entry_map=100, entry_group_id=None,
        chapter_id="TESTCH", exit_provided=True)

    assert {(e.before, e.after) for e in edges if e.reason == "warp_topology:map102"} == {
        ("HouseDoor", "TownBeat"), ("HouseDoor", "TownDoor")}
    assert ("TownDoor", "InteriorExit") in {(e.before, e.after) for e in edges}


# ---------------------------------------------------------------------------
# soft_precedence (beat_gen.interiors)
# ---------------------------------------------------------------------------


def test_soft_precedence_orders_interior_before_exit() -> None:
    """`soft_precedence` forces an order the cost function alone would never
    pick -- the entry->exit direct hop is far cheaper than entry->interior->
    exit, mirroring the "cost-optimal is wrong" shape of the warp-topology
    test above."""
    chapter, map_ids = _chapter_with_groups(
        ("Interior", "MAP_INT", 101), ("Exit", "MAP_EXIT", 102),
    )

    w = _World()
    w.home(100)  # entry
    w.home(101)  # Interior
    w.home(102)  # Exit
    w.home(103)  # route exit
    w.add(100, 101, 201, 5)   # entry <-> Interior: expensive
    w.add(100, 102, 202, 1)   # entry <-> Exit: cheap shortcut (the trap)
    w.add(101, 102, 203, 1)   # Interior <-> Exit: cheap
    w.add(102, 103, 204, 1)   # Exit <-> route exit: cheap

    soft = (PrecedenceEdge(before="Interior", after="Exit", reason="interior_exit:map100<-map101"),)

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
        soft_precedence=soft,
    )

    assert PrecedenceEdge(
        before="Interior", after="Exit", reason="interior_exit:map100<-map101",
    ) in route.precedence
    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["Interior", "Exit"]


def test_soft_precedence_edge_closing_a_cycle_is_dropped_and_logged(caplog) -> None:  # noqa: ANN001
    """A soft edge that would close a cycle against an already-accepted hard
    edge is dropped (never applied) and logged at INFO -- same discipline as
    a story edge, never silently changing the plan's precedence."""
    intro_row = _warp_row("map101/ev005/p0", map_id=101, event_id=5)

    builder = ChapterBuilder("test", doc="reference/chapters/00-test.md")

    @builder.beat("Wintro", "introduces the far map", map_constant="MAP_WINTRO", at=(0, 0),
                  group="Wintro", rows=(intro_row.row_id,))
    def wintro(emu) -> None:  # noqa: ANN001
        pass

    @builder.beat("Bfar", "far-side beat", map_constant="MAP_BFAR", at=(0, 0), group="Bfar")
    def bfar(emu) -> None:  # noqa: ANN001
        pass

    chapter = builder.build()
    map_ids = {"MAP_WINTRO": 101, "MAP_BFAR": 102}

    w = _World()
    w.home(100)
    w.home(101)
    w.home(102)
    w.home(103)
    w.add(100, 101, 201, 5)
    w.add(100, 102, 202, 1)
    w.add(101, 103, 204, 1)
    w.add(102, 103, 205, 5)

    edges = w.edges + [
        WorldEdge(src_map=101, dst_map=102, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=5),
        WorldEdge(src_map=102, dst_map=101, kind="warp",
                  src_cell=(0, 0), dst_cell=(0, 0), event_id=6),
    ]
    world = _world(edges, w.map_ids)

    # The hard warp-topology edge is Wintro -> Bfar (Wintro introduces map
    # 102). A soft edge asking for the reverse closes a cycle and must be
    # dropped.
    soft = (PrecedenceEdge(before="Bfar", after="Wintro", reason="interior_exit:mockcycle"),)

    with caplog.at_level("INFO"):
        route = solve_route(
            chapter, "TESTCH", manifest_rows=[intro_row],
            graphs=w.graphs, overlays=w.overlays, world=world,
            entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
            soft_precedence=soft,
        )

    assert PrecedenceEdge(before="Bfar", after="Wintro", reason="interior_exit:mockcycle") \
        not in route.precedence
    assert PrecedenceEdge(before="Wintro", after="Bfar", reason="warp_topology:map102") \
        in route.precedence
    assert any("interior_exit:mockcycle" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# order_violations
# ---------------------------------------------------------------------------


def _p1_immediately_before_p2_count(seq) -> int:  # noqa: ANN001
    seq = list(seq)
    return sum(1 for i in range(len(seq) - 1) if seq[i] == "P1" and seq[i + 1] == "P2")


def test_order_violations_keeps_cost_optimal_interleave_out_of_the_solved_order() -> None:
    """Cost alone wants P1 immediately followed by P2 (E-P1-P2-P3-exit is the
    cheapest order); `order_violations` counts that adjacency as a break, so
    the solved order must place something else right after P1 even though it
    costs more, and end with zero violations."""
    chapter, map_ids = _chapter_with_groups(
        ("P1", "MAP_P1", 101), ("P2", "MAP_P2", 102), ("P3", "MAP_P3", 103),
    )

    w = _World()
    for mid in (100, 101, 102, 103, 104):  # entry, P1, P2, P3, exit
        w.home(mid)

    w.add(100, 101, 201, 2)   # E-P1: cheap
    w.add(100, 102, 202, 10)  # E-P2: expensive
    w.add(100, 103, 203, 10)  # E-P3: expensive
    w.add(101, 102, 204, 2)   # P1-P2: cheap
    w.add(101, 103, 205, 10)  # P1-P3: expensive
    w.add(102, 103, 206, 2)   # P2-P3: cheap
    w.add(101, 104, 207, 10)  # P1-exit: expensive
    w.add(102, 104, 208, 10)  # P2-exit: expensive
    w.add(103, 104, 209, 2)   # P3-exit: cheap

    route = solve_route(
        chapter, "TESTCH", manifest_rows=[],
        graphs=w.graphs, overlays=w.overlays, world=w.build(),
        entry=(100, (0, 0)), exit_=(104, (0, 0)), map_ids=map_ids,
        order_violations=_p1_immediately_before_p2_count,
    )

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert _p1_immediately_before_p2_count(group_order) == 0
    # the forbidden adjacency (P1, P2, P3) costs 2+2+2+2=8 -- strictly
    # cheaper than anything a zero-violation order allows, proving the
    # constraint bit actually steered the solve.
    assert group_order != ["P1", "P2", "P3"]


def test_order_violations_falls_back_and_logs_when_every_group_breaks_it(caplog) -> None:  # noqa: ANN001
    """An `order_violations` that adds a break no matter which group is
    placed next must not make the solver fail -- it falls back to precedence
    alone (placing one of the tied-fewest-violation groups) and logs the
    decision at INFO."""
    chapter, map_ids = _chapter_with_groups(("A", "MAP_A", 101))
    w = _World()
    w.home(100)
    w.home(101)
    w.home(103)
    w.add(100, 101, 201, 2)
    w.add(101, 103, 202, 2)

    # Any non-empty prefix counts one violation; the empty prefix counts
    # none -- so placing the first (and only) group always adds a break.
    with caplog.at_level("INFO"):
        route = solve_route(
            chapter, "TESTCH", manifest_rows=[],
            graphs=w.graphs, overlays=w.overlays, world=w.build(),
            entry=(100, (0, 0)), exit_=(103, (0, 0)), map_ids=map_ids,
            order_violations=lambda seq: 1 if seq else 0,
        )

    group_order = [n.group for n in route.nodes if n.kind == "group"]
    assert group_order == ["A"]
    assert any(
        "order_violations: every available group breaks the order" in rec.message
        for rec in caplog.records
    )
