# Nuclear Type — Phase 6 Implementation Spec (2026-07-14)

Implementation-ready spec for ROADMAP Phase 6 (§6.1–§6.5), written so a
builder agent can execute it without re-deriving the research. Every engine
claim below was verified against the vendored fork (`engine/`, upstream
`21c24202`) and every Uranium claim against real game data
(`reference/uranium_data/types_dump.json`, `reference/scripts_dump/`).
Follow `reference/guides/engine_extension_surface.md` for how each engine
divergence lands (gen hook > config gate > sentinel fence).

## 0. A correction to ROADMAP §6.4 — there is no out-of-battle HP drain

ROADMAP 6.4 ("Nuclear Pokémon lose HP each step until cured") and the recon
doc's "1/8 HP per turn outside battle" are **wrong**; the recon itself flagged
the mechanic as never-located. Verified against the scripts dump:

- The only out-of-battle HP drain in Uranium is **plain poison** field damage
  (`101__PField_Field.rb:1539-1573`: 1 HP per 4 steps, `POISONINFIELD=true`,
  survive-at-1HP), identical in kind to vanilla Emerald's native behavior.
  Nothing Nuclear-specific.
- The real ownership mechanic for un-cured Nuclear Pokémon is **50 %
  disobedience in battle** (`083__PokeBattle_Battler.rb:2712-2715`:
  `isNuclear? && !nuclearFree → disobedient |= pbRandom(10) < 5`), fed into
  the standard Essentials disobedience consequences (ignore / random move /
  nap / confusion-hit).
- The cure is the **EXPUNGE field move** (`103__PField_HiddenMoves.rb:1390-
  1400`): party-menu use → choose an un-cured Nuclear mon → set its
  `nuclearFree=true`. The mon keeps its Nuclear typing; only obedience
  changes. (The separate "cleaning" chooser: `225_Nuclear_Cleaning.rb`.)

§6.4 below is therefore a *disobedience* feature, not a field-damage feature.
ROADMAP 6.4 has been corrected to match.

## 1. Sources of truth

| fact | SoT |
|---|---|
| Type chart matrix | `reference/uranium_data/types_dump.json` (dumped from `types.dat`, §2.10) |
| Uranium type index → name | same file, `types` array (20 types; NUCLEAR=18, FAIRY=19, QMARKS=9) |
| Nuclear-ness predicate | `scripts_dump/122__PokeBattle_Pokemon.rb:375` |
| Disobedience roll | `scripts_dump/083__PokeBattle_Battler.rb:2711-2715` |
| Cure flow | `scripts_dump/103__PField_HiddenMoves.rb:1390`, `225_Nuclear_Cleaning.rb` |
| Nuclear move / ability codenames | `scripts_dump/217_Nuclear_Forms_Moves.rb` (recon doc lists them) |
| Nuclear form data | species/`regionals.dat` form ids (recon "Nuclear Form Transitions") |

## 2. §6.1 — the type constant

`engine/include/constants/pokemon.h`: fork enum runs `TYPE_NONE=0` …
`TYPE_FAIRY=19`, `TYPE_STELLAR=20`, `NUMBER_OF_MON_TYPES` — add
**`TYPE_NUCLEAR = 21`** before `NUMBER_OF_MON_TYPES` (sentinel-fenced; this
is a baseline-behavior change class → §10 ask already covered by the Phase 6
CONVERT decision). Both `gTypeEffectivenessTable` and `gTypesInfo` are
dimensioned `[NUMBER_OF_MON_TYPES]`, so they extend automatically once rows
are added.

**Index remap is mandatory:** Uranium's type indices differ from the fork's
(Uranium: NUCLEAR=18, FAIRY=19, QMARKS=9 ↔ fork: TYPE_MYSTERY=10,
TYPE_FAIRY=19, TYPE_STELLAR=20, TYPE_NUCLEAR=21; every index ≥10 shifts).
Emit a single deterministic `URANIUM_TYPE_INDEX → TYPE_*` table in the
converter (extend `types_dump.py` or a small new module) and use it wherever
Phase-2 data carries a type index (species types, move types). QMARKS (a
pseudotype, `pseudotypes=[9]`) maps to `TYPE_MYSTERY`.

## 3. §6.2 — the effectiveness chart

From the verified matrix (`types_dump.json`, values 0/1/2/4 = immune / ½× /
1× / 2×):

- **Nuclear attacking:** 2× against *everything* except STEEL ½×, NUCLEAR ½×,
  QMARKS/MYSTERY 1×. (Yes, including Fairy, Dragon, Ghost — no immunities.)
- **Nuclear defending:** takes 2× from *every* attacking type except NUCLEAR
  ½× and QMARKS/MYSTERY 1×. (Steel attacks hit Nuclear 2× like everything
  else — the resistance is one-directional.)

Implementation: one new row + one new column in
`engine/src/data/types_info.h::gTypeEffectivenessTable` (UQ_4_12 macros,
`X(2.0)`/`X(0.5)` — same idiom as existing rows). `TYPE_STELLAR` and
`TYPE_NONE` interactions: 1× both ways (Uranium has no equivalent; Stellar is
tera-only). Add a golden test in the Python side: re-parse the emitted (or
hand-written) C row/column and diff against `types_dump.json` — the §4.6
round-trip discipline applied to a hand-authored table.

## 4. §6.3 — gTypesInfo entry + icon art

