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

#if RPG2GBA_MAP_WALKER == TRUE && RPG2GBA_HARNESS != TRUE
#error "RPG2GBA_MAP_WALKER requires RPG2GBA_HARNESS"
#endif

// END RPG2GBA HARNESS

#endif // GUARD_CONFIG_RPG2GBA_HARNESS_H
