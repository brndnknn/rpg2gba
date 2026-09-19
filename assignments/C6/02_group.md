# Task 2 — Group: which beat claims each row? (25 points)

## Goal

Implement `beat_gen/group.py`: owned rows → `PlannedBeat`s, where every owned row is claimed by
exactly one beat.

## Learning objectives

- Layered claiming: the more specific interpreter goes first, and the general one takes the rest
  (R11: "archetypes are layered on top, not a fallback")
- Names derived from content, not from position, so the output is stable under reordering
- Discover a grouping rule from the data rather than from an assumption

## The claiming order

1. **Archetype matches** (`chapter_manifest.archetypes.classify_manifest(rows)`). A match
   claims its role rows (`match.roles` keys) **only if all of them are owned**. A trainer
   can't be registered without its retalk page, so a half-owned match is dropped and its
   owned pages fall through to generic.
   - The **arms** of those pages go to a separate beat, `<name>_arms`, template `generic`,
     **same group**, `kwargs=make_kwargs(skip_claimed=True)`. Why separate? See the hint.
2. **Obstacles**: owned rows whose floor carries `blocked_obstacle`, grouped by
   `(map_id, capability)`, template `obstacle`, `kwargs` `capability=`. (C7's ruling: "C6 groups
   these beats by (map, blocking capability)".)
3. **Stairs**: terrain rows grouped into staircases, template `stair`.
4. **Seams**: one beat per seam row, template `seam`.
5. **Everything else**: each remaining page row gets a `generic` beat together with its owned
   arms. Arms whose page isn't planned at all get a `generic` `<page-name>_arms` beat.

Beats come out ordered by the manifest position of their **first** row, with an `_arms` beat
immediately after its principal.

## Naming

| Template | Name | Example |
|---|---|---|
| archetype | `m{map:03d}e{event:03d}_{template}` | `m036e004_trainer` |
| generic (page) | `m{map:03d}e{event:03d}p{page}` | `m037e005p0` |
| arms | principal name + `_arms` | `m036e004_trainer_arms` |
| obstacle | `m{map:03d}obstacle_{capability}` | `m032obstacle_rock_smash` |
| stair | `m{map:03d}stair{x}x{y}` (smallest cell) | `m037stair11x9` |
| seam | `m{map:03d}seam{dir}{other:03d}` | `m035seamN040` |

Each beat's `group` is its own name, except that `_arms` beats share their principal's group.

## Hints

- **`owning_page` first.** An arm's `parent_row_id` can be another *arm* (nesting). You can
  walk parents, or look at what `schema.parse_row_id` already gives you. One of those is a
  single line.
- **Why not hand the arms straight to the archetype template?** Each template decides at
  registration which arms it walks (`walked_arms`; `item_ball` claims only the "always" arm;
  `trainer` only the arm with the defeat write). If the generator re-derived those rules, the
  template and generator would be two detectors that can disagree. With `skip_claimed`, the
  generator hands *all* the arms to a generic beat that runs *after* the template and takes
  only what the template left. The template stays the single source of truth.
- **Stairs: measure before you group.** Print CH05's four terrain rows with their
  `TerrainRef`. The obvious key (`source_event_id`) gives four one-cell "staircases", but the
  hand module has two two-cell ones. What do the two cells of one staircase share? (The tests
  also pin that same-map adjacent cells with *different* behaviours are separate.)
- Naming is where determinism starts. `beat_name` must not depend on the order you pass rows
  in, which a test checks.
- End with an assertion that every owned row is claimed exactly once. It'll catch your own
  bugs before the tests do.

## Tests

`tests/test_beat_gen_group.py`: `owning_page` (including nesting), every naming rule, each
claiming layer, the dropped half-match, order, the exactly-once property, and the full
20-beat CH05 plan, pinned name by name.

## Questions (commit message)

1. What decides whether two terrain rows are one staircase? What would go wrong in the ROM
   walk if you'd grouped by `source_event_id`?
2. `skip_claimed` makes a beat's final rows depend on registration order in the generated
   module. Why is that safe here? (Think about who guarantees the order.)
3. A trainer whose retalk page is refused upstream becomes a generic beat. Is that a loss of
   coverage or an honest downgrade? What would the review doc need to show for the operator
   to notice?
