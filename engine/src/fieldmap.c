#include "global.h"
#include "battle_pyramid.h"
#include "bg.h"
#include "fieldmap.h"
#include "fldeff.h"
#include "fldeff_misc.h"
#include "frontier_util.h"
#include "menu.h"
#include "mirage_tower.h"
#include "overworld.h"
#include "palette.h"
#include "pokenav.h"
#include "script.h"
#include "secret_base.h"
#include "trainer_hill.h"
#include "tv.h"
#include "constants/rgb.h"
#include "constants/metatile_behaviors.h"
#include "constants/metatile_behaviors_frlg.h"
#include "wild_encounter.h"
// BEGIN URANIUM PATHFINDER SLICE — connection id remap
#include "uranium_connection_remap.h"
#include "field_camera.h"
// END URANIUM PATHFINDER SLICE
// BEGIN RPG2GBA STREAMING
#include "field_stream.h"
// END RPG2GBA STREAMING

struct ConnectionFlags
{
    u8 south:1;
    u8 north:1;
    u8 west:1;
    u8 east:1;
};

EWRAM_DATA u16 ALIGNED(4) sBackupMapData[MAX_MAP_DATA_SIZE] = {0};
EWRAM_DATA struct MapHeader gMapHeader = {0};
EWRAM_DATA struct Camera gCamera = {0};
EWRAM_DATA static struct ConnectionFlags sMapConnectionFlags = {0};

COMMON_DATA struct BackupMapLayout gBackupMapLayout = {0};
// BEGIN RPG2GBA STREAMING — windowed backup grid (fieldmap.h)
EWRAM_DATA struct BigMap gBigMap = {0};
STATIC_ASSERT(BIGMAP_WIN_W * BIGMAP_WIN_H <= MAX_MAP_DATA_SIZE, BigMapWindowFitsBackupBuffer);
static void BigMapInit(struct MapHeader *mapHeader);
static u16 BigMapGetBlock(int x, int y);
static void BigMapSetBlock(int x, int y, u16 block);
// END RPG2GBA STREAMING

static const struct ConnectionFlags sDummyConnectionFlags = {0};

static void InitMapLayoutData(struct MapHeader *mapHeader);
static void InitBackupMapLayoutData(const u16 *map, u16 width, u16 height);
// BEGIN URANIUM PATHFINDER SLICE — connection id remap (added `remap` param)
static void FillSouthConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap);
static void FillNorthConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap);
static void FillWestConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap);
static void FillEastConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap);
// END URANIUM PATHFINDER SLICE
static void InitBackupMapLayoutConnections(struct MapHeader *mapHeader);
static void LoadSavedMapView(void);
static bool8 SkipCopyingMetatileFromSavedMap(u16 *mapBlock, u16 mapWidth, u8 yMode);
static const struct MapConnection *GetIncomingConnection(enum Connection direction, int x, int y);
static bool8 IsPosInIncomingConnectingMap(enum Connection direction, int x, int y, const struct MapConnection *connection);
static bool8 IsCoordInIncomingConnectingMap(int coord, int srcMax, int destMax, int offset);

static inline u16 GetBorderBlockAt(int x, int y)
{
    const struct MapLayout *mapLayout = gMapHeader.mapLayout;

    if (mapLayout->isFrlg)
    {
        s32 xprime;
        s32 yprime;

        xprime = x - MAP_OFFSET;
        xprime += 8 * mapLayout->borderWidth;
        xprime %= mapLayout->borderWidth;

        yprime = y - MAP_OFFSET;
        yprime += 8 * mapLayout->borderHeight;
        yprime %= mapLayout->borderHeight;

        return mapLayout->border[xprime + yprime * mapLayout->borderWidth] | MAPGRID_COLLISION_MASK;
    }

    int i = (x + 1) & 1;
    i += ((y + 1) & 1) * 2;
    return gMapHeader.mapLayout->border[i] | MAPGRID_IMPASSABLE;
}

#define AreCoordsWithinMapGridBounds(x, y) (x >= 0 && x < gBackupMapLayout.width && y >= 0 && y < gBackupMapLayout.height)

// RPG2GBA STREAMING: windowed backup grid — an oversized map reads through BigMapGetBlock
#define GetMapGridBlockAt(x, y) (AreCoordsWithinMapGridBounds(x, y) ? (gBigMap.active ? BigMapGetBlock(x, y) : gBackupMapLayout.map[x + gBackupMapLayout.width * y]) : GetBorderBlockAt(x, y))
// END RPG2GBA STREAMING

// Masks/shifts for metatile attributes
// This is the format of the data stored in each data/tilesets/*/*/metatile_attributes.bin file
static const u32 sMetatileAttrMasks[METATILE_ATTRIBUTE_COUNT] = {
    [METATILE_ATTRIBUTE_BEHAVIOR]       = METATILE_ATTR_BEHAVIOR_MASK_FRLG, // Bits 0-8
    [METATILE_ATTRIBUTE_TERRAIN]        = 0x00003e00, // Bits 9-13
    [METATILE_ATTRIBUTE_2]              = 0x0003c000, // Bits 14-17
    [METATILE_ATTRIBUTE_3]              = 0x00fc0000, // Bits 18-23
    [METATILE_ATTRIBUTE_ENCOUNTER_TYPE] = 0x07000000, // Bits 24-26
    [METATILE_ATTRIBUTE_5]              = 0x18000000, // Bits 27-28
    [METATILE_ATTRIBUTE_LAYER_TYPE]     = METATILE_ATTR_LAYER_MASK_FRLG, // Bits 29-30
    [METATILE_ATTRIBUTE_7]              = 0x80000000  // Bit  31
};

static const u8 sMetatileAttrShifts[METATILE_ATTRIBUTE_COUNT] = {
    [METATILE_ATTRIBUTE_BEHAVIOR]       = METATILE_ATTR_BEHAVIOR_SHIFT_FRLG,
    [METATILE_ATTRIBUTE_TERRAIN]        = 9,
    [METATILE_ATTRIBUTE_2]              = 14,
    [METATILE_ATTRIBUTE_3]              = 18,
    [METATILE_ATTRIBUTE_ENCOUNTER_TYPE] = 24,
    [METATILE_ATTRIBUTE_5]              = 27,
    [METATILE_ATTRIBUTE_LAYER_TYPE]     = METATILE_ATTR_LAYER_SHIFT_FRLG,
    [METATILE_ATTRIBUTE_7]              = 31
};

static const u32 sMetatileAttrMasksEmerald[METATILE_ATTRIBUTE_COUNT] = {

    [METATILE_ATTRIBUTE_BEHAVIOR]       = METATILE_ATTR_BEHAVIOR_MASK,
    [METATILE_ATTRIBUTE_TERRAIN]        = 0xFFFFFFFF,
    [METATILE_ATTRIBUTE_2]              = 0xFFFFFFFF,
    [METATILE_ATTRIBUTE_3]              = 0xFFFFFFFF,
    [METATILE_ATTRIBUTE_ENCOUNTER_TYPE] = 0xFFFFFFFF,
    [METATILE_ATTRIBUTE_5]              = 0xFFFFFFFF,
    [METATILE_ATTRIBUTE_LAYER_TYPE]     = METATILE_ATTR_LAYER_MASK,
    [METATILE_ATTRIBUTE_7]              = 0xFFFFFFFF
};

