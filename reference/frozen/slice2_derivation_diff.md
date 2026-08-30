# Slice 2 validation diff — `blocked:<set>` derivation vs frozen oracle

Run 2026-08-29, after `traversal/{triggers,capabilities,reachability}.py` landed and
**after** `slice2_blocked_expectations.json` was frozen. Oracle authored independently
of the derivation (CH04's rows by hand during that chapter's build; CH02's beats by an
earlier BFS in `playtest/chapters/route1.py`).

Start cells (derived, not assumed):
- CH04 / map 35 — `(21, 56)`, the Kevlar seam arrival (`route2.KEVLAR_SEAM_ARROW` -> map035).
- CH02 / map 33 — `(70, 11)`, the Moki Town warp arrival (map32 ev23/36/37 -> map033).

## Result

| Set | Rows | Derived | Agrees with oracle |
|---|---|---|---|
| CH04 `unreachable:*` | 24 | `blocked:rock_smash` | yes, 24/24 |
| CH04 `deferred:rock_smash` | 4 | `reachable` (approach) | yes — see below |
| CH02 `DEFERRED_ROCK_GATED` | 10 | `blocked:rock_smash` | yes, 10/10 |

## The 4-row split is a confirmation, not a mismatch

`map035/ev014/p0`, `ev014/p1`, `ev017/p0`, `ev017/p1` derive as `reachable`. These are
the two boulders the CH04 author dispositioned `deferred:rock_smash` rather than
`unreachable:*`, on the stated grounds that the player *can* reach and attempt them.
The reachability pass reproduced that line without access to the verdicts.

This is the two-source structure `chapter_manifest/schema.py:190` anticipates:

- **Reachability source** (this slice, Q6.3's unbuilt half): supplies the 24 rows whose
  *approach* is gated.
- **Script-head source** (already built, `_HEAD_REQUIRES`): supplies the 4 rows whose
  *interaction* is gated — `Kernel.pbRockSmash` in the event's own page.

They compose to all 28 rows with no overlap. A `requires[]` populated from reachability
alone would miss the 4; from heads alone would miss the 24.

## Caveats recorded at freeze time

- Derivation candidates are `VERIFIED_CAPABILITIES` only: rock_smash, strength, surf,
  waterfall. `cut`/`flash`/`dive` have no grant site and no obstacle surface anywhere in
  the corpus (re-verified across BOTH code-355/655 script text and code-111 branch
  parameters), and raise rather than return empty.
- CH02's half is a beat->cell containment check, not a row-level diff: CH02 has no
  `.dispositions.json`. Dispositioning it first would have meant authoring the answers
  this derivation is meant to be checked against.
- `B14b` and `B9` share cell `(15, 23)` (same NPC, EV035). `B14b` asserts the NPC paces a
  y-span of up to 2, so its runtime tile varies; the whole pocket shares one gate.
