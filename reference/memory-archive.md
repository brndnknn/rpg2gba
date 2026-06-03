# MEMORY.md Archive

> Append-only graveyard for retired MEMORY.md content: superseded Last Session
> Summary entries and resolved Open Questions. **Not auto-read** — MEMORY.md and
> CLAUDE.md do not point here for routine work. Consult only when you need the
> provenance of a past decision and git blame is too coarse. Newest entries on
> top within each section.

---

## Retired Session Summaries

**2026-05-25 (Phase 4 — conversion-agent MACHINERY, code complete):** Built the whole Phase 4 machinery against `PHASE4_PLAN.md` (scoped machinery-only) in one session. Filled the Phase-1 stubs: `flag_registry.py` (pre-seed/mint/validate/persist/dump_header + `validate` CLI), `orchestrator.py` (per-event loop, injectable `compile_fn`, idempotent checkpoints, unhandled queue + `triage`), `backends/{claude_code,ollama}.py`; added `poryscript.py` (compile-gate) + `prompt_builder.py`. Authored `reference/essentials_to_emerald_map.md`, `reference/poryscript_cheatsheet.md`, 3 `prompts/few_shot/*.md`; reconciled `ConversionResult` to system.md's list schema. Wired `pipeline.py phase4` (dry by default; `--run` gated/spends budget) + `convert-map`. New `tests/test_conversion_agent.py` (22 tests: registry collision/validation/roundtrip, backend parse w/ mocked subprocess, orchestrator retry/queue/idempotence w/ MockBackend+fake compiler, prompt assembly) + `phase4` marker. **Suite 97 pass / 1 skip (compile-gate, poryscript absent), ruff clean.** **Key finding:** the obvious badge names `FLAG_BADGE0N_GET` already exist in the fork — the registry's live fork-collision check caught it; badge→vanilla mapping deferred to §9 (fidelity call). `phase4 --clean` dry path: 8 flags + 5 vars pre-seeded, 34 script-switches blocked, 199 maps pending. **Next:** install poryscript (P2), then the §9 #2 calibration gate (budget-gated — confirm with user).

**2026-05-25 (Phase 3 — Map Deserialization, code complete):** Implemented the whole phase in one session against `PHASE3_PLAN.md`. **§3.0:** built `deserialize.rb`'s `rxdata` branch (folded recon_maps.rb's nested RPG stubs; added `marshal_load_lenient` for the nested-`const_missing` gotcha), explicit container shaping into the Phase 4 raw-command contract. **§3.1–§3.4:** new `src/rpg2gba/map_deserializer/` package (`driver`/`validate`/`command_catalog`), wired `pipeline.py phase3 --clean`. Conservation **exact** (199/5301/8429). Emitted committed `reference/rgss_event_commands.md` (59 codes, 250 script-call signatures) + switch/var sidecars (235/119 named). **Tests:** `tests/test_map_deserializer.py` (9: conservation, schema, no-merge, coverage, 4 golden maps, idempotence) + `phase3` marker; full suite 75 pass, ruff clean. **Key finding:** Uranium adds **no custom command codes** — all custom behaviour is in Script commands (355/655) as `pbXxx` calls; the §3.2 doc inventories these 250 signatures as Phase 4's real translation surface. **Exit gate V1–V3+V6 done;** V4 (user map spot-check) + V5 (review command reference) remain advisory. **Next: Phase 4.**

**2026-05-25 (V5 gate passed + env/toolchain setup; Phase 2 logically complete):** Session via `/phase2-walkthrough`. **Setup:** installed devkitPro/devkitARM 15.2.0 + `libpng-dev`, fork builds clean (`make -j16 modern`); renamed tracked `.env`→`.env-paths` (collided with `Read(**/.env)` deny rule) + pointed `_load_dotenv` at it (commits `6187832`); relocated Uranium tree to sibling `/home/b/repos/uranium-src` + updated `RPG2GBA_URANIUM_SRC` (`31eaf7c`). **Gate:** walked §2.0–§2.10, resolved the 4 P4 fidelity decisions (see Decisions), implemented the 2 needing code (hidden-ability sidecar+needs_engine; species-201 unobtainable sidecar+comment) in `pokemon.py` (+1 gate test, 66 pass, idempotent — commit `6fdff92`); ran the worklist/inventory scan + 4 artifact spot-checks (all clean); added the CONVERTED/STRIP/DEFER status table to `uranium_dat_inventory.md`. **Key finding:** the V6 "isolated compile-check" is architecturally fused with the species-roster swap (constant-name collisions; fork config headers need vanilla constants) → **exit #3/#4 deferred to Phase 7** (see Decisions), no fork changes made. **Pending commit:** `uranium_dat_inventory.md` + `MEMORY.md`. **Next: Phase 3 (Map Deserialization).**

