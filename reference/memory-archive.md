# MEMORY.md Archive

> Append-only graveyard for retired MEMORY.md content: superseded Last Session
> Summary entries and resolved Open Questions. **Not auto-read** — MEMORY.md and
> CLAUDE.md do not point here for routine work. Consult only when you need the
> provenance of a past decision and git blame is too coarse. Newest entries on
> top within each section.

---

## Retired Session Summaries

**2026-05-20 (§2.1 species):** Cloned the pokeemerald-expansion fork
(`/home/b/repos/pokeemerald-expansion`, shallow, HEAD `21c24202`; `make modern`
not yet run — needs devkitARM). Added `.env` (gitignored) +
`pipeline.py::_load_dotenv()` so `RPG2GBA_URANIUM_SRC`
(`/home/b/Pokemon_Uranium_132/_unpacked`) and `RPG2GBA_POKEEMERALD` resolve
without shell exports; `.env.example` committed. Did P4 (struct verification →
`reference/pokeemerald_struct_shapes.md`). **Completed §2.1 species C-emit:** new
`_naming.py` (shared name→constant rule + fork-enum loader), rewrote evolution
parser (0x3F mask + 0xC0 forward-only filter), and `pokemon.py::run()` emits
`species.h`, `species_info.h` (designated initializers, inline evolutions),
`level_up_learnsets.h`, `egg_moves.h`, `intermediate/tandor_dex.json`. Output
validated (Orchynx Grass/Steel→Metalynx@28, Urayne Nuclear/genderless),
idempotent (`diff -r` clean), needs_engine = 27 moves/17 abilities/7 items/166
species. **37 tests pass** (5 new §2.1). Found the `messages.dat` sidecar mojibake
bug (fixed in §2.2). Pickup: §2.2 moves (`moves.py`). Added working-pref memory:
don't `cd` to the current dir in Bash calls. Allowlist expanded in
`.claude/settings.local.json`.

**2026-05-18 (afternoon):** Wrote PHASE2_PLAN.md (also copied to
`/home/b/.claude/plans/`). Implemented Phase 2 §2.0 scaffolding: `_binary.py`
(DatReader + parse_indexed + Essentials varint string decoder), `_id_map.py`
(single-source-of-truth for SPECIES_*/MOVE_*/etc., fail-loud on conflict),
`_c_emit.py` (escape/banner/header-guard helpers), extended `deserialize.rb` with
`dat <in> <out>` mode (Marshal-format `.dat` → JSON), wired `pipeline.py phase2
--clean` with lazy converter discovery, and `scripts/dump_messages.rb` to extract
the `messages.dat` strings to 22 sidecars under `reference/`. **27/27 unit tests
passing.** Found species 201 = "Gengar" via the names dump. Pickup point:
implement §2.1 (`pbs_converter/pokemon.py`) — parse `dexdata.dat` (76-byte flat
records) + aux files (`attacksRS.dat`, `evolutions.dat`, `eggEmerald.dat`,
`tutor.dat`, `regionals.dat`, `metrics.dat`) and emit C. The fork is **not** set
up yet — V6 (fork drop-in build) deferred until it is.

**2026-05-18 (morning):** Closed Phase 0 and ran the `.dat` deserialization
spike. Confirmed: species data in `dexdata.dat` (76 bytes/species, 201 species);
level-up learnsets in `attacksRS.dat`; `tmpbs.dat` = Uranium-custom extra move
list; Shadow Pokémon STRIP confirmed (0 TPSHADOW hits, `shadowmoves.dat` empty);
Tandor dex = 200 entries; two distinct binary formats (custom Essentials binary
vs Ruby Marshal). Updated `uranium_dat_inventory.md` throughout. Spike script at
`scripts/spike_dat_inventory.rb`. Phase 2 is now unblocked.

