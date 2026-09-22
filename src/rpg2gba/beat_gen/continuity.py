"""Map continuity over the solved order (C6 part two).

Beats don't travel between maps on their own: every template walks on the
map it expects to start on, and only a warp beat moves the player to
another map. So the generated module is walkable only if, beat by beat,
the player is on the map the next beat needs, and the only way to change
map is a warp beat's legs. This pass tracks the player's map from the
chapter's start through the ordered beats and sets each warp beat's
`start_side` (the side the player is on) and `end_side` (the side the next
beat needs). `warp_beat` then walks the shortest leg sequence of two or
more that does both (F,B / F,B,F / B,F / B,F,B), so every warp is still
proven in both directions (the operator's round-trip rule).

An arrival nudge observes the autorun that fires when the player lands on
its map from its source map, so the beat before it must be a warp whose
last leg arrives exactly that way.

When the next beat is on a map no warp beat takes the player to, a
`transit` beat is inserted before it: rowless travel across the warps
between the two maps (`route_between`, a shortest hop path over the
chapter's own maps). The warps it crosses are asserted by their own beats;
the transit only gets the player there. With no way at all, it fails loud
naming the beat.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence

from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs

Hop = tuple[str, int, int, str, str]   # `generic.transit_beat`'s hop shape
RouteBetween = Callable[[int, int], tuple[tuple[int, int, Hop], ...]]
"""(from map, to map) -> ((src map id, dest map id, hop), ...); raises
`ValueError` when there is no way."""


def _is_crossing_warp(beat: PlannedBeat) -> bool:
    return beat.template == "warp" and not dict(beat.kwargs).get("boundary", False)


def _maps_accepted(beat: PlannedBeat, warp_dest: Mapping[str, int]) -> frozenset[int]:
    """The maps a beat can start on: either side of a crossing warp, else
    its own map."""
    if _is_crossing_warp(beat):
        return frozenset({beat.map_id, warp_dest[beat.name]})
    return frozenset({beat.map_id})


def thread_maps(
    beats: Sequence[PlannedBeat],
    *,
    start_map: int,
    warp_dest: Mapping[str, int],
    nudge_source: Mapping[str, int],
    route_between: RouteBetween | None = None,
) -> tuple[PlannedBeat, ...]:
    """`beats` with `start_side`/`end_side` set on every crossing warp (and
    `round_trip` dropped: `end_side` replaces it), and a `transit` beat
    inserted wherever the player must change map between two beats.

    `warp_dest` maps each warp beat to its destination map; `nudge_source`
    maps each arrival-nudge beat to the map its source warp leaves from.
    Where the next beat accepts either side, the warp ends where it started
    (two legs, not three). `route_between(a, b)` returns the hops from map
    `a` to map `b` (raising when there are none); without it, a map change
    no beat performs raises `ValueError` naming the beat."""
    out: list[PlannedBeat] = []
    cur = start_map
    arrived_from: int | None = None     # the map the last crossing left from

    def travel(beat: PlannedBeat, targets: Sequence[int], via: int | None = None) -> None:
        """Insert a transit to the first of `targets` with the fewest hops,
        going through map `via` first when given (an arrival nudge must land
        from its source map, so the transit's last hop leaves `via`)."""
        nonlocal cur, arrived_from
        if route_between is None:
            raise ValueError(
                f"beat {beat.name!r} needs map {sorted(targets)}, but the player is on map "
                f"{cur}: the route needs a crossing no beat claims")
        routes = []
        for target in targets:
            try:
                if via is None:
                    routes.append(route_between(cur, target))
                else:
                    first = route_between(cur, via) if cur != via else ()
                    routes.append(first + route_between(via, target))
            except ValueError:
                continue
        if not routes:
            raise ValueError(f"beat {beat.name!r}: no way from map {cur} to {sorted(targets)}"
                             + (f" via {via}" if via is not None else ""))
        route = min(routes, key=len)
        out.append(PlannedBeat(name=f"{beat.name}_transit", template="transit", map_id=cur,
                               rows=(), group=beat.group,
                               kwargs=make_kwargs(hops=tuple(hop for _, _, hop in route))))
        arrived_from, cur = route[-1][0], route[-1][1]

    for i, beat in enumerate(beats):
        if _is_crossing_warp(beat):
            origin, dest = beat.map_id, warp_dest[beat.name]
            if cur not in (origin, dest):
                travel(beat, (origin, dest))
            other = dest if cur == origin else origin
            end = cur
            if i + 1 < len(beats):
                need = _maps_accepted(beats[i + 1], warp_dest)
                ends = [m for m in (cur, other) if m in need]
                if ends:
                    end = ends[0]
                elif route_between is None:
                    raise ValueError(
                        f"beat {beat.name!r} can end on map {origin} or {dest}, but the next "
                        f"beat {beats[i + 1].name!r} needs map {sorted(need)}")
            kwargs = {k: v for k, v in beat.kwargs if k != "round_trip"}
            kwargs["start_side"] = "origin" if cur == origin else "dest"
            kwargs["end_side"] = "origin" if end == origin else "dest"
            out.append(dataclasses.replace(beat, kwargs=make_kwargs(**kwargs)))
            # Legs alternate, so the last one always lands on `end` from the
            # opposite side.
            arrived_from = origin if end == dest else dest
            cur = end
            continue

        if beat.template == "arrival_nudge" and route_between is not None and (
                cur != beat.map_id or arrived_from != nudge_source[beat.name]):
            travel(beat, (beat.map_id,), via=nudge_source[beat.name])
        elif cur != beat.map_id:
            travel(beat, (beat.map_id,))
        if beat.template == "arrival_nudge" and arrived_from != nudge_source[beat.name]:
            raise ValueError(
                f"arrival nudge {beat.name!r} needs the player to have just landed on map "
                f"{beat.map_id} from map {nudge_source[beat.name]}; the beat before it is "
                f"{out[-1].name if out else None!r}")
        arrived_from = None     # only the beat right after a crossing sees the arrival
        out.append(beat)
    return tuple(out)
