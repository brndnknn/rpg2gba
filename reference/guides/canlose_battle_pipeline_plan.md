# Pipeline plan: deterministic can-lose trainer battles

> Implementation design for graduating the Theo hand-conversion
> (`hand_conversions/Map050_EV019.pory`) into the deterministic spine. Written
> 2026-07-21. Mechanism + engine facts: `canlose_trainer_battles.md` (read that
> first). Status: **design only, not built** (user chose design-first 2026-07-21).

## Goal

A can-lose `pbTrainerBattle` inside a code-111 branch should convert
deterministically to `trainerbattle_earlyrival` + a `VAR_RESULT` win/loss branch,
with the opponent's party auto-emitted into the engine — no hand-conversion. Two
independent gaps (either can ship first):

- **Gap A — transpiler**: emit the earlyrival + branch pattern.
- **Gap B — staging**: wire converted trainers into the slice engine build.

## Gap A — transpiler (`conversion_agent/`)

### Where it hooks

Today: `transpiler.py` parses code-111 into an `IfNode`; `condition_expr`
(`:546`) returns `None` for a `ctype==12` script condition, so the node is queued
UNHANDLED. Add a **pre-pass on `IfNode`** (or a new `deterministic.py` classifier
that runs before the generic 111 path): if the condition is
`ctype==12` and its script string matches `pbTrainerBattle(`, handle it here
instead of queuing.

Reuse the existing arg parser in `deterministic.py:842-874`
(`classify_trainer_battle` already regex-parses class/name/defeat-text/party_id
and looks up `ctx.trainers[(class_const, name, party_id)] -> TRAINER_*`).

### Detection predicate

- `IfNode` whose condition `params[0]==12` and `params[1]` contains
  `pbTrainerBattle(` (and not `pbDoubleTrainerBattle`).
- The `canlose` arg is truthy. (Essentials arg order:
  `(trainerid, name, endspeech, doublebattle, party_id, canlose, ...)` — parse
  positionally, stripping the `_I("...")` blob first as the existing parser does.)
- `then` block = player-**won** aftermath; `otherwise` (code-411) block =
  player-**lost** aftermath.

### Emission shape

```
# optional: runtime party selection (see below)
trainerbattle_earlyrival(TRAINER_X, RIVAL_BATTLE_HEAL_AFTER, <defeat_text>, <victory_text>)
if (var(VAR_RESULT) == 1) {
    <transpile the RMXP else/LOSS block>
} else {
    <transpile the RMXP then/WIN block>
}
# reconverged tail = whatever followed the 111 in the parent block
```

**Polarity (critical):** `VAR_RESULT == 1` means the player **lost** (engine sets
`gSpecialVar_Result = TRUE` on an EARLY_RIVAL defeat), which is the RMXP **else**
branch. `pbTrainerBattle` returns true on a **win** = RMXP **then** branch. So the
poryscript `if (VAR_RESULT==1)` body is the RMXP *else*, and the `else` body is the
RMXP *then* — the branches swap. Get this wrong and every canlose battle plays the
opposite aftermath.

The branch bodies are ordinary event commands — recurse through the existing node
emitter. `[121]` control-switch writes (e.g. Uranium switch 35) convert to
`setflag`/`clearflag` for free, so the **outcome flag is recorded automatically**
(no special-casing needed) as long as the RMXP script wrote it.

### Runtime party selection (the hard case)

`party_id` is often an expression, e.g. `pbGet(151)+18`. Handle two forms:

- **Literal** `party_id` → single `trainerbattle_earlyrival(TRAINER_X, ...)`.
- **`pbGet(N)+K`** → wrap in `switch (var(VAR_for_N)) { case v: trainerbattle_
  earlyrival(TRAINER_for(v+K), ...) }`. Enumerate `v` over the values the source
  var takes (or over the `(class,name,party_id)` keys present in `ctx.trainers`
  for that class+name). The Theo fight: `N=151` (`VAR_POKEMONTEST`), `K=18`,
  values 1..3 → `TRAINER_THEO_9/10/11`. Anything more exotic (arithmetic the
  parser doesn't recognize) → **queue**, don't guess.

### Text slots

- `defeat_text` (trainer loses = player wins) = the `pbTrainerBattle` `endspeech`
  arg (`_I("...")`), which is exactly the trainer's "you beat me" line.
- `victory_text` (trainer wins = player loses) — RMXP has **no** explicit arg for
  this; the loss reaction lives in the else-branch dialogue. Options: (a) lift the
  first opponent `[101]` line from the else block; (b) leave a generic line and
  let the else-branch field dialogue carry it. **Decision:** (b) — keep the slot
  minimal, since the full loss speech is already in the transpiled else block.
  (The hand-conversion used a lifted line; either is fine.)

## Gap B — staging (`scripts/assemble_pathfinder.py`)

The Phase-2 converter already writes `intermediate/trainers.json`
(`TRAINER_* -> {class, name, party_id, party[]}`). It is never staged. Add a pass
that, for the `TRAINER_*` referenced by the slice's scripts, emits:

1. **Party blocks** into `trainers.party`. Prefer a **gitignored `*.gen`
   overlay** appended via an include hook (matches how layouts/flags are handled),
   NOT edits to the committed `trainers.party` — keep the vendored tree pristine
   (RPG2GBA_VENDOR.md). If `trainerproc` can't take an overlay file, fall back to
   writing a generated `trainers.party` from `upstream + slice`.
2. **`TRAINER_*` constants**. `opponents.h` is hand-maintained + committed and the
   fork-index gate reads it from `HEAD:engine`. Two viable routes:
   - **Generated header** (like `uranium_flags.h`): write a gitignored
     `uranium_trainers.h` with `#define TRAINER_X (TRAINERS_COUNT_EMERALD + n)`,
     include it via the existing hook, AND feed the names to the gate via a new
     `trainer_manifest.json` consumed by `fork_index.registry_extra_symbols`
     (mirrors `species_manifest.json`). This keeps `opponents.h` untouched.
   - **Commit into `opponents.h`** (what the Theo fix did): simplest, but edits a
     tracked vendor file and needs a commit before the gate passes. Fine for a
     handful; doesn't scale to the corpus.
   **Decision:** generated header + manifest (scales, keeps vendor pristine).
3. **Budget guard**: only stage trainers actually referenced by slice scripts (the
   corpus has 331; the flag/`TRAINERS_COUNT` budget note in `opponents.h` says ~9
   free before flag overflow — a manifest+gen header must also bump
   `TRAINERS_COUNT`/`MAX_TRAINERS_COUNT` deliberately, see the ledger).
4. **Trainer battle sprite**: no Uranium trainer-pic pipeline yet → `Pic:` is a
   stock stand-in (Youngster). Cosmetic; tracked as a separate follow-up.

## Open decisions to settle before building

1. **Double-heal**: `RIVAL_BATTLE_HEAL_AFTER` auto-heals; RMXP loss branches also
   run an explicit heal (`[314]`/fade dialogue). Drop the explicit heal on
   conversion, or accept a harmless double-heal? (Lean: drop explicit heal, let
   the engine flag own it — one source of truth.)
2. **No-heal canlose**: battles that are losable but should NOT heal have no native
   mode (only heal-or-whiteout). Enumerate the corpus; if any exist, they need a
   custom-C "no-whiteout, no-heal, return-to-script" battle flag (Phase-6). Defer.
3. **Faithfulness**: full transpile of the win/loss branch bodies vs trimming
   randomizer/nuzlocke sub-branches (the hand file trimmed). Lean: transpile what
   the deterministic tier handles, queue the rest (fail-loud), don't trim silently.
4. **Constant allocation scheme** (gen header + manifest vs committed opponents.h).
5. **Retiring the hand file**: once the transpiler output is verified equivalent,
   delete `hand_conversions/Map050_EV019.pory` and confirm the slice still
   builds + boots identically (diff the generated `Map050.pory`).

## Test plan

- Unit: detection predicate (canlose true/false, double-battle reject); arg parse;
  literal vs `pbGet(N)+K` party selection; branch polarity (VAR_RESULT==1 → RMXP
  else); text-slot extraction.
- Golden: the Theo EV019 fixture → expected earlyrival + swapped-branch output.
- Integration: stage → assemble → `make modern` clean; fork-index gate resolves the
  auto-staged `TRAINER_*`.
- Boot-walk: S6b win AND loss both play correctly with the hand file removed.

## Suggested sequencing

1. Gap B staging first (unblocks any trainer battle, corpus-wide) — but it needs
   the constant-allocation decision (#4).
2. Gap A transpiler (literal-party case), then the `pbGet(N)+K` switch case.
3. Retire the hand file (#5) once A+B produce equivalent output.