static const u8 sMetatileAttrShiftsEmerald[METATILE_ATTRIBUTE_COUNT] = {

    [METATILE_ATTRIBUTE_BEHAVIOR]       = METATILE_ATTR_BEHAVIOR_SHIFT,
    [METATILE_ATTRIBUTE_TERRAIN]        = 0,
    [METATILE_ATTRIBUTE_2]              = 0,
    [METATILE_ATTRIBUTE_3]              = 0,
    [METATILE_ATTRIBUTE_ENCOUNTER_TYPE] = 0,
    [METATILE_ATTRIBUTE_5]              = 0,
    [METATILE_ATTRIBUTE_LAYER_TYPE]     = METATILE_ATTR_LAYER_SHIFT,
    [METATILE_ATTRIBUTE_7]              = 0
};

const struct MapHeader *const GetMapHeaderFromConnection(const struct MapConnection *connection)
{
    return Overworld_GetMapHeaderByGroupAndId(connection->mapGroup, connection->mapNum);
}

void InitMap(void)
{
    InitMapLayoutData(&gMapHeader);
    SetOccupiedSecretBaseEntranceMetatiles(gMapHeader.events);
    RunOnLoadMapScript();
}

void InitMapFromSavedGame(void)
{
    InitMapLayoutData(&gMapHeader);
    InitSecretBaseAppearance(FALSE);
    SetOccupiedSecretBaseEntranceMetatiles(gMapHeader.events);
    LoadSavedMapView();
    RunOnLoadMapScript();
    UpdateTVScreensOnMap(gBackupMapLayout.width, gBackupMapLayout.height);
}

void InitBattlePyramidMap(bool8 setPlayerPosition)
{
    gBigMap.active = FALSE; // RPG2GBA STREAMING: the floor generator writes the grid directly
    CpuFastFill16(MAPGRID_UNDEFINED, sBackupMapData, sizeof(sBackupMapData));
    GenerateBattlePyramidFloorLayout(sBackupMapData, setPlayerPosition);
}

void InitTrainerHillMap(void)
{
    gBigMap.active = FALSE; // RPG2GBA STREAMING: the floor generator writes the grid directly
    CpuFastFill16(MAPGRID_UNDEFINED, sBackupMapData, sizeof(sBackupMapData));
    GenerateTrainerHillFloorLayout(sBackupMapData);
}

static void InitMapLayoutData(struct MapHeader *mapHeader)
{
    struct MapLayout const *mapLayout;
    int width;
    int height;
    mapLayout = mapHeader->mapLayout;
    CpuFastFill16(MAPGRID_UNDEFINED, sBackupMapData, sizeof(sBackupMapData));
    gBackupMapLayout.map = sBackupMapData;
    width = mapLayout->width + MAP_OFFSET_W;
    gBackupMapLayout.width = width;
    height = mapLayout->height + MAP_OFFSET_H;
    gBackupMapLayout.height = height;
    gBigMap.active = FALSE; // RPG2GBA STREAMING: windowed backup grid
    if (width * height <= MAX_MAP_DATA_SIZE)
    {
        InitBackupMapLayoutData(mapLayout->map, mapLayout->width, mapLayout->height);
        InitBackupMapLayoutConnections(mapHeader);
    }
    // BEGIN RPG2GBA STREAMING — windowed backup grid: stock skipped the oversized map,
    // leaving only its border
    else
    {
        BigMapInit(mapHeader);
    }
    // END RPG2GBA STREAMING
}

// BEGIN RPG2GBA STREAMING — windowed backup grid (fieldmap.h)
static void BigMapAddRect(const u16 *src, u16 srcWidth, const u16 *remap, int x, int y, int w, int h)
{
    struct BigMapRect *rect;

    if (w <= 0 || h <= 0)
        return;
    assertf(gBigMap.rectCount < BIGMAP_RECT_MAX, "big map: more than %d grid rectangles", BIGMAP_RECT_MAX)
    {
        return;
    }
    rect = &gBigMap.rects[gBigMap.rectCount++];
    rect->src = src;
    rect->srcWidth = srcWidth;
    rect->remap = remap;
    rect->x = x;
    rect->y = y;
    rect->w = w;
    rect->h = h;
}

// The cell the stock loader would have put at (x, y): the last rectangle covering it wins,
// as the last FillConnection to write it would have.
static u16 BigMapBaseBlock(int x, int y)
{
    int i;

    for (i = gBigMap.rectCount - 1; i >= 0; i--)
    {
        const struct BigMapRect *rect = &gBigMap.rects[i];
        u32 dx = x - rect->x;
        u32 dy = y - rect->y;
        if (dx < (u32)rect->w && dy < (u32)rect->h)
        {
            u16 block = rect->src[dy * rect->srcWidth + dx];
            if (rect->remap != NULL)
                UraniumApplyConnectionRemap(&block, 1, rect->remap);
            return block;
        }
    }
    return MAPGRID_UNDEFINED;
}

static struct BigMapCell *BigMapFindEdit(int x, int y)
{
    u32 i;

    for (i = 0; i < gBigMap.overlayCount; i++)
    {
        if (gBigMap.overlay[i].x == x && gBigMap.overlay[i].y == y)
            return &gBigMap.overlay[i];
    }
    return NULL;
}

static inline bool32 BigMapInWindow(int x, int y)
{
    return (u32)(x - gBigMap.ox) < BIGMAP_WIN_W && (u32)(y - gBigMap.oy) < BIGMAP_WIN_H;
}

// (x, y) must be within the grid bounds.
static u16 BigMapGetBlock(int x, int y)
{
    struct BigMapCell *edit;

    if (BigMapInWindow(x, y))
        return sBackupMapData[BIGMAP_INDEX(x, y)];
    edit = BigMapFindEdit(x, y);
    if (edit != NULL)
        return edit->block;
    return BigMapBaseBlock(x, y);
}

// (x, y) must be within the grid bounds. The overlay keeps only cells that differ from the
// layout, so a door that opens and closes again leaves nothing behind.
static void BigMapSetBlock(int x, int y, u16 block)
{
    struct BigMapCell *edit;

    if (BigMapInWindow(x, y))
        sBackupMapData[BIGMAP_INDEX(x, y)] = block;
    edit = BigMapFindEdit(x, y);
    if (block == BigMapBaseBlock(x, y))
    {
        if (edit != NULL)
            *edit = gBigMap.overlay[--gBigMap.overlayCount];
        return;
    }
    if (edit != NULL)
    {
        edit->block = block;
        return;
    }
    assertf(gBigMap.overlayCount < BIGMAP_OVERLAY_MAX, "big map: more than %d edited cells", BIGMAP_OVERLAY_MAX)
    {
        return;
    }
    edit = &gBigMap.overlay[gBigMap.overlayCount++];
    edit->x = x;
    edit->y = y;
    edit->block = block;
}

