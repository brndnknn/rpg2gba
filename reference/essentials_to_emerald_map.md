# Essentials → pokeemerald-expansion flag/var pre-seed map

> Canonical pre-seed source for the Phase 4 flag registry
> (`src/rpg2gba/conversion_agent/flag_registry.py`). Read
> `reference/flag_registry_policy.md` for the policy this serves.

This file holds the **high-confidence, hand-authored** mappings from a Uranium
`System.rxdata` switch/variable (by index) to the `FLAG_*` / `VAR_*` constant the
registry should mint *before* any conversion run. It is intentionally small.

**What is and isn't here:**

- The full universe of named switches/variables lives in the Phase 3 sidecars
  (`reference/uranium_switches.json`, `reference/uranium_variables.json`). The
  registry reads those for two things: (1) detecting Essentials **script-switches**
  (names beginning `s:`, runtime-evaluated — *never* minted, per Phase 3 §3.3), and
  (2) carrying each switch's human label as *context* the conversion agent sees.
- The registry does **not** bulk-mint a flag for every labelled switch — the
  agent proposes a context-derived name when it first encounters an unassigned
  switch, and the registry validates + commits it (one source of truth).
- This table only pins the switches/vars whose meaning is stable and
  story-load-bearing enough that we don't want to leave their naming to chance
  (badges, gym-completion gates, the gym-8 / Tandor-championship state). Indices
  verified against the Phase 3 sidecars (2026-05-25).

**Adding rows:** when you confirm another Uranium switch maps to a stable concept,
add a row. Each row is `| kind | index | uranium label | constant | notes |`.
`kind` is `flag` (switch) or `var` (variable); `constant` must start with
`FLAG_`/`VAR_` accordingly and be `SCREAMING_SNAKE_CASE`. The loader parses every
well-formed row in the table below and fails loud on a malformed one.

**Vanilla-equivalence caveat:** some of these (e.g. "Got Pokemon") likely
correspond to an existing pokeemerald flag (`FLAG_ADVENTURE_STARTED` and kin). We
do **not** assert that equivalence here — we mint a fresh `rpg2gba` name and leave
the "is this really the vanilla flag?" call to the §9 review. The registry's
fork-collision check rejects any name that *already exists* in the fork, so a row
that intends to **alias** a vanilla constant will fail loud until that decision is
made deliberately.

**Deferred — badges (switches 251–263).** Uranium ships 12 badge switches
(251–263, with 258/259 both labelled "BADGE 8"). pokeemerald already defines
`FLAG_BADGE01_GET … FLAG_BADGE08_GET` and wires them into HM/gym gating. Whether
Uranium's badges should *reuse* those 8 vanilla flags (and what to do with badges
9–12) is a §9 fidelity decision, so no badge rows are pre-seeded here yet.

<!-- PRESEED-TABLE-START -->

| kind | index | uranium label | constant | notes |
|------|-------|---------------|----------|-------|
| flag | 2   | Got Pokemon          | FLAG_RECEIVED_STARTER          | Player has their starter. Possible vanilla equivalent — review at §9. |
| flag | 27  | First Badge          | FLAG_RECEIVED_FIRST_BADGE      | Set when the first gym badge is obtained. |
| flag | 55  | Gym 1 defeated       | FLAG_DEFEATED_GYM1_LEADER      | Gym-1 leader beaten. |
| flag | 81  | Gym 4 end            | FLAG_DEFEATED_GYM4_LEADER      | Gym-4 cleared. |
| flag | 94  | Gym 5 End            | FLAG_DEFEATED_GYM5_LEADER      | Gym-5 cleared. |
| flag | 111 | Gym 6 end            | FLAG_DEFEATED_GYM6_LEADER      | Gym-6 cleared. |
| flag | 113 | Gym 7 end            | FLAG_DEFEATED_GYM7_LEADER      | Gym-7 cleared. |
| flag | 121 | Gym 8 end            | FLAG_DEFEATED_GYM8_LEADER      | Gym-8 cleared. Distinct from var[121] "Gym 8 Progress". |
| var  | 1   | Temp Pokemon Choice  | VAR_TEMP_POKEMON_CHOICE        | Scratch var for a Pokémon selection prompt. |
| var  | 23  | CHAMPIONSHIP LIST    | VAR_TANDOR_CHAMPIONSHIP_LIST   | Tandor Championship 4-trainer bracket (random 2+2). |
| var  | 24  | CHAMPIONSHIP PROGRESS| VAR_TANDOR_CHAMPIONSHIP_ROUND  | Current championship round (1–4). |
| var  | 87  | White Tiles          | VAR_GYM8_WHITE_TILES           | Live white-tile counter for the 8th-gym puzzle HUD. |
| var  | 121 | Gym 8 Progress       | VAR_GYM8_PROGRESS              | Gym-8 quest-state sentinel. |

<!-- PRESEED-TABLE-END -->