**2026-05-23 (§2.5–§2.10 — Phase 2 converters DONE):** Finished the last six sections. **Step 0 prep** (committed `d8eb688`): added `WordArray._load` to `deserialize.rb` + the shared `_marshal.py` (`dump_dat`/`load_json`); verified all 6 Marshal dats dump clean. **§2.5 tm_hm** + **§2.6 trainers** done on the main session (committed `17b92fc`); **§2.7 encounters, §2.8 metadata, §2.9 tmpbs, §2.10 types** done sequentially on main (the earlier parallel worktree fan-out was killed by a session limit and produced nothing durable except the §2.9 agent's `tmpbs.py`, which leaked into main with a `load_fork_constants("MOVE_")` bug — rewrote it clean). Format corrections vs the plan: tm.dat is **Marshal+WordArray** (not indexed), tutor.dat **empty**; trainers/teachables/encounters are fork **build-generated**, so §2.5/§2.6 emit constants-keyed **intermediate JSON** (V6 generates the generator inputs / `.party`), per the user's "stick to PHASE2_PLAN.md + MEMORY supplements" steer. See per-section Key File Notes. Full `phase2 --clean` ×2 `diff -r` clean (idempotent); **65 phase2 tests pass** (+20 new), ruff clean. §2.5/§2.6 committed; §2.7–§2.10 + doc updates **pending commit**. **Now at the V5 / §9 #1 manual review gate** — STOP, awaiting user review before the fork drop-in (V6, still devkitARM-blocked).

**2026-05-22 (§2.4 abilities):** Completed §2.4 abilities via the `/pbs-convert` skill. `abilities.py` emits the **Uranium-original ability constants** — `PBAbilities` sidecar entries (210) whose `to_constant` is absent from the fork enum, a clean contiguous block **ids 192–210 (19 originals)**. Key call: the plan assumed a dexdata in-use scan, but that misses **form-only abilities** (CHERNOBYL=209 URAYNE form 2, NIGHT_TERROR=210); switched to the sidecar-vs-fork definition, kept `collect_ability_ids` as a fail-loud cross-check. Emits `include/constants/abilities.h` (originals only), a placeholder TU `src/data/abilities/uranium_abilities.c` (no literal stubs — fork effects are inline in battle scripts), and `intermediate/ability_codes.json`. §2.1 marked 17 needs_engine; §2.4 → 19 (idempotent union). Idempotent; **45 tests pass** (4 new §2.4), ruff clean.

**2026-05-21 (§2.3 items):** Completed §2.3 items. `items.dat` turned out to be Essentials `writeSerialRecords` TLV format (not the simple fput indexed binary the plan assumed) — corrected the schema in PHASE2_PLAN.md. `items.py` parses 607 items and emits `gItemsInfo[]` (`src/data/items.h`), `ITEM_*` defines (`include/constants/items.h`), and the `intermediate/item_field_codes.json` Phase 6 worklist. Mapped only deterministic fields (name/price/desc/pocket/importance); **deferred all item behavior to Phase 6** (mirrors §2.2/D3). 111 needs_engine. Hit two shared-code fixes: (1) `dump_constants.rb` all-caps regex dropped `POKeBALL=211` and ~70 mixed-case trainer classes — loosened regex, regenerated sidecars (trainer_class sidecar 60→130 entries, **matters for §2.6**); (2) added diacritic folding to `_naming.to_constant` so "Poké Ball"→ITEM_POKE_BALL. Verified idempotent (`diff -r` clean across two runs). **41 tests pass** (5 new §2.3), ruff clean. Pickup: §2.4 abilities.

**2026-05-20 (§2.2 moves):** Fixed the `messages.dat` mojibake in `dump_messages.rb` (UTF-8 bytes were being mis-transcoded as windows-1252) and regenerated all 22 sidecars; re-pinned the §2.1 golden fixture to the corrected `Pok\xE9mon`. **Completed §2.2 moves:** `moves.py` parses flat 14-byte `moves.dat` (637 nonzero of 639) and emits `gMovesInfo[]`, `moves.h` (`MOVE_*` defines), and the `move_function_codes.json` Phase 6 worklist. Mapped target (PBTargets→TARGET_*), category, type, and positive flags faithfully; **deferred all move effects to Phase 6** via `EFFECT_PLACEHOLDER` + worklist (see Decisions) — 324 function codes have no clean map. 9 Nuclear moves flagged needs_engine (32 moves total). Output idempotent (`diff -r` clean across two full `phase2 --clean` runs); id_map now 201 species / 637 moves / 19 types. **9 phase2 tests pass** (4 new §2.2: roundtrip, golden Tackle+Atomic Punch, effect-placeholder/worklist, Nuclear needs_engine), ruff clean. New working-pref memory: prefer temp script files over inline multi-line shell. Pickup: §2.3 items. **Phase 2 manual review gate (§9 #1) still NOT reached — it's at the END of Phase 2.** Not yet committed this session.

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
