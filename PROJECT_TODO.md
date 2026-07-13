# Project TODO — cross-cutting, post-slice loose ends

Working checklist for things that are **not** phase-plan items (→ `ROADMAP.md`)
and **not** scoped to the pathfinder slice (→ `SLICE1_TODO.md`), but keep
getting deferred across sessions and need a home so they don't get lost.
Commit updates as items close; move to **Done** with a one-line result rather
than deleting. Facts here are pointers — the cited code/docs stay authoritative.

## Open

### 1. Delete the old external pokeemerald-expansion clone

`engine/` is the vendored, in-repo copy now (cutover done 2026-06-19). The old
external clone at `/home/b/repos/pokeemerald-expansion` is stale and
superseded but was never removed — the agent's attempt was classifier-blocked,
needs a user-run `rm -rf`. Also clean the stale `.claude/settings.local.json`
allowlist entry naming the old clone path. (MEMORY.md Open Questions.)

### 2. Locate the Nuclear type's 1/8-HP-per-turn out-of-battle effect

Not in `217_Nuclear_Forms_Moves.rb`; likely a field/step hook or
`PokeBattle_Pokemon` patch. Needed before Phase 6 (custom engine work for the
Nuclear type) can start in earnest.

### 3. GBA charmap handling for accented characters

Sidecars are correct UTF-8 (`Pok\xE9mon`); `tileset_converter.assembly.normalize_pory`
owns charmap legality at staging (normalizes or fails loud) and the quantize
pipeline owns glyph rendering — but full correctness for é/♀/♂ across the
whole corpus (not just the slice) is unverified. Phase 5/6 integration
concern.

### 4. TMPBS field semantics

`tmpbs.dat` is confirmed a Uranium-custom extra move list per species, but
whether it's a move-reminder list or a broader compatibility list is still
open. Needed to decide the Phase 2 JSON representation before a full-corpus
PBS re-run.

### 5. Verify pre-seeded `VAR_GYM8_*` / `VAR_TANDOR_CHAMPIONSHIP_*` names

Proposed in Flag Registry Notes (MEMORY.md); may need renaming once the full
flag-registry policy is exercised outside the slice.

### 6. F3 — yesnobox two-step → native `msgbox(text, MSGBOX_YESNO)`

From the 2026-07-07 native-reuse audit (`reference/native_reuse_audit_2026-07-07.md`):
small transpiler fidelity win, not yet built. F1/F2 (the critical ones) are
done; F4 was no-action.

### 7. HEROINE player sprite

Slice boots MALE hardcoded. HEROINE sheets are exact-2× and convert cleanly
with the existing `sprites.convert_player_sheets` path whenever wanted —
mechanical, not blocked on anything.

### 8. Bike / surf / fish / field-move player poses beyond rock smash

HERO-BIKE/SURF/FISH etc. exist but are nonstandard grids (264×288, 384×384 —
not 4×4-of-64), so the exact-2×/majority-vote pipeline doesn't apply as-is.
None are slice-1-reachable; needed once a later slice touches water/cycling
routes.

### 9. `displayNinjaLetter` card UI

Currently converts as a scrolling msgbox (hand override, Map049 EV021). A
bespoke letter-card scene is a Phase-8 custom-C candidate if the flattened
version reads poorly in-game.

### 10. Full-corpus art walk is sampled only

Checkpoint-2 certification (2026-07-02) covered the 8-map walker batch by
sample, not exhaustively. Follow-up open: a systematic pass over all 199 maps'
converted art once more slices exist to make it worth doing in bulk.

### 11. 88 CommonEvent queue entries

Zero are called by slice 1, so they're out of scope there, but they're real
unconverted transpiler queue residue that blocks any slice that does call a
CE. Will need the CE-context idiom/native/hand triage (same shape as the
slice-1 event triage) once a slice pulls one in.

## Accepted deferrals (not currently planned — listed so they aren't re-litigated)

- **Reflection narrow-scan** — tried and reverted 2026-07-07 (user: "not
  actually a fix"). Do not re-apply; if pond reflections get revisited it
  needs a different approach than narrowing the engine scan box.
- **new_game.c test harness** (grants FLAG_BADGE03_GET + a Rock-Smash Geodude
  on fresh boot) — tracked as a to-remove-when-real-progression-covers-it
  obligation, currently live pending the slice-1 decision in
  `SLICE1_TODO.md` #5.

## Done

- **12. Map viewer hot-reload** (2026-07-13) — built as scoped, both halves:
  tileset source PNGs joined the request-time stat fingerprint (eager
  `sources.tileset_source_paths` + memoized per-map derivation in
  `map_viewer_common`), and `map_viewer_server.py` self-restarts via
  `os.execv` when any imported repo source changes (watch set derived from
  `sys.modules` each 1 s poll, so converter modules are covered; `--no-watch`
  opt-out). Browser still needs a manual F5 after restart, as scoped.
  Live-verified end-to-end; +33 tests.
