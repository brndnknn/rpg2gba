// BEGIN RPG2GBA HARNESS — embedded-save boot (dev/review tooling).
// See include/rpg2gba_embedded_save.h for the design. Delete this file (and
// the CB2_StartRpg2gbaHarness branch in new_game.c) to remove the feature.

#include "global.h"
#include "rpg2gba_embedded_save.h"
#include "load_save.h"
#include "save.h"
#include "gpu_regs.h"
#include "pokemon_storage_system.h"
#include "event_data.h"
#include "pokemon.h"
#include "script_pokemon_util.h"
#include "constants/items.h"
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

// The walk ROM id rides in SaveBlock2's unused filler_90 bytes, so an in-game
// save made on a walk ROM carries the id of the ROM it was made on.
static u32 *SavedWalkRomId(void)
{
    return (u32 *)gSaveBlock2Ptr->filler_90;
}

static bool32 PlayerOwnsSpecies(u16 species)
{
    u32 i, box, pos;

    for (i = 0; i < PARTY_SIZE; i++)
    {
        if (GetMonData(&gPlayerParty[i], MON_DATA_SPECIES) == species)
            return TRUE;
    }
    for (box = 0; box < TOTAL_BOXES_COUNT; box++)
    {
        for (pos = 0; pos < IN_BOX_COUNT; pos++)
        {
            if (GetBoxMonDataAt(box, pos, MON_DATA_SPECIES) == species)
                return TRUE;
        }
    }
    return FALSE;
}

// Gives each listed species the player doesn't own yet, at the party's top
// level: party slots first, then the PC (ScriptGiveMon routes it, and marks
// the Pokédex caught as a scripted gift would).
static void GrantWalkSpecies(void)
{
    u32 i, count = gRpg2gbaEmbeddedSave.walk.grantCount;
    u8 level = 1;

    if (count > RPG2GBA_WALK_GRANT_MAX)
        FailLoud();
    for (i = 0; i < PARTY_SIZE; i++)
    {
        if (GetMonData(&gPlayerParty[i], MON_DATA_SPECIES) != SPECIES_NONE
         && GetMonData(&gPlayerParty[i], MON_DATA_LEVEL) > level)
            level = GetMonData(&gPlayerParty[i], MON_DATA_LEVEL);
    }
    for (i = 0; i < count; i++)
    {
        u16 species = gRpg2gbaEmbeddedSave.walk.grants[i];

        if (species == SPECIES_NONE || PlayerOwnsSpecies(species))
            continue;
        ScriptGiveMon(species, level, ITEM_NONE);
    }
}

bool32 Rpg2gbaEmbeddedSave_TryLoad(void)
{
    u32 romId;

    if (gRpg2gbaEmbeddedSave.magic == 0)
        return FALSE;
    if (gRpg2gbaEmbeddedSave.magic != RPG2GBA_EMBEDDED_SAVE_MAGIC
     || gRpg2gbaEmbeddedSave.sb1Size != sizeof(struct SaveBlock1)
     || gRpg2gbaEmbeddedSave.sb2Size != sizeof(struct SaveBlock2)
     || gRpg2gbaEmbeddedSave.sb3Size != sizeof(struct SaveBlock3)
     || gRpg2gbaEmbeddedSave.storageSize != sizeof(struct PokemonStorage))
        FailLoud();

    // The player's own save on this walk ROM wins over the blob. LoadGameSave
    // already put any valid flash save in the save blocks; only a save holding
    // this ROM's id counts, so a .sav left by another build or another walk
    // ROM still loses to the blob (the 2026-08-01 stale-save protection).
    romId = gRpg2gbaEmbeddedSave.walk.romId;
    if (romId != 0 && gSaveFileStatus == SAVE_STATUS_OK && *SavedWalkRomId() == romId)
        return FALSE;

    CopyFromBlob(gSaveBlock1Ptr, &gRpg2gbaEmbeddedSave.sb1, sizeof(struct SaveBlock1));
    CopyFromBlob(gSaveBlock2Ptr, &gRpg2gbaEmbeddedSave.sb2, sizeof(struct SaveBlock2));
    CopyFromBlob(gSaveBlock3Ptr, &gRpg2gbaEmbeddedSave.sb3, sizeof(struct SaveBlock3));
    CopyFromBlob(gPokemonStoragePtr, &gRpg2gbaEmbeddedSave.storage, sizeof(struct PokemonStorage));
    // Same post-load sync LoadGameSave does for a real flash save: pulls the
    // party (+ count) and object events out of SaveBlock1 into their live
    // globals.
    CopyPartyAndObjectsFromSave();
    gSaveFileStatus = SAVE_STATUS_OK;

    *SavedWalkRomId() = romId;
    if (gRpg2gbaEmbeddedSave.walk.expShare && FLAG_RPG2GBA_EXP_SHARE != 0)
        FlagSet(FLAG_RPG2GBA_EXP_SHARE);
    GrantWalkSpecies();
    return TRUE;
}

// END RPG2GBA HARNESS
