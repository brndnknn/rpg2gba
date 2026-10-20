// BEGIN RPG2GBA ENGINE — split-map popup
// Lookup for the pipeline-generated split-sibling table. See
// include/rpg2gba_split_maps.h. The generated header is gitignored; a fresh
// clone without it falls back to an empty table via __has_include, so the
// engine always builds.
#include "global.h"
#include "overworld.h"
#include "rpg2gba_split_maps.h"

#if __has_include("data/rpg2gba_split_siblings.gen.h")
#include "data/rpg2gba_split_siblings.gen.h"
#else
#define RPG2GBA_SPLIT_SIBLING_COUNT 0
static const struct Rpg2gbaSplitSibling sRpg2gbaSplitSiblings[] = { {0} };
#endif

#if RPG2GBA_SPLIT_SIBLING_COUNT > 0
static const struct Rpg2gbaSplitSibling *FindSplitSibling(u8 mapGroup, u8 mapNum)
{
    u32 i;

    for (i = 0; i < RPG2GBA_SPLIT_SIBLING_COUNT; i++)
    {
        if (sRpg2gbaSplitSiblings[i].mapGroup == mapGroup && sRpg2gbaSplitSiblings[i].mapNum == mapNum)
            return &sRpg2gbaSplitSiblings[i];
    }
    return NULL;
}
#endif

bool8 Rpg2gbaIsSplitSiblingWarp(void)
{
#if RPG2GBA_SPLIT_SIBLING_COUNT > 0
    const struct Rpg2gbaSplitSibling *from = FindSplitSibling(gLastUsedWarp.mapGroup, gLastUsedWarp.mapNum);
    const struct Rpg2gbaSplitSibling *to = FindSplitSibling(gSaveBlock1Ptr->location.mapGroup, gSaveBlock1Ptr->location.mapNum);

    return from != NULL && to != NULL && from != to && from->origin == to->origin;
#else
    (void)sRpg2gbaSplitSiblings;
    return FALSE;
#endif
}
// END RPG2GBA ENGINE
