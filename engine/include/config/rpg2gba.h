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

#endif // GUARD_CONFIG_RPG2GBA_H