Add a `[TYPE_NUCLEAR]` entry to `gTypesInfo` mirroring the existing entry
shape (`engine/src/data/types_info.h:468` area): name "Nuclear", `generic`
text, damage category palette, `isHiddenPowerType = FALSE` (**required** —
setting it TRUE redistributes all Hidden Power types, per the header's own
note), tera RGB, move-type icon references. The file's trailing comment block
documents exactly which per-type data a new type needs — follow it.

Icon art: Uranium ships a Nuclear type icon in its UI graphics (green/black);
convert or redraw at the fork's type-icon tile size and add to the type icon
sheet(s) referenced by the `gTypesInfo` entry. This is the only new art in
Phase 6 and it's tiny; do it with the entry, not deferred (§9 art-included
rule).

## 5. §6.4 (corrected) — disobedience + the nuclearFree bit

Three pieces, all small:

1. **Predicate.** `IsNuclearMon(mon)`: species' `types[1] == TYPE_NUCLEAR &&
   types[0] != types[1] && species != SPECIES_GEIGEROACH` (the Ruby source's
   exact rule — Geigeroach is natively/stably Nuclear and always obeys; on
   GBA, types come from `gSpeciesInfo` so nuclear *forms* satisfy this via
   their own species/form entries).
2. **Save bit.** `nuclearFree` needs one persistent bit per Boxable mon.
   Builder task: claim one spare bit in `struct BoxPokemon` (the expansion
   keeps explicit spare/padding bits — locate with a grep for `padding` /
   unused bitfields in `include/pokemon.h` and extend, STATIC_ASSERT size
   unchanged; this is save-format-affecting, so it must land before any
   long-lived test saves). Default 0 = not cured.
3. **Obedience hook.** The fork's obedience logic lives in one function
   (grep `GetBattlerObedience` / obedience handling in `src/battle_util.c`).
   Sentinel-fenced addition: if `IsNuclearMon && !nuclearFree`, 50 % chance
   (`Random() % 10 < 5`) to force the disobedient path, composed with (not
   replacing) the badge-based check. Reuse the existing disobedience
   consequence machinery wholesale — Uranium's is a straight port of it.

**Cure (EXPUNGE):** a field-effect move usable from the party menu that picks
an un-cured Nuclear party member and sets the bit. Slice-wise this is far
away (EXPUNGE is mid-game); spec it as: new move constant (already flagged
`needs_engine` by moves.py), party-menu field move handler modeled on the
existing non-HM field moves, message + bit set. If a story event also cures
(script 225's chooser), that arrives via the transpiler/hand bucket calling a
new special — one `def_special` + registry entry, gated by §4.7.

Optional polish (defer): summary-screen "corrupted" marker
(`205_BW_Summary.rb:570` shows Uranium displayed one).

## 6. §6.5 — nuclear forms

Uranium's nuclear variants are form ids on the species (recon: "Nuclear Form
Transitions", data in species/`regionals.dat`). Recon's recommendation stands:
model as the expansion's existing form-change/evolution machinery — no new C.
Phase-2 species conversion already carries form data; the Phase-6 work is
only wiring form entries whose `types[1]` is TYPE_NUCLEAR. The anti-cheat
`pbRemoveNuclearActan` guard (recon §pbRemoveActan) is event-conversion
scope, not engine scope — its "give fallback mon if party empty" behavior
must be preserved when that event converts.

## 7. Related but explicitly out of Phase-6 scope

- **The 9 custom Nuclear moves** (`GAMMARAY` … `METALCRUNCHER`) — already
  minted + flagged `needs_engine` by `moves.py`; their *effects* are mostly
  standard effect constants. They land with Phase-7 ID reconciliation
  (`phase7_integration_plan.md`), only their `type` field needs TYPE_NUCLEAR.
- **Custom abilities** LEADSKIN ("Radiation Proof": Nuclear-type moves miss
  the holder — `083__PokeBattle_Battler.rb:2899`) and CHERNOBYL (Urayne's
  form-2 ability, script 217) — implement with the ability batch (Phase-2
  §2.4 marked them for Phase 6/7); LEADSKIN is a one-condition accuracy hook.
- **Nuclear horde battles** (script 224) — a separate battle-format feature;
  needs its own Convert/Adapt/Strip decision (§10 ask) when its maps reach
  the frontier. Nothing in this spec depends on it.
- **Wild-area Repel ban on nuclear maps** (`221_Extra_Scripts.rb:424`) —
  event/metadata scope.

## 8. Suggested build order + tests

1. Enum + chart row/column + gTypesInfo entry + icon → `make modern` clean;
   golden test matrix-vs-dump; boot a battle with a hacked Nuclear-typed mon
   (harness pattern: `engine/src/new_game.c` rig, SLICE1_TODO #5 Done — it's
   the standing test rig, extend it) and verify 2×/½× messages both
   directions.
2. BoxPokemon bit + predicate + obedience hook → harness-grant an un-cured
   Nuclear mon, observe ~50 % disobedience; set the bit via debug, observe
   obedience.
3. EXPUNGE field move + cure special (when a slice needs it).
4. Forms wiring (with Phase-7 species reconciliation).

Exit criteria = ROADMAP Phase 6's, with 6.4's rewritten to: "an un-cured
Nuclear-type Pokémon disobeys ~50 % of the time; curing restores obedience;
the state survives save/load."
