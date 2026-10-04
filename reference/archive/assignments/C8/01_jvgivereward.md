# Task 1 — The `jvGiveReward` Reward Ladder (45 points)

## Goal

Replace `beat_floor`'s blanket refusal of `jvGiveReward` with a real extractor that reads the
`PROFREWARDS` table from source and emits the item/egg grants each rung actually pays out.

Operator ruling: `REDERIVATION_PLAN.md` §16.3, "C8 shape" ruling **(e)** — "`jvGiveReward` gets
its own extractor that reads `PROFREWARDS` from source rather than interpreting Uranium's
script library."

## ⚠️ Read this before anything else: the task is a *replacement*, not an addition

The ruling says "gets its own extractor", which sounds like there is nothing there today.
There is. `src/rpg2gba/beat_floor/script.py:397-400` already registers one:

```python
"jvGiveReward": _refuse(
    "non_literal_args",
    "jvGiveReward: reward selected by $game_variables[22], not literal",
),
```

and `src/rpg2gba/beat_floor/condition.py:189-201` (`_extract_uranium_jv_reward`) refuses the
same way for the 111-type-12 condition form. **Your job is to replace these with something that
resolves, not to add a third reader.**

That refusal's *reason* is also the thing you are going to disprove. Read it again: "reward
selected by `$game_variables[22]`, not literal". True — and irrelevant, because variable 22 is
**modelled state**. The bar for the floor is not "is it a literal", it is "can the pipeline
know it".

## Learning objectives

- Tell apart two functions that *look* like they need the same unavailable model, when only one
  of them actually does
- Read a static data table out of vendored source instead of re-implementing the logic over it
- Emit a set-valued assertion (a rung you cannot pin down yields *several* possible grants)
  without either guessing one or refusing everything

## The crux: `jvGiveReward` does not need the party model; `jvNextReward` does

Read `reference/scripts_dump/213_Bambo_Reward.rb` in full — it is 49 lines. The two functions
that matter:

```ruby
def jvNextReward
  if $Trainer.pokedexOwned >= PROFREWARDS[$game_variables[22]+1][0]   # <-- dex read
    $game_variables[22]+=1
    return true
  else
    return false
  end
end

def jvGiveReward
  if [4,6,8].include?($game_variables[22])                            # <-- var 22 only
    poke=PROFREWARDS[$game_variables[22]][1]
    if poke == "starter"
      poke=1 if $game_switches[60]==true                              # <-- switches only
      poke=3 if $game_switches[61]==true
      poke=5 if $game_switches[59]==true
    end
    return pbGenerateEgg(poke)
  else
    item = true
    item = false if Kernel.pbReceiveItem(PROFREWARDS[$game_variables[22]][1])
    if PROFREWARDS[$game_variables[22]][2]
      item = false if Kernel.pbReceiveItem(PROFREWARDS[$game_variables[22]][2])
    end
    return item
  end
end
```

`jvGiveReward` reads **exactly two kinds of state**: `$game_variables[22]` and
`$game_switches[59/60/61]`. Both are ordinary modelled state — a `Variable` and three
`Switch`es in `story_state`. It never touches `$Trainer` at all.

`jvNextReward` is the one that reads `$Trainer.pokedexOwned`. **Its `party_model` refusal is
correct and must stay.** Ruling (b) deliberately declines to model dex quantities.

Variable 22 (`"BAMBO REWARD"`, `reference/uranium_variables.json:23`) is a **claimed-rung
index, not a dex counter** — its only writer in the whole corpus is `jvNextReward`'s
`$game_variables[22]+=1`. `REDERIVATION_PLAN.md` states this around line 940; verify it
yourself with a grep before you rely on it, and say so in Q3.

## The source of truth you must reuse

| Thing | Where | Don't |
|---|---|---|
| The `PROFREWARDS` table | `reference/scripts_dump/213_Bambo_Reward.rb` | Don't retype the table into Python. Parse it, or generate it and cite the source — see R1. |
| Item symbol → assertion params | `beat_floor/script.py`'s `_extract_receive_item` (line ~172) | Don't resolve to a pokeemerald constant here; that extractor stores the **raw symbol** and leaves mapping downstream. Match it. |
| Refusal construction | `beat_floor/script.py`'s `_refuse` (line ~146) | Don't hand-build `FloorRefusal` where `_refuse` fits. |
| Assertion kinds | `item_grant`, `pokemon_grant` already exist in `AssertionKind` and are already in `OFFLINE_KINDS` | Don't add a new kind. |

## Requirements

### R1 — Read the table: new module `beat_floor/reward_ladder.py`

