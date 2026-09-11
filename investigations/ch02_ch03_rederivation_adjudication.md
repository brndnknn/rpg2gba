# CH02 + CH03 manifest re-derivation adjudication (REDERIVATION_PLAN P8)

**Scope.** Classification of every line in the CH02 and CH03 manifest diffs against
the P7 freeze (`reference/frozen/rederivation/CH0{2,3}.freeze.json`), per
`REDERIVATION_PLAN.md` §1: category 1 (derivation better than the hand-authored
answer), 2 (the hand-authored answer was always wrong), or 3 (the derivation
regressed — stops the pass).

This is adjudication, not disposition-authoring. Neither `CH02.dispositions.json`
nor `CH03.dispositions.json` exists, and per `REDERIVATION_PLAN.md` §8.1 neither
ever did — #62's freeze-then-diff safeguard is structurally unavailable on the
disposition side for these chapters, so nothing here should be read as approving a
disposition.

## Summary

**Every diff line is category 1. No category-3 finding. Both passes are clean.**

| | CH02 | CH03 |
|---|---|---|
| rows frozen / fresh | 83 / 83 | 131 / 131 |
| rows added | 7 | 3 |
| rows removed | 7 | 3 |
| content-hash changes | 0 | 0 |
| field diffs to adjudicate | 20 | 5 |
| auto-marked benign | 0 | 1 |

Two independent findings came out of the pass, neither of which is a diff line:

- The `minimal_sets[0]` narrowing (§3) — a silent discard of alternative capability
  sets, pre-existing but first made visible here.
- `content_hash` covers less than the diff tool's headline suggests (§4).

## 1. The row swap — 7 (CH02) + 3 (CH03), category 1

CH02 removed `map033/ev{026,031,033,047,048,066,069}/p0` and added
`map033/terrain/stairs/{52,41 · 52,42 · 53,43 · 53,44 · 57,10 · 57,11 · 57,9}`.
CH03 removed `map031/ev{024,026,027}/p0` and added
`map031/terrain/stairs/{25,16 · 25,17 · 25,18}`.

**Coverage is exact, cell for cell** — not a superset. Each added terrain row carries
a `terrain.source_event_id` equal to the id of the event whose row it replaced, at
identical coordinates:

| removed | added | `source_event_id` |
|---|---|---|
| `map033/ev069/p0` (52,41) | `terrain/stairs/52,41` | 69 |
| `map033/ev066/p0` (52,42) | `terrain/stairs/52,42` | 66 |
| `map033/ev048/p0` (53,43) | `terrain/stairs/53,43` | 48 |
| `map033/ev047/p0` (53,44) | `terrain/stairs/53,44` | 47 |
| `map033/ev031/p0` (57,10) | `terrain/stairs/57,10` | 31 |
| `map033/ev026/p0` (57,11) | `terrain/stairs/57,11` | 26 |
| `map033/ev033/p0` (57,9)  | `terrain/stairs/57,9`  | 33 |
| `map031/ev027/p0` (25,16) | `terrain/stairs/25,16` | 27 |
| `map031/ev026/p0` (25,17) | `terrain/stairs/25,17` | 26 |
| `map031/ev024/p0` (25,18) | `terrain/stairs/25,18` | 24 |

No cell ends up covered by zero rows.

**The swap is lossless.** All 10 removed rows were pure `effects: ["move_route"]`
with empty `script_heads` / `unrecognized_heads` / `other_codes`, all-null
`condition`, `unhandled: 0`, `trigger: "player_touch"`, named `"Stairs"` or
auto-named. Nothing they carried is inexpressible in a terrain row; the diagonal-step
mechanic is now encoded natively as `behavior: MB_SIDEWAYS_STAIRS_RIGHT_SIDE`.

**Mechanism.** `_generate_terrain_rows` (`src/rpg2gba/chapter_manifest/generator.py:601-631`)
emits a terrain row per cell returned by `tileset_converter.stairs.detect_stair_cells`
and adds the originating event to `absorbed_event_ids` (`:657-660`), so the per-page
loop skips it (`:661-662`) and no page row is emitted.

