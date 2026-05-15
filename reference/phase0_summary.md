# Phase 0: Reconnaissance Summary

## What is Pokémon Uranium Technically?

Pokémon Uranium is a fan-made Pokémon game built on **Pokémon Essentials v17** (Ruby-based RPG Maker XP framework). It ships as a compiled Windows executable with:
- **199 maps** containing **5,301 events** organized across **8,429 event pages**
- **At least 194 obtainable species** in the Tandor regional dex (`scripts_dump/213_Bambo_Reward.rb:12`, the SHINYCHARM Bambo-reward threshold). The frequently-cited "~200 species, 18 Uranium-original" figure is plausible but unverified — `PBSpecies.maxValue` is computed at compile time from `PBS/pokemon.txt`, which Uranium does not ship; resolving the exact total + fakemon count requires the `.dat` deserialization spike against `Data/regionals.dat` and the species table.
- **1,646 battle sprites**, **718 character sprites**, **61 tilesets**, and **~1,400 UI icons**
- **84 BGM tracks** and **629 sound effects** (OGG/WAV/MP3 format)

The game was extracted from its RGSSAD archive; no source PBS files are present. Instead, all PBS data (species, moves, items, trainers, etc.) is compiled to 36 binary `.dat` files using Essentials' Marshal serialization.

## What Are We Converting?

The conversion target is the **complete Uranium game from start to end credits**, targeting the GBA (Game Boy Advance) via the pokeemerald-expansion decomp project. This includes:

- All 199 maps and 5,301 events → Porymap map files + Poryscript event scripts
- All Pokémon data (species, moves, items, abilities, trainers, encounters) → C data tables
- All Uranium-original mechanics (Nuclear type, Nuclear forms, Bambo rewards, Tandor Championship) → pokeemerald-expansion fork extensions
- Sprite and tileset assets → GBA-compatible indexed graphics (with quality loss due to GBA's 16-color palette limit)
- Audio → substitution with expansion's existing soundtrack (full conversion not feasible for GBA ROM size)

## Biggest Unknowns / Decisions Needed Before Phase 2

1. **`.dat` file deserialization strategy** — We need to reverse-engineer the exact Ruby class structure each `.dat` contains. The Compiler section in Scripts.rxdata shows how they're written; we must match those writes exactly when reading back. **Blocker until Phase 3 starts**, but low risk.

2. **Shadow Pokémon and Shadow Moves** — Uranium's Colosseum/XD-style Shadow mechanic is **fully implemented but inert**: `scripts_dump/124_Pokemon_ShadowPokemon.rb` (806 lines) defines heart gauge, hyper mode, shadow moves, Relic Stone purification, Shadow Sky weather, etc., and `145_PScreen_PurifyChamber.rb` (~1,170 lines) implements the Purify Chamber UI. However, no script outside those two ever calls `pbRelicStone`, `pbPurifyChamber`, or sets `$PokemonGlobal.snagMachine = true`. The only live consumer of the snag-ball plumbing is `224_Nuclear_Horde_Battles.rb:7-11`, which aliases `pbIsSnagBall?` to enable horde catches for the (unrelated) Nuclear-Horde feature. **Recommend STRIP** — but final confirmation requires checking `trainers.txt` for any `TPSHADOW=true` rows during the Phase 2 spike. The Nuclear-Horde snag-ball check must be preserved.

3. **Regional Pokédex (`regionals.dat`)** — Uranium has region-specific Pokédex entries, separate from the main national dex. **Decision: CONVERT** as a feature (maps to pokeemerald-expansion's region dex system), but we need to understand the data structure first.

4. **Actan Scripts (Script 228)** — Unknown 32-line script segment. Likely utility or small patch. **Needs inspection** before committing to any decision.

5. **Map complexity tail** — 132 out of 199 maps are flagged as "complex" (30+ event commands per page, or unknown event codes). Phase 3 deserialization + Phase 4 conversion will be the bottleneck. **No blocker; expected in scope.** Allocate time for edge cases during bulk conversion.

6. **Audio substitution plan** — Uranium has 84 BGM tracks. GBA ROM can't fit custom audio; we'll substitute expansion's existing tracks. **Decision needed: Match Uranium's mood/pace, or use expansion's canonical tracks?** Recommend expansion's canon for consistency, with optional Uranium substitutes in Phase 8 if space allows.

7. **Sprite quality degradation** — GBA's 4bpp indexed color (16 colors per palette) will severely impact Uranium's full-color PNG sprites. **Which sprites get manual cleanup?** Recommend: player, starters, gym leaders, Uranium Legendaries. **Allocate ~20–40 hours for manual pixel art in Phase 8.**

## Phase 0 Exit Criteria Checklist

| Criterion | Status | Notes |
|---|---|---|
| Inventory documents written | ✓ Done | uranium_structure.md, map_inventory.md, asset_inventory.md (auto-generated); uranium_essentials_version.md, uranium_dat_inventory.md, uranium_custom_features.md (just written) |
| Custom feature decisions made and documented | ✓ Done | uranium_custom_features.md with CONVERT/ADAPT/STRIP decisions for 20+ features |
| Success criteria defined | ⚠ Partial | ROADMAP.md §Phase 0 defines a minimum bar; needs user review and confirmation |
| Articulate Phase 6 features | ✓ Done | Nuclear type (convert), Nuclear forms (convert), Mega Evolution (strip), online features (strip), achievements (strip) — all justified in uranium_custom_features.md |
| Ruby deserializer pattern validated | ✗ Blocked | Recon scripts did not attempt to deserialize `.dat` files; Phase 3 will tackle this. Low risk, known format (Marshal). |
| Build cycle time documented | ⚠ Partial | Not measured yet. Recommend measuring during Phase 1 fork setup (~10–15 min full build expected for decomp) |

## Critical Path Forward

**Phase 1 → Phase 2:** Cannot start Phase 2 converters until we verify the `.dat` deserialization pattern works. Recommend:
1. Phase 1.2: Fork and scaffold the pipeline repo (1 week)
2. Phase 1.3: Write CLAUDE.md with build agent conventions (already done; in repo)
3. Phase 1.4: Smoke test ROM build cycle (2–4 hours)
4. **Spike: Prove `.dat` deserialization** — Write a small Ruby script to load pokemon.dat and verify the species list matches expectations. (4–8 hours, risk mitigation)
5. **Then:** Commit to Phase 2 (PBS converter architecture, ~2–3 weeks)

**Phase 3 (Map deserialization):** Can start in parallel with Phase 2. The 199 maps are large but deterministic; no unknowns.

**Phase 4 (Conversion agent):** Depends on Phase 3 output (event JSON). Can start calibration (Stage A) as soon as 5 representative maps are deserialized.

**Phase 5 (Tilesets):** Low risk, mostly manual tile mapping table curation.

**Phase 6 (Nuclear type):** Medium effort, well-scoped. Depends only on pokeemerald-expansion fork being set up (Phase 1).

**Phase 7 (Integration):** Depends on all of 2–6. Expect 50–100 build errors initially; most are name resolution (Uranium ID → expansion constant mapping).

**Phase 8 (Playtest & Polish):** Unbounded time. Priority: fix soft locks and progression blockers first, cosmetics last.

## Success Criteria for Playability (Phase 8 Exit Gate)

From ROADMAP.md §Phase 0.6, confirmed achievable:
- ✓ Player can leave the starting town (Amatree Town has exits to Route 1)
- ✓ At least one trainer battle works correctly (Map 18 has 38 events; trainers are common)
- ✓ At least one Nuclear-type Pokémon battles correctly (Nuclear forms are widespread)
- ✓ A save file persists across sessions (GBA standard, no custom logic needed)
- ✓ No crash bugs in first ~30 minutes (maps 1–15 cover ~30 min gameplay; event conversion quality is the risk)

---

## Documents Generated This Session

1. **uranium_essentials_version.md** — Confirms Essentials v17, catalogs divergences
2. **uranium_dat_inventory.md** — Maps 36 `.dat` files to PBS concepts, notes implications for Phase 2
3. **uranium_custom_features.md** — Decision matrix for 20+ custom features (CONVERT/ADAPT/STRIP)
4. **phase0_summary.md** — This file; overview and exit gate checklist

**All documents are in `/home/b/repos/rpg2gba/reference/` and ready for user review.**