```python
"""Uranium's Bambo reward ladder (`PROFREWARDS`), read from source.

`reference/scripts_dump/213_Bambo_Reward.rb` is the single source of truth
for what each rung pays out (CLAUDE.md §4.3). ...
"""

def load_profrewards(scripts_dump_dir: Path | None = None) -> tuple[Rung, ...]:
    """The `PROFREWARDS` table, parsed from the Ruby source.

    Raises if the file is missing or the literal cannot be parsed -- a
    silently empty ladder would turn every rung into a no-op (§4.5).
    """
```

- `Rung` is a frozen dataclass: `index: int`, `threshold: int`, `items: tuple[str, ...]`,
  `species: str | None`, `is_egg: bool`.
- **You already have a Ruby parser.** Writing a regex for a Ruby array literal in the one repo
  that just spent six stages deleting Ruby regexes will lose points.
- ⚠️ **`parse_program` will NOT parse this file, and that is not a bug.** Verified 2026-09-23:
  feeding it `PROFREWARDS=[...]` raises
  `RubyParseError: unsupported_syntax:constant_assignment at line 1 col 13`. Assignment to a
  **constant** (capitalised name) is deliberately outside the subset — the interpreter models
  game state, and a Ruby constant is not game state. Isolate the bracketed literal and hand it
  to `parse_expression` instead, which returns a clean `ast.ArrayLit` of 12 `ast.ArrayLit`s.
  How you isolate it is your call; note that the last rung carries a trailing `#` comment,
  which the lexer handles fine once the literal is what you pass.
- Inside, `PBItems::RARECANDY` parses as a `ScopedConst` (`scope`/`name`); `PBSpecies::MINICORN`
  likewise; `"starter"` is a `Str`; thresholds are `Int`. Decide how each maps onto `Rung`'s
  fields and document it. **`ScopedConst.scope` is what tells an item from a species** — do not
  infer it from the rung index, or rung 8's `"starter"` will mislead you.
- Index 0 (`[0]`) grants nothing. Index 11 (`[999]`) is the author's own crash workaround and
  is unreachable — represent it, don't special-case it away, and explain in Q1.

### R2 — The extractor

Replace the `script.py` stub refusal with a real extractor with the standard signature:

```python
def _extract_jv_give_reward(
    text: str, list_index: int, ctx: ExtractContext,
) -> ExtractResult:
```

The call is always bare (`jvGiveReward`, no arguments) at all 7 script-form sites. If the text
is anything else, refuse `non_literal_args` as today. If the ladder cannot be read at all,
refuse loudly — never fall back to the old blanket refusal silently.

#### ⚠️ The hard part: "one of eleven" does not fit the floor's vocabulary

The obvious move is to emit one `item_grant` per item rung and one `pokemon_grant` per egg
rung — eleven assertions — on the grounds that the floor is a lower bound. **That is wrong, and
`beat_floor/coverage.py` is where you can see why.** Read it before you design anything:

- `uncovered()` requires **every** floor assertion to be covered by a declared one. The floor is
  a **conjunction**: "all of these hold", not "one of these holds". Eleven grant assertions
  would demand a generated beat assert all eleven grants happen at one call site. Exactly one
  rung fires per visit, so that is false.
- `assertion_key` is `(row_id, kind, list_index, code)` — **all eight item rungs at one call
  site share the same key.** They are not distinguishable to the coverage relation.
- `contradicts()` says a declared assertion sharing a key but disagreeing on a param value
  refutes the floor. So those eight sibling assertions **pairwise contradict each other**. A
  floor that contradicts itself is not a weaker floor; it is a broken one.

So the real question this task asks is the C7 Task 3 question again: **a fact has shown up that
the existing vocabulary cannot express. Extend the vocabulary, or refuse precisely?**

Pick one and defend it in Q2. All three are defensible:

| Option | What it costs |
|---|---|
| **Refuse, precisely.** Keep a refusal, but replace the wrong reason ("not literal") with one naming the real obstruction: the floor cannot express a one-of-N grant at a single call site. | The rows stay red — but red for a true reason, which is the §4.5 bargain. |
| **Narrow the rung set.** Use what the story model knows about variable 22 to cut the candidates down. | Two costs. `ExtractContext` carries no story state and its docstring says "extractors never load files", so this means extending that contract. **And narrowing is not the same as solving:** the story model yields a value *set*, so var 22 ∈ `{4,6}` still leaves two live rungs and you are back in the same contradiction. This option only finishes the job where the set collapses to a **singleton** — decide what you emit when it does not. |
| **Extend the vocabulary.** Add a disjunctive kind (say `one_of_grant`) whose params carry the candidate set, so coverage compares one value. | A new `AssertionKind` member, an `OFFLINE_KINDS` decision, and every consumer of the vocabulary. C7 Task 3 is your precedent for doing this properly. |

