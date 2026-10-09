// BEGIN URANIUM PATHFINDER SLICE — split-map popup
// Lookup for the pipeline-generated split-sibling table. See
// include/uranium_split_maps.h. The generated header is gitignored; a fresh
// clone without it falls back to an empty table via __has_include, so the
// engine always builds.
#include "global.h"
#include "overworld.h"
#include "uranium_split_maps.h"

#if __has_include("data/uranium_split_siblings.gen.h")
#include "data/uranium_split_siblings.gen.h"
#else
#define URANIUM_SPLIT_SIBLING_COUNT 0
static const struct UraniumSplitSibling sUraniumSplitSiblings[] = { {0} };
#endif

#if URANIUM_SPLIT_SIBLING_COUNT > 0
static const struct UraniumSplitSibling *FindSplitSibling(u8 mapGroup, u8 mapNum)
{
    u32 i;

    for (i = 0; i < URANIUM_SPLIT_SIBLING_COUNT; i++)
    {
        if (sUraniumSplitSiblings[i].mapGroup == mapGroup && sUraniumSplitSiblings[i].mapNum == mapNum)
            return &sUraniumSplitSiblings[i];
    }
    return NULL;
}
#endif

bool8 UraniumIsSplitSiblingWarp(void)
{
#if URANIUM_SPLIT_SIBLING_COUNT > 0
    const struct UraniumSplitSibling *from = FindSplitSibling(gLastUsedWarp.mapGroup, gLastUsedWarp.mapNum);
    const struct UraniumSplitSibling *to = FindSplitSibling(gSaveBlock1Ptr->location.mapGroup, gSaveBlock1Ptr->location.mapNum);

    return from != NULL && to != NULL && from != to && from->origin == to->origin;
#else
    (void)sUraniumSplitSiblings;
    return FALSE;
#endif
}
// END URANIUM PATHFINDER SLICE
