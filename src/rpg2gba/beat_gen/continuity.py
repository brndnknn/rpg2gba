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
from rpg2gba.beat_gen.rooms import Place

Hop = tuple[str, int, int, str, str]   # `generic.transit_beat`'s hop shape
RouteStep = tuple[Place, Place, Hop, int]  # (src place, dst place, hop, event id)
RouteBetween = Callable[[Place, Place], tuple[RouteStep, ...]]
"""(from place, to place) -> ((src place, dest place, hop, event id), ...);
raises `ValueError` when there is no way. The event id is the door event
each hop crosses -- needed by the gated-door transit guard, since a hop's
`Hop` tuple (`generic.transit_beat`'s own shape) carries no event id."""


def _is_crossing_warp(beat: PlannedBeat) -> bool:
    return beat.template == "warp" and not dict(beat.kwargs).get("boundary", False)


def _start_place(beat: PlannedBeat, beat_place: Mapping[str, Place],
                 warp_origin: Mapping[str, Place]) -> Place:
    """The place a beat starts in: a crossing warp's origin room, else the
    beat's own place. Fails loud on a beat with neither."""
    table = warp_origin if _is_crossing_warp(beat) else beat_place
    try:
        return table[beat.name]
    except KeyError:
        raise ValueError(f"beat {beat.name!r} has no start place") from None


