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

## Hard rule for the build agent

You may modify `flag_registry.py`. You may modify
`reference/essentials_to_emerald_map.md`. You may NOT manually edit the registry's
persistent state file mid-run. If the registry's state is wrong, fix the input
data or the registry logic — don't patch the output.
