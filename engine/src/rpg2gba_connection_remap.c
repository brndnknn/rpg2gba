// BEGIN RPG2GBA ENGINE — connection id remap
// Lookup for the pipeline-generated connection remap tables. See
// include/rpg2gba_connection_remap.h. The generated header is gitignored; a
// fresh clone without it falls back to an empty table via __has_include, so
// the engine always builds.
#include "global.h"
#include "fieldmap.h"
#include "rpg2gba_connection_remap.h"

#if __has_include("data/rpg2gba_connection_remaps.gen.h")
#include "data/rpg2gba_connection_remaps.gen.h"
#else
#define RPG2GBA_CONNECTION_REMAP_COUNT 0
static const struct Rpg2gbaConnectionRemap sRpg2gbaConnectionRemaps[] = { {0} };
#endif

const u16 *Rpg2gbaGetConnectionRemap(u8 connGroup, u8 connNum)
{
#if RPG2GBA_CONNECTION_REMAP_COUNT > 0
    u32 i;
    u8 mapGroup = gSaveBlock1Ptr->location.mapGroup;
    u8 mapNum = gSaveBlock1Ptr->location.mapNum;

    for (i = 0; i < RPG2GBA_CONNECTION_REMAP_COUNT; i++)
    {
        const struct Rpg2gbaConnectionRemap *remap = &sRpg2gbaConnectionRemaps[i];
        if (remap->mapGroup == mapGroup && remap->mapNum == mapNum
         && remap->connGroup == connGroup && remap->connNum == connNum)
            return remap->table;
    }
#else
    (void)sRpg2gbaConnectionRemaps;
#endif
    return NULL;
}

void Rpg2gbaApplyConnectionRemap(u16 *entries, int count, const u16 *table)
{
    int i;

    for (i = 0; i < count; i++)
    {
        u16 entry = entries[i];
        if (entry == MAPGRID_UNDEFINED)
            continue;
        entries[i] = (entry & ~MAPGRID_METATILE_ID_MASK) | table[entry & MAPGRID_METATILE_ID_MASK];
    }
}
// END RPG2GBA ENGINE
