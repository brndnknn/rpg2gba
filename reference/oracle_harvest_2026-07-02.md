# Oracle harvest — differential dispositions (2026-07-02)

**What this is:** the grill-D6 one-time harvest. Maps 001–007 transpiled by the
deterministic transpiler (`transpiler.py` + `transpile_driver.py`, classifiers
first) and diffed block-by-block on normalized text against the frozen-Opus
oracle (`reference/archive/oracle_pory/`). Tool: `scripts/oracle_harvest.py`.
Every divergence cluster below carries its disposition. Per D6, goldens come
from *reviewed transpiler output*, never from Opus text; with these
dispositions recorded, **the oracle is retired** (the archive stays for
provenance, it gates nothing).

Final block census (maps 001–007): **43 identical**, 18 divergent,
42 only-in-ours, 20 only-in-oracle (before the fixes below; the three
transpiler bugs the harvest surfaced were fixed during the harvest, which is
the point of the exercise).

## A. Transpiler bugs — found by the harvest, FIXED

| # | Cluster | Fix |
|---|---|---|
| A1 | **Label collision.** Map002 has two events both named "Receptionist TRADE"; name-based labels (`Map002_Receptionist_TRADE_Page1`) collide → duplicate script symbols at compile. Opus had id-qualified labels. | Transpiler now emits the canonical id-based label `Map{m:03d}_EV{e:03d}_Page{n}` (= `metadata_wiring.page_label`, the form map.json wiring references — no `normalize_labels` rewrite needed). Event name rides as a `#` comment above the block. The classifier (idiom-collapse) layer keeps its name labels internally; `transpile_driver._canonicalize_labels` rewrites them on the way out. |
| A2 | **Missing lock on touch triggers.** Opus wrapped player-touch doormat scripts (Map001 EV002/EV005) in `lock`/`release`; we only wrapped trigger 0. A touch cutscene without `lock` leaves the player free to walk mid-script. | Triggers 1/2 with a non-empty body now get `lock`/…/`release` (no `faceplayer`). |
| A3 | **122 random operand queued.** Oracle (Map002 EV004/EV007) shows the native idiom. | Now emitted: `random(hi-lo+1)` [+ `addvar(VAR_RESULT, lo)` if lo≠0] + `copyvar(target, VAR_RESULT)`. Verified against real params `[102,102,0,2,0,2]` / `[102,102,0,2,1,2]`. |

## B. Opus errors / silent drops — ours is correct, oracle text discarded

| # | Cluster | Evidence |
|---|---|---|
| B1 | **`healparty`** — the invented command (Map002 EV001 pages 1–2, plus Map048/049 in the slice archive). | Ours emits `special(HealPlayerParty)`; the fork-index gate makes the invented form unshippable. This is the exact bug class the spine exists to stop. |
| B2 | **Dropped choreography.** Opus omitted move routes, delays, fadescreens, waitstates it deemed pacing (Map001 doormat walk-in, Map002 nurse bow + heal jingle wait, Map003/005/006 tone fades, Map007). | Ours emits `applymovement`/`waitmovement`/`delay`/`fadescreen` per the source commands. More faithful; harmless where cosmetic. |
| B3 | **Flattened conditionals.** Map002 EV001: the "Thank you for waiting" text lives inside a `Kernel.pbPokerus?` branch; Opus silently dropped the condition and emitted one arm unconditionally. | Ours queues the script-condition branch **visibly** (`# UNHANDLED` + queue entry). Silent-wrong vs loud-and-queued — the queue is the design. |
| B4 | **`lock`/`release` around empty pages** (Map007 EV008). | Ours emits a bare `end` block. Same semantics, less noise. |
| B5 | **Inconsistent touch-trigger locking.** Opus locked Map001 doormats but not Map007's equivalents. | Ours locks all non-empty touch pages uniformly (see A2). |

## C. Cosmetic-equivalent — no action

- **msgbox merging:** Opus merged consecutive text runs with `\p` and used
  `msgbox(text, MSGBOX_YESNO)`; ours emits one `msgbox` per source text run
  and `yesnobox(0, 0)`. Same VAR_RESULT semantics. A future idiom-collapse
  pass may merge trailing msgbox + YES/NO into the `MSGBOX_YESNO` form for
  polish — not correctness.
- **`elif` chains vs nested `else { if`:** structurally different, logically
  identical (Map002 EV004/EV007 random dispatch).

## D. v1 queue tier — expected gaps, queued by design (grow per D8 evidence)

- Script conditions (`pbPokerus?`, `onEvent?`, `$game_player.x==…`) — the
  condition-interpreter growth list; corpus-wide 1,667 type-12 conditions.
- Non-YES/NO choice menus → need minted `MULTI_*` + `case` blocks
  (Map003 EV004 / Map005 EV003 ticket kiosks; oracle used switch/case).
- Labels/`goto` submenus (Map006 EV002 Bealbeach/Legen menu) — 118/119 tier.
- Dialogue with Essentials control codes (`\.`, `\wtnp[..]`) — queued, not
  mistranslated (Map004 EV003, Map007 EV001).
- Whole events Opus never converted (its own queue), e.g. Map002 EV005: ours
  emits every mechanical page + queue markers — strictly more coverage.

## E. Open fidelity question (user call, CLAUDE.md §10)

- **`ITEM_PARLYZ_HEAL` vs `ITEM_PARALYZE_HEAL`** (Map004 mart): Phase-2 item
  minting names vanilla items Uranium kept by their Uranium display name;
  the expansion renamed some (`PARLYZ HEAL` → `ITEM_PARALYZE_HEAL`). Items
  that ARE vanilla items should probably resolve to the fork-native constant
  instead of minting a Uranium duplicate. That's a `pbs_converter/items.py`
  reconcile question, not a transpiler bug — parked here so it isn't lost.

## Not harvested

- **CommonEvents**: the driver has no CE pass yet (maps only). Harvest the
  oracle's `CommonEvents.pory` when the CE pass lands, before retiring that
  file's oracle status.
