# The Flag Registry

> Externalized from CLAUDE.md §6. This is a **Phase 4** component — read it when
> Phase 4 starts. The hard rule (never hand-edit the registry's persistent state
> mid-run) is mirrored as a pointer in CLAUDE.md.

This deserves its own document because it's the most common place pipelines like
this go wrong.

## The problem it solves

RPG Maker uses numbered switches and variables (`Switch 42`, `Variable 17`).
pokeemerald-expansion uses named flags and vars (`FLAG_RECEIVED_STARTER`,
`VAR_STORY_PROGRESS`). The conversion agent must translate between them — and must
do so consistently across all 200+ maps. If `Switch 42` becomes
`FLAG_RECEIVED_STARTER` in one map and `FLAG_GOT_FIRST_POKEMON` in another, the
game breaks.

## How the registry works

- `flag_registry.py` is a stateful singleton during a pipeline run
- The conversion agent never invents a flag name in its output. It either uses a
  name the registry has already assigned to that switch ID, or it *proposes* a
  name and the orchestrator decides whether to accept
- New flag proposals go through a validation step:
  - Name follows the `FLAG_*` / `VAR_*` convention
  - Name doesn't collide with an existing pokeemerald-expansion constant
  - Name passes a basic sanity check (not empty, not "FLAG_TODO", not gibberish)
- Once accepted, the assignment is permanent for that pipeline run
- The final registry state is dumped to a `.h` file the pokeemerald-expansion
  fork includes

## Pre-seeded mappings

Before the first run, the registry is pre-seeded with known stable mappings —
things every Pokémon game has (received starter, beat first gym, talked to
professor). Look at `reference/essentials_to_emerald_map.md` for the canonical
list. Add new pre-seeds when you confirm a Uranium switch maps to a vanilla
concept.

## Self-switches (per-event flags)

RPG Maker self-switches (A–D) are local to an event instance — the "this NPC
remembers it talked to you" mechanism, used by ~860 events in Uranium. They have
**no global switch ID**, so they're handled apart from proposed flags:

- The conversion agent emits the deterministic name
  `FLAG_MAP{map}_EVENT{event}_SS{letter}` directly and does **not** propose it (it
  can't — there's no switch ID). This is by design (`system.md`,
  `few_shot/give_item_with_fanfare.md`).
- The **orchestrator derives** each event's self-switch usage (Control Self Switch
  / code 123, plus page conditions gated on a self-switch) and calls
  `registry.mint_self_switch(map, event, letter)`. Registration happens in the
  orchestrator, not the agent — so the frozen prompt needs no change.
- `mint_self_switch` is deterministic + idempotent, keyed by `(map, event,
  letter)`, and `dump_header` emits these under `RPG2GBA_SELFSWITCH_BASE`.

Without this the names are undefined symbols at assembly — discovered via the
rung-3 spike (2026-06-01), which is exactly the kind of integration gap the
poryscript compile-gate can't catch (it doesn't verify constants exist).

## The flag budget (RESOLVED 2026-07-10 — pulled forward from Phase 7)

Uranium's self-switch flags alone (1132 distinct by census, plus 235 global
switches, 345 temp switches, 119 vars) **exceed the fork's free saved-flag
space**, so the fork's saved ranges were expanded behind the
`RPG2GBA_EXPAND_EVENT_RANGES` config gate (`engine/include/config/rpg2gba.h` —
capacities; `constants/flags.h`/`vars.h` — derived `RPG2GBA_*_START` region
constants; see `reference/engine_extension_surface.md` §2). The assembler now
passes those constant *names* to `dump_header(flag_base=…, var_base=…,
selfswitch_base=…, tempswitch_base=…)` — the emitted header references them
symbolically — plus the parsed capacities, so a mint overflow fails loud at
dump time. The numeric int defaults remain only for placeholder *intermediate*
dumps; they are not fork-safe. Temp switches live in a dedicated region that
`ClearTempFieldEventData` resets on map transition (vanilla temp-flag
lifetime), disjoint from the `FLAG_TEMP_11..1F` rock-obstacle range.

## Hard rule for the build agent

You may modify `flag_registry.py`. You may modify
`reference/essentials_to_emerald_map.md`. You may NOT manually edit the registry's
persistent state file mid-run. If the registry's state is wrong, fix the input
data or the registry logic — don't patch the output.
