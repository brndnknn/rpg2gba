# C6 Task 7 research — the generic template

**Dated:** 2026-09-21. **This is measured data, not a solution.** It answers the
MEASURE items in the brief with counts, citations, and feasibility facts. It makes
none of the design calls Task 7 asks the operator to make (`GENERIC_EXECUTED_KINDS`
above all). Where a real choice exists, options are listed with neutral trade-offs,
not a recommendation.

Method: read the cited source files directly; ran scratch scripts against
`/tmp/c6research/data.pkl` (CH01-CH05 `rows`/`verdicts`/`floors`, built by the
existing `/tmp/c6research/gather.py`) and against a live `FlagRegistry.load()` of
`output/uranium-build/flag_state.json`. `python -m rpg2gba.chapter_manifest check
--chapter CH05` was run directly (finished in well under two minutes). Dialogue text
is never quoted below — counted only ("text assertion, N chars" style facts).

---

## 1. Floor kind census (CH01-CH05)

`AssertionKind` (`src/rpg2gba/beat_floor/assertion.py:19-42`) defines 21 kinds. Their
params, from that same block's comments:

| kind | params (from assertion.py comment) |
|---|---|
| `trigger` | `trigger` ("action"\|"touch"\|"event_touch"\|"autorun"\|"parallel") |
| `completes` | none |
| `text` | `index`, `text` |
| `choice` | `options` (tuple of normalized strings) |
| `switch_write` | `switch_id`, `value` |
| `var_write` | `var_id`, `op`, `value` |
| `self_switch_write` | `event_id`, `letter`, `value` |
| `warp` | `map_id`, `x`, `y`, `direction`, `arrives_on_door` |
| `heal_party` | none |
| `erase_event` | `event_id` |
| `item_grant` | `item`, `quantity` |
| `pokemon_grant` | `species`, `level` |
| `service` | `name`, plus literal args |
| `battle` | `kind` ("trainer"\|"wild"), plus identity fields |
| `displacement` | `target` (-1 player, 0 this event, N event), `dx`, `dy`, `facing`\|None |
| `event_position` | `target`, `x`, `y`, `facing`\|None |
| `audio` | `code`, `name` |
| `visual` | `code`, `detail` (asserts nothing beyond `completes` — `assertion.py:50-54`) |
| `seam_crossing` (row-level) | `map_id`, `direction`, `offset`, `other_map_id`, `other_direction`, `other_offset` |
| `stair_crossing` (row-level) | `x`, `y`, `side`, `steps` |
| `blocked_obstacle` (row-level) | `x`, `y`, `capability` |

Measured counts, script `/tmp/c6research/census.py` against `data.pkl`'s `floors`
(a `dict[row_id -> RowFloor]` per chapter — confirmed by `type()` at runtime:
`rpg2gba.beat_floor.assertion.RowFloor`):

**All rows, all kinds, per chapter:**

| kind | CH01 | CH02 | CH03 | CH04 | CH05 | total |
|---|---:|---:|---:|---:|---:|---:|
| audio | 62 | 20 | 25 | 23 | 3 | 133 |
| battle | 1 | 9 | 5 | 4 | 3 | 22 |
| blocked_obstacle | 3 | 6 | 5 | 5 | 0 | 19 |
| choice | 10 | 0 | 13 | 0 | 0 | 23 |
| completes | 457 | 164 | 218 | 84 | 39 | 962 |
| displacement | 160 | 12 | 87 | 27 | 1 | 287 |
| erase_event | 6 | 6 | 1 | 5 | 0 | 18 |
| event_position | 6 | 0 | 3 | 0 | 0 | 9 |
| heal_party | 8 | 0 | 2 | 0 | 0 | 10 |
| item_grant | 7 | 9 | 12 | 3 | 5 | 36 |
| pokemon_grant | 0 | 0 | 2 | 0 | 0 | 2 |
| seam_crossing | 1 | 0 | 1 | 2 | 0 | 4 |
| self_switch_write | 48 | 24 | 17 | 24 | 8 | 121 |
| service | 13 | 9 | 18 | 6 | 0 | 46 |
| stair_crossing | 0 | 7 | 3 | 0 | 4 | 14 |
| switch_write | 16 | 9 | 23 | 2 | 4 | 54 |
| text | 478 | 31 | 188 | 25 | 8 | 730 |
| trigger | 457 | 164 | 218 | 84 | 39 | 962 |
| var_write | 18 | 1 | 7 | 0 | 0 | 26 |
| visual | 723 | 134 | 258 | 95 | 35 | 1245 |
| warp | 23 | 7 | 21 | 1 | 4 | 56 |
| **grand total** | | | | | | **4779** |