**2026-05-12:** Phase 0 verification pass. Walked the user through the seven
Phase-0 deliverables. Then attempted the four quick-win + two medium verification
items from Open Questions via three parallel Opus sub-agents. First-round agents
reported several files as "0 bytes / empty stubs" — investigation revealed a
**dumper encoding bug** in `recon_scripts.rb`: 85 of 260 sections had failed to
write because `File.write(out, source, encoding: 'utf-8')` raised on Windows-1252
bytes. Fixed by transcoding `Windows-1252 → UTF-8` and using `File.binwrite`;
re-ran the dumper (all 260 sections now valid; 40 genuinely empty). Re-spawned the
three Opus agents against the corrected dump. Applied verified updates to
`uranium_custom_features.md` (expanded Nuclear-move list to 9 codenames, corrected
Multiple Fogs #232→#223, rewrote Tandor Championship entry + downgraded
CONVERT→ADAPT, added Custom Mode and Gym 8 puzzle sections, updated Summary
Decision Matrix), `phase0_summary.md`, `uranium_dat_inventory.md`. Populated Flag
Registry Notes with 4 pre-seed candidates from gym-8 and championship scripts.

**2026-05-09:** Did Phase 0 reconnaissance. Wrote `scripts/extract_rgssad.py`,
extracted `Uranium.rgssad` to `~/Pokemon_Uranium_132/_unpacked/`, fixed two
pre-existing bugs in `recon_maps.rb` (RPG class nesting, `_load` vs
`marshal_load`) and one in `recon_scripts.rb` (allowlist normalization). Ran 4/5
recon scripts (skipped `recon_pbs.py` — no PBS source). Spawned a Haiku agent to
produce `reference/uranium_essentials_version.md`, `uranium_dat_inventory.md`,
`uranium_custom_features.md`, `phase0_summary.md`; rewrote the dat inventory after
spotting hallucinations (claimed `pokemon.dat`/`abilities.dat` that don't exist).
Updated ROADMAP.md (removed wrong "team open-sourced it" claim, restructured Phase
2 around `.dat` inputs instead of PBS text).

---

## Resolved Open Questions (breadcrumbs)

Conclusions that still matter live in MEMORY.md's Decisions Made or
Uranium-Specific Discoveries; these lines are kept only for provenance.

- **messages.dat sidecars double-encoded (mojibake).** Resolved 2026-05-20. Root
  cause: `messages.dat` strings are raw **UTF-8 bytes tagged ASCII-8BIT**
  (`Pok\xC3\xA9mon`, `SWIMMER\xE2\x99\x80`=♀); the old `dump_messages.rb` ran
  `force_encoding('windows-1252').encode('utf-8')`, reinterpreting those UTF-8
  bytes as Latin-1 → `Ã©`. Fix: `force_encoding('UTF-8')`, fall back to
  windows-1252 only if `!valid_encoding?`. Regenerated all 22 sidecars; §2.1
  golden fixture re-pinned to corrected `Pok\xE9mon`. (Encoding fact promoted to
  Discoveries; the still-live GBA-charmap downstream concern remains an Open
  Question.)
- **Identity of species ID 201** — had no Tandor dex number in `regionals.dat`.
  Resolved 2026-05-18: "Gengar" — placeholder/Easter-egg slot. (See Discoveries.)
- **Which `.dat` holds the species table?** Resolved 2026-05-18: `dexdata.dat`.
- **Exact Tandor dex size.** Resolved 2026-05-18: 200 entries (regionals.dat),
  201 internal species IDs.
- **Confirm no TPSHADOW=true rows.** Resolved 2026-05-18: 0 hits in 331 trainers.
  STRIP confirmed.
- **tmpbs.dat unknown.** Resolved 2026-05-18: Uranium-custom TMPBS extra move list
  per species.
- **Re-examine previously-undumped sections for description accuracy.** Resolved
  2026-05-15 (followed from the recon_scripts.rb Windows-1252 dumper-bug fix).
