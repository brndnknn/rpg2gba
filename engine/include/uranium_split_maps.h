#ifndef GUARD_URANIUM_SPLIT_MAPS_H
#define GUARD_URANIUM_SPLIT_MAPS_H

// BEGIN URANIUM PATHFINDER SLICE — split-map popup
// The rpg2gba pipeline can cut one Uranium map into several GBA maps joined
// by arrow warps (reference/guides/map_split_stage.md). Every piece of one
// origin map is listed in src/data/uranium_split_siblings.gen.h with that
// origin's Uranium id, so the engine can tell a warp between two pieces of
// the same town from a real change of place.
struct UraniumSplitSibling
{
    u8 mapGroup;
    u8 mapNum;
    u16 origin;
};

// TRUE when the warp just taken (gLastUsedWarp -> current location) joined two
// pieces of the same split map: the map-name popup must not fire for it.
bool8 UraniumIsSplitSiblingWarp(void);
// END URANIUM PATHFINDER SLICE

#endif // GUARD_URANIUM_SPLIT_MAPS_H