**Reconciliation, row shape (`floors` dict keys split by row-id shape: `/seam/`,
`/terrain/`, trailing `/bN`, else page):**

| chapter | page rows | branch rows | seam rows | terrain rows | total floors | refused (page) | refused (branch) |
|---|---:|---:|---:|---:|---:|---:|---:|
| CH01 | 210 | 247 | 1 | 0 | 458 | 21 | 35 |
| CH02 | 76 | 88 | 0 | 7 | 171 | 1 | 2 |
| CH03 | 127 | 91 | 1 | 3 | 222 | 11 | 7 |
| CH04 | 40 | 44 | 2 | 0 | 86 | 1 | 2 |
| CH05 | 21 | 18 | 0 | 4 | 43 | 0 | 0 |

Manifest-row totals here match `assignments/C6/README.md`'s own "manifest rows"
table (458/171/222/86/43) exactly — `floors` is one entry per manifest row, and a
refused row still gets an entry (empty `assertions`, non-empty `refusals`).

**Page+branch rows only** (what `generic_beat` mostly sees) drop only `seam_crossing`
(4) and `stair_crossing` (14) from the all-rows total: **4779 - 4 - 14 = 4761**,
confirmed by the script's own separate pass. Every other kind's count is identical
between "all rows" and "page+branch rows only" — `blocked_obstacle` (19) IS a
page-row kind (see §9), not a distinct row shape; it always appears at
`list_index=-1, code=None` on an ordinary `mapNNN/evNNN/p0` row id, same as
`trigger`/`completes`.

**Row-shape x assertion-kind cross-tab** (full breakdown, all chapters summed):
`trigger`/`completes` split 962 total into page 474 + branch 488 each (every page
AND every branch row carries its own trigger+completes pair — 474+488=962,
reconciles). `text` splits 730 into page 488 + branch 242. `blocked_obstacle` (19),
`seam_crossing` (4), `warp` (56) are page-only (0 on branch rows). `seam_crossing`
(4) is seam-row-only, `stair_crossing` (14) is terrain-row-only — neither ever
appears on a page or branch row.

---

## 2. Feasibility: can `emulator.py` observe each kind today?

Grepped every `def ` in `src/rpg2gba/playtest/emulator.py` (88 methods) for
party/pokemon/species/hp/facing accessors: **zero matches** — no method reads
party contents, species, level, or HP. *(Lead correction: the player's facing is
readable. The grep missed it because it lives in `playtest/assertions.py:377`
`assert_player_facing`, not `emulator.py`. See the `warp` row below.)* Grepped for
choice/multichoice reading: only `yesno_prompt_up()` (line 1316) exists, and
`advance_dialog`'s own docstring (2880-2884) states plainly: "the harness has no
probe for 'a yesnobox is highlighted on option N'" — button-mashing is a *driver*,
not an *observer*, for anything past yes/no.

