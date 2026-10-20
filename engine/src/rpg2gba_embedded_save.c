// BEGIN RPG2GBA HARNESS — embedded-save boot (dev/review tooling).
// See include/rpg2gba_embedded_save.h for the design. Delete this file (and
// the CB2_StartRpg2gbaHarness branch in new_game.c) to remove the feature.

#include "global.h"
#include "rpg2gba_embedded_save.h"
#include "load_save.h"
#include "save.h"
#include "gpu_regs.h"
#include "pokemon_storage_system.h"
#include "constants/rgb.h"

// Zero-filled in a pristine build; the stamper rewrites these bytes in the
// .gba file directly (the symbol's ROM address comes from the linker map).
// The explicit {0} initializer keeps it in .rodata rather than .bss so the
// bytes exist in the ROM image at a stable stampable offset. volatile: see
// the header — without it LTO folds the blob to its link-time zeroes.
const volatile struct Rpg2gbaEmbeddedSave gRpg2gbaEmbeddedSave = {0};

// memcpy can't take a volatile source, and a cast would invite the compiler
// to fold again; a plain volatile byte loop is unfoldable by construction
// (~53 KiB, once, at boot — cost is irrelevant).
static void CopyFromBlob(void *dst, const volatile void *src, u32 size)
{
    u8 *d = dst;
    const volatile u8 *s = src;
    while (size--)
        *d++ = *s++;
}

static void FailLoud(void)
{
    // Stamped blob disagrees with this build's struct sizes: a stale stamper
    // or a ROM/blob version skew. Copying anyway would boot a silently
    // corrupt state, so paint the backdrop red and hang where the harness's
    // boot timeout (and a human eye) will catch it.
    SetGpuReg(REG_OFFSET_DISPCNT, 0);
    ((vu16 *)PLTT)[0] = RGB(31, 0, 0);
    for (;;)
        ;
}

bool32 Rpg2gbaEmbeddedSave_TryLoad(void)
{
    if (gRpg2gbaEmbeddedSave.magic == 0)
        return FALSE;
    if (gRpg2gbaEmbeddedSave.magic != RPG2GBA_EMBEDDED_SAVE_MAGIC
     || gRpg2gbaEmbeddedSave.sb1Size != sizeof(struct SaveBlock1)
     || gRpg2gbaEmbeddedSave.sb2Size != sizeof(struct SaveBlock2)
     || gRpg2gbaEmbeddedSave.sb3Size != sizeof(struct SaveBlock3)
     || gRpg2gbaEmbeddedSave.storageSize != sizeof(struct PokemonStorage))
        FailLoud();

    CopyFromBlob(gSaveBlock1Ptr, &gRpg2gbaEmbeddedSave.sb1, sizeof(struct SaveBlock1));
    CopyFromBlob(gSaveBlock2Ptr, &gRpg2gbaEmbeddedSave.sb2, sizeof(struct SaveBlock2));
    CopyFromBlob(gSaveBlock3Ptr, &gRpg2gbaEmbeddedSave.sb3, sizeof(struct SaveBlock3));
    CopyFromBlob(gPokemonStoragePtr, &gRpg2gbaEmbeddedSave.storage, sizeof(struct PokemonStorage));
    // Same post-load sync LoadGameSave does for a real flash save: pulls the
    // party (+ count) and object events out of SaveBlock1 into their live
    // globals.
    CopyPartyAndObjectsFromSave();
    gSaveFileStatus = SAVE_STATUS_OK;
    return TRUE;
}

// END RPG2GBA HARNESS