// Rebuilds the ring cells of grid rows [y0, y1) x columns [x0, x1).
static void BigMapFill(int x0, int y0, int x1, int y1)
{
    int x, y;
    u32 i;

    if (x0 < 0)
        x0 = 0;
    if (y0 < 0)
        y0 = 0;
    if (x1 > gBackupMapLayout.width)
        x1 = gBackupMapLayout.width;
    if (y1 > gBackupMapLayout.height)
        y1 = gBackupMapLayout.height;
    for (y = y0; y < y1; y++)
    {
        for (x = x0; x < x1; x++)
            sBackupMapData[BIGMAP_INDEX(x, y)] = BigMapBaseBlock(x, y);
    }
    for (i = 0; i < gBigMap.overlayCount; i++)
    {
        const struct BigMapCell *edit = &gBigMap.overlay[i];
        if (edit->x >= x0 && edit->x < x1 && edit->y >= y0 && edit->y < y1)
            sBackupMapData[BIGMAP_INDEX(edit->x, edit->y)] = edit->block;
    }
}

static void BigMapMoveWindow(int ox, int oy, bool32 full)
{
    int dx = ox - gBigMap.ox;
    int dy = oy - gBigMap.oy;

    if (full || dx >= BIGMAP_WIN_W || dx <= -BIGMAP_WIN_W || dy >= BIGMAP_WIN_H || dy <= -BIGMAP_WIN_H)
    {
        gBigMap.ox = ox;
        gBigMap.oy = oy;
        BigMapFill(ox, oy, ox + BIGMAP_WIN_W, oy + BIGMAP_WIN_H);
        return;
    }
    // Columns first at the old rows, then rows at the new columns; each strip overwrites
    // exactly the ring cells that left the window.
    if (dx > 0)
        BigMapFill(gBigMap.ox + BIGMAP_WIN_W, gBigMap.oy, ox + BIGMAP_WIN_W, gBigMap.oy + BIGMAP_WIN_H);
    else if (dx < 0)
        BigMapFill(ox, gBigMap.oy, gBigMap.ox, gBigMap.oy + BIGMAP_WIN_H);
    gBigMap.ox = ox;
    if (dy > 0)
        BigMapFill(ox, gBigMap.oy + BIGMAP_WIN_H, ox + BIGMAP_WIN_W, oy + BIGMAP_WIN_H);
    else if (dy < 0)
        BigMapFill(ox, oy, ox + BIGMAP_WIN_W, gBigMap.oy);
    gBigMap.oy = oy;
}

static int BigMapOrigin(int focus, int win, int size)
{
    int origin = focus - win / 2;

    if (origin > size - win)
        origin = size - win;
    if (origin < 0)
        origin = 0;
    return origin;
}

static void BigMapCentre(bool32 full)
{
    BigMapMoveWindow(BigMapOrigin(gSaveBlock1Ptr->pos.x + MAP_OFFSET, BIGMAP_WIN_W, gBackupMapLayout.width),
                     BigMapOrigin(gSaveBlock1Ptr->pos.y + MAP_OFFSET, BIGMAP_WIN_H, gBackupMapLayout.height),
                     full);
}

// Keeps the window centred on the camera. Only speed depends on this: reads outside the
// window are rebuilt, just more slowly.
void BigMap_Track(void)
{
    if (gBigMap.active)
        BigMapCentre(FALSE);
}

static void BigMapInit(struct MapHeader *mapHeader)
{
    struct MapLayout const *mapLayout = mapHeader->mapLayout;

    gBigMap.active = TRUE;
    gBigMap.rectCount = 0;
    gBigMap.overlayCount = 0;
    BigMapAddRect(mapLayout->map, mapLayout->width, NULL, MAP_OFFSET, MAP_OFFSET, mapLayout->width, mapLayout->height);
    // FillConnection records each connection's rectangle instead of copying it.
    InitBackupMapLayoutConnections(mapHeader);
    BigMapCentre(TRUE);
}
// END RPG2GBA STREAMING

static void InitBackupMapLayoutData(const u16 *map, u16 width, u16 height)
{
    u16 *dest;
    int y;
    dest = gBackupMapLayout.map;
    dest += gBackupMapLayout.width * 7 + MAP_OFFSET;
    for (y = 0; y < height; y++)
    {
        CpuCopy16(map, dest, width * 2);
        dest += width + MAP_OFFSET_W;
        map += width;
    }
}

static void InitBackupMapLayoutConnections(struct MapHeader *mapHeader)
{
    int count;
    const struct MapConnection *connection;
    int i;

    if (mapHeader->connections)
    {
        count = mapHeader->connections->count;
        connection = mapHeader->connections->connections;
        sMapConnectionFlags = sDummyConnectionFlags;
        for (i = 0; i < count; i++, connection++)
        {
            struct MapHeader const *cMap = GetMapHeaderFromConnection(connection);
            s32 offset = connection->offset;
            // BEGIN URANIUM PATHFINDER SLICE — connection id remap
            const u16 *remap = UraniumGetConnectionRemap(connection->mapGroup, connection->mapNum);
            // END URANIUM PATHFINDER SLICE
            switch (connection->direction)
            {
            case CONNECTION_SOUTH:
                FillSouthConnection(mapHeader, cMap, offset, remap);
                sMapConnectionFlags.south = TRUE;
                break;
            case CONNECTION_NORTH:
                FillNorthConnection(mapHeader, cMap, offset, remap);
                sMapConnectionFlags.north = TRUE;
                break;
            case CONNECTION_WEST:
                FillWestConnection(mapHeader, cMap, offset, remap);
                sMapConnectionFlags.west = TRUE;
                break;
            case CONNECTION_EAST:
                FillEastConnection(mapHeader, cMap, offset, remap);
                sMapConnectionFlags.east = TRUE;
                break;
            }
        }
    }
}

// URANIUM PATHFINDER SLICE: connection id remap — added `remap` param (NULL = vanilla)
static void FillConnection(int x, int y, struct MapHeader const *connectedMapHeader, const u16 *remap, int x2, int y2, int width, int height)
{
    int i;
    const u16 *src;
    u16 *dest;
    int mapWidth;

    mapWidth = connectedMapHeader->mapLayout->width;
    src = &connectedMapHeader->mapLayout->map[mapWidth * y2 + x2];
    // BEGIN RPG2GBA STREAMING — windowed backup grid: record the rectangle, don't copy
    if (gBigMap.active)
    {
        BigMapAddRect(src, mapWidth, remap, x, y, width, height);
        return;
    }
    // END RPG2GBA STREAMING
    dest = &gBackupMapLayout.map[gBackupMapLayout.width * y + x];

    for (i = 0; i < height; i++)
    {
        CpuCopy16(src, dest, width * 2);
        // BEGIN URANIUM PATHFINDER SLICE — connection id remap
        if (remap != NULL)
            UraniumApplyConnectionRemap(dest, width, remap);
        // END URANIUM PATHFINDER SLICE
        dest += gBackupMapLayout.width;
        src += mapWidth;
    }
}

