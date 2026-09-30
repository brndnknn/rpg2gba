"""Refused Pokémon gifts inside a claimed page (2026-09-29 operator ruling,
ROM run 27).

The starter give (`map050/ev019/p0/b1`: `pbAddPokemon(X,5) if
$game_variables[151]==N`, three species on one var) is refused by the floor
(`conditional_script_effect`: the floor is unconditional, so it can't claim
which species is given). The arm still runs on the ROM, inside the page its
beat claims, and the transpiler's gift flow (`transpiler._emit_give_pokemon`)
puts an "obtained" line and a nickname yes/no on screen. The beat must get
through that ceremony to keep reading the page's own text, without claiming
the arm: `generic_beat(gift_ceremonies=)` names the list indexes where one
runs, and the body answers NO there and checks nothing.

One ceremony per list index: the block's statements are guarded on one var,
so exactly one of them gives. A ceremony that never comes up fails the beat
loud.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import PlannedBeat, Refusal, make_kwargs
from rpg2gba.chapter_manifest.schema import parse_row_id

_REASON = "conditional_script_effect"
_HEAD = "pbAddPokemon"


def _gift_indexes(refusals: Sequence[Refusal], floors: Mapping[str, RowFloor]) -> dict[str, set[int]]:
    """Owning page row id -> list indexes of its refused, conditional gives."""
    out: dict[str, set[int]] = {}
    for refusal in refusals:
        if refusal.reason != _REASON or _HEAD not in refusal.detail:
            continue
        floor = floors.get(refusal.row_id)
        page = parse_row_id(refusal.row_id).owning_page_row_id
        if floor is None or page is None:
            continue
        for r in floor.refusals:
            if r.reason == _REASON and _HEAD in r.detail and r.list_index is not None:
                out.setdefault(page, set()).add(r.list_index)
    return out


def annotate_gift_ceremonies(
    beats: tuple[PlannedBeat, ...],
    refusals: Sequence[Refusal],
    floors: Mapping[str, RowFloor],
) -> tuple[PlannedBeat, ...]:
    """Give each generic beat whose page holds a refused conditional gift a
    `gift_ceremonies` kwarg (sorted list indexes)."""
    gifts = _gift_indexes(refusals, floors)
    if not gifts:
        return beats
    out = []
    for beat in beats:
        page = parse_row_id(beat.rows[0]).owning_page_row_id if beat.rows else None
        if beat.template != "generic" or page not in gifts:
            out.append(beat)
            continue
        kwargs = dict(beat.kwargs)
        kwargs["gift_ceremonies"] = tuple(sorted(gifts[page]))
        out.append(dataclasses.replace(beat, kwargs=make_kwargs(**kwargs)))
    return tuple(out)
