# Oracle harvest — `CommonEvents.pory` differential dispositions (2026-09-15)

**What this is:** the one obligation the 2026-07-02 grill-D6 harvest
(`oracle_harvest_2026-07-02.md`) deliberately left open. That harvest retired the
frozen-Opus oracle for *maps* with one explicit exception:

> **Not harvested** — CommonEvents: the driver has no CE pass yet (maps only).
> Harvest the oracle's `CommonEvents.pory` when the CE pass lands, before retiring
> that file's oracle status.

The CE pass has since landed (`convert-common-events` is a registered pipeline
stage; `transpile_common_events` is the entry point). Tool:
`scripts/oracle_harvest.py --common-events`, which diffs block-by-block on
normalized text against `reference/archive/oracle_pory/CommonEvents.pory`.
Filed as `PROJECT_TODO.md` #87.

**Block census:** oracle **22 blocks / 263 lines**; ours **23 blocks / 402 lines**.
**0 identical, 22 divergent, 1 only-in-ours** (`CommonEvent_010_Move1`, a movement
block ours emits and Opus never produced). The zero-identical count is not alarming
on its own: the archive is pre-normalization by design, so every text-bearing block
differs on escapes alone.

## Headline result

**No transpiler bugs.** Every one of the 22 divergences dispositions as an Opus
error, a strip-path stub, a cosmetic text-normalization difference, or a loud
queued `# UNHANDLED`. This is the opposite of the map harvest, which found three
genuine transpiler bugs — and the difference is informative, because the CE pass
was written *after* those three fixes landed.

The file also demonstrates the §4.1 thesis on a single artifact better than any
argument: **the transpiler's 88 `# UNHANDLED` markers across 9 of 23 blocks are
all visible, and Opus's corresponding gaps are all invisible.** Where the
transpiler could not convert, it said so. Where Opus could not, it invented
something plausible and moved on (see B4).

## A. Transpiler bugs — found by the harvest

**None.**

## B. Opus errors / fabrications — ours is correct, oracle text discarded