static void FillSouthConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap)
{
    int x, y;
    int x2;
    int width;
    int cWidth;

    if (connectedMapHeader)
    {
        cWidth = connectedMapHeader->mapLayout->width;
        x = offset + MAP_OFFSET;
        y = mapHeader->mapLayout->height + MAP_OFFSET;
        if (x < 0)
        {
            x2 = -x;
            x += cWidth;
            if (x < gBackupMapLayout.width)
                width = x;
            else
                width = gBackupMapLayout.width;
            x = 0;
        }
        else
        {
            x2 = 0;
            if (x + cWidth < gBackupMapLayout.width)
                width = cWidth;
            else
                width = gBackupMapLayout.width - x;
        }

        FillConnection(
            x, y,
            connectedMapHeader, remap, // URANIUM PATHFINDER SLICE: connection id remap
            x2, /*y2*/ 0,
            width, /*height*/ MAP_OFFSET);
    }
}

static void FillNorthConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap)
{
    int x;
    int x2, y2;
    int width;
    int cWidth, cHeight;

    if (connectedMapHeader)
    {
        cWidth = connectedMapHeader->mapLayout->width;
        cHeight = connectedMapHeader->mapLayout->height;
        x = offset + MAP_OFFSET;
        y2 = cHeight - MAP_OFFSET;
        if (x < 0)
        {
            x2 = -x;
            x += cWidth;
            if (x < gBackupMapLayout.width)
                width = x;
            else
                width = gBackupMapLayout.width;
            x = 0;
        }
        else
        {
            x2 = 0;
            if (x + cWidth < gBackupMapLayout.width)
                width = cWidth;
            else
                width = gBackupMapLayout.width - x;
        }

        FillConnection(
            x, /*y*/ 0,
            connectedMapHeader, remap, // URANIUM PATHFINDER SLICE: connection id remap
            x2, y2,
            width, /*height*/ MAP_OFFSET);

    }
}

static void FillWestConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap)
{
    int y;
    int x2, y2;
    int height;
    int cWidth, cHeight;
    if (connectedMapHeader)
    {
        cWidth = connectedMapHeader->mapLayout->width;
        cHeight = connectedMapHeader->mapLayout->height;
        y = offset + MAP_OFFSET;
        x2 = cWidth - MAP_OFFSET;
        if (y < 0)
        {
            y2 = -y;
            if (y + cHeight < gBackupMapLayout.height)
                height = y + cHeight;
            else
                height = gBackupMapLayout.height;
            y = 0;
        }
        else
        {
            y2 = 0;
            if (y + cHeight < gBackupMapLayout.height)
                height = cHeight;
            else
                height = gBackupMapLayout.height - y;
        }

        FillConnection(
            /*x*/ 0, y,
            connectedMapHeader, remap, // URANIUM PATHFINDER SLICE: connection id remap
            x2, y2,
            /*width*/ MAP_OFFSET, height);
    }
}

static void FillEastConnection(struct MapHeader const *mapHeader, struct MapHeader const *connectedMapHeader, s32 offset, const u16 *remap)
{
    int x, y;
    int y2;
    int height;
    int cHeight;
    if (connectedMapHeader)
    {
        cHeight = connectedMapHeader->mapLayout->height;
        x = mapHeader->mapLayout->width + MAP_OFFSET;
        y = offset + MAP_OFFSET;
        if (y < 0)
        {
            y2 = -y;
            if (y + cHeight < gBackupMapLayout.height)
                height = y + cHeight;
            else
                height = gBackupMapLayout.height;
            y = 0;
        }
        else
        {
            y2 = 0;
            if (y + cHeight < gBackupMapLayout.height)
                height = cHeight;
            else
                height = gBackupMapLayout.height - y;
        }

        FillConnection(
            x, y,
            connectedMapHeader, remap, // URANIUM PATHFINDER SLICE: connection id remap
            /*x2*/ 0, y2,
            /*width*/ MAP_OFFSET + 1, height);
    }
}

u8 MapGridGetElevationAt(int x, int y)
{
    u16 block = GetMapGridBlockAt(x, y);

    if (block == MAPGRID_UNDEFINED)
        return 0;

    return UNPACK_ELEVATION(block);
}

u8 MapGridGetCollisionAt(int x, int y)
{
    u16 block = GetMapGridBlockAt(x, y);

    if (block == MAPGRID_UNDEFINED)
        return TRUE;

    return UNPACK_COLLISION(block);
}

u32 GetNumTilesInPrimary(struct MapLayout const *mapLayout)
{
    return mapLayout->isFrlg ? NUM_TILES_IN_PRIMARY_FRLG : NUM_TILES_IN_PRIMARY;
}

u32 GetNumMetatilesInPrimary(struct MapLayout const *mapLayout)
{
    return mapLayout->isFrlg ? NUM_METATILES_IN_PRIMARY_FRLG : NUM_METATILES_IN_PRIMARY;
}

u32 GetNumPalsInPrimary(struct MapLayout const *mapLayout)
{
    return mapLayout->isFrlg ? NUM_PALS_IN_PRIMARY_FRLG : NUM_PALS_IN_PRIMARY;
}

u32 MapGridGetMetatileIdAt(int x, int y)
{
    u16 block = GetMapGridBlockAt(x, y);

    if (block == MAPGRID_UNDEFINED)
        return GetBorderBlockAt(x, y) & MAPGRID_METATILE_ID_MASK;

    return UNPACK_METATILE(block);
}

u32 MapGridGetMetatileAttributeAt(s16 x, s16 y, u8 attributeType)
{
    u16 metatileId = MapGridGetMetatileIdAt(x, y);
    return GetAttributeByMetatileIdAndMapLayout(metatileId, attributeType, gMapHeader.mapLayout->isFrlg);
}

u32 MapGridGetMetatileBehaviorAt(int x, int y)
{
    return MapGridGetMetatileAttributeAt(x, y, METATILE_ATTRIBUTE_BEHAVIOR);
}

u8 MapGridGetMetatileLayerTypeAt(int x, int y)
{
    return MapGridGetMetatileAttributeAt(x, y, METATILE_ATTRIBUTE_LAYER_TYPE);
}