def thread_maps(
    beats: Sequence[PlannedBeat],
    *,
    start: Place,
    beat_place: Mapping[str, Place],
    warp_dest: Mapping[str, Place],
    warp_origin: Mapping[str, Place],
    nudge_source: Mapping[str, tuple[int, int | None]],
    places_on_map: Mapping[int, tuple[Place, ...]] | None = None,
    route_between: RouteBetween | None = None,
    door_steps: Mapping[tuple[int, int], tuple[RouteStep, ...]] | None = None,
    gated_doors: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[PlannedBeat, ...]:
    """`beats` with `start_side`/`end_side` set on every crossing warp (and
    `round_trip` dropped: `end_side` replaces it), and a `transit` beat
    inserted wherever the player must change map between two beats.

    Places are `(map id, room)`. `beat_place` is the place each non-transit
    beat starts in, `warp_origin` the place each crossing warp is pressed
    from, `warp_dest` the place a warp or escort lands in. `nudge_source`
    maps each arrival-nudge beat to `(map, warp event)` its source warp
    leaves from; the event is None when one warp between the two maps is the
    only candidate (the template's own `from_event_id` is then omitted).
    `places_on_map` lists the places of each map (an arrival nudge's transit
    may enter its source map in any of them -- the shortest route wins; with
    an event, its last hop must be that very warp: 2026-10-02, the three
    Kevlar shop doors' nudges all left by one door). `door_steps` maps
    (map id, warp event) to the hops over that warp; without it, the
    shortest route's last hop must happen to be the warp.
    A crossing warp beat always starts on its origin (`travel()`s there
    first if the player isn't already) and ends on `dest` (one leg) unless
    the next beat needs `origin` and not `dest`, in which case it ends on
    `origin` (the local back-and-forth, "F", "B"). If the next beat needs
    neither side, the warp still ends on `dest`; the next beat's own travel
    inserts whatever transit it needs. `route_between(a, b)` returns the
    hops from place `a` to place `b` (raising when there are none); without it,
    a map change no beat performs raises `ValueError` naming the beat.

    `gated_doors` is `(map id, event id)` pairs of doors that refuse until a
    condition is met (`metadata_wiring.classify_event`'s own test). A
    transit hop may cross one only after the warp beat that claims that same
    door has already run in the output order; otherwise this raises
    `ValueError` naming the transit, the hop, and that warp beat (or that
    none claims it)."""
    out: list[PlannedBeat] = []
    cur = start
    # (map, warp event) the last crossing left from; the event is None when
    # the crossing doesn't say (a warp beat's return leg, an escort).
    arrived_from: tuple[int, int | None] | None = None
    claimed_doors: set[tuple[int, int]] = set()
    door_beat_name: dict[tuple[int, int], str] = {
        (b.map_id, int(dict(b.kwargs)["event_id"])): b.name
        for b in beats if _is_crossing_warp(b)
    }

    def arrived_as(need: tuple[int, int | None]) -> bool:
        if arrived_from is None or arrived_from[0] != need[0]:
            return False
        return need[1] is None or arrived_from[1] is None or arrived_from[1] == need[1]

    def travel(beat: PlannedBeat, targets: Sequence[Place],
               via: tuple[int, int | None] | None = None) -> None:
        """Insert a transit to the first of `targets` with the fewest hops,
        going through map `via[0]` (any place on it) first when given (an
        arrival nudge must land from its source map, so the transit's last
        hop leaves `via[0]` -- over warp event `via[1]` when that is set)."""
        nonlocal cur, arrived_from
        if route_between is None:
            raise ValueError(
                f"beat {beat.name!r} needs place {sorted(targets)}, but the player is at "
                f"{cur}: the route needs a crossing no beat claims")
        routes = []
        for target in targets:
            try:
                if via is None:
                    routes.append(route_between(cur, target))
                else:
                    via_map, via_event = via
                    for mid in sorted((places_on_map or {}).get(via_map, ((via_map, 0),))):
                        try:
                            first = route_between(cur, mid) if cur != mid else ()
                            tail = route_between(mid, target)
                        except ValueError:
                            continue
                        if via_event is not None and (
                                len(tail) != 1 or tail[0][3] != via_event):
                            continue
                        routes.append(first + tail)
                    if via_event is not None and door_steps is not None:
                        for step in door_steps.get((via_map, via_event), ()):
                            if step[1] != target:
                                continue
                            try:
                                first = route_between(cur, step[0]) if cur != step[0] else ()
                            except ValueError:
                                continue
                            routes.append(first + (step,))
            except ValueError:
                continue
        if not routes:
            raise ValueError(f"beat {beat.name!r}: no way from {cur} to {sorted(targets)}"
                             + (f" via {via}" if via is not None else ""))
        route = min(routes, key=len)
        for src, _dst, _hop, ev in route:
            key = (src[0], ev)
            if key in gated_doors and key not in claimed_doors:
                owner = door_beat_name.get(key)
                raise ValueError(
                    f"beat {beat.name!r}: its transit crosses gated door (map {src[0]}, "
                    f"event {ev}) before that door's own warp beat has run -- "
                    + (f"{owner!r} claims it later in the order"
                       if owner is not None else "no warp beat in this chapter claims it"))
        out.append(PlannedBeat(name=f"{beat.name}_transit", template="transit", map_id=cur[0],
                               rows=(), group=beat.group,
                               kwargs=make_kwargs(hops=tuple(hop for _, _, hop, _ in route))))
        arrived_from, cur = (route[-1][0][0], route[-1][3]), route[-1][1]

    for i, beat in enumerate(beats):
        if _is_crossing_warp(beat):
            origin, dest = warp_origin[beat.name], warp_dest[beat.name]
            if cur != origin:
                travel(beat, (origin,))
            end = "dest"
            if i + 1 < len(beats):
                need = _start_place(beats[i + 1], beat_place, warp_origin)
                if origin == need and dest != need:
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
            claimed_doors.add((origin[0], int(dict(beat.kwargs)["event_id"])))
            if end == "origin":
                arrived_from, cur = (dest[0], None), origin
            else:
                arrived_from, cur = (origin[0], int(dict(beat.kwargs)["event_id"])), dest
            continue

        here = _start_place(beat, beat_place, warp_origin)
        if beat.template == "arrival_nudge" and route_between is not None and (
                cur != here or not arrived_as(nudge_source[beat.name])):
            travel(beat, (here,), via=nudge_source[beat.name])
        elif cur != here:
            travel(beat, (here,))
        if beat.template == "arrival_nudge" and not arrived_as(nudge_source[beat.name]):
            raise ValueError(
                f"arrival nudge {beat.name!r} needs the player to have just landed on map "
                f"{beat.map_id} from (map, warp event) {nudge_source[beat.name]}; the beat "
                f"before it is "
                f"{out[-1].name if out else None!r}")
        arrived_from = None     # only the beat right after a crossing sees the arrival
        out.append(beat)
        if beat.template == "escort":
            arrived_from, cur = (here[0], None), warp_dest[beat.name]
    return tuple(out)


def attach_reclears(beats: Sequence[PlannedBeat],
                    map_constant_for: Callable[[int], str],
                    passage: Mapping[str, Sequence[str]]) -> tuple[PlannedBeat, ...]:
    """Give a transit the obstacles it must clear again on arrival
    (`generic.transit_beat`'s `reclear`).

    Obstacles respawn on a map reload, and a transit's arrival is one, so a
    wall the chain treats as released (`__main__`'s `released`) is standing
    again when the transit lands. That only matters when the beat right after
    the transit is reachable only THROUGH such a wall: `passage` is
    `_passage_enablers`' row -> the clearing rows it waits on. The transit
    gets those walls that an EARLIER smash beat cleared on its destination
    map, page rows only (an arm row shares its page's event); the transit
    skips any already gone. CH09 (2026-10-22): CH08's walk from the lab to
    Moki's east edge met Moki's rock wall, smashed earlier in CH08; Route 1's
    transit to a stair the rocks don't wall gets nothing."""
    cleared: dict[str, dict[str, str]] = {}
    out: list[PlannedBeat] = []
    for i, beat in enumerate(beats):
        kw = dict(beat.kwargs)
        if beat.template == "smash":
            pages = [r for r in beat.rows if not r.rsplit("/", 1)[-1].startswith("b")]
            cleared.setdefault(map_constant_for(beat.map_id), {}).update(
                (r, kw["capability"]) for r in pages)
        elif beat.template == "transit" and kw["hops"] and i + 1 < len(beats):
            on_dest = cleared.get(kw["hops"][-1][4], {})
            waits = {w for r in beats[i + 1].rows for w in passage.get(r, ())}
            need = tuple((r, cap) for r, cap in on_dest.items() if r in waits)
            if need:
                beat = dataclasses.replace(beat, kwargs=make_kwargs(**kw, reclear=need))
        out.append(beat)
    return tuple(out)
