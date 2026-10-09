#ifndef GUARD_URANIUM_CONNECTION_REMAP_H
#define GUARD_URANIUM_CONNECTION_REMAP_H

// BEGIN URANIUM PATHFINDER SLICE — connection id remap
// Two map-connected maps on DIFFERENT tilesets cannot render each other's
// border strip with raw metatile ids. The rpg2gba pipeline generates, per
// (current map, connected map) direction, a NUM_METATILES_TOTAL table that
// maps a neighbour metatile id to the current map's metatile id
// (src/data/uranium_connection_remaps.gen.h). Vanilla connections have no
// table and are untouched.
struct UraniumConnectionRemap
{
    u8 mapGroup;
    u8 mapNum;
    u8 connGroup;
    u8 connNum;
    const u16 *table;
};

// Remap table for the CURRENT map (gSaveBlock1Ptr->location) viewing the
// connected map (connGroup, connNum), or NULL if none.
const u16 *UraniumGetConnectionRemap(u8 connGroup, u8 connNum);

// Rewrites the metatile-id bits of `count` map-grid entries in place through
// `table`, preserving collision/elevation bits. MAPGRID_UNDEFINED is kept.
void UraniumApplyConnectionRemap(u16 *entries, int count, const u16 *table);

// Defined in fieldmap.c (needs its static tileset helpers). Used by
// LoadMapFromCameraTransition when a connection changes primary tileset.
struct MapLayout;
void UraniumCopyPrimaryTilesetToVramUsingHeap(struct MapLayout const *mapLayout);
void UraniumLoadPrimaryTilesetPalette(struct MapLayout const *mapLayout, bool8 skipFaded);
// END URANIUM PATHFINDER SLICE

#endif // GUARD_URANIUM_CONNECTION_REMAP_H