void MapGridSetMetatileIdAt(int x, int y, u16 metatile)
{
    int i;
    if (AreCoordsWithinMapGridBounds(x, y))
    {
        // BEGIN RPG2GBA STREAMING — windowed backup grid
        if (gBigMap.active)
        {
            BigMapSetBlock(x, y, (BigMapGetBlock(x, y) & MAPGRID_ELEVATION_MASK) | (metatile & ~MAPGRID_ELEVATION_MASK));
            return;
        }
        // END RPG2GBA STREAMING
        i = x + y * gBackupMapLayout.width;

        // Elevation is ignored in the argument, but copy metatile ID and collision
        gBackupMapLayout.map[i] = (gBackupMapLayout.map[i] & MAPGRID_ELEVATION_MASK) | (metatile & ~MAPGRID_ELEVATION_MASK);
    }
}

void MapGridSetMetatileEntryAt(int x, int y, u16 metatile)
{
    int i;
    if (AreCoordsWithinMapGridBounds(x, y))
    {
        // BEGIN RPG2GBA STREAMING — windowed backup grid
        if (gBigMap.active)
        {
            BigMapSetBlock(x, y, metatile);
            return;
        }
        // END RPG2GBA STREAMING
        i = x + gBackupMapLayout.width * y;
        gBackupMapLayout.map[i] = metatile;
    }
}

u32 ExtractMetatileAttribute(u32 attributes, u8 attributeType, bool32 isFrlg)
{
    if (attributeType >= METATILE_ATTRIBUTE_COUNT) // Check for METATILE_ATTRIBUTES_ALL
        return attributes;

    if (isFrlg)
        return (attributes & sMetatileAttrMasks[attributeType]) >> sMetatileAttrShifts[attributeType];

    return (attributes & sMetatileAttrMasksEmerald[attributeType]) >> sMetatileAttrShiftsEmerald[attributeType];
}

static u32 GetAttributeByMetatileIdAndMapLayoutFrlg(u16 metatile, u8 attributeType)
{
    u32 attribute;
    if (metatile < GetNumMetatilesInPrimary(gMapHeader.mapLayout))
    {
        const u32 *attributes = (const u32*)gMapHeader.mapLayout->primaryTileset->metatileAttributes;
        attribute = attributes[metatile];
    }
    else if (metatile < NUM_METATILES_TOTAL)
    {
        const u32 *attributes = (const u32*) gMapHeader.mapLayout->secondaryTileset->metatileAttributes;
        metatile -= GetNumMetatilesInPrimary(gMapHeader.mapLayout);
        attribute = attributes[metatile];
    }
    else
    {
        return MB_INVALID;
    }

    return ExtractMetatileAttribute(attribute, attributeType, TRUE);
}

u32 GetAttributeByMetatileIdAndMapLayout(u16 metatile, u8 attributeType, bool32 isFrlg)
{
    u32 attribute;

    if (isFrlg)
        return GetAttributeByMetatileIdAndMapLayoutFrlg(metatile, attributeType);

    if (metatile < GetNumMetatilesInPrimary(gMapHeader.mapLayout))
    {
        const u16 *attributes = (const u16*)gMapHeader.mapLayout->primaryTileset->metatileAttributes;
        attribute = attributes[metatile];
    }
    else if (metatile < NUM_METATILES_TOTAL)
    {
        const u16 *attributes = (const u16*)gMapHeader.mapLayout->secondaryTileset->metatileAttributes;
        metatile -= GetNumMetatilesInPrimary(gMapHeader.mapLayout);
        attribute = attributes[metatile];
    }
    else
    {
        return MB_INVALID;
    }

    return ExtractMetatileAttribute(attribute, attributeType, FALSE);
}

void SaveMapView(void)
{
    int i, j;
    int x, y;
    u16 *mapView;
    int width;
    mapView = gSaveBlock1Ptr->mapView;
    width = gBackupMapLayout.width;
    x = gSaveBlock1Ptr->pos.x;
    y = gSaveBlock1Ptr->pos.y;
    // BEGIN RPG2GBA STREAMING — windowed backup grid
    if (gBigMap.active)
    {
        for (i = y; i < y + MAP_OFFSET_H; i++)
        {
            for (j = x; j < x + MAP_OFFSET_W; j++)
                *mapView++ = GetMapGridBlockAt(j, i);
        }
        return;
    }
    // END RPG2GBA STREAMING
    for (i = y; i < y + MAP_OFFSET_H; i++)
    {
        for (j = x; j < x + MAP_OFFSET_W; j++)
            *mapView++ = sBackupMapData[width * i + j];
    }
}

static bool32 SavedMapViewIsEmpty(void)
{
    u16 i;
    u32 marker = 0;

#ifndef UBFIX
    // BUG: This loop extends past the bounds of the mapView array. Its size is only 0x100.
    for (i = 0; i < 0x200; i++)
        marker |= gSaveBlock1Ptr->mapView[i];
#else
    // UBFIX: Only iterate over 0x100
    for (i = 0; i < ARRAY_COUNT(gSaveBlock1Ptr->mapView); i++)
        marker |= gSaveBlock1Ptr->mapView[i];
#endif


    if (marker == 0)
        return TRUE;
    else
        return FALSE;
}

static void ClearSavedMapView(void)
{
    CpuFill16(0, gSaveBlock1Ptr->mapView, sizeof(gSaveBlock1Ptr->mapView));
}

static void LoadSavedMapView(void)
{
    u8 yMode;
    int i, j;
    int x, y;
    u16 *mapView;
    int width;
    mapView = gSaveBlock1Ptr->mapView;
    if (!SavedMapViewIsEmpty())
    {
        width = gBackupMapLayout.width;
        x = gSaveBlock1Ptr->pos.x;
        y = gSaveBlock1Ptr->pos.y;
        for (i = y; i < y + MAP_OFFSET_H; i++)
        {
            if (i == y && i != 0)
                yMode = 0;
            else if (i == y + MAP_OFFSET_H - 1 && i != gMapHeader.mapLayout->height - 1)
                yMode = 1;
            else
                yMode = 0xFF;

            for (j = x; j < x + MAP_OFFSET_W; j++)
            {
                // BEGIN RPG2GBA STREAMING — windowed backup grid
                if (gBigMap.active)
                {
                    if (AreCoordsWithinMapGridBounds(j, i)
                     && (yMode == 0xFF || !IsLargeBreakableDecoration(UNPACK_METATILE(GetMapGridBlockAt(j, yMode == 0 ? i - 1 : i + 1)), yMode)))
                        BigMapSetBlock(j, i, *mapView);
                    mapView++;
                    continue;
                }
                // END RPG2GBA STREAMING
                if (!SkipCopyingMetatileFromSavedMap(&sBackupMapData[j + width * i], width, yMode))
                    sBackupMapData[j + width * i] = *mapView;
                mapView++;
            }
        }
        for (j = x; j < x + MAP_OFFSET_W; j++)
        {
            if (y != 0)
                FixLongGrassMetatilesWindowTop(j, y - 1);
            if (i < gMapHeader.mapLayout->height - 1)
                FixLongGrassMetatilesWindowBottom(j, y + MAP_OFFSET_H - 1);
        }
        ClearSavedMapView();
    }
}