**Provenance.** This is `PROJECT_TODO.md` **#54**, commit `292a94bf` (2026-09-01),
documented at `MEMORY.md:150`. It is *not* #79/#90/`507b1997` — that commit touches
only `playtest/cells.py` and `routing/locations.py`, the beat-authoring approach-cell
resolver, and never `chapter_manifest/generator.py`. Both changes involve Map033's
stairs, which is why they are easy to conflate; recorded here because the
misattribution was made once during this pass.

## 2. The `requires` field diffs — 25 rows, category 1

CH02 (`map033`): 18 rows gained `["rock_smash"]` — `ev008/p{0,1}`, `ev009/p{0,1}`,
`ev010/p{0,1}`, `ev032/p{0,1}`, `ev035/p{0,1}`, `ev037/p{0,1}`, `ev039/p{0,1,2}`,
`ev041/p{0,1}`, `ev141/p0` — and 2 gained `["surf"]`: `ev013/p0`, `ev020/p0`.
CH03 (`map019`): 5 rows gained `["strength"]` — `ev005/p{0,1,2}`, `ev006/p{0,1}`.

**The old `[]` was never a judgment; it was the absence of one.**
`_build_reachability_context` returns `None` for any map with no
`_CHAPTER_MAP_START_CELLS` entry (`generator.py:374-387`), and `_reachability_requires`
then returns `()` unconditionally (`:404-405`). Maps 33, 31 and 19 received their
entries in `90c5470a` (P6b, 2026-09-09) — `git log -S` on each map's table key returns
exactly that one commit. So `[] → ["rock_smash"]` is `reachability_consulted: False →
True`: an unmeasured default replaced by a measurement, not a changed opinion on the
same evidence.

**All 25 are approach gates, not script gates.** Two mechanisms populate `requires`:
`_HEAD_REQUIRES` (`generator.py:167-171`), a text scan for `pbRockSmash*` /
`pbPushThisBoulder` on the row's own page; and `_reachability_requires`
(`:354-411`), a terrain flood. None of these 25 rows carries the corresponding script
— `ev008` is `Kernel.pbItemBall(::PBItems::REPEL)`, `ev005`/`ev006` are
`pbTrainerBattle` — so every one arrived via mechanism 2. `surf` has no
`_HEAD_REQUIRES` entry at all and can only ever arrive that way.

Measured directly (`derive_blocked_verdict_for_event_from_starts`):

```
CH02 map033  starts={(15,7),(16,7),(70,11)}
  ev008 'EV008'      (13,19)  minimal_sets=[['rock_smash'], ['surf']]
  ev009 'Trainer(3)' (30,41)  minimal_sets=[['rock_smash'], ['surf']]
  ev013 'Tree'       (18,34)  minimal_sets=[['surf']]
  ev020 'EV020'      (27,35)  minimal_sets=[['surf']]
  ev032 'EV032'      (55,41)  minimal_sets=[['rock_smash'], ['surf']]
  ev141 'block'      (54,40)  minimal_sets=[['rock_smash'], ['surf']]
CH03 map019  starts={(11,29)}
  ev005 'Trainer(4)' (11,6)   minimal_sets=[['strength']]
  ev006 'Richboy'    (22,7)   minimal_sets=[['strength']]
```

**`PROJECT_TODO.md` #92 does not bear on these.** #92 is about the *grant* side —
`capability_sites.py` cannot find a switch/variable write that hands the player
`rock_smash` or `surf`, because Uranium has no HMs and the real unlock is
`badge AND (move OR item)`. These values are the *gate* side, measured from collision
data. The distinction matters: #92 makes them **unenforceable, not wrong**.

