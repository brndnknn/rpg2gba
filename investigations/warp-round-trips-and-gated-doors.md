# Warp round trips and gated doors

*2026-09-28. Written after the first generated-suite ROM runs (`playtest run --chapter CH05
--suite gen`) stopped on a gated reciprocal. Compares three ways forward; the operator decides.*

## The problem

Run 17 reached CH01 ~beat 45 and failed on `m032e003_warp` (Moki Town → professor's lab).
The beat crossed into the lab (fine — the lab's intro scene fired and walked the player to
Bambo), then tried to cross **back** out, and the lab exit refused: "Hey, where are you
going?". The lab exit (`map050/ev001`) is a **gated door** — page 0 (no condition) is the
refusal, page 1 (var 101) is the transfer — and var 101 is only set once you have a starter.

Two things make ordering alone unable to fix it:

1. **Rule 1** (`routing/solver._derive_warp_precedence`, introducing-warp precedence) correctly
   makes the town→lab warp the lab's introducer: every lab group comes after it, the starter
   included. A story edge "this warp comes after the starter" closes a cycle and is dropped.
2. **The arrival nudge after it** (`m032e003_arrival_nudge`, Moki Town's lab-door mat) needs
   the player to *arrive in town from the lab* — the same shut exit.

The house door (`map049/ev002`) has the same shape and was fixed on 2026-09-27 by making rule 1
count only first-entry warps plus a story edge on the door's own row. That fix works for a
warp's **forward** crossing. It does nothing for the **reverse** leg of a round trip.

## Measured (generated CH01–CH05, 2026-09-28)

| | |
|---|---|
| Non-boundary warp beats | **43** (CH01 14, CH02 8, CH03 17, CH04 0, CH05 4) |
| Crossings they make today (legs) | **105** |
| …whose reciprocal crossing is claimed by **its own** warp beat | **43 / 43** |
| Real gated doors on the slice maps | **2**, both CH01: house door `map049/ev002` (switch 52; page 2 can shut it again on a later switch), lab exit `map050/ev001` (var 101) |

(`output/scratch/measure_warps.py`; its "gated" flag also caught four scripted-transfer scenes —
the Letter, Trainer(6), NurseTut's escort, Theo — which are not doors. The two above were
confirmed by reading their pages.)

The 43/43 line is the important one. The generator makes **one beat per direction**, and each
round-trips — so every door is crossed four times (two beats × F,B) where two crossings already
prove each claimed row once.

## The current rule and why it exists

`BUILD_PLAN.md` §2 (operator ruling 2026-09-04): *"A warp is tested by crossing it, crossing back,
and crossing again — the beat ENDS on the far side. One beat per warp **pair**, claiming both
manifest rows."* Rationale: a one-way crossing "cannot see a return warp pointing at the wrong
cell, and the return leg is where arrival nudges actually fire."

Note the generator already departs from the letter of this ruling: it emits one beat **per
direction**, each claiming one row, and each still round-trips (`continuity.thread_maps` sets
`start_side`/`end_side`; `warp_beat` walks ≥2 legs). The ruling was written for hand-authored
CH05, where one beat per pair was the author's choice.

## Approach 1 — the operator's: round-trip only when nothing else crosses back

*A warp needs the back-and-forth only when the route has no other reason to come back through
it. For a building you enter, do the building, and leave — the leave is its own crossing.*

Formalized: a warp beat crosses **once** (one leg, origin → dest) when its reciprocal crossing
is claimed by its own warp beat somewhere in the chain; it keeps the round trip only when the
reverse direction would otherwise go unproven (a one-way warp, or a reciprocal no chapter
claims). In CH01–CH05 that is every warp beat — 43/43 — so the round trip effectively
disappears from generated chapters.

For the lab: `m032e003_warp` crosses town → lab and stops inside; the lab beats run (rule 1 keeps
them after it); `m050e001_warp` crosses lab → town and is already ordered after the starter by
the story edge on its own row (`map050/ev001/p1`, var 101). The nudge on the town side then
follows the lab exit naturally — that exit is the arrival it needs.

**Pros**
- Fixes the lab (and any "can't leave yet" building) without new state machinery: nobody
  crosses back early, because nothing asks them to.
- Matches how the game is played — enter, do, leave — so the generated walk reads like a
  playthrough and the review doc gets easier to follow.
- Removes ~60 of 105 crossings in CH01–CH05 (each ~a few seconds of emulated fade, walk and
  settle), which matters at CH06+ scale.
- The ruling's rationale still holds: the return warp **is** checked — by its own beat, at the
  exact landing cell — and arrival nudges still fire on the real return crossing, now in their
  natural story position instead of a synthetic one.
- Simpler continuity: a warp beat has one leg, so `start_side`/`end_side` bookkeeping mostly
  collapses to "be on the origin side" (a transit gets you there if not).

**Cons**
- Amends a standing operator ruling (`BUILD_PLAN.md` §2); needs a dated correction there and in
  `continuity.py`/`warp.py` docstrings.
- The two directions of a door are proven at two different points in the walk, possibly far
  apart. A wrong return landing is still caught, but later, with more between cause and failure.
- Doesn't by itself stop a **transit** from crossing a shut gated door. If the solver orders
  "lab beat, town beat, starter", continuity inserts a transit out of the lab before var 101 is
  set and it hits the same refusal. That's less likely than today (the round trip forced an early
  exit every time), but the solver's cost function doesn't forbid it.
- A gate that can shut again isn't covered (the house door's page 2 refuses on a later switch
  until the Letter is read). Not reached in CH01–CH05 per the story model, but CH06+ will have
  more of these.