**What you may not do** is emit several same-key grant assertions and call it a lower bound. A
test pins exactly that: no two assertions your extractor emits for one call site may
`contradicts()` each other.

### R3 — The condition form is a third of the work, not a footnote

Measured 2026-09-23: of the **11** `jvGiveReward` sites on `Map050`, only **7 are code-355
script calls**. The other **4 are code-111 type-12 conditions** (`if jvGiveReward`), handled by
`condition.py`'s `_extract_uranium_jv_reward`. All 11 are on `ev005` (pages 5 and 6).

A *condition* on `jvGiveReward` tests its **return value**. Read the Ruby again: it returns
`item`, a bool tracking whether `Kernel.pbReceiveItem` succeeded — i.e. **bag-space
success/failure**, not which rung fired. That is a genuinely different question from R2's, and
the reward table tells you nothing about it.

Decide whether the condition form can resolve or must still refuse, and **say which in Q3**.
Both answers can be defended; an undefended one scores zero.

### R4 — Leave `jvNextReward` alone

Confirm by test that `jvNextReward` still refuses, and that its reason still names the dex
read. If your change makes `jvNextReward` resolve, you have modelled the dex by accident and
broken ruling (b).

## Hints

- **Start by measuring, not coding.** Run the floor and story reports for CH01 and write down
  the current numbers. You need them for the commit message anyway:
  ```bash
  python -m rpg2gba.beat_floor report --chapter CH01
  python -m rpg2gba.story_state report --chapter CH01
  ```
  Today CH01's floor shows `non_literal_args` 15 (one of them this call), and ~33 story branch
  rows under `map050/ev005/p5`–`/p6` carry both `party_model` and
  `unmodelled_outcome:pokedex_owned_vs_profreward_tier`.
- **If you take the narrowing option**, know what it costs before you start. `ExtractContext`
  (`assertion.py:115`) carries `map_id`, `event_id`, `page_idx`, `row_id`, `event`, `map_data`,
  `common_events_by_id`, `door_cells` — and its docstring says *"Everything an extractor may
  read. Extractors never load files."* There is no variable-22 constraint in there, so narrowing
  inside the extractor means changing that contract. `beat_floor` does already consume story
  state once, at a different layer — find `_state_assertions_for_row` in `walk.py` and see
  where. Deciding which layer should own this is the interesting part; do it before you code.
- **Eight items, seven rungs.** `[75, SHINYSTONE, DUSKSTONE]` is one rung paying two items. If
  your count says 8 rungs grant items, you have merged those two. `REDERIVATION_PLAN.md`'s own
  prose says "eight rungs grant items", which is off by one in rungs and right in items — a
  good reminder that the plan is a plan, not the source.
- **`"starter"` is not a species.** Rung 8 resolves its species from switches 59/60/61, the
  starter-choice flags. Those are modelled, so this is resolvable in principle — but decide
  whether the floor should resolve it or emit all three, and justify it.

## Tests

`tests/test_beat_floor_reward_ladder.py`: table-parsing cases (all 12 rungs, the two-item rung,
the egg indices, the `"starter"` rung, the unreachable `[999]`, a missing file, an unparseable
literal), `rungs_for_variable` cases, the self-contradiction guard described above, the
`jvNextReward`-still-refuses guard, and a real-data test pinning the 7/4 split on `Map050`.

The extractor tests deliberately do **not** pick one of R2's three options for you. They pin the
properties every correct answer shares: the ladder parses, `jvNextReward` still refuses, and the
extractor never emits two assertions at one call site that contradict each other.

## Questions (commit message)

1. Index 11 is `[999]`, commented in the original as "Workaround, game crashes when loading
   last one." What does your `Rung` do with it, and why is representing it better than
   dropping it?
2. **Which of R2's three options did you take, and why?** Name the one you rejected most
   reluctantly and what would have to change to make it the right call. If you narrowed:
   what does your code do when the narrowed set still has more than one rung in it?
3. Does the 111-type-12 condition form (4 of the 11 sites) resolve now, or still refuse?
   Defend it in two sentences, naming what the condition is actually testing.
4. You were told variable 22's only writer is `jvNextReward`. Show the grep you ran to confirm
   it. What would break if that were false?
5. Report CH01's `non_literal_args` and `party_model` counts before and after. If
   `party_model` did **not** drop, explain why that is the correct outcome. If your answer to
   Q2 was "refuse precisely", say what the refusal count did and why an unchanged count can
   still be progress.
