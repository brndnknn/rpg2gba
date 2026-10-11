"""Interior-exit and arrival-nudge soft precedence edges for the beat-gen
route solver.

Implements the operator's 2026-09-28 ruling in
`investigations/warp-round-trips-and-gated-doors.md` ("Ruling (operator,
2026-09-28)"): warp beats are one-way, and a dead-end interior (a house, a
shop, a nested upstairs -- any region whose only way out leads back to one
parent map) must have every FIRST-VISIT beat inside it ordered before the
beat that leaves it: "enter a dead-end interior, do all its beats, leave."
A beat whose enablers reach outside the region (a later-visit beat, e.g. a
scene gated on a switch flipped elsewhere) is exempted -- it isn't reachable
on the first visit anyway, so forcing it before the exit would be wrong.

Both functions here are pure (no I/O) and return `PrecedenceEdge`s meant to
be passed to `routing.solver.solve_route(..., soft_precedence=...)`, which
merges them in only where they close no cycle against the hard/story edges
already accepted (logging a drop at INFO otherwise) -- so a caller never
needs to pre-filter for cycles itself.

2026-10-02 (ROM run 63, operator ruling "room-aware continuity + solver"):
every function works on generic hashable NODES -- map ids by default, or
`rooms.Place`s -- so one map holding several disconnected rooms (Kevlar's
shop map 73) is several regions, not one. `world` is anything with
`edges_from(node)` (`WorldGraph` for maps, `rooms.PlaceWorld` for places),
`label` renders a node in a reason string (default `map031`; a multi-room
room reads `map073r2`), and `node_map` gives a node's map id for matching
`group_warps`, which stay `(map id, event id)`.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from ..routing.plan import PrecedenceEdge


class _World(Protocol):
    def edges_from(self, node: Any) -> Sequence[Any]: ...  # noqa: ANN401


def _default_label(node: Any) -> str:  # noqa: ANN401
    return f"map{node:03d}"


def _default_node_map(node: Any) -> int:  # noqa: ANN401
    return node


def _region_from(world: _World, start: Any, blocked_map: Any) -> frozenset[Any]:
    """Maps reachable from `start` over any world edge, never entering
    `blocked_map`, ignoring same-map self-loop edges (e.g. same-map stairs,
    which carry no map-to-map information for this purpose)."""
    seen: set[Any] = {start}
    stack: list[Any] = [start]
    while stack:
        cur = stack.pop()
        for edge in world.edges_from(cur):
            if edge.src_map == edge.dst_map:
                continue
            if edge.dst_map == blocked_map:
                continue
            if edge.dst_map not in seen:
                seen.add(edge.dst_map)
                stack.append(edge.dst_map)
    return frozenset(seen)


def _is_dead_end(
    world: _World, region: frozenset[Any], blocked_map: Any, chapter_maps: frozenset[Any],
) -> bool:
    if blocked_map in region:
        return False
    if not region <= chapter_maps:
        return False
    # Every edge leaving the region must land back on `blocked_map` or stay
    # inside the region -- true by construction of `_region_from`'s BFS, but
    # checked explicitly (cheap) rather than trusted implicitly.
    for m in region:
        for edge in world.edges_from(m):
            if edge.src_map == edge.dst_map:
                continue
            if edge.dst_map not in region and edge.dst_map != blocked_map:
                return False
    return True


def _find_dead_end_regions(
    world: _World, chapter_maps: frozenset[Any],
) -> dict[tuple[Any, frozenset[Any]], None]:
    """Every distinct `(parent_map, region)` dead-end pair reachable by some
    warp/seam-warp edge `parent -> entrance_map` within the chapter's own
    maps. A dict (not a set) purely to get deterministic insertion-order
    iteration for callers that want it; values are unused."""
    found: dict[tuple[int, frozenset[int]], None] = {}
    for parent in sorted(chapter_maps):
        for edge in world.edges_from(parent):
            if edge.kind not in ("warp", "seam_warp"):
                continue
            entrance = edge.dst_map
            if entrance == parent or entrance not in chapter_maps:
                continue
            region = _region_from(world, entrance, parent)
            if _is_dead_end(world, region, parent, chapter_maps):
                found[(parent, region)] = None
    return found


def _region_doors(
    world: _World, chapter_maps: frozenset[Any],
    group_warps: Mapping[str, tuple[tuple[int, int], ...]],
    node_map: Callable[[Any], int] = _default_node_map,
) -> list[tuple[Any, frozenset[Any], frozenset[str], frozenset[str]]]:
    """(parent, region, entry groups, exit groups) per dead-end region:
    entry groups own a warp `parent -> region`, exit groups one `region ->
    parent`."""
    out = []
    for parent, region in _find_dead_end_regions(world, chapter_maps):
        entry_groups: set[str] = set()
        exit_groups: set[str] = set()
        nodes = sorted(chapter_maps | region | {parent})
        for group_id, warps in group_warps.items():
            for map_id, event_id in warps:
                for edge in (e for n in nodes if node_map(n) == map_id
                             for e in world.edges_from(n)):
                    if edge.event_id != event_id:
                        continue
                    if edge.src_map == parent and edge.dst_map in region:
                        entry_groups.add(group_id)
                    if edge.src_map in region and edge.dst_map == parent:
                        exit_groups.add(group_id)
        out.append((parent, region, frozenset(entry_groups), frozenset(exit_groups)))
    return out


def _held_regions(
    world: _World,
    chapter_maps: frozenset[Any],
    group_warps: Mapping[str, tuple[tuple[int, int], ...]],
    gated_doors: frozenset[tuple[int, int]] | None,
    node_map: Callable[[Any], int] = _default_node_map,
) -> list[tuple[Any, frozenset[Any], frozenset[str], frozenset[str]]]:
    """Dead-end regions with an exit warp group; with `gated_doors`, only
    those whose every exit group's door refuses until a condition is met
    (`__main__._gated_doors`) -- a region you cannot walk out of early."""
    out = []
    for parent, region, entries, exits in _region_doors(
            world, chapter_maps, group_warps, node_map):
        if not exits:
            continue
        if gated_doors is not None and not all(
                door in gated_doors for g in exits for door in group_warps.get(g, ())):
            continue
        out.append((parent, region, entries, exits))
    return out


def _stay_breaks(
    held: Sequence[tuple[Any, frozenset[Any], frozenset[str], frozenset[str]]],
    entry_map: Any,
    group_map: Mapping[str, Any],
) -> Callable[[Sequence[str]], int]:
    def count(order: Sequence[str]) -> int:
        active = {i for i, (_, region, _, _) in enumerate(held) if entry_map in region}
        done: set[int] = set()
        broken = 0
        for g in order:
            for i in sorted(active):
                _, region, _, exits = held[i]
                if g in exits or group_map.get(g) not in region:
                    broken += g not in exits
                    active.discard(i)
                    done.add(i)
            for i, (_, _, entries, _) in enumerate(held):
                if i not in active and i not in done and g in entries:
                    active.add(i)
        return broken

    return count


def gated_region_check(
    world: _World,
    *,
    chapter_maps: frozenset[Any],
    entry_map: Any,
    group_map: Mapping[str, Any],
    group_warps: Mapping[str, tuple[tuple[int, int], ...]],
    gated_doors: frozenset[tuple[int, int]],
    label: Callable[[Any], str] = _default_label,
    node_map: Callable[[Any], int] = _default_node_map,
) -> Callable[[Sequence[str]], int]:
    """`region_order_check` restricted to regions whose exit is a gated door
    -- a `solve_route(hard_order_violations=)` count that must stay 0
    (2026-09-30, operator: "keep you in that gated area until everything
    that is compatible has been done"). Leaving such a region early is not a
    detour, it is a walk through a shut door (ROM run 34's regen: CH01 left
    the lab after the quiz, before the starter opened its exit)."""
    return _stay_breaks(
        _held_regions(world, chapter_maps, group_warps, gated_doors, node_map),
        entry_map, group_map)


def gated_entry_edges(
    world: _World,
    *,
    chapter_maps: frozenset[Any],
    entry_map: Any,
    group_map: Mapping[str, Any],
    group_warps: Mapping[str, tuple[tuple[int, int], ...]],
    gated_doors: frozenset[tuple[int, int]],
    hard_and_story: Sequence[PrecedenceEdge],
    any_of: Sequence[tuple[str, tuple[str, ...]]] = (),
    label: Callable[[Any], str] = _default_label,
    node_map: Callable[[Any], int] = _default_node_map,
) -> tuple[PrecedenceEdge, ...]:
    """`before=<outside group>, after=<entry group>` edges that make the
    hard stay in a gated region satisfiable by a greedy solver.

    Everything the region's exit waits on, transitively, must be done by the
    time the exit fires; the stay rule forbids leaving to do it, so whatever
    of it lies outside the region must precede the entry warp. The closure
    follows `hard_and_story` edges, and through an any-of only the
    alternatives inside the region (the ones the stay can satisfy): CH01's
    lab exit waits on `var 101 >= 1` (any of three writers, the rival scene
    the only one inside), the rival scene waits on the west-exit blocker's
    page 0 (a killer edge), so the blocker comes before the lab entry.

    A region the chapter starts inside gets no edges -- its only entry warp
    is a later re-entry, and the hard stay already holds the start."""
    pred: dict[str, set[str]] = {}
    for e in hard_and_story:
        pred.setdefault(e.after, set()).add(e.before)
    any_of_by_after: dict[str, list[tuple[str, ...]]] = {}
    for after, befores in any_of:
        any_of_by_after.setdefault(after, []).append(befores)

    edges: set[PrecedenceEdge] = set()
    for parent, region, entries, exits in _held_regions(
            world, chapter_maps, group_warps, gated_doors, node_map):
        if entry_map in region:
            continue

        def inside(g: str) -> bool:
            return group_map.get(g) in region

        seen: set[str] = set()
        stack = list(exits)
        while stack:
            node = stack.pop()
            for before in pred.get(node, ()):
                if before not in seen:
                    seen.add(before)
                    stack.append(before)
            for befores in any_of_by_after.get(node, ()):
                for before in (b for b in befores if inside(b)):
                    if before not in seen:
                        seen.add(before)
                        stack.append(before)
        outside = sorted(g for g in seen if not inside(g) and g not in entries)
        for before in outside:
            for entry in sorted(entries):
                edges.add(PrecedenceEdge(
                    before=before, after=entry,
                    reason=f"gated_entry:{label(parent)}<-{label(min(region))}"))
    return tuple(sorted(edges, key=lambda e: (e.before, e.after, e.reason)))


def gated_interior_edges(
    world: _World,
    *,
    chapter_maps: frozenset[Any],
    entry_map: Any,
    group_map: Mapping[str, Any],
    group_warps: Mapping[str, tuple[tuple[int, int], ...]],
    gated_doors: frozenset[tuple[int, int]],
    hard_and_story: Sequence[PrecedenceEdge],
    label: Callable[[Any], str] = _default_label,
    node_map: Callable[[Any], int] = _default_node_map,
) -> tuple[PrecedenceEdge, ...]:
    """`before=<entry group>, after=<interior group>` edges for a dead-end
    region every entry door of which is gated: nothing inside can be walked
    to before a beat has opened the way in (the continuity guard's own
    rule, `continuity.thread_maps(gated_doors=)`). The entry is the region's
    earliest entry group -- the one no other entry group precedes through
    `hard_and_story`; none or several such and the region gets no edges.
    2026-10-11, CH06: the leader house opens with Maria's key (the door's
    page 0) and stays open after (page 1); its rooms come after the key."""
    pred: dict[str, set[str]] = {}
    for e in hard_and_story:
        pred.setdefault(e.after, set()).add(e.before)

    edges: set[PrecedenceEdge] = set()
    for parent, region, entries, _exits in _region_doors(
            world, chapter_maps, group_warps, node_map):
        if entry_map in region or not entries:
            continue
        if not all(door in gated_doors for g in entries for door in group_warps.get(g, ())):
            continue
        first = [g for g in sorted(entries) if not (_ancestors(g, pred) & entries)]
        if len(first) != 1:
            continue
        for g in sorted(g for g, m in group_map.items() if m in region):
            if g != first[0]:
                edges.add(PrecedenceEdge(
                    before=first[0], after=g,
                    reason=f"gated_interior:{label(parent)}->{label(min(region))}"))
    return tuple(sorted(edges, key=lambda e: (e.before, e.after, e.reason)))


def region_order_check(
    world: _World,
    *,
    chapter_maps: frozenset[Any],
    entry_map: Any,
    group_map: Mapping[str, Any],
    group_warps: Mapping[str, tuple[tuple[int, int], ...]],
    label: Callable[[Any], str] = _default_label,
    node_map: Callable[[Any], int] = _default_node_map,
) -> Callable[[Sequence[str]], int]:
    """A `solve_route(order_violations=)` count: once an order enters a
    dead-end region (its first entry warp, or the chapter starting inside
    it), every group until one of its exit warps should sit inside the
    region; each group that doesn't is one violation, and the region then
    counts as left (so one break isn't charged again on every later group).
    Only the first visit is held; a region left once is free afterwards (a
    later visit walks through doors already proven). Regions without an exit
    warp group are not held -- nothing could end the stay.

    Interior-before-exit edges alone let the solver slot an outside beat
    between entering and leaving -- a transit back out through a door that
    may still be shut (2026-09-28: CH01's lab, exit gated until the starter,
    the continuity guard caught `m032e075p1`)."""
    return _stay_breaks(
        _held_regions(world, chapter_maps, group_warps, None, node_map),
        entry_map, group_map)


def _ancestors(group: str, pred: Mapping[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(pred.get(group, ()))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(pred.get(node, ()))
    return seen


def interior_exit_edges(
    world: _World,
    *,
    chapter_maps: frozenset[Any],
    entry_map: Any,
    group_map: Mapping[str, Any],
    group_warps: Mapping[str, tuple[tuple[int, int], ...]],
    hard_and_story: Sequence[PrecedenceEdge],
    any_of: Sequence[tuple[str, tuple[str, ...]]] = (),
    label: Callable[[Any], str] = _default_label,
    node_map: Callable[[Any], int] = _default_node_map,
) -> tuple[PrecedenceEdge, ...]:
    """`before=<interior group>, after=<exit group>` edges for every
    dead-end region found in `chapter_maps`.

    `entry_map` is accepted for interface symmetry with the chapter's other
    entry-point plumbing and documents an edge case explicitly allowed by
    the ruling (the entry map may sit INSIDE a dead-end region -- CH01
    starts upstairs in the player's house); it does not otherwise change the
    algorithm below, since the entry point is a fixed route endpoint, not a
    group `hard_and_story` can carry an edge to or from.

    A dead-end region behind parent map `P` is the set of maps reachable
    from some entrance map `X` (a warp/seam-warp edge `P -> X`, both in
    `chapter_maps`) without re-entering `P`, provided that whole set stays
    inside `chapter_maps` and leaks only back to `P` (`_is_dead_end`).
    Nested regions (a 2F behind a 1F behind the town) are found and treated
    independently, since the 2F region's own BFS is blocked only by the 1F
    map, not by the town.

    For each region:
      - entry groups: groups owning a warp row whose edge is `P -> (map in
        region)`.
      - exit groups: groups owning a warp row whose edge is `(map in
        region) -> P`.
      - interior groups: groups located (`group_map`) inside the region,
        excluding exit groups.
      - later-visit exclusion: an interior group has an ancestor (via
        `hard_and_story`'s before->after edges) located outside the region
        that isn't itself an ancestor-or-self of any entry group -- i.e. its
        precondition can't be satisfied on the FIRST visit through the
        region's own entrance(s). So is one with a story any-of (`any_of`,
        `(after, befores)`) every alternative of which is outside, and one
        with a later-visit ancestor. Such a group gets no edge.

    Every remaining (first-visit) interior group is ordered before every
    exit group of its region (`before=interior, after=exit`, skipping
    `interior == exit`), reason `interior_exit:map{P:03d}<-map{X:03d}` (`X`
    = min entrance map of the region, for a stable, readable reason string).
    Output is sorted for determinism.
    """
    pred: dict[str, set[str]] = {}
    for e in hard_and_story:
        pred.setdefault(e.after, set()).add(e.before)

    edges: set[PrecedenceEdge] = set()

    for parent, region, entry_groups, exit_groups in _region_doors(
            world, chapter_maps, group_warps, node_map):
        if not exit_groups:
            continue

        # Closure of "necessarily satisfied by the time the region is first
        # entered": every entry group, plus everything that must happen
        # before an entry group.
        entry_closure: set[str] = set(entry_groups)
        for g in entry_groups:
            entry_closure |= _ancestors(g, pred)

        interior_groups = {
            g for g, m in group_map.items() if m in region
        } - exit_groups

        def outside(a: str) -> bool:
            return group_map.get(a) not in region and a not in entry_closure

        # Later-visit, to a fixpoint: an outside edge ancestor, an any-of
        # whose every alternative is outside (CH01's Auntie heal page, var
        # 101 >= 2, written only outside the house), or an edge ancestor
        # that is itself later-visit.
        later: set[str] = set()
        changed = True
        while changed:
            changed = False
            for g in interior_groups - later:
                ancestors = _ancestors(g, pred)
                if (any(outside(a) or a in later for a in ancestors)
                        or any(all(outside(b) or b in later for b in befores)
                               for after, befores in any_of if after == g)):
                    later.add(g)
                    changed = True

        for g in sorted(interior_groups - later):
            for e in sorted(exit_groups):
                if g == e:
                    continue
                entrance = min(region)
                edges.add(PrecedenceEdge(
                    before=g, after=e,
                    reason=f"interior_exit:{label(parent)}<-{label(entrance)}",
                ))

    return tuple(sorted(edges, key=lambda e: (e.before, e.after, e.reason)))


def arrival_nudge_edges(
    *,
    nudge_groups: Mapping[str, tuple[int, int, int | None]],
    warp_groups: Mapping[str, tuple[int, int, int]],
) -> tuple[PrecedenceEdge, ...]:
    """`before=<warp group>, after=<nudge group>` edges: an arrival nudge
    (a beat that reads a tile/mat only sensible right after stepping off a
    specific warp) must come after the warp beat that lands the player
    there from the nudge's required source map.

    `nudge_groups[g] = (nudge_map, source_map, source_event)`: group `g`'s
    beat lives on `nudge_map` and needs the player to have just arrived there
    FROM `source_map` over warp event `source_event` (None: any warp between
    the two maps). `warp_groups[g] = (origin_map, dest_map, event)`: group `g`
    owns warp `event` crossing `origin_map -> dest_map`. Every warp group whose
    `origin_map == source_map`, `dest_map == nudge_map` and event matches is
    ordered before the nudge (2026-10-02: Kevlar's four shop doors, one nudge
    each). Output sorted for determinism.
    """
    edges: set[PrecedenceEdge] = set()
    for nudge_id, (nudge_map, source_map, source_event) in nudge_groups.items():
        for warp_id, (origin_map, dest_map, event) in warp_groups.items():
            if origin_map == source_map and dest_map == nudge_map and (
                    source_event is None or event == source_event):
                edges.add(PrecedenceEdge(
                    before=warp_id, after=nudge_id,
                    reason=f"arrival_nudge:map{source_map:03d}->map{nudge_map:03d}",
                ))
    return tuple(sorted(edges, key=lambda e: (e.before, e.after, e.reason)))