| kind | can the emulator observe this today? | concrete method(s) |
|---|---|---|
| `trigger` | Partially. `interact()` (2825) presses A and reports whether a script started — covers `action`. `touch`/`event_touch` fire from `walk_to()` (2395) stepping onto/adjacent to the tile, observed the same way. `autorun`/`parallel` start with no player input; observable only via `field_locked()` (1281) polling, not a dedicated "did autorun fire" primitive. |
| `completes` | Yes. `advance_dialog()` (2871) returns once the field controls release; `field_locked()` (1281) is the raw poll it's built on. |
| `text` | Yes. `wait_for_field_message()` (1507), `assert_text_contains()` (1535), `current_field_message_text()` (1400). |
| `choice` | Partially. `advance_dialog(key=...)` (2871) can *drive* a yes/no choice (A=yes, B=no per its own docstring 2886-2897). No method reads back which option a multichoice (`dynmultichoice`/N-option) menu actually selected. |
| `switch_write` | Yes, contingent. `flag(flag: str\|int)` (1117) reads a `FLAG_*` bit; needs the name resolved through `FlagRegistry.get_flag(switch_id)` (`flag_registry.py:211`) first — see §4. |
| `var_write` | Yes, contingent. `var(var: str\|int)` (1122) reads a `VAR_*`; needs `FlagRegistry.get_var(var_id)` (`flag_registry.py:214`) first. |
| `self_switch_write` | Yes, unconditionally. `flag()` (1117) + `self_switch_flag_name(map_id, event_id, letter)` (`flag_registry.py:74-81`) — a pure function, no registry state needed (map_id must be parsed from the row id; the assertion's own params carry only `event_id`/`letter`/`value`, not `map_id` — confirmed by inspecting a live `self_switch_write` assertion's `.params`). |
| `warp` | Yes. `map_location()` (1039) + `player_pos()` (1035) confirm which map/cell the player landed on. Arrival facing IS observable: `assertions.assert_player_facing(emu, beat, expected)` (`playtest/assertions.py:377`) reads it, and `warp.py:322-343` already uses it with `facing_for_direction`/`arrival_landing_cell` to check `direction` and `arrives_on_door`. *(Corrected 2026-09-21 by the lead: the draft said no player-facing read exists.)* |
| `heal_party` | No. No party/HP read method exists (confirmed above). |
| `erase_event` | Partially. `object_event(local_id)` (1056) `.active` flips false — but `local_id` is the *compiled* object-event id, not the RMXP `event_id` the assertion names; needs `playtest.cells.local_id(map_constant, event_id)` (`cells.py:194-229`) first, which itself needs a staged local-id table on disk. |
| `item_grant` | Yes. `bag_item_quantity(item)` (1201) — already used this way by `item_ball.py:431/441`. |
| `pokemon_grant` | No. Same gap as `heal_party` — no species/party read. |
| `service` | No generic primitive. Ad hoc per name is partially possible (`money()` 1168 for a mart's money delta), but nothing reads "which service menu opened" as such. |
| `battle` | Yes. `is_trainer_battle()` (2458), `opponent_trainer_id()` (2480); `_in_battle()` (2448) is private. |
| `displacement` / `event_position` | Partially. `object_event(local_id).x/y/facing` (1056) for `target >= 0`, `player_pos()` (1035) for `target == -1` — same `local_id` resolver caveat as `erase_event`. |
| `audio` | Partially. `bgm_song_id()` (1249) reads the currently-playing `MUS_*` id — BGM only. No SE/jingle read exists. `assertion.py:36` itself flags audio as "not checked until audio is mapped." |
| `visual` | Trivially satisfiable. `assertion.py:50-54`'s own comment: visual "asserts nothing a ROM walk could fail beyond `completes`" — it is in `OFFLINE_KINDS` for that reason. |

---

## 3. How existing templates check things, and what "honesty" means

**`flavour_npc.py`'s `talk` body** (`flavour_npc.py:264-294`): calls
`assertions.require_map` (265), `emu.walk_to` (266), `emu.face` (267),
`emu.interact(require_script=True)` (268) — raises if no script starts (satisfies
`trigger`). Then either `_assert_one_of` (279, for `randomized`, using
`emu.assert_text_contains` internally per line 434) or `_walk_text_boxes` (281,
`emu.wait_for_field_message`/`emu.advance_dialog` per lines 407-418) — satisfies
`text`. Then, only when `ssa0 is not None` (283-292): `actual = emu.flag(ssa0)`
(284) compared against `expected_ssa0_value` — satisfies `self_switch_write`, and
only because it is actually read after the talk, not merely written-and-ignored
(module docstring 113-116 makes this the honesty argument explicitly: "a beat that
never reads the flag it writes cannot honestly declare `self_switch_write`").

**`item_ball.py`'s `grant_beat` body** (`item_ball.py:425-448`), the flag+item
example: `if emu.flag(ssa):` as a *precondition* (426), `bag_before =
emu.bag_item_quantity(item)` (431) before walking, then after `emu.interact()` +
`emu.advance_dialog()` (434-435): `if not emu.flag(ssa):` (436, postcondition —
self-switch fired) and `bag_after = emu.bag_item_quantity(item)` (441) compared
`!= bag_before + grant_quantity` (442) — this is what backs `item_grant` and
(when claimed) `self_switch_write` for that archetype.

**`declare_assertions`** (`archetypes/__init__.py:132-183`): signature
`declare_assertions(rows: Sequence[str], *, executed_kinds: frozenset[str],
template: str, extras: Sequence[FloorAssertion] = (), floor_lookup: FloorLookup |
None = None) -> frozenset[FloorAssertion]`. It filters each row's real floor
(`floor_for_row` by default) down to only the assertions whose `.kind in
executed_kinds` (166-168), so a kind left out of `executed_kinds` is silently
absent from what's declared — never a false claim. Its own docstring (140-151)
states the honesty rule directly: "a floor kind the template does not execute is
left out rather than declared, so the checker's ⊇ rule reports it as uncovered
instead of the template claiming a check it never makes."

**Every one of the other five templates' call sites** (all pass a *fixed or
computed* `executed_kinds` frozenset, never `set(STEP_HANDLERS)` because none of
them use a per-kind handler table — Task 7's design is new in that respect):

| file:line | template | `executed_kinds` shape |
|---|---|---|
| `flavour_npc.py:249-252` | `flavour_npc` (primary) | `{"trigger","completes","visual","audio"}` plus conditionally `"text"`/`"self_switch_write"` (line 243-247) |
| `flavour_npc.py:350-353` | `flavour_npc` (toggled `_again`) | same conditional shape, separately computed (342-349) |
| `item_ball.py:410-413` | `item_ball_beats:grant` | `grant_executed_kinds`, conditionally unioned with `{"self_switch_write"}` (405-408) |
| `item_ball.py:467-...` | `item_ball_beats` (spent page) | `spent_executed_kinds`, derived from `spent_present_kinds` (456-464) |
| `warp.py:354-357` | `warp_beat` | module-level `_EXECUTED_KINDS` constant, plus per-call `extras=` (a strengthened `warp` assertion carrying `arrival_facing`/`bgm` on top of the floor's own, built 340-350) |
| `arrival_nudge.py:169-172` | `arrival_nudge_beat` | module-level `_EXECUTED_KINDS` constant, plus per-call `extras=` (a straight copy of one `displacement` assertion, named precisely so a sibling `target=0` displacement on the same arm stays undeclared — comment at 158-164) |
| `trainer.py:447, 574` | `trainer_beat` (x2 forms) | not read in this pass — same `declare_assertions` call shape (fixed `executed_kinds`, not `set(STEP_HANDLERS)`) |

All six existing call sites (five templates plus `flavour_npc`'s second beat)
compute a *fixed* `executed_kinds` set by hand per beat shape. Task 7 is the first
template whose `executed_kinds` (here, `GENERIC_EXECUTED_KINDS`) is a single
module-level constant reused unchanged across every beat it registers, and the
first pinned by an equality test against `STEP_HANDLERS` rather than eyeballed per
call.

---

## 4. Flag/var naming: registry resolution census

Signatures (`conversion_agent/flag_registry.py`):
- `self_switch_flag_name(map_id: int, event_id: int, letter: str) -> str` (74) —
  pure, deterministic, format `FLAG_MAP{map:03d}_EVENT{event:03d}_SS{LETTER}`.
- `FlagRegistry.get_flag(switch_id: int) -> str | None` (211) — dict lookup only,
  **returns `None`**, never raises, for an id with no committed mint.
- `FlagRegistry.get_var(variable_id: int) -> str | None` (214) — same shape.
- `resolve_switch_flag(registry, switch_id) -> str | None` (113-131) — a
  *different, stronger* lookup: if `get_flag` misses, it mints on the fly from
  `registry.label_for_switch(switch_id)` via `to_constant("FLAG", label)` and
  `registry.propose_flag(...)`, returning `None` only if the switch is a script
  switch (`s:`-prefixed) or has no label at all. Mutates the in-memory registry
  (via `propose_flag`'s `_commit`, 366-379) but does **not** write
  `flag_state.json` to disk on its own — only `FlagRegistry.save(path)` does.
- `resolve_variable_var(registry, variable_id) -> str | None` (134-148) — mirrors
  the above for vars.

State file: `output/uranium-build/flag_state.json` (loaded via
`FlagRegistry.load(path, fork_path=None)`, `flag_registry.py:463`).

**Census (`/tmp/c6research/flagnames.py`), every `switch_write`/`var_write` in
CH01-CH05 floors, resolved via `registry.get_flag`/`get_var` against the
persisted state (labels not loaded — plain committed-mint lookup):**

| kind | total | resolved (`get_*` hit) | unresolved (`get_*` -> None) |
|---|---:|---:|---:|
| `switch_write` | 54 | 51 | 3 |
| `var_write` | 26 | 26 | 0 |
| `self_switch_write` | 121 | n/a (pure function, no lookup) | n/a |

The 3 unresolved `switch_write`s: `CH03 map068/ev001/p0/b1` (switch 3), `CH03
map068/ev009/p0` (switch 114), `CH03 map068/ev013/p0` (switch 114). **These are
not permanently unnameable** — re-checked with `resolve_switch_flag` (which mints
from the Phase-3 sidecar label instead of only reading already-committed mints):
switch 3 has label "PokeRus in Pokemon Center" -> `FLAG_POKERUS_IN_POKEMON_CENTER`,
switch 114 has label "First time online" -> `FLAG_FIRST_TIME_ONLINE`; neither is a
script switch (`is_script_switch` False for both). So `get_flag`-only lookup
against the currently-persisted state undercounts what's nameable; `get_flag` plus
an on-demand `resolve_switch_flag` mint would resolve all 54/54 in this sample —
subject to `resolve_switch_flag`'s own not-yet-persisted-mint caveat above.

*(Lead check, 2026-09-21: neither `FLAG_POKERUS_IN_POKEMON_CENTER` nor
`FLAG_FIRST_TIME_ONLINE` appears anywhere under `engine/include/` or `output/uranium-build/`.
A name minted at walk time would be one the ROM was never built with, so `emu.flag(name)`
would have no symbol to read. "Nameable from the label" is not "exists in the ROM". The 3
CH03 writes are unresolvable against what the ROM actually has, whichever lookup you
choose.)*

---

## 5. `steps_for` ordering facts

`coverage.uncovered`'s sort key (`beat_floor/coverage.py:54`):
`key=lambda a: (a.list_index, a.kind, repr(a.params))`.

`list_index` semantics, measured directly (`/tmp/c6research/ties.py`): `-1` is used
by exactly five kinds and **only** those five, corpuswide — `trigger`, `completes`,
`blocked_obstacle`, `seam_crossing`, `stair_crossing` (the row-level kinds plus the
two structural page-level ones). Every other kind (`text`, `switch_write`,
`self_switch_write`, `var_write`, `warp`, `item_grant`, `pokemon_grant`, `choice`,
`service`, `battle`, `displacement`, `event_position`, `erase_event`, `heal_party`,
`audio`, `visual`) has a real (command-list-position) `list_index >= 0` somewhere
in the corpus.

`trigger` and `completes` **share** `list_index = -1` on every row that has both
(962 of each) — the task's hint that the sort key needs `trigger` forced first and
`completes` forced last, despite equal `list_index`, is confirmed structurally: a
plain `(list_index, kind, repr(params))` sort puts them adjacent and orders them
alphabetically by kind (`completes` before `trigger`), the wrong way round for
execution order.

**Real ties on `(kind, list_index)` within one row** (26 found across CH01-CH05;
the `repr(params)` tiebreak is load-bearing, not a defensive nicety):

- `self_switch_write` ties, single-event pages: e.g. `CH01 map032/ev078/p0` at
  `list_index=42` carries two `self_switch_write` assertions differing only in
  `event_id` (78 vs 79) — same page writing two different events' self-switches at
  the same command-list position (a "call this on two neighbours" idiom).
- A pathological case, `CH03 map068/ev009/p0` (and its sibling `ev011/p0`, a large
  multi-branch terminal/menu event): **30 `text` assertions and 7 `displacement`
  assertions all share `list_index=0`**, along with ties on `service` (3-way),
  `audio` (2-way), `visual` (5-way), `choice` (2-way). This single row is by far
  the largest tie cluster in the corpus and the strongest evidence that
  `repr(params)` (not just kind) is needed to get a stable, deterministic order —
  `list_index` alone collapses dozens of genuinely distinct assertions onto one
  bucket for this row.

---

## 6. The checker-union question (Q3)

**Declarations from two beats claiming the same row ARE unioned**, not "one beat's
declaration wins." `ChapterFloorCoverageModel.declared`
(`chapter_manifest/floor_model.py:69-75`):

```
def declared(self, row_id: str) -> frozenset[FloorAssertion] | None:
    beats = self._claiming.get(row_id, ())
    declaring = [b for b in beats if b.assertions is not None]
    if not declaring:
        return None
    return frozenset(
        a for b in declaring for a in b.assertions if a.row_id == row_id)
```

`self._claiming` is built at construction (`floor_model.py:60-64`) as `dict[row_id,
list[Beat]]` from **every** beat in `chapter.beats` whose `rows` include `row_id` —
no dedup, no "first wins." `declared()` then flattens `a for b in declaring for a
in b.assertions` across all beats that have declared *something* (any beat with
`assertions is None` — an undeclared hand-written beat — contributes nothing and
is excluded from `declaring`, but does not block another beat's contribution).
`_check_floor_coverage` (`checker.py:1721`) calls this `declared()` once per row
and compares the *union* against the floor via `coverage.uncovered` (§1's table).

**Confirmed against real data**: `python -m rpg2gba.chapter_manifest check --chapter
CH05` (ran in well under two minutes) reports exactly **six** `floor_uncovered`
errors, matching the task's "C5's six CH05 `floor_uncovered` trainer errors":

| row | missing kinds (counted, text redacted) |
|---|---|
| `map036/ev004/p0` | 5 missing: `audio@5`, `visual@6`, `visual@7`, `text@8` (1 text assertion), `visual@13` |
| `map036/ev004/p1` | 1 missing: `visual@0` |
| `map036/ev006/p0` | 5 missing: `audio@5`, `visual@6`, `visual@7`, `text@8` (1 text assertion), `visual@13` |
| `map036/ev006/p1` | 1 missing: `visual@0` |
| `map037/ev004/p0` | 5 missing: `audio@7`, `visual@8`, `visual@9`, `text@10` (1 text assertion), `visual@13`/`15` |
| `map037/ev004/p1` | 1 missing: `visual@0` |

All six are trainer battle pages (`p0` battle-trunk pages missing the
`pbTrainerIntro`/`pbNoticePlayer`/`pbCallBub`/battle-line-text/`pbTrainerEnd`
sequence a `trainer_beat` template doesn't declare, and `p1` re-battle pages each
missing one `visual@0` `pbCallBub`). **What the union answer means for these six:**
since `declared()` unions across every beat claiming a row, a generic beat
registered on the *same* row **alongside** the existing (undeclared or
partially-declaring) trainer beat would have its own `steps_for`-derived
declarations added to the union — a real path to closing these six, *if* the
generic template's `GENERIC_EXECUTED_KINDS` covers `audio`/`visual`/`text` (per
§1/§2's feasibility) and *if* something registers a generic beat on these
already-trainer-claimed rows (which needs `skip_claimed=False`, since
`skip_claimed=True` would drop them). That is a design choice, not measured here.

The run also surfaced other findings worth naming for completeness, none of them
`floor_uncovered`: 8 `undispositioned` branch-arm errors, 4 `derived_unaffirmed`
surf-capability proposals, several `floor_undeclared` warnings (rows claimed but no
claiming beat declares anything — the pre-Task-7 state for the stair rows and two
map037 flavour-adjacent rows), and one `WARNING` (`warp_beat(B8_return)`) unrelated
to floor coverage.

---

## 7. `ChapterBuilder` facts

Fields (`chapter.py:388-396`, `@dataclass`): `name: str`, `doc: str`, `predecessor:
str | None = None`, `route_entry: BeatLocation | None = None`, `_beats: list[Beat] =
field(default_factory=list)` (private).

Beats register via the `@builder.beat(name, description, ...)` decorator
(`chapter.py:398-579`), which appends a `Beat` to `_beats`
(`decorate`, 571-577). `Beat.rows: tuple[str, ...] = ()` (127-157) is the row-claim
field; validated per-row against `chapter_manifest.schema.parse_row_id` shape
(`_validate_row_id`, 93-105) at registration time.

**No public accessor for claimed rows exists today.** Grepped `chapter.py` for
`claimed_rows` and for `def build`: zero matches for the former; `build()` is
defined at line 581. The task's ask to add `ChapterBuilder.claimed_rows() ->
frozenset[str]` is therefore adding new surface, not wiring up something latent.

**`build()` does NOT reject a row claimed by two beats.** Read in full
(581-616) plus its helper `_validate_groups` (618-659): the only cross-beat
invariants enforced at `build()` time are (a) no duplicate beat *name*
(508-509), (b) `group=` contiguity and the singleton/explicit-group-id collision
check (618-659). Nothing walks `rows=` across beats for uniqueness. The *only*
place in the codebase that rejects two beats claiming one row is
`playtest.archetypes.ChapterArchetypeModel.__init__` (`archetypes/__init__.py:344-363`)
— and even that only raises when the two beats claim the row under **different**
archetypes; two beats claiming the same row under the same archetype (or one/both
with `archetype=None`, the generic template's own shape) pass through unchecked
there too. `assignments/C6/README.md`'s "Deliberately NOT in this assignment"
section (B1) independently confirms this is a known open gap: "while hand and
generated suites coexist, `RULE_UNREGISTERED_BEAT` and `RULE_ARCHETYPE_CONFORMANCE`
must tolerate two beats claiming one row."

---

## 8. Location helpers

`routing.locations.cell_for_row(row: ManifestRow) -> RowCell` (`locations.py:318-367`,
no `approach_prefer`/`prefer` parameter in its own signature). Behavior by
`row.kind`:
- `"terrain"` (322-336): resolves via `_stair_approach` + `_stair_resolver_string`,
  and separately returns `approach_candidates=_stair_side_candidates(...)`
  (334-335) — a tuple of `ApproachCandidate(x, y, side, resolver)` for west/east,
  whichever are walkable.
- `"seam"` (338-344): **always raises** — "seam rows carry a connection
  direction/offset, not a cell... a seam beat's routing point must be supplied by
  hand."
- `"page"` (346-367): raises if `event_id is None`; for `_ON_EVENT_TRIGGERS`
  (`player_touch`, `autorun`, 166) returns the event's own cell
  (`event_cell`); for `_ADJACENT_TRIGGERS` (`action`, `event_touch`, 167) returns
  `approach_to(map_constant, event_id)` (no `prefer=` — picks the *first* walkable
  side) plus `approach_candidates=_approach_side_candidates(...)` (361-362), a
  tuple of `ApproachCandidate` for every walkable side in N/S/E/W order.
- any other `row.kind`: raises "unknown row kind."

So `cell_for_row` itself has no `approach_prefer=` parameter — a caller wanting a
*specific* side must pick it out of the returned `RowCell.approach_candidates`
tuple by matching `.side` against the desired preference, or call
`playtest.cells.approach_to(map_constant, event_id, prefer=...)` directly instead
of `cell_for_row`.

**`approach_prefer` usage across the four existing templates** (grep,
`archetypes/*.py`): `trainer.py:406`, `item_ball.py:331`, `flavour_npc.py:156` all
pass it straight through as `approach_to(map_constant, event_id,
prefer=approach_prefer)` — a plain pass-through parameter, never derived or
validated against `cell_for_row`'s `approach_candidates`.

---

## 9. Row-level shapes: `blocked_obstacle`, `stair_crossing`, `seam_crossing`

**`blocked_obstacle`** — real examples (CH01, `x=65,y=45` and `x=66,y=46` on
`map032/ev014/p0`/`map032/ev015/p0`, capability `rock_smash`) match the test
file's `ROCKS`/`_rock_lookup` fixtures exactly. 19 corpus-wide instances (§1),
all `capability in {"rock_smash", "strength"}` (rock_smash: CH01 x3, CH02 x6, CH04
x5 = 14; strength: CH03 x5). Every instance sits at `list_index=-1, code=None` on
an ordinary page row id (`mapNNN/evNNN/p0`) — **not** a distinct row-kind the way
seam/terrain are; the manifest treats a smashable rock as a page event whose floor
happens to carry this one row-level assertion alongside (or instead of) ordinary
command-derived ones.

**`stair_crossing`** — CH05's `map037/terrain/stairs/11,9` and `.../11,10` (from
the test file's `STAIRS` constant) are real: `side="left"`, `steps=(("LEFT",-1,1),
("RIGHT",1,-1))`. 14 corpus-wide (CH02 x7, CH03 x3, CH05 x4). `side` values seen:
`"left"` (CH05 only) and `"right"` (CH02, CH03, and CH05's other staircase) — both
values occur. `steps` is always a 2-tuple of `(step_dir, dx, dy)` triples in the
sample, `step_dir` always `"LEFT"`/`"RIGHT"`.

**`seam_crossing`** — CH03's `map031/seam/N/map035` (test file's `SEAM` constant)
is real: `direction="N", map_id=31, offset=11, other_direction="S",
other_map_id=35, other_offset=0`. 4 corpus-wide (CH01 x1, CH03 x1, CH04 x2).

**Existing ROM-walk helpers to build the three row-level bodies on**
(`playtest/cells.py`):
- `stair_approach(map_constant: str, *, stair_event: int, side: str) -> Cell`
  (431-515) — the side-aware crossing-point resolver; fails loud if `side` is
  unwalkable or `stair_event` isn't a detected diagonal-stair event.
- `seam_cells(map_constant: str, *, to: str) -> tuple[Cell, ...]` (670-773) —
  always returns a tuple (1 or more cells) of the arrow-warp seam tile(s) on
  `map_constant`'s side of the crossing into `to`; raises three distinct, named
  ways (no seam at all vs. a real whole-border connection instead vs. ambiguous
  multi-entry).
- For obstacle rows, no equivalent named resolver was found in `cells.py`'s
  function list (`event_cell`, `local_id`, `approach_to`, `warp_cell`,
  `arrival_cell`, `entry_cell`, `stair_approach`, `grass_cell`,
  `cell_for_local_id`, `seam_cells`, `raw_cell`) — the `blocked_obstacle`
  assertion's own `x`/`y` params (§9 above) are the only location data available;
  `obstacle_beat`'s own docstring (generic.py:97-99) says its location is "the
  first rock's cell," implying the obstacle's own `x`/`y` param is the source, not
  a `cells.py` resolver.

---

## Decisions left to you

These are the calls the brief reserves for you. No recommendation below — just the
facts from §1-§9 that bear on each.

- **`GENERIC_EXECUTED_KINDS`.** Tests pin `{"trigger", "completes", "text"} <=
  GENERIC_EXECUTED_KINDS` and forbid the three row-level kinds
  (`seam_crossing`/`stair_crossing`/`blocked_obstacle` — those go through
  `obstacle_beat`/`stair_beat`/`seam_beat` instead, per the task's registration
  rules). Beyond that minimum, §2's feasibility table is the relevant input:
  `switch_write`/`var_write`/`self_switch_write`/`item_grant`/`battle` are cleanly
  observable today; `visual` asserts nothing beyond `completes` per its own
  OFFLINE_KINDS comment; `audio` is BGM-only (no SE read) and the module itself
  flags it unmapped; `choice`/`warp`(direction)/`heal_party`/`pokemon_grant`/
  `service`/`displacement`/`event_position` each have a real observation gap
  (§2's "Partially"/"No" rows) that a handler for them would have to either work
  around or leave unhandled. §1's page+branch counts tell you how much coverage
  each kind buys: `visual` (1245), `text` (730), `displacement` (287),
  `self_switch_write` (121), `switch_write`+`var_write` (80), `service` (46),
  `warp` (56), `item_grant` (36), `choice` (23), `battle` (22),
  `erase_event`/`heal_party`/`event_position`/`pokemon_grant` (single digits to
  18 each).

- **Whether `switch_write`/`var_write` handlers use `get_flag`/`get_var`
  (already-committed mints only, §4: 51/54 and 26/26 resolved against the current
  persisted state) or `resolve_switch_flag`/`resolve_variable_var` (mints on
  demand from the Phase-3 label, resolving all 54/54 in the measured sample, but
  mutating in-memory registry state that the hard rule in CLAUDE.md §6 and the
  task's own "it doesn't guess" line bear on — a handler that mints a name at ROM
  -walk time is proposing a name outside the normal pipeline-run minting flow).

- **Whether the generic template ever gets a chance to close CH05's six
  `floor_uncovered` trainer rows (§6).** The union-across-beats fact means it
  *can*, mechanically, if registered on those rows with `skip_claimed=False`
  (since `skip_claimed=True` drops rows another beat already claims) and if
  `GENERIC_EXECUTED_KINDS` includes `audio`/`visual`/`text` (the three missing
  kinds on those six rows, per §6's table). Whether that's the right way to close
  them — versus fixing the trainer template itself — isn't decided here.

- **How `steps_for` breaks ties.** §5 gives the two real shapes: the
  `trigger`/`completes` special-case (both always `list_index=-1`, must sort
  first/last regardless) and the `repr(params)` tiebreak for same-`(kind,
  list_index)` assertions, which is not a hypothetical edge case — one CH03 row
  alone produces a 30-way `text` tie and several other multi-way ties at
  `list_index=0`.

- **Whether/how `obstacle_beat`'s location derivation ("the first rock's cell")
  uses a `cells.py` resolver or the assertion's own `x`/`y` param directly** — no
  named resolver for obstacle cells exists in `cells.py` today (§9).

- **How a handler surfaces a kind it can't fully check** (e.g. `warp`'s
  `direction`/`arrives_on_door`, `choice`'s selected option) — declare it anyway
  and check what's checkable, or leave the kind out of `GENERIC_EXECUTED_KINDS`
  entirely and let it show up as `floor_uncovered`. Both are consistent with the
  honesty rule (§3); which one is right for which kind is your call.
