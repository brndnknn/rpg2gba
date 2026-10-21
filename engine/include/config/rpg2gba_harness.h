#ifndef GUARD_CONFIG_RPG2GBA_HARNESS_H
#define GUARD_CONFIG_RPG2GBA_HARNESS_H

// BEGIN RPG2GBA HARNESS — test-harness switches (rpg2gba).

// TRUE: the build exists for the automated playtests and walks. It boots
// straight into a new game (no copyright screen, intro, title or main menu),
// names the player with a fixed default, and loads a save embedded in the ROM
// when one is present. FALSE: stock boot, so a release build shows the
// copyright screen, intro, title screen and main menu.
#define RPG2GBA_HARNESS TRUE

// TRUE builds the Map Walker debug ROM: boots into a cursor-based map
// inspector instead of normal gameplay. Requires RPG2GBA_HARNESS.
#define RPG2GBA_MAP_WALKER FALSE

// Party-wide EXP Share for walk ROMs (config/item.h I_EXP_SHARE_FLAG points
// here). Set only by an embedded-save boot whose walk extras ask for it
// (src/rpg2gba_embedded_save.c), so suite runs keep stock experience. A stock
// unused flag: engine harness state, not a game flag, so it is not minted by
// the rpg2gba flag registry. 0 disables the feature.
#if RPG2GBA_HARNESS == TRUE
#define FLAG_RPG2GBA_EXP_SHARE FLAG_UNUSED_0x020
#else
#define FLAG_RPG2GBA_EXP_SHARE 0
#endif

#if RPG2GBA_MAP_WALKER == TRUE && RPG2GBA_HARNESS != TRUE
#error "RPG2GBA_MAP_WALKER requires RPG2GBA_HARNESS"
#endif

// END RPG2GBA HARNESS

#endif // GUARD_CONFIG_RPG2GBA_HARNESS_H