static void MoveMapViewToBackup(enum Connection direction)
{
    int width;
    u16 *mapView;
    int x0, y0;
    int x2, y2;
    u16 *src, *dest;
    int srci, desti;
    int r9, r8;
    int x, y;
    int i, j;
    mapView = gSaveBlock1Ptr->mapView;
    width = gBackupMapLayout.width;
    r9 = 0;
    r8 = 0;
    x0 = gSaveBlock1Ptr->pos.x;
    y0 = gSaveBlock1Ptr->pos.y;
    x2 = MAP_OFFSET_W;
    y2 = MAP_OFFSET_H;

    switch (direction)
    {
    case CONNECTION_NORTH:
        y0 += 1;
        y2 = MAP_OFFSET_H - 1;
        break;
    case CONNECTION_SOUTH:
        r8 = 1;
        y2 = MAP_OFFSET_H - 1;
        break;
    case CONNECTION_WEST:
        x0 += 1;
        x2 = MAP_OFFSET_W - 1;
        break;
    case CONNECTION_EAST:
        r9 = 1;
        x2 = MAP_OFFSET_W - 1;
        break;
    default:
        break;
    }

    for (y = 0; y < y2; y++)
    {
        i = 0;
        j = 0;
        for (x = 0; x < x2; x++)
        {
            desti = width * (y + y0);
            srci = (y + r8) * MAP_OFFSET_W + r9;
            src = &mapView[srci + i];
            // BEGIN RPG2GBA STREAMING — windowed backup grid
            if (gBigMap.active)
            {
                if (AreCoordsWithinMapGridBounds(x0 + j, y + y0))
                    BigMapSetBlock(x0 + j, y + y0, *src);
                i++;
                j++;
                continue;
            }
            // END RPG2GBA STREAMING
            dest = &sBackupMapData[x0 + desti + j];
            *dest = *src;
            i++;
            j++;
        }
    }

    ClearSavedMapView();
}

enum Connection GetMapBorderIdAt(int x, int y)
{
    if (GetMapGridBlockAt(x, y) == MAPGRID_UNDEFINED)
        return CONNECTION_INVALID;

    if (x >= (gBackupMapLayout.width - (MAP_OFFSET + 1)))
    {
        if (!sMapConnectionFlags.east)
            return CONNECTION_INVALID;

        return CONNECTION_EAST;
    }
    else if (x < MAP_OFFSET)
    {
        if (!sMapConnectionFlags.west)
            return CONNECTION_INVALID;

        return CONNECTION_WEST;
    }
    else if (y >= (gBackupMapLayout.height - MAP_OFFSET))
    {
        if (!sMapConnectionFlags.south)
            return CONNECTION_INVALID;

        return CONNECTION_SOUTH;
    }
    else if (y < MAP_OFFSET)
    {
        if (!sMapConnectionFlags.north)
            return CONNECTION_INVALID;

        return CONNECTION_NORTH;
    }
    else
    {
        return CONNECTION_NONE;
    }
}

enum Connection GetPostCameraMoveMapBorderId(int x, int y)
{
    return GetMapBorderIdAt(gSaveBlock1Ptr->pos.x + MAP_OFFSET + x, gSaveBlock1Ptr->pos.y + MAP_OFFSET + y);
}

bool32 CanCameraMoveInDirection(enum Direction direction)
{
    int x, y;
    x = gSaveBlock1Ptr->pos.x + MAP_OFFSET + gDirectionToVectors[direction].x;
    y = gSaveBlock1Ptr->pos.y + MAP_OFFSET + gDirectionToVectors[direction].y;

    if (GetMapBorderIdAt(x, y) == CONNECTION_INVALID)
        return FALSE;

    return TRUE;
}

static void SetPositionFromConnection(const struct MapConnection *connection, enum Connection direction, int x, int y)
{
    struct MapHeader const *mapHeader = GetMapHeaderFromConnection(connection);

    switch (direction)
    {
    case CONNECTION_EAST:
        gSaveBlock1Ptr->pos.x = -x;
        gSaveBlock1Ptr->pos.y -= connection->offset;
        break;
    case CONNECTION_WEST:
        gSaveBlock1Ptr->pos.x = mapHeader->mapLayout->width;
        gSaveBlock1Ptr->pos.y -= connection->offset;
        break;
    case CONNECTION_SOUTH:
        gSaveBlock1Ptr->pos.x -= connection->offset;
        gSaveBlock1Ptr->pos.y = -y;
        break;
    case CONNECTION_NORTH:
        gSaveBlock1Ptr->pos.x -= connection->offset;
        gSaveBlock1Ptr->pos.y = mapHeader->mapLayout->height;
        break;
    default:
        errorf("invalid direction: %d", direction);
        break;
    }
}

bool8 CameraMove(int x, int y)
{
    enum Connection direction;
    const struct MapConnection *connection;
    int old_x, old_y;
    gCamera.active = FALSE;
    direction = GetPostCameraMoveMapBorderId(x, y);
    if (direction == CONNECTION_NONE || direction == CONNECTION_INVALID)
    {
        gSaveBlock1Ptr->pos.x += x;
        gSaveBlock1Ptr->pos.y += y;
    }
    else
    {
        SaveMapView();
        ClearMirageTowerPulseBlendEffect();
        old_x = gSaveBlock1Ptr->pos.x;
        old_y = gSaveBlock1Ptr->pos.y;
        connection = GetIncomingConnection(direction, gSaveBlock1Ptr->pos.x, gSaveBlock1Ptr->pos.y);
        assertf(connection)
        {
            return gCamera.active;
        }

        // BEGIN URANIUM PATHFINDER SLICE — connection id remap
        u8 oldMapGroup = gSaveBlock1Ptr->location.mapGroup;
        u8 oldMapNum = gSaveBlock1Ptr->location.mapNum;
        const struct Tileset *oldPrimaryTileset = gMapHeader.mapLayout->primaryTileset;
        const u16 *viewRemap;
        // END URANIUM PATHFINDER SLICE
        SetPositionFromConnection(connection, direction, x, y);
        LoadMapFromCameraTransition(connection->mapGroup, connection->mapNum);
        gCamera.active = TRUE;
        gCamera.x = old_x - gSaveBlock1Ptr->pos.x;
        gCamera.y = old_y - gSaveBlock1Ptr->pos.y;
        gSaveBlock1Ptr->pos.x += x;
        gSaveBlock1Ptr->pos.y += y;
        // BEGIN URANIUM PATHFINDER SLICE — connection id remap
        // location is now the new map, so this is the new map's table for
        // viewing the map just left (NULL = vanilla).
        viewRemap = UraniumGetConnectionRemap(oldMapGroup, oldMapNum);
        if (viewRemap == NULL && gMapHeader.mapLayout->primaryTileset == oldPrimaryTileset)
        {
            MoveMapViewToBackup(direction);
        }
        else
        {
            // Cross-tileset crossing: the saved view holds the OLD map's ids, and
            // copying it back would overwrite the new map's own cells with a lossy
            // round trip (unmappable ids fall back to void). InitMap already loaded
            // the new grid with correct ids, so drop the saved view instead — the
            // only loss is runtime metatile edits in view at the seam.
            ClearSavedMapView();
            // On-screen BG tiles still index the old tileset(s): redraw the whole
            // view from the new layout. The caller advances the BG tile offset and
            // draws the incoming edge only after we return, so draw at the
            // pre-step position to stay aligned with the current tile offset.
            gSaveBlock1Ptr->pos.x -= x;
            gSaveBlock1Ptr->pos.y -= y;
            DrawWholeMapView();
            gSaveBlock1Ptr->pos.x += x;
            gSaveBlock1Ptr->pos.y += y;
        }
        // END URANIUM PATHFINDER SLICE
    }

    BigMap_Track(); // RPG2GBA STREAMING: windowed backup grid follows the camera
    return gCamera.active;
}

