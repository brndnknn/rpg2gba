# Task 5 — Adapt: template keyword arguments (30 points)

## Goal

Implement `beat_gen/adapt.py`. Every template call in the generated module needs arguments.
They come from two places:

| Kind | Function | Source |
|---|---|---|
| source-derived | `archetype_kwargs(beat, match, floors, map_constant_fn=)` | the RMXP floor + the archetype match |
| route-derived | `route_kwargs(template, side)` | the solver's pick |

plus `warp_candidates(cell, graph)`, which makes a warp pickable in the first place.

**The oracle is the hand module.** `playtest/chapters/ch05.py` was written by a person who
typed `item="ITEM_ESCAPE_ROPE"`, `trainer_const="TRAINER_MANNY_5"` and so on into each
template call. `test_beat_gen_adapt.py`'s `EXPECTED` table is those values. Your code must
reach every one of them from source data alone. That's R1 ("zero hand overrides") in one
test.

## What the floor gives you (measured on CH05)

```
map036/ev003/p0  item_grant {'item': 'ESCAPEROPE', 'quantity': 1}
map036/ev004/p0  battle     {'kind': 'trainer', 'name': 'Manny', 'trainer_type': 'HIKER'}
map036/ev001/p0  warp       {'map_id': 35, 'x': 20, 'y': 33, 'direction': 2, 'arrives_on_door': True}
```

So `ESCAPEROPE` has to become `ITEM_ESCAPE_ROPE`, and (Manny, HIKER) has to become
`TRAINER_MANNY_5`. **Neither mapping is yours to invent.** CLAUDE.md §4.3's table names the
single source of truth for `ITEM_*`/`TRAINER_*` spellings and resolution. Find it, and find
the Phase 2 sidecar that lists minted trainers. The `_5` is the thing to explain: which of
the trainer's fields becomes the suffix, and where is it recorded?

## Per-template notes

- **warp**: `dest_map_constant` from the floor's `map_id` through `map_constant_fn`;
  `mechanism="threshold"` (A2's answer: every warp source cell is door-stamped, so it's a
  step-on crossing).
- **arrival_nudge**: `from_map_constant`/`from_event_id` = the chapter warp **whose floor
  lands on this event's cell**. The event's `x`/`y` are in the staged map JSON. Which rows'
  floors do you have to search?
- **item_ball**: `negative_beat=True` exactly when the match has a `spent` role.
- **trainer**: the five behaviour flags are already in `match.params`, under the template's
  own keyword names. `defeat_flag` is `f"TRAINER_FLAGS_START + {trainer_const}"`; `ch05.py`'s
  `_trainer_defeat_flag` docstring explains why it isn't a self-switch.
- All archetype templates take `map_constant`, `map_id`, `event_id`.
- Return **only** keywords the template accepts, and **every** required one except those the
  emitter or route supply. A test checks both against `inspect.signature`.

## warp_candidates and route_kwargs

`cell_for_row` puts the player *on* a warp's cell, which offers the solver no side to pick,
so a warp would never get a press direction. `warp_candidates` lists the walkable orthogonal
neighbours as `ApproachCandidate`s ("north" means the player stands above the tile).
`route_kwargs("warp", "south")` then says: stand south, press `UP`, come back pressing `DOWN`,
`round_trip=True` (A3's idiom, applied to warps). Every other template just takes
`approach_prefer=side`.

## Hints

- **Look for the forward check before writing the reverse lookup.** `playtest/archetypes/
  trainer.py` already validates a trainer's identity against the battle floor, and
  `item_ball.py` already resolves item constants. Their lookups are your lookups.
- **Ambiguity is a refusal, not a pick.** The trainer lookup keys on what the battle
  floor carries. CH05's three trainers each match exactly one entry, but nothing in the floor
  distinguishes two trainers with the same name *and* class. If you find more than one match,
  raise and list them all (checked 2026-09-19: none of CH05's three is ambiguous).
- `flavour_npc` has no row in `EXPECTED` (CH05 has no flavour NPC match), so no test pins its
  kwargs. Read its signature and the `variant` check in `flavour_npc.py`, and decide.
- Write one small function per template and dispatch on `beat.template` with a dict. The
  per-template logic is short, and mixing five of them into one function is what makes it
  hard to read.
- Fail loud with the **row id** in the message. `test_missing_floor_assertion_fails_loud`
  strips a real floor's `item_grant` and expects the row named.
- `make_kwargs` sorts for you.

## Tests

`tests/test_beat_gen_adapt.py`: the ten CH05 archetype beats against the hand values; a
signature-compliance test per beat; sortedness; the loud failure; `warp_candidates` in open
space and against walls and edges; the four warp presses; `approach_prefer` for everything
else; unknown side.

## Questions (commit message)

1. Where did `TRAINER_MANNY_5`'s `_5` come from? Name the file and the field.
2. The hand author and your generator agree on every value in `EXPECTED`. Name one kwarg in
   `ch05.py` you could **not** derive (or chose not to), and say whether that's a gap in the
   source data or a genuine authoring choice.
3. `round_trip=True` on a warp whose destination is outside the chapter (map037 ev2 → map 40,
   unstaged) would fail in the ROM. How should the generator know not to do that, and which
   stage should own the decision?