## Approach 2 — static gate rule (my first proposal)

Mark a crossing gated when its event is a gated door (a live non-transfer touch page plus a
conditioned transfer page — `metadata_wiring.classify_event`'s own test). A warp beat whose
reciprocal is gated crosses one way; rows that need a gated crossing (arrival nudges) get story
edges from the gate's writers.

**Pros**: small; reuses today's precedence machinery; gated doors are rare (2 in five chapters).

**Cons**: special-cases exactly the doors that broke, and keeps the redundant quadruple crossing
everywhere else. Conservative — it never round-trips a gated door even after the gate opens.
Shares Approach 1's transit blind spot and "shuts again" blind spot. Approach 1 subsumes it: with
round trips gone, the only remaining gated-door hazard is transits, which is Approach 2's leftover
too.

## Approach 3 — simulate gates along the order

Continuity tracks which crossings are open at each point by simulating story state along the
solved order (the machinery exists: `beat_gen/state_arms.py` / `page_sim.py` already run page
firings forward from `seed_out`). Transits use only open crossings; a round trip happens only
when its reciprocal is open; a beat needing a shut crossing is reordered or fails loud.

**Pros**: exact. Handles gates that open *and* shut, transits as well as warp legs, and any
future gate shape the static rule doesn't recognize. The same simulation could replace some
hand-derived precedence.

**Cons**: the biggest build (about a session). Reordering on a shut crossing is a solver
change, not just a continuity check. More coupling between the solver and the story model. And
if the round trip stays, it still pays the redundant crossings.

## Comparison

| | 1: round-trip only when needed | 2: static gate rule | 3: simulate gates |
|---|---|---|---|
| Fixes the lab / house round trips | yes | yes | yes |
| Transit through a shut door | not prevented | not prevented | prevented |
| Gates that shut again | no | no | yes |
| Removes redundant crossings (~60/105) | yes | no | no |
| Amends a standing ruling | yes (§2) | no | no |
| Build size | small–medium | small | large |

## Recommendation

**Approach 1, plus a fail-loud guard for transits.** Drop the round trip whenever the reciprocal
has its own warp beat; keep it otherwise. Then add a generation-time check: a transit hop (or any
warp leg) over a gated door must come after that gate's writers in the solved order, else
`beat_gen generate` fails naming the hop — the same bounded, loud failure the transpiler uses
(`CLAUDE.md` §4.1). That covers today's two doors and makes a future bad order an offline error
rather than a ROM-run discovery. Approach 3 stays on the shelf until a chapter actually needs a
gate that shuts again. The guard is the tripwire that says when.

## Open questions for the operator

1. **Amend §2?** Approach 1 replaces "cross, cross back, cross again" with "cross once when the
   reverse has its own beat". The §2 rationale (catching a wrong return warp; nudges on the
   return leg) is still met, just by the other beat.
2. **One beat per pair or per direction?** §2 says per pair; the generator does per direction.
   Approach 1 fits per-direction naturally. Either formalize per-direction in §2, or change the
   generator to one beat per pair, claiming both rows and crossing each once.
3. **Unclaimed reciprocals** (one-way warps, a reciprocal no chapter claims): keep the round trip
   there, as proposed, or make those one-way beats plus a review-doc note?
