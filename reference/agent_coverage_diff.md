# Data-derived command census vs. the conversion agent's referenced lists

> Generated 2026-06-14. Compares the **data-derived** command vocabulary
> (`scripts/count_unique_commands.py` → `uranium_real_commands.md` /
> `uranium_excluded_noncommands.md`, walked fresh over all 199 maps + 100 common
> events) against the lists the **conversion agent** actually references in its
> frozen system prompt (`prompt_builder.build_static_context` + `system.md` +
> `few_shot/*.md` + the two `reference/` tables).
>
> Purpose: find coverage gaps in the agent's frozen reference, in both directions.
> Reproduce the numbers with the inline snippets at the bottom.

## What the agent references

| Source | Role | Loaded by |
|---|---|---|
| `reference/rgss_event_commands.md` | 59-code table **+** a 250-row script-call signature *inventory* (names + counts, no disposition) | `load_command_reference` (codes sliced per-event) |
| `reference/uranium_script_calls.md` | ~54-row script-call **disposition** table (MAP/STRIP/UNHANDLED) | `load_script_call_reference` (frozen system prompt) |
| `prompts/system.md` | instruction set; names `pbTrainerBattle` + the `onEvent?` trigger idiom | `load_system_prompt` |
| `prompts/few_shot/*.md` | 5 worked examples (incl. `trainer_battle_and_unhandled.md`) | `load_few_shots` |
| `reference/poryscript_cheatsheet.md` | target-language cheatsheet | `load_cheatsheet` |

## Command codes — exact match

The agent's `rgss_event_commands.md` table lists the **identical 59 codes** the
census finds (47 real + 11 scaffolding + `355`). Same set, no gap either way.
**Full parity.**

## Script calls — three tiers of coverage

The census finds **148 real script-call heads** (7,424 occ). The agent covers them
in three tiers:

| Tier | Definition | Distinct heads | By occurrence |
|---|---|---|---|
| **Enumerated** | signature appears in the 250-row inventory in `rgss_event_commands.md` | superset (our 148 ⊂ its 250; the 250 also lists the noise the census filters: `item`, `PBItems`, `end`, `if`, `(non-identifier)`, `$game_variables`) | — |
| **Has a disposition** | a MAP/STRIP/UNHANDLED row in `uranium_script_calls.md` | **~54** | **~83%** of script-call lines |
| **+ system.md / few-shots** | `pbTrainerBattle` (317×) + `onEvent?` trigger idiom (`get_character` 324×) | +2 high-freq | **~91%** of occurrences |
| **No naming anywhere** | falls through the explicit rule *"absent ⇒ UNHANDLED, queue it"* | **31** | 613 occ |

So nothing in the corpus is *unknown* to the agent at the `355/655` level — its
inventory was built from the same deserialization. The long-tail gap is **by
design** (the doc states the rare tail is "intentionally undocumented").

## The structural blind spot the census surfaced

The agent's 250-signature inventory was built from **`355/655` Script calls only.**
**Action-bearing code-111 *script-conditions* are not in it** — the agent sees
them only as raw branch text plus the generic `111` row. All 31 "never named"
heads are this kind. Highest-frequency:

| Head | Occ | Note |
|---|---|---|
| `get_character` | 324 | the `get_character(0).onEvent?` event-trigger idiom — **covered conceptually** in `system.md` via "onEvent", literal token absent |
| `pbTrainerBattle` | 317 | **covered** in `system.md` + `trainer_battle_and_unhandled.md` |
| `pbQuantity` | 44 | bag-count check (`$PokemonBag.pbQuantity(...)>0`) |
| `pbPickBerry` | 41 | berry harvest — `pbBerryPlant` is UNHANDLED-tagged (its `355` sibling) |
| `pbCoralBreak` | 36 | coral/rock break field action |
| `pbRockSmash` | 29 | field-move check — `pbRockSmashRandomEncounter` is UNHANDLED-tagged |
| `pbPhoneBattleCount` | 26 | phone rematch count |
| `pbMoveTutorChoose` | 20 | move-tutor selection |

Functionally **benign**: most of these resolve to features already tagged
UNHANDLED under their `355` names, so the agent queues them anyway (the safe
default). But this census is the first list to name them as distinct ops, and a
future cluster-triage / classifier pass should treat the **111-condition call**
as a first-class signature, not just branch text.

## Granularity mismatch (reconciled)

Where a call has a receiver, the census recorded the **receiver**; the agent's
table names the **method**. Same operations, sliced differently:

| Census head (excluded bucket) | Agent reference names | Occ |
|---|---|---|
| `pkmn` / `pok` (local-receiver/scratch) | `pkmn.pbLearnMove`, `pkmn.setAbility`, `pkmn.setItem` | 61 (`pbLearnMove`) |
| `spriteset` (local-receiver) | `$scene.spriteset.addUserSprite` (STRIP) | 17 |
| `XInput` | `XInput.vibrate` (STRIP) | 54 |
| `nextBattleNuclearHorde` (global state-write) | `$PokemonGlobal.nextBattleNuclearHorde` (UNHANDLED) | 17 |

⇒ the census's "excluded" buckets (receivers / state-writes) contain **~16 ops the
agent treats as first-class commands.** This is exactly the caveat flagged when the
census was built: the receiver/state-write buckets hide real operations.

## Count drift (staleness, not error)

`uranium_script_calls.md` counts predate the current deserialization (measured by
an earlier `_tmp_scriptcall_dict.py` pass). Same signatures, different tallies:

| Signature | Doc count | Fresh census |
|---|---|---|
| `pbSetSelfSwitch` | 336 | 191 (`355`-form) |
| `pbItemBall` | 46 | 243 (incl. 234 in `111`-conditions) |
| `setTempSwitchOn` | 345 | 345 ✓ |
| `pbTrainerEnd` | 250 | 250 ✓ |

The `pbItemBall` divergence is the same 111-vs-355 lens: the doc's 46 counted only
the `355` form; the census also counts the 234 ground-item `if Kernel.pbItemBall(...)`
conditions (now claimed by `classify_ground_item`). Not a correctness issue, but
the doc's counts should be regenerated if they're ever used for prioritization.

## Net

The two lists **agree on vocabulary** — codes identical, script calls a clean
subset of the agent's inventory. They differ only in:
1. **disposition depth** (54 dispositioned / ~91% of volume; the rest queued by design), and
2. the census additionally naming the **111-condition action calls** the agent's
   `355/655`-only inventory omits, and
3. **granularity** (census records receivers; agent names methods) + **stale doc counts.**

---

## Reproduce

```bash
# census files
python3 scripts/count_unique_commands.py

# code-table parity
python3 - <<'PY'
import re; from pathlib import Path
codes={int(m.group(1)) for ln in Path("reference/rgss_event_commands.md").read_text().splitlines()
       if (m:=re.match(r"^\|\s*(\d+)\s*\|",ln))}
print(len(codes), sorted(codes))
PY

# script-head coverage vs full agent context
#   (uranium_script_calls.md + rgss_event_commands.md + poryscript_cheatsheet.md
#    + prompts/system.md + prompts/few_shot/*.md)
```
