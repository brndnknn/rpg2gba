#ifndef GUARD_RPG2GBA_CONNECTION_REMAP_H
#define GUARD_RPG2GBA_CONNECTION_REMAP_H

// BEGIN RPG2GBA ENGINE — connection id remap
// Two map-connected maps on DIFFERENT tilesets cannot render each other's
// border strip with raw metatile ids. The rpg2gba pipeline generates, per
// (current map, connected map) direction, a NUM_METATILES_TOTAL table that
// maps a neighbour metatile id to the current map's metatile id
// (src/data/rpg2gba_connection_remaps.gen.h). Vanilla connections have no
// table and are untouched.
struct Rpg2gbaConnectionRemap
{
    u8 mapGroup;
    u8 mapNum;
    u8 connGroup;
    u8 connNum;
    const u16 *table;
};

// Remap table for the CURRENT map (gSaveBlock1Ptr->location) viewing the
// connected map (connGroup, connNum), or NULL if none.
const u16 *Rpg2gbaGetConnectionRemap(u8 connGroup, u8 connNum);

// Rewrites the metatile-id bits of `count` map-grid entries in place through
// `table`, preserving collision/elevation bits. MAPGRID_UNDEFINED is kept.
void Rpg2gbaApplyConnectionRemap(u16 *entries, int count, const u16 *table);

// Defined in fieldmap.c (needs its static tileset helpers). Used by
// LoadMapFromCameraTransition when a connection changes primary tileset.
struct MapLayout;
void Rpg2gbaCopyPrimaryTilesetToVramUsingHeap(struct MapLayout const *mapLayout);
void Rpg2gbaLoadPrimaryTilesetPalette(struct MapLayout const *mapLayout, bool8 skipFaded);
// END RPG2GBA ENGINE

#endif // GUARD_RPG2GBA_CONNECTION_REMAP_H