**Accepting them is low-risk downstream.** The only reader of `ManifestRow.requires`
is `render.py:159`, which prints it. `checker.py` reads the sibling boolean
`reachability_consulted` (`:717-729`, `RULE_REACHABILITY_UNENFORCED`, severity
warning) and recomputes capabilities independently; no route planning, disposition
verdict or build gate branches on `requires`.

## 3. Finding: `minimal_sets[0]` silently discarded the alternatives

Not a diff line — pre-existing behaviour that this pass made visible.

`_reachability_requires` ends `best = verdict.minimal_sets[0]` (`generator.py:410`).
On 18 of the 25 rows there are **two** minimal sets — `rock_smash` *or* `surf`, two
independent ways into the same pocket of Route 1 — and the second is dropped with no
warning. `_minimal_sets_for_predicate` orders by size then sorted value
(`traversal/reachability.py:203`), so `rock_smash` wins on spelling alone.

This was tolerable while `requires` was decorative. It stopped being tolerable at the
disposition layer: `BlockedVerdict.as_disposition()` (`traversal/reachability.py:256-264`)
narrowed by the identical `minimal_sets[0]`, and `|` in `blocked:a|b` meant **AND**
(`schema.py:118-142`) — the members of one minimal set. The grammar had no way to
express a disjunction, so authoring CH01–CH03's dispositions would have written
`blocked:rock_smash` onto 18 rows whose real gate is an either/or, and the freeze
would have encoded it. That is §1's stated failure mode: the frozen literal and the
resolver agree with each other and disagree with the game.

**Operator ruling (2026-09-10): extend the grammar.** `|` becomes OR (alternative
capability sets), `+` becomes AND (members within one set), `+` binding tighter.
Migration cost is zero, verified before deciding: every `blocked:` spec committed
anywhere in `reference/manifests/*.dispositions.json` is a single bare token
(`blocked:rock_smash` ×28, `blocked:surf` ×4); nothing in the corpus uses `|`.

The checker's fold changes with it. `checker.py:620` looped per token and treated each
as an independent claim, which is wrong under OR: `RULE_BLOCKED_ALREADY_GRANTED` must
fire when **at least one** alternative set is fully granted, and
`RULE_BLOCKED_NO_GRANT_SITE` only when **every** alternative set is impossible. Note
the old per-token fold was already too aggressive for multi-token specs under AND
semantics as well — one held capability does not open a cell needing two. It never
fired because no multi-token spec has ever existed.

## 4. Finding: what `content_hash` does and does not cover

"Zero content-hash changes on all four chapters" is a strong result but a narrower one
than it reads as. For an event row the hash is `content_hash(page)`
(`generator.py:682`) — the raw RMXP event page. Terrain rows hash `asdict(terrain)`
(`:630`); seam rows hash the connection (`:720`, `:734`).

- It does establish that **the underlying game data is byte-identical** across the
  re-derivation.
- It covers **none** of the derived fields — `requires`, `archetype`,
  `reachability_consulted`, `terrain` are not in the payload. All 25 field diffs in §2
  are invisible to it by construction.
- It gives §1's row swap **no** continuity check at all: removed and added rows differ
  in both id and hash payload, so the swap had to be adjudicated on cell coverage
  alone.

One useful consequence: the `affirmed_hash` values in `CH04.dispositions.json` remain
valid, so the §10 R2/R3 disposition flip on `map035/ev001` does not require
re-affirming the chapter's other rows.

## 5. Skipped comparisons

The diff tool declines to compare fields absent from the frozen rows because those
rows predate the field — there is no before-value. CH02: `reachability_consulted` and
`terrain` on 76 rows each. CH03: the same two on 128 rows each. These are reported
rather than silently skipped, which is deliberate (`55f0f3dd`).

CH03 carries one auto-marked benign line: `map031/seam/N/map035` `unhandled: 0 → None`.
Seam rows have no event page for `transpile_unhandled` to join against, so `None`
("never measured") is the schema-correct value and the frozen `0` read as "measured,
none found". Same finding already adjudicated for CH01 (`investigations/ch01_coverage.md` §1).
