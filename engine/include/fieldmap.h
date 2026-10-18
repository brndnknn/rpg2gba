#ifndef GUARD_FIELDMAP_H
#define GUARD_FIELDMAP_H

#define NUM_TILES_IN_PRIMARY_FRLG 640
#define NUM_METATILES_IN_PRIMARY_FRLG 640
#define NUM_PALS_IN_PRIMARY_FRLG 7

#define NUM_TILES_IN_PRIMARY 512
#define NUM_METATILES_IN_PRIMARY 512
#define NUM_PALS_IN_PRIMARY 6

// BEGIN RPG2GBA STREAMING — 11-bit metatile ids (global.fieldmap.h): secondary holds 512..2047
#define NUM_METATILES_TOTAL 2048
// END RPG2GBA STREAMING
#define NUM_TILES_TOTAL 1024
#define NUM_PALS_TOTAL 13
#define MAX_MAP_DATA_SIZE 10240

#define NUM_TILES_PER_METATILE 8

// Map coordinates are offset by 7 when using the map
// buffer because it needs to load sufficient border
// metatiles to fill the player's view (the player has
// 7 metatiles of view horizontally in either direction).
#define MAP_OFFSET 7
#define MAP_OFFSET_W (MAP_OFFSET * 2 + 1)
#define MAP_OFFSET_H (MAP_OFFSET * 2)

#include "main.h"

extern struct BackupMapLayout gBackupMapLayout;
extern u16 ALIGNED(4) sBackupMapData[MAX_MAP_DATA_SIZE];

// BEGIN RPG2GBA STREAMING — windowed backup grid for maps over MAX_MAP_DATA_SIZE
// A map whose backup grid (width+15)*(height+14) won't fit keeps only a 128x64 window of
// it in sBackupMapData, as a ring indexed by BIGMAP_INDEX and recentred on the camera each
// step. Cells outside the window are rebuilt on demand from the layout and connection
// rectangles recorded at load, plus an overlay of runtime edits (setmetatile, doors,
// collision), so every grid read is correct wherever the window sits.
#define BIGMAP_WIN_W 128
#define BIGMAP_WIN_H 64
#define BIGMAP_INDEX(x, y) ((((y) & (BIGMAP_WIN_H - 1)) * BIGMAP_WIN_W) + ((x) & (BIGMAP_WIN_W - 1)))
#define BIGMAP_RECT_MAX 8
#define BIGMAP_OVERLAY_MAX 256

struct BigMapRect
{
    const u16 *src;     // the rectangle's top-left cell in the source layout
    const u16 *remap;   // connection id remap, NULL = none
    s16 x, y, w, h;     // destination, in backup-grid coordinates
    u16 srcWidth;
};

struct BigMapCell
{
    u16 x, y, block;
};

// screen_check.py reads active (+0), ox (+2) and oy (+4).
struct BigMap
{
    bool8 active;
    u8 rectCount;
    s16 ox, oy;         // window origin, in backup-grid coordinates
    u16 overlayCount;
    struct BigMapRect rects[BIGMAP_RECT_MAX];
    struct BigMapCell overlay[BIGMAP_OVERLAY_MAX];
};

extern struct BigMap gBigMap;
void BigMap_Track(void);
// END RPG2GBA STREAMING

u32 GetNumTilesInPrimary(struct MapLayout const *mapLayout);
u32 GetNumMetatilesInPrimary(struct MapLayout const *mapLayout);
u32 GetNumPalsInPrimary(struct MapLayout const *mapLayout);
u32 MapGridGetMetatileIdAt(int x, int y);
u32 MapGridGetMetatileBehaviorAt(int x, int y);
void MapGridSetMetatileIdAt(int x, int y, u16 metatile);
void MapGridSetMetatileEntryAt(int x, int y, u16 metatile);
void GetCameraCoords(u16 *x, u16 *y);
u8 MapGridGetCollisionAt(int x, int y);
enum Connection GetMapBorderIdAt(int x, int y);
bool32 CanCameraMoveInDirection(enum Direction direction);
u32 GetAttributeByMetatileIdAndMapLayout(u16 metatile, u8 attributeType, bool32 isFrlg);
void GetCameraFocusCoords(u16 *x, u16 *y);
u32 ExtractMetatileAttribute(u32 attributes, u8 attributeType, bool32 isFrlg);
u32 MapGridGetMetatileAttributeAt(s16 x, s16 y, u8 attributeType);
u8 MapGridGetMetatileLayerTypeAt(int x, int y);
u8 MapGridGetElevationAt(int x, int y);
bool8 CameraMove(int x, int y);
void SaveMapView(void);
void SetCameraFocusCoords(u16 x, u16 y);
void InitMap(void);
void InitMapFromSavedGame(void);
void InitTrainerHillMap(void);
void InitBattlePyramidMap(bool8 setPlayerPosition);
void CopyMapTilesetsToVram(struct MapLayout const *mapLayout);
void LoadMapTilesetPalettes(struct MapLayout const *mapLayout);
void LoadSecondaryTilesetPalette(struct MapLayout const *mapLayout, bool8 skipFaded);
void CopySecondaryTilesetToVramUsingHeap(struct MapLayout const *mapLayout);
void CopyPrimaryTilesetToVram(struct MapLayout const *mapLayout);
void CopySecondaryTilesetToVram(struct MapLayout const *mapLayout);
const struct MapHeader *const GetMapHeaderFromConnection(const struct MapConnection *connection);
const struct MapConnection *GetMapConnectionAtPos(s16 x, s16 y);
void MapGridSetMetatileImpassabilityAt(int x, int y, bool32 impassable);

// field_region_map.c
void FieldInitRegionMap(MainCallback callback);

#endif //GUARD_FIELDMAP_H
