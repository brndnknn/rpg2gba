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

Anything else fails loud naming the beat: a beat on a map the player
can't be on means the route needs a crossing no beat claims, and papering
over that would ship a module that can't be walked.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs


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
) -> tuple[PlannedBeat, ...]:
    """`beats` with `start_side`/`end_side` set on every crossing warp (and
    `round_trip` dropped: `end_side` replaces it).

    `warp_dest` maps each warp beat to its destination map; `nudge_source`
    maps each arrival-nudge beat to the map its source warp leaves from.
    Where the next beat accepts either side, the warp ends where it started
    (two legs, not three). Raises `ValueError` naming the beat when the
    player can't be on the map a beat needs."""
    out: list[PlannedBeat] = []
    cur = start_map
    arrived_from: int | None = None     # the map the last crossing left from
    for i, beat in enumerate(beats):
        if _is_crossing_warp(beat):
            origin, dest = beat.map_id, warp_dest[beat.name]
            if cur not in (origin, dest):
                raise ValueError(
                    f"beat {beat.name!r} crosses map {origin} <-> {dest}, but the player "
                    f"is on map {cur}: the route needs a crossing no beat claims")
            other = dest if cur == origin else origin
            if i + 1 < len(beats):
                need = _maps_accepted(beats[i + 1], warp_dest)
                ends = [m for m in (cur, other) if m in need]
                if not ends:
                    raise ValueError(
                        f"beat {beat.name!r} can end on map {origin} or {dest}, but the next "
                        f"beat {beats[i + 1].name!r} needs map {sorted(need)}")
                end = ends[0]
            else:
                end = cur
            kwargs = {k: v for k, v in beat.kwargs if k != "round_trip"}
            kwargs["start_side"] = "origin" if cur == origin else "dest"
            kwargs["end_side"] = "origin" if end == origin else "dest"
            out.append(dataclasses.replace(beat, kwargs=make_kwargs(**kwargs)))
            # Legs alternate, so the last one always lands on `end` from the
            # opposite side.
            arrived_from = origin if end == dest else dest
            cur = end
            continue

        if cur != beat.map_id:
            raise ValueError(
                f"beat {beat.name!r} is on map {beat.map_id}, but the player is on map {cur}: "
                f"the route needs a crossing no beat claims")
        if beat.template == "arrival_nudge" and arrived_from != nudge_source[beat.name]:
            raise ValueError(
                f"arrival nudge {beat.name!r} needs the player to have just landed on map "
                f"{beat.map_id} from map {nudge_source[beat.name]}; the beat before it is "
                f"{out[-1].name if out else None!r}")
        arrived_from = None     # only the beat right after a crossing sees the arrival
        out.append(beat)
    return tuple(out)