| # | Cluster | Evidence |
|---|---|---|
| B1 | **`end` where `return` is required — 11 of 22 blocks.** Opus terminated common events with `end`. | A common event is reached by `call(...)`. `end` terminates the whole script and never returns to the caller; `return` is the only correct terminator. Verified at the live call site: `Map068_EV009_Page1` is `lock / faceplayer / call(CommonEvent_004) / release / end` — the `end` belongs to the *caller*. Opus's form would strand every caller mid-script. |
| B2 | **Invented variable names — 5 distinct vars across CE 035/037/077/080/081/082.** Opus emitted descriptive names; ours derives from `reference/uranium_variables.json` (§4.3 SoT) via `_naming.to_constant`. | Every one resolves in our favour, checked against the SoT: var 4 = "Temp Move Name" → `VAR_TEMP_MOVE_NAME` (Opus invented a dex-milestone name); var 22 = "BAMBO REWARD" → `VAR_BAMBO_REWARD`; var 88 = "Black Tiles" → `VAR_BLACK_TILES` (Opus: `VAR_GYM8_DARK_TILES`); var 102 = "People Talking" → `VAR_PEOPLE_TALKING` (Opus: `VAR_THEO_FOLLOW_CHATTER`); var 123 = "PowerPlant2 Quest" → `VAR_POWERPLANT2_QUEST` (Opus: `VAR_THEO_FOLLOW_PROGRESS`). **Uranium genuinely reuses var 4 ("Temp Move Name") as CE 035's PokéDex-milestone index** — ugly, and faithful. Opus's prettier name was a guess that happened to read better and describe the wrong variable. |
| B3 | **`lock`/`faceplayer`/`release`/`lockall`/`releaseall` *inside* the common event** (CE 012, CE 083). | The call site already locks (see B1's Map068 evidence). Opus's form double-locks. Ours emits the bare body. |
| B4 | **Fabricated multichoice bodies — CE 086, CE 087.** Opus emitted a full `multichoice(0, 0, MULTI_DREAM_VISUALIZER, TRUE)` + `switch` with three arms, warps to `MAP_URANIUM_70/97/204` at specific coordinates, and five `FLAG_DREAM_*` clearflags. | None of it is derivable from the source. `MULTI_DREAM_VISUALIZER` is not a constant the fork defines, and the flags/coords are invention. Ours emits the msgbox and then `# UNHANDLED code 102: choice menu ['No thanks', 'Yes, reset this vision', 'Yes, end the dream'] — needs a minted MULTI_* multichoice; arms not emitted`, and queues it. **Compile-clean-but-wrong versus loud-and-queued, in one block.** |
| B5 | **Stub text drift — CE 004/005/006.** Opus: "The Tandor Network is currently unavailable." Ours: "The Tandor Network is unavailable." | `reference/strip_list.json` → `common_events` is the SoT for the stub and carries the shorter string with `expect_name` guards. Ours matches it; Opus paraphrased. |

## C. Cosmetic-equivalent — no action

- **`format(...)` wrapping.** Ours wraps dialogue in Poryscript's `format()` and lets it
  re-flow; Opus hand-placed `\n`/`\p`. Ours is the better form — hand-placed breaks were
  computed for RMXP's box, not the GBA's.
- **`\p` page-break splitting** (CE 079). Opus emitted one `msgbox` with an internal `\p`;
  ours emits two `msgbox` calls. Same player-visible result.
- **Unrolled waits** (CE 076: 51 × `delay`, all `# UNHANDLED code 231`). Ours emits the
  literal unrolled sequence where Opus emitted a bare `end`. Verbose but faithful; a
  future idiom-collapse `loop` candidate, not a defect.

## D. Queue work this harvest confirms (not bugs — already loud)

88 `# UNHANDLED` markers across 13 codes, in 9 of 23 blocks:

| Code | N | Shape |
|---|---|---|
| 231 | 51 | command outside the v1 deterministic tier (CE 076's unrolled fade/wait) |
| 111 | 7 | conditional on button-input |
| 224 | 5 | command outside the v1 deterministic tier |
| 232 / 235 | 4 / 4 | command outside the v1 deterministic tier |
| 101 | 4 | dialogue with untranslated control code (`\wt[n]`, `\r\v[n]\c[0]`) |
| 355 | 4 | `pbSet(...)` with a computed argument — no expression evaluator |
| 122 | 3 | operand kind 6 (random/item/actor/…) |
| 102 | 2 | choice menu needing a minted `MULTI_*` (CE 086/087 — see B4) |
| 209 / 203 / 247 / 234 | 1 each | move route / command outside the v1 tier |

**CE 035 is the densest block in the file** and worth reading as a specimen: it carries
code 101 control codes, four code-355 computed `pbSet`s (including
`pbSet(1,PROFREWARDS[pbGet(22)+1][0])`, an array index through a variable read), and an
eleven-arm dex-milestone ladder. It converts, it is honest about what it dropped, and
none of it is silently wrong.

## E. Corroborated backlog items

- **#6 (F3 — `yesnobox` two-step → native `msgbox(text, MSGBOX_YESNO)`)** is live in
  CE 035: ours emits `msgbox(...)` + `yesnobox(0, 0)` where the native idiom is one call.
  Same `VAR_RESULT` semantics; still the cosmetic-equivalent the 2026-07-02 harvest
  called it (its section C), now with a second instance.
- **#5 (verify pre-seeded `VAR_GYM8_*` names)** gains a data point from CE 037. Our
  `VAR_BLACK_TILES` sits beside `VAR_GYM8_WHITE_TILES` and `VAR_GYM8_PROGRESS` and looks
  inconsistent — but it is the faithful derivation of Uranium's own var 88, "Black Tiles".
  The inconsistency is upstream, in Uranium's naming. **Any prefix-normalizing rename is a
  registry-policy change and needs the §10 gate; do not "fix" it in passing.**

## Consequence

With these dispositions recorded, `reference/archive/oracle_pory/` is **fully inert
history**. It gates nothing, no harvest target remains in it, and its README says so as
of this commit. Per D6, goldens are minted from reviewed transpiler output and never
from Opus text — that remains true and unaffected by this file.
