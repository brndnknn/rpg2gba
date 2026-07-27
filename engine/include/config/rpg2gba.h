#ifndef GUARD_CONFIG_RPG2GBA_H
#define GUARD_CONFIG_RPG2GBA_H

// rpg2gba event-data range expansion.
//
// When TRUE, FLAGS_COUNT and VARS_END grow to add converter-owned regions
// ABOVE the vanilla ranges: three flag regions (temp switches, cleared on map
// transition like vanilla temp flags; global switches; per-event self
// switches) and one var region. The registry dump
// (data/scripts/uranium_flags.h) keys its bases off the RPG2GBA_*_START
// constants derived in constants/flags.h / constants/vars.h, and the pipeline
// reads the *_COUNT capacities below at assembly time to fail loud on
// overflow — keep this file the single source of truth for the sizes.
//
// Save impact: +256 flag bytes, +512 var bytes in SaveBlock1, offset by
// FREE_MYSTERY_EVENT_BUFFERS = TRUE (config/save.h); the budget is enforced
// by STATIC_ASSERT(SaveBlock1FreeSpace) in src/save.c.
#define RPG2GBA_EXPAND_EVENT_RANGES TRUE

// Region capacities. Keep each flag count a multiple of 8 so regions stay
// byte-aligned (ClearTempFieldEventData memsets whole bytes).
// Uranium corpus demand (census 2026-07-10): 345 temp switches, 235 global
// switches, 1132 self switches, 119 variables.
#define RPG2GBA_TEMP_FLAGS_COUNT       0x180  // 384
#define RPG2GBA_GLOBAL_FLAGS_COUNT     0x180  // 384
#define RPG2GBA_SELFSWITCH_FLAGS_COUNT 0x500  // 1280
#define RPG2GBA_VARS_COUNT             0x100  // 256

// rpg2gba pacing knobs (boot-walk 2026-07-27).
//
// Played side by side with the RMXP original, stock Emerald pacing reads as
// sluggish: Essentials prints text near-instantly and its transitions are
// short, while Emerald defaults to 4 frames per character and 8-frame palette
// fades. The two active constants below close that gap; each is a pure timing
// scale, so reverting one restores vanilla behavior exactly.
//
// Measured before changing anything (headless mGBA, `engine/pokeemerald.gba`):
// the overworld main loop keeps 60 fps (16 hardware frames per walked tile),
// and gMPlayInfo_BGM plays MUS_LITTLEROOT at tempoD 108 / tempoU 0x100 —
// exactly the tempo `sound/songs/midi/mus_littleroot.s` asks for. So the
// engine has no speed *bug*; these are deliberate pacing choices, and the
// audio knob below is deliberately inert (see its own note).

// New games start on OPTIONS_TEXT_SPEED_FAST (1 frame/char) instead of MID
// (4 frames/char). The Options menu still works normally.
#define RPG2GBA_FAST_TEXT_DEFAULT      TRUE

// Blend step per frame for software palette fades. Vanilla is 2 (y walks
// 0..16, so 8 frames); 4 halves every fade-to/from-black in the game —
// warps, script `fadescreen`, menu and battle-intro fades alike.
#define RPG2GBA_FADE_DELTA_Y           4

// BGM playback tempo, where 256 is the tempo the song itself asks for.
// 128 would be half speed; at 256 the call site compiles away entirely.
// Applies to map/script BGM only (PlayBGM); fanfares, jingles, cries and SEs
// keep their authored tempo regardless.
//
// Left at 256 deliberately. A half-tempo build was tried (2026-07-27) because
// the music reads as too fast against the RMXP original, and it is the wrong
// lever: the engine plays every song at exactly its authored tempo, and what
// is actually wrong is *which* song. Every slice map still gets MUS_LITTLEROOT
// from metadata_wiring.DEFAULT_MUSIC because the per-map substitution table in
// reference/findings/audio_decision_2026-07-14.md was never built, and
// Littleroot's theme is far peppier than Uranium's interior themes. Slowing it
// makes a wrong track sound sluggish instead of wrong. Fix the mapping.
#define RPG2GBA_BGM_TEMPO_SCALE        256

#endif // GUARD_CONFIG_RPG2GBA_H
