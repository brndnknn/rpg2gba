#ifndef GUARD_RPG2GBA_EMBEDDED_SAVE_H
#define GUARD_RPG2GBA_EMBEDDED_SAVE_H

// BEGIN RPG2GBA HARNESS — embedded-save boot (dev/review tooling).
//
// A reserved const blob the playtest harness stamps a finished game state into
// (rpg2gba: src/rpg2gba/playtest/). A stamped ROM is a single self-contained
// review artifact: it boots by copying this blob into the live save blocks and
// continuing, so a taildropped .gba opens on any device already in the tested
// state — no separate .sav to pair. Pristine ROMs (magic zero, as linked) are
// unaffected. Strip for a release ROM.

#include "global.h"
#include "pokemon_storage_system.h"

// "URNS" little-endian. The linker zero-fills the pristine blob, so any
// nonzero magic means a stamper wrote it.
#define RPG2GBA_EMBEDDED_SAVE_MAGIC 0x534E5255

struct Rpg2gbaEmbeddedSave
{
    u32 magic;
    // Sizes as the stamper understood them; must equal sizeof() of the
    // corresponding structs or the boot fails loud (red screen + hang),
    // because a stale stamper writing shifted structs would otherwise
    // produce a silently corrupt game state.
    u32 sb1Size;
    u32 sb2Size;
    u32 sb3Size;
    u32 storageSize;
    struct SaveBlock1 sb1;
    struct SaveBlock2 sb2;
    struct SaveBlock3 sb3;
    struct PokemonStorage storage;
};

// volatile is load-bearing: the pristine ROM links this blob zero-filled, and
// the stamper rewrites the bytes in the .gba file after linking. Without
// volatile, LTO constant-folds "magic == 0" against the initializer and
// deletes both the check and (via section GC) the blob itself — verified
// against this build: TryLoad shrank to 4 bytes and .rodata was dropped.
extern const volatile struct Rpg2gbaEmbeddedSave gRpg2gbaEmbeddedSave;

// Returns TRUE if a stamped state was found and copied into the live save
// blocks (party/objects synced, gSaveFileStatus set); FALSE on pristine ROM.
bool32 Rpg2gbaEmbeddedSave_TryLoad(void);

// END RPG2GBA HARNESS

#endif // GUARD_RPG2GBA_EMBEDDED_SAVE_H