static const struct MapConnection *GetIncomingConnection(enum Connection direction, int x, int y)
{
    int count;
    int i;
    const struct MapConnection *connection;
    const struct MapConnections *connections = gMapHeader.connections;

#ifdef UBFIX // UB: Multiple possible null dereferences
    if (connections == NULL || connections->connections == NULL)
        return NULL;
#endif
    count = connections->count;
    connection = connections->connections;
    for (i = 0; i < count; i++, connection++)
    {
        if (connection->direction == direction && IsPosInIncomingConnectingMap(direction, x, y, connection) == TRUE)
            return connection;
    }
    return NULL;
}

static bool8 IsPosInIncomingConnectingMap(enum Connection direction, int x, int y, const struct MapConnection *connection)
{
    struct MapHeader const *mapHeader;
    mapHeader = GetMapHeaderFromConnection(connection);
    switch (direction)
    {
    case CONNECTION_SOUTH:
    case CONNECTION_NORTH:
        return IsCoordInIncomingConnectingMap(x, gMapHeader.mapLayout->width, mapHeader->mapLayout->width, connection->offset);
    case CONNECTION_WEST:
    case CONNECTION_EAST:
        return IsCoordInIncomingConnectingMap(y, gMapHeader.mapLayout->height, mapHeader->mapLayout->height, connection->offset);
    default:
        return FALSE;
    }
}

static bool8 IsCoordInIncomingConnectingMap(int coord, int srcMax, int destMax, int offset)
{
    int offset2;
    offset2 = offset;

    if (offset2 < 0)
        offset2 = 0;

    if (destMax + offset < srcMax)
        srcMax = destMax + offset;

    if (offset2 <= coord && coord <= srcMax)
        return TRUE;

    return FALSE;
}

static int IsCoordInConnectingMap(int coord, int max)
{
    if (coord >= 0 && coord < max)
        return TRUE;

    return FALSE;
}

static int IsPosInConnectingMap(const struct MapConnection *connection, int x, int y)
{
    struct MapHeader const *mapHeader;
    mapHeader = GetMapHeaderFromConnection(connection);
    switch (connection->direction)
    {
    case CONNECTION_SOUTH:
    case CONNECTION_NORTH:
        return IsCoordInConnectingMap(x - connection->offset, mapHeader->mapLayout->width);
    case CONNECTION_WEST:
    case CONNECTION_EAST:
        return IsCoordInConnectingMap(y - connection->offset, mapHeader->mapLayout->height);
    }
    return FALSE;
}

const struct MapConnection *GetMapConnectionAtPos(s16 x, s16 y)
{
    int count;
    const struct MapConnection *connection;
    int i;
    enum Connection direction;
    if (!gMapHeader.connections)
    {
        return NULL;
    }
    else
    {
        count = gMapHeader.connections->count;
        connection = gMapHeader.connections->connections;
        for (i = 0; i < count; i++, connection++)
        {
            direction = connection->direction;
            if ((direction == CONNECTION_DIVE || direction == CONNECTION_EMERGE)
             || (direction == CONNECTION_NORTH && y > MAP_OFFSET - 1)
             || (direction == CONNECTION_SOUTH && y < gMapHeader.mapLayout->height + MAP_OFFSET)
             || (direction == CONNECTION_WEST && x > MAP_OFFSET - 1)
             || (direction == CONNECTION_EAST && x < gMapHeader.mapLayout->width + MAP_OFFSET))
            {
                continue;
            }
            if (IsPosInConnectingMap(connection, x - MAP_OFFSET, y - MAP_OFFSET) == TRUE)
            {
                return connection;
            }
        }
    }
    return NULL;
}

void SetCameraFocusCoords(u16 x, u16 y)
{
    gSaveBlock1Ptr->pos.x = x - MAP_OFFSET;
    gSaveBlock1Ptr->pos.y = y - MAP_OFFSET;
}

void GetCameraFocusCoords(u16 *x, u16 *y)
{
    *x = gSaveBlock1Ptr->pos.x + MAP_OFFSET;
    *y = gSaveBlock1Ptr->pos.y + MAP_OFFSET;
}

static void UNUSED SetCameraCoords(u16 x, u16 y)
{
    gSaveBlock1Ptr->pos.x = x;
    gSaveBlock1Ptr->pos.y = y;
}

void GetCameraCoords(u16 *x, u16 *y)
{
    *x = gSaveBlock1Ptr->pos.x;
    *y = gSaveBlock1Ptr->pos.y;
}

void MapGridSetMetatileImpassabilityAt(int x, int y, bool32 impassable)
{
    if (AreCoordsWithinMapGridBounds(x, y))
    {
        // BEGIN RPG2GBA STREAMING — windowed backup grid
        if (gBigMap.active)
        {
            u16 block = BigMapGetBlock(x, y);
            BigMapSetBlock(x, y, impassable ? (block | MAPGRID_COLLISION_MASK) : (block & ~MAPGRID_COLLISION_MASK));
            return;
        }
        // END RPG2GBA STREAMING
        if (impassable)
            gBackupMapLayout.map[x + gBackupMapLayout.width * y] |= MAPGRID_COLLISION_MASK;
        else
            gBackupMapLayout.map[x + gBackupMapLayout.width * y] &= ~MAPGRID_COLLISION_MASK;
    }
}

static bool8 SkipCopyingMetatileFromSavedMap(u16 *mapBlock, u16 mapWidth, u8 yMode)
{
    if (yMode == 0xFF)
        return FALSE;

    if (yMode == 0)
        mapBlock -= mapWidth;
    else
        mapBlock += mapWidth;

    if (IsLargeBreakableDecoration(UNPACK_METATILE(*mapBlock), yMode) == TRUE)
        return TRUE;
    return FALSE;
}

static void CopyTilesetToVram(struct Tileset const *tileset, u16 numTiles, u16 offset)
{
    if (tileset)
    {
        if (!tileset->isCompressed)
            LoadBgTiles(2, tileset->tiles, numTiles * 32, offset);
        else
            DecompressAndCopyTileDataToVram(2, tileset->tiles, numTiles * 32, offset, 0);
    }
}

