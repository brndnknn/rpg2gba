# Read-through checklist (READ, loop step 5)

Runs after WIRE generates the chapter's manifest and a human authors dispositions
for each row, and before ROUTE's operator approval — the approve-before-build gate
this step protects. What it is for: catching a verdict that is *mechanically legal
and answering the wrong question*, and catching a row that was visible on the page
and got skipped anyway. Those are the two things it caught the one time it ran
(CH04, informally, before this document existed) — four beats (B9, B13, B14, B15)
added that the approved manifest had missed.

This is not a re-derivation of the manifest, and not a substitute for the checker.
The checker enforces mechanical rules (does every row have a verdict, does the
route model agree with beat registration order, and so on). This step catches
errors the checker cannot see because they're legal by its rules — a `cosmetic`
verdict on a row that compiles fine and is simply wrong.

## 1. The per-row-kind verdict question

| `kind` | Represents | Legitimate verdicts | Question to ask |
|---|---|---|---|
| `page` | One RPG Maker event page | `beat`, `blocked`, `cosmetic`\*, `unreachable` | Does this page's *event* — not just this page in isolation — change game state a player can observe? |
| `seam` | An overland connection between two maps | `beat`, `blocked`, `unreachable` | Does crossing this seam require a beat (item, flag, battle) to be crossable, or is it open? |
| `terrain` | A terrain mechanic realized by a metatile behaviour | `beat`, `blocked`, `unreachable` | Does this metatile behaviour gate traversal the player must clear? |

\* `cosmetic` is legal for `page` only. It is **never** legal for `seam` or
`terrain` — both are load-bearing traversal by construction, not decoration, so a
`cosmetic` verdict on either is a definition error on its face. A `page` may only
be `cosmetic` if its whole effect set is non-state-writing **and** its map has
actually been transpiled — an untranspiled map yields `unhandled: null`, and
`cosmetic` is refused on it rather than passing vacuously.

## 2. The verdict-definition traps

**(a) Page-level reasoning where the question is event-level.** A page can write
no state and still not be decoration, if a sibling page on the same event does.
CH04's B14 was a trainer's post-battle re-talk page: read on its own it writes no
state (true — a re-talk page just delivers a line), so the per-page rule said
`cosmetic`. But the event as a whole is a battle-and-re-talk pair, and the re-talk
page only exists because the battle page set the self-switch that exposes it. The
question to ask is not "does this page write state" but "is this page reachable
only because another page in the same event already did." If yes, it inherits the
event's significance and cannot be `cosmetic`.

**(b) Trusting the event's name over its content.** Map 35 has an event named
"Sign" that is an empty page — nothing to translate. The actual sign at the cave
entrance is a different event, ev002, unnamed or differently named. A verdict
authored from the name list without opening the page content will misfile both:
call the empty "Sign" event significant because the name promises text, and miss
ev002 because its name doesn't say "sign." The question to ask: does the verdict
come from the event's *content*, or from what a plausible-sounding name implied it
would contain?

**(c) `blocked` vs `unreachable`.** `blocked` means the player cannot reach this
row **yet** — a capability arrives in a later chapter and the row is owed a
revisit. `unreachable` means no chapter will ever reach it — dead content, no debt
owed. Picking `blocked` for something truly unreachable manufactures a revisit
debt nobody will ever pay down; picking `unreachable` for something actually
blocked silently erases a debt that's real. Neither error is caught mechanically —
both verdicts are legal on a `page` or `seam` row. The question to ask: name the
specific future chapter or capability that unblocks this row. If you can't name
one, it's `unreachable`.

## 3. Was any row skipped

The second framing question, separate from verdict-correctness: read the rendered
manifest top to bottom and confirm every row got a disposition, not just that the
dispositions present look right. The B14 lesson is specifically that the row was
never missing — it was on the page, visible, in the normal enumeration — and a
human's eye slid off it anyway because a re-talk page reads as boilerplate next to
its battle page. Treat rows that look like duplicates or boilerplate of a
neighboring row as the likeliest place to look, not the safest to skim.

## 4. The decaying blind-spot appendix

**Instruction:** when the generator learns to emit a row kind for one of these,
delete that item from this list and note the date. This appendix is meant to
shrink as generator coverage grows — an item surviving here is a live gap, not
ritual.

- **Wild-encounter tables.** Structurally invisible to the manifest, which
  enumerates event pages and seams — a table has neither. This is how CH04's B15
  was found: it wasn't dispositioned wrong, it was never a row. Still owed.
- **Map properties that are neither page, seam, nor terrain.** Worked example:
  `dark_map` / darkness — a whole-map property with no event page and no seam to
  attach a verdict to. **Still owed, and note precisely why:** `dark_map` was
  wired on 2026-08-31, but into the *emitted map header* (`requires_flash` ->
  `gMapHeader.cave`), not into the manifest. The conversion is correct and the
  manifest still cannot see it, so no verdict is ever authored about darkness.
  That is the distinction this appendix exists to hold: a property being handled
  by the pipeline is not the same as it being visible to the read-through. Map 19
  shipped lit through CH03's gate for exactly this reason.
- **Diagonal staircases** were on this list and were removed 2026-09-01 when the
  generator learned to emit `terrain` rows for them. Kept here, struck through in
  spirit rather than deleted outright, as the worked example of what decay looks
  like — the instruction above is easy to skip if nobody has ever seen it fire.

## Closing note

A verdict-*definition* error is a class, not an instance. CH04's `cosmetic` rule
was wrong for every re-talk-style page in the manifest, not just B14 — fixing the
one row and moving on would have left the others silently misdispositioned. When
this step finds a definition error, fix the definition and re-review every row of
that `kind` against it before moving to ROUTE.
