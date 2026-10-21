# Walk quality-of-life upgrades

Branch `walk-quality-of-life-upgrades`, opened 2026-10-21 from `main` after I3
closed. Serves intermission items I1 (a usable walk party) and I6 (keep playing
your own game), in the narrow form decided below. Decisions come from an
operator grill session on 2026-10-21.

## 1. Decisions

**A. Your save wins on the same ROM.**
- `playtest walk` stamps a random ROM id into each walk ROM. An in-game save
  records the id.
- On boot, a valid `.sav` whose id matches this ROM loads. Otherwise (no save,
  another build's save, another walk ROM's save) the stamped seed loads, as
  today. This keeps the 2026-08-01 protection against a stale `.sav`.
- Across rebuilds the seed still wins; carrying a save across builds is the
  rest of I6 and is out of scope here.

**B. Pokémon granted into the seed.**
- Species: everything catchable in every map the suite's beats entered before
  the seed point, CH01 onward. Catchable means every wild encounter table in
  the map (grass, cave, surf, rods, rock smash; gated methods included) plus
  story gift and static Pokémon. Trainers' species are not included.
- Form: exactly the species found; no pre-evolving, no other forms.
- Level: the highest level in the seed's party. Moves: the engine's normal
  level-up learnset at that level.
- Destination: the party fills to 6, the rest go to the PC. Species already in
  the seed's party or PC are skipped.
- Pokédex: normal give behaviour (caught). Suites never see grants, and
  dex-count events are tested by their own beats.
- Mechanism: the seed carries a species/level list; the engine creates the
  Pokémon on boot with its own give routines (no Pokémon records built in
  Python).
- On by default for walk ROMs; `--no-grant` turns it off. Suite runs and the
  green review ROM never get it.

**C. Party-wide EXP Share.**
- `I_EXP_SHARE_FLAG` names a harness flag. The walk stamper sets it in the
  seed, in the same step as the grant, so it stays on for that playthrough.
- On by default for walk ROMs; `--no-exp-share` turns it off. Suite runs are
  unchanged.

## 2. Done means

- CH08 498/498 from boot; full pytest green.
- A CH06-end walk ROM that boots with the granted Pokémon and EXP Share on, and
  that reloads an in-game save after a power cycle (and ignores a foreign
  `.sav`).
- Operator walk.

## 3. Progress

- **BUILT 2026-10-21; awaiting operator walk.**
  - Engine (`RPG2GBA HARNESS`):
    - `struct Rpg2gbaWalkExtras` sits at the end of the embedded save
      (`include/rpg2gba_embedded_save.h`).
    - In `Rpg2gbaEmbeddedSave_TryLoad`, a flash save holding this ROM's id
      wins. A blob boot copies the id into SaveBlock2 `filler_90`, sets
      `FLAG_RPG2GBA_EXP_SHARE` (stock `FLAG_UNUSED_0x020`, wired to
      `I_EXP_SHARE_FLAG`), and gives unowned species through `ScriptGiveMon`
      at the party's top level.
  - Python: `playtest/walk_extras.py` (map scope, species, encoding, ROM patch,
    verification). `playtest walk` gained `--grant/--no-grant` and
    `--exp-share/--no-exp-share`. The engine audit declares the EXP Share write
    as harness-only.
  - Verification runs on every walk build:
    - a foreign `.sav` still loses to the blob;
    - the EXP Share flag matches what was asked for;
    - money written before an in-game save survives a reboot of the same ROM.
  - CH06-end ROM `output/playtest-gen/walk/QOL-CH06-end.gba`:
    - 17 catchable species (wild tables plus the starter-scene gifts), with
      the seed's Raptorch skipped;
    - party: Raptorch plus 5 granted; PC box 1 holds the other 11;
    - EXP Share on.
  - The teach-HM tests' fixture ROM is now built with `--no-grant
    --no-exp-share`.
  - Results: CH08 498/498 from boot; pytest 5639 passed.
