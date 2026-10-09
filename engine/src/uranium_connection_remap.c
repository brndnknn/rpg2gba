// BEGIN URANIUM PATHFINDER SLICE — connection id remap
// Lookup for the pipeline-generated connection remap tables. See
// include/uranium_connection_remap.h. The generated header is gitignored; a
// fresh clone without it falls back to an empty table via __has_include, so
// the engine always builds.
#include "global.h"
#include "fieldmap.h"
#include "uranium_connection_remap.h"

#if __has_include("data/uranium_connection_remaps.gen.h")
#include "data/uranium_connection_remaps.gen.h"
#else
#define URANIUM_CONNECTION_REMAP_COUNT 0
static const struct UraniumConnectionRemap sUraniumConnectionRemaps[] = { {0} };
#endif

const u16 *UraniumGetConnectionRemap(u8 connGroup, u8 connNum)
{
#if URANIUM_CONNECTION_REMAP_COUNT > 0
    u32 i;
    u8 mapGroup = gSaveBlock1Ptr->location.mapGroup;
    u8 mapNum = gSaveBlock1Ptr->location.mapNum;

    for (i = 0; i < URANIUM_CONNECTION_REMAP_COUNT; i++)
    {
        const struct UraniumConnectionRemap *remap = &sUraniumConnectionRemaps[i];
        if (remap->mapGroup == mapGroup && remap->mapNum == mapNum
         && remap->connGroup == connGroup && remap->connNum == connNum)
            return remap->table;
    }
#else
    (void)sUraniumConnectionRemaps;
#endif
    return NULL;
}

void UraniumApplyConnectionRemap(u16 *entries, int count, const u16 *table)
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
// END URANIUM PATHFINDER SLICE