static void CopyTilesetToVramUsingHeap(struct Tileset const *tileset, u16 numTiles, u16 offset)
{
    if (tileset)
    {
        if (!tileset->isCompressed)
            LoadBgTiles(2, tileset->tiles, numTiles * 32, offset);
        else
            DecompressAndLoadBgGfxUsingHeap(2, tileset->tiles, numTiles * 32, offset, 0);
    }
}

// Below two are dummied functions from FRLG, used to tint the overworld palettes for the Quest Log
static void ApplyGlobalTintToPaletteEntries(u16 offset, u16 size)
{

}

static void UNUSED ApplyGlobalTintToPaletteSlot(u8 slot, u8 count)
{

}

static void LoadTilesetPalette(struct Tileset const *tileset, u16 destOffset, u16 size, bool8 skipFaded, u32 numPalsInPrimary)
{
    if (tileset)
    {
        if (tileset->isSecondary == FALSE)
        {
            if (skipFaded)
                CpuFastCopy(tileset->palettes, &gPlttBufferUnfaded[destOffset], size); // always word-aligned
            else
                LoadPaletteFast(tileset->palettes, destOffset, size);
            gPlttBufferFaded[destOffset] = gPlttBufferUnfaded[destOffset] = RGB_BLACK;
            ApplyGlobalTintToPaletteEntries(destOffset + 1, (size - 2) >> 1);
        }
        else if (tileset->isSecondary == TRUE)
        {
            // All 'gTilesetPalettes_' arrays should have ALIGNED(4) in them,
            // but we use SmartCopy here just in case they don't
            if (skipFaded)
                CpuCopy16(tileset->palettes[numPalsInPrimary], &gPlttBufferUnfaded[destOffset], size);
            else
                LoadPaletteFast(tileset->palettes[numPalsInPrimary], destOffset, size);
        }
        else
        {
            LoadPalette((const u16 *)tileset->palettes, destOffset, size);
            ApplyGlobalTintToPaletteEntries(destOffset, size >> 1);
        }
    }
}

// BEGIN RPG2GBA STREAMING — a streamed layout has no whole-tileset copy: the primary
// load starts the tile cache, and the secondary load is a no-op once it runs.
static bool32 StreamPrimaryLoad(struct MapLayout const *mapLayout)
{
    return FieldStream_OnTilesetLoad(mapLayout);
}

static bool32 StreamSecondaryLoad(struct MapLayout const *mapLayout)
{
    if (!FieldStream_IsLayoutStreamed(mapLayout))
        return FALSE;
    if (gFieldStream.source != mapLayout->primaryTileset)
        FieldStream_OnTilesetLoad(mapLayout);
    return TRUE;
}
// END RPG2GBA STREAMING

void CopyPrimaryTilesetToVram(struct MapLayout const *mapLayout)
{
    // BEGIN RPG2GBA STREAMING
    if (StreamPrimaryLoad(mapLayout))
        return;
    // END RPG2GBA STREAMING
    CopyTilesetToVram(mapLayout->primaryTileset, GetNumTilesInPrimary(mapLayout), 0);
}

void CopySecondaryTilesetToVram(struct MapLayout const *mapLayout)
{
    // BEGIN RPG2GBA STREAMING
    if (StreamSecondaryLoad(mapLayout))
        return;
    // END RPG2GBA STREAMING
    CopyTilesetToVram(mapLayout->secondaryTileset, NUM_TILES_TOTAL - GetNumTilesInPrimary(mapLayout), GetNumTilesInPrimary(mapLayout));
}

void CopySecondaryTilesetToVramUsingHeap(struct MapLayout const *mapLayout)
{
    // BEGIN RPG2GBA STREAMING
    if (StreamSecondaryLoad(mapLayout))
        return;
    if (FieldStream_SeamCopyTiles(mapLayout->secondaryTileset, NUM_TILES_TOTAL - GetNumTilesInPrimary(mapLayout), GetNumTilesInPrimary(mapLayout)))
        return;
    // END RPG2GBA STREAMING
    CopyTilesetToVramUsingHeap(mapLayout->secondaryTileset, NUM_TILES_TOTAL - GetNumTilesInPrimary(mapLayout), GetNumTilesInPrimary(mapLayout));
}

static void LoadPrimaryTilesetPalette(struct MapLayout const *mapLayout)
{
    LoadTilesetPalette(mapLayout->primaryTileset, 0, GetNumPalsInPrimary(mapLayout) * PLTT_SIZE_4BPP, FALSE, GetNumPalsInPrimary(mapLayout));
}

void LoadSecondaryTilesetPalette(struct MapLayout const *mapLayout, bool8 skipFaded)
{
    LoadTilesetPalette(mapLayout->secondaryTileset, GetNumPalsInPrimary(mapLayout) * 16, (NUM_PALS_TOTAL - GetNumPalsInPrimary(mapLayout)) * PLTT_SIZE_4BPP, skipFaded, GetNumPalsInPrimary(mapLayout));
}

// BEGIN URANIUM PATHFINDER SLICE — connection id remap
// Primary-tileset counterparts of the secondary reload used by
// LoadMapFromCameraTransition, for connections that change primary tileset.
void UraniumCopyPrimaryTilesetToVramUsingHeap(struct MapLayout const *mapLayout)
{
    // BEGIN RPG2GBA STREAMING
    if (StreamPrimaryLoad(mapLayout))
        return;
    if (FieldStream_SeamCopyTiles(mapLayout->primaryTileset, GetNumTilesInPrimary(mapLayout), 0))
        return;
    // END RPG2GBA STREAMING
    CopyTilesetToVramUsingHeap(mapLayout->primaryTileset, GetNumTilesInPrimary(mapLayout), 0);
}

void UraniumLoadPrimaryTilesetPalette(struct MapLayout const *mapLayout, bool8 skipFaded)
{
    LoadTilesetPalette(mapLayout->primaryTileset, 0, GetNumPalsInPrimary(mapLayout) * PLTT_SIZE_4BPP, skipFaded, GetNumPalsInPrimary(mapLayout));
}
// END URANIUM PATHFINDER SLICE

void CopyMapTilesetsToVram(struct MapLayout const *mapLayout)
{
    // BEGIN RPG2GBA STREAMING
    if (StreamPrimaryLoad(mapLayout))
        return;
    // END RPG2GBA STREAMING
    if (mapLayout)
    {
        CopyTilesetToVramUsingHeap(mapLayout->primaryTileset, GetNumTilesInPrimary(mapLayout), 0);
        CopyTilesetToVramUsingHeap(mapLayout->secondaryTileset, NUM_TILES_TOTAL - GetNumTilesInPrimary(mapLayout), GetNumTilesInPrimary(mapLayout));
    }
}

void LoadMapTilesetPalettes(struct MapLayout const *mapLayout)
{
    if (mapLayout)
    {
        LoadPrimaryTilesetPalette(mapLayout);
        LoadSecondaryTilesetPalette(mapLayout, FALSE);
    }
}
