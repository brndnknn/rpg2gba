"""Map continuity over the solved order (C6 part two).

Beats don't travel between maps on their own: every template walks on the
map it expects to start on, and only a warp beat moves the player to
another map. So the generated module is walkable only if, beat by beat,
the player is on the map the next beat needs, and the only way to change
map is a warp beat's legs. This pass tracks the player's map from the
chapter's start through the ordered beats and sets each warp beat's
`start_side` (the side the player is on) and `end_side` (the side the next
beat needs).

2026-09-28 (operator ruling, `investigations/warp-round-trips-and-gated-
doors.md`): warp beats are one-way by default, amending the round-trip rule
this docstring used to state. A crossing warp beat now always STARTS on its
origin (a transit gets it there if the player isn't already) and ends on
`dest` (`warp_beat` walks a single "F" leg) unless the very next beat needs
the origin and not the dest, in which case it ends on `origin` ("F", "B") --
the local back-and-forth a through-map needs when the route has no other
reason to cross back (CH05's Passage Cave). The reverse direction of an
ordinary crossing is proven by ITS OWN warp beat elsewhere in the chain, not
by a round trip here. A transit beat may cross a GATED door only after that
door's own warp beat has already run in the output order (`gated_doors=`);
otherwise generation fails loud naming the hop and the door's warp beat.

An escort (C9 grading ruling 11) is a one-way crossing: it starts on its
own map and leaves the player on its destination, having arrived there from
the origin. `warp_dest` carries its destination too.

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
RouteStep = tuple[int, int, Hop, int]  # (src map id, dst map id, hop, event id)
RouteBetween = Callable[[int, int], tuple[RouteStep, ...]]
"""(from map, to map) -> ((src map id, dest map id, hop, event id), ...);
raises `ValueError` when there is no way. The event id is the door event
each hop crosses -- needed by the gated-door transit guard, since a hop's
`Hop` tuple (`generic.transit_beat`'s own shape) carries no event id."""


def _is_crossing_warp(beat: PlannedBeat) -> bool:
    return beat.template == "warp" and not dict(beat.kwargs).get("boundary", False)


def _maps_accepted(beat: PlannedBeat, warp_dest: Mapping[str, int]) -> frozenset[int]:
    """The maps a beat can start on. 2026-09-28: a crossing warp beat now
    always starts on its origin (`beat.map_id`), never on `dest` -- so this
    is just the beat's own map for every beat, crossing warp or not.
    `warp_dest` is kept as a parameter for call-site stability even though
    it is no longer read here."""
    del warp_dest
    return frozenset({beat.map_id})


def thread_maps(
    beats: Sequence[PlannedBeat],
    *,
    start_map: int,
    warp_dest: Mapping[str, int],
    nudge_source: Mapping[str, int],
    route_between: RouteBetween | None = None,
    gated_doors: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[PlannedBeat, ...]:
    """`beats` with `start_side`/`end_side` set on every crossing warp (and
    `round_trip` dropped: `end_side` replaces it), and a `transit` beat
    inserted wherever the player must change map between two beats.

    `warp_dest` maps each warp beat to its destination map; `nudge_source`
    maps each arrival-nudge beat to the map its source warp leaves from.
    A crossing warp beat always starts on its origin (`travel()`s there
    first if the player isn't already) and ends on `dest` (one leg) unless
    the next beat needs `origin` and not `dest`, in which case it ends on
    `origin` (the local back-and-forth, "F", "B"). If the next beat needs
    neither side, the warp still ends on `dest`; the next beat's own travel
    inserts whatever transit it needs. `route_between(a, b)` returns the
    hops from map `a` to map `b` (raising when there are none); without it,
    a map change no beat performs raises `ValueError` naming the beat.

    `gated_doors` is `(map id, event id)` pairs of doors that refuse until a
    condition is met (`metadata_wiring.classify_event`'s own test). A
    transit hop may cross one only after the warp beat that claims that same
    door has already run in the output order; otherwise this raises
    `ValueError` naming the transit, the hop, and that warp beat (or that
    none claims it)."""
    out: list[PlannedBeat] = []
    cur = start_map
    arrived_from: int | None = None     # the map the last crossing left from
    claimed_doors: set[tuple[int, int]] = set()
    door_beat_name: dict[tuple[int, int], str] = {
        (b.map_id, int(dict(b.kwargs)["event_id"])): b.name
        for b in beats if _is_crossing_warp(b)
    }

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
        for src, _dst, _hop, ev in route:
            key = (src, ev)
            if key in gated_doors and key not in claimed_doors:
                owner = door_beat_name.get(key)
                raise ValueError(
                    f"beat {beat.name!r}: its transit crosses gated door (map {src}, "
                    f"event {ev}) before that door's own warp beat has run -- "
                    + (f"{owner!r} claims it later in the order"
                       if owner is not None else "no warp beat in this chapter claims it"))
        out.append(PlannedBeat(name=f"{beat.name}_transit", template="transit", map_id=cur,
                               rows=(), group=beat.group,
                               kwargs=make_kwargs(hops=tuple(hop for _, _, hop, _ in route))))
        arrived_from, cur = route[-1][0], route[-1][1]

    for i, beat in enumerate(beats):
        if _is_crossing_warp(beat):
            origin, dest = beat.map_id, warp_dest[beat.name]
            if cur != origin:
                travel(beat, (origin,))
            end = "dest"
            if i + 1 < len(beats):
                need = _maps_accepted(beats[i + 1], warp_dest)
                if origin in need and dest not in need:
                    end = "origin"
            # `adapt.route_kwargs` always supplies `return_direction` (it
            # used to always be load-bearing, every `end_side` crossed the
            # reciprocal). 2026-09-28: `end == "dest"` from an origin start
            # is now the one-leg case (`warp._legs`) that does NOT cross the
            # reciprocal, so a stale `return_direction` here would trip
            # `warp_beat`'s own "no effect on a lone forward crossing"
            # guard -- drop it along with `round_trip`.
            drop = {"round_trip"} | ({"return_direction"} if end == "dest" else set())
            kwargs = {k: v for k, v in beat.kwargs if k not in drop}
            kwargs["start_side"] = "origin"
            kwargs["end_side"] = end
            out.append(dataclasses.replace(beat, kwargs=make_kwargs(**kwargs)))
            claimed_doors.add((origin, int(dict(beat.kwargs)["event_id"])))
            if end == "origin":
                arrived_from, cur = dest, origin
            else:
                arrived_from, cur = origin, dest
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
        if beat.template == "escort":
            arrived_from, cur = beat.map_id, warp_dest[beat.name]
    return tuple(out)
