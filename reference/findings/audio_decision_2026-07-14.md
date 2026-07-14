# Audio Architecture Decision Sketch — 2026-07-14

**Question (SLICE1_TODO #7 / FABLE_PLAN step 4):** everything audio is a
`# audio` comment today and every map gets `MUS_LITTLEROOT`
(`metadata_wiring.DEFAULT_MUSIC`). What's the architecture for Uranium audio
on GBA, what's the slice-1 bar, and what's the corpus plan?

**Recommendation in one line:** a deterministic **substitution table**
(`reference/audio_map.json`, new SoT) mapping Uranium audio names →
stock `MUS_*`/`SE_*` constants, consumed by metadata_wiring (per-map BGM) and
the transpiler (event audio commands); conversion and streaming are rejected
by arithmetic; sequencing signature tracks is a Phase-8 polish lane that plugs
into the same table.

## Supply side (measured)

- Uranium ships **187 MB of BGM** (84 files: 79 `.ogg`, **only 3 `.mid`**),
  3.3 MB BGS (12), 7.4 MB ME (24), 41 MB SE (593 files, mixed ogg/wav/mp3).
- The fork ships a sequenced m4a/MP2K engine with **212 `MUS_*`** and
  **269 `SE_*`** constants (Emerald + FRLG `MUS_RG_*` vocabulary), native
  fanfare handling, and per-map `music` in map.json. No audio streaming
  support exists in the engine.

## Demand side (corpus census, Phase-3 JSON)

- **Map BGM:** 167 of 199 maps autoplay a BGM; **45 distinct tracks**. Heavy
  reuse: the top interior themes cover dozens of maps each (e.g. the
  starter-house theme plays on 19 maps, the Pokémon-Center theme on 14, the
  mart theme on 12).
- **Event commands:** PlaySE ×1 384, PlayME ×116, PlayBGM ×114 (36 distinct
  — mostly encounter/scene stingers), FadeBGM ×33, PlayBGS ×8, FadeBGS ×4.
  Union of map + command BGM ≈ **65 distinct tracks needing a mapping row**.
- **ME (jingles): 11 distinct**, and they're almost all the standard set with
  exact native equivalents: healing ×56 (`MUS_HEAL`), key item / regular item
  (`MUS_OBTAIN_ITEM`-family), TM/HM (`MUS_OBTAIN_TMHM`), egg
  (`MUS_OBTAIN_ITEM`/`MUS_EVOLVED`-class call), badge (`MUS_OBTAIN_BADGE`).
- **SE: 135 distinct names, but usage is head-heavy** — doors (Exit/Entering
  Door ×396), battle-damage ticks, throw, switch beeps, save. The top ~15
  names cover the large majority of the 1 384 uses and all have obvious
  `SE_*` analogs (`SE_DOOR`, `SE_SELECT`, `SE_SAVE`, `SE_BALL_THROW`, …).
- **Cries:** `pbPlayCry` ×26 plus cry-style SE files — these should NOT go
  through the SE table; they map to the engine's native cry system once
  Uranium species data lands (Phase 7). Until then they stay queued/commented.
- **BGS (ambient loops):** marginal — 5 map autoplays + 8 commands. Vanilla
  has no BGS concept; nearest analogs are looping SEs. Default disposition:
  SKIP, with per-case table overrides if one ever matters.

## Options

**A. Substitution table (RECOMMENDED v1).** Hand-authored
`reference/audio_map.json` with `bgm` / `me` / `se` sections plus explicit
`SKIP` entries (§4.3 SoT discipline — nothing else mints audio names). ~65 BGM
rows + ~11 ME + ~20 SE rows covers effectively all usage; grows per slice
(data changes, not code — the slice guardrail). Deterministic, zero ROM cost,
zero engine work. Cost: the ROM sounds like Hoenn/Kanto, not Uranium.

**B. Convert the actual music — REJECTED for v1 by arithmetic.** The engine
plays sequences, not audio files; only 3 of 84 BGM have MIDI sources, so
"convert" means hand-sequencing ~60 tracks — a music-production project, not
a converter feature.

**C. Stream the OGGs — REJECTED.** GBA streaming ≈ 0.5–0.8 MB/min at
tolerable quality; the soundtrack is 187 MB source, and the scaling audit
(`corpus_scaling_audit_2026-07-14.md`) leaves ~7 MB total ROM headroom before
audio. Even a 10-track subset blows the budget, and the engine would need
custom mixer surgery (a genuinely new C subsystem) for a result that still
sounds worse than sequenced music.

**D. Silence — REJECTED.** Strictly worse than A for playability.

## Recommended architecture (v1)

1. **SoT:** `reference/audio_map.json` — `{"bgm": {uranium_name: "MUS_*" | "SKIP"},
   "me": {...}, "se": {...}}`. Loader validates every target constant against
   the fork index (§4.7 forward gate — no invented `MUS_`/`SE_` symbols).
2. **Per-map BGM:** metadata_wiring reads the map's `bgm.name` through the
   table and replaces the `MUS_LITTLEROOT` hardcode. Unmapped name =
   fail-loud at build for slice maps (the table is small; keep it complete
   for the frontier), not for out-of-slice bulk runs.
3. **Transpiler:** the `# audio` comment path gains a table lookup —
   241 PlayBGM → `playbgm`, 242 FadeBGM → `fadeoutbgm`, 249 PlayME →
   `playfanfare` (+ `waitfanfare` where the RMXP pattern waits), 250 PlaySE →
   `playse`. Mapped → emit; `SKIP` → current comment behavior; *unmapped* →
   comment + drop-report line (audio is cosmetic — don't queue 1 384 entries).
   Volume/pitch parameters are dropped (no per-play equivalent on sequenced
   GBA audio); log when ≠ 100 so fidelity loss is visible.
4. **Cries:** excluded from the table; route to the native cry system with
   species integration (Phase 7).
5. **Battle BGM:** trainer-class battle music is data on the emerald side
   (trainer conversion / map metadata), not event scripts — out of scope
   here; note only that the same table can serve it.

## Slice-1 bar (user call, §10 fidelity)

Recommended: the **minimal table for the 8 slice maps** — 3–4 BGM rows
(town theme, starter-house/interior themes, lab), ~5 SE rows (doors, save,
switch), 1–2 ME rows (healing if the slice's interiors expose it) — wired
through items 1–3 above. That's a ~15-row table and two small consumers, and
it upgrades the slice from "Littleroot theme everywhere + silent doors" to
"coherent stock audio in the right places". The zero-effort alternative
(accept current state) is defensible for the §9 gate since audio isn't named
there — but the table mechanism has to exist eventually, and building it
against 8 maps is the cheap moment.

## Corpus plan + Phase-8 polish lane

- Table grows per slice; mapping guidance: match *function first, mood second*
  (town→town, cave→cave, battle→battle, jingle→same jingle). FRLG's
  `MUS_RG_*` set roughly doubles the vocabulary for variety.
- Phase 8 (optional, pluggable): hand-sequence or commission the handful of
  signature tracks (title, starter town, rival, key battles) as new m4a
  sequences under `MUS_URANIUM_*` constants; each lands as a one-row table
  change. The 3 shipped MIDIs are the free starting point.
- BGS: default SKIP corpus-wide; revisit per-case (e.g. a looping `SE_RAIN`
  analog) only if a walk finds a place where the ambience is load-bearing.
