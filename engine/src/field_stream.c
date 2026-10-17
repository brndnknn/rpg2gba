// BEGIN RPG2GBA STREAMING — the streaming tile cache (reference/streaming_prototype_plan.md §3.3)
//
// A streamed map's tile pool can be larger than the 1024 BG tile slots. Only the
// tiles the 32x32 overworld tilemap ring buffer references are resident. Each slot
// is refcounted by the tilemap cells using it; field_camera.c acquires a slot for a
// cell's new word before releasing the word it overwrites, so the tilemap buffers
// themselves are the record of which slot each cell holds.
//
// Uploads are synchronous CPU copies. That is safe outside VBlank because a slot is
// only ever written while no tilemap cell references it: a freshly allocated slot has
// refcount 0, and a slot freed this frame is not reused until the next frame, by which
// time the tilemap copy that dropped it has reached VRAM.
#include "global.h"
#include "bg.h"
#include "fieldmap.h"
#include "field_stream.h"
#include "overworld.h"

EWRAM_DATA struct FieldStream gFieldStream = {0};

static u8 *sCharBase;

bool32 FieldStream_IsLayoutStreamed(const struct MapLayout *mapLayout)
{
    return mapLayout != NULL && mapLayout->primaryTileset != NULL
        && mapLayout->primaryTileset->streamMetatiles != NULL;
}

bool32 FieldStream_IsActive(void)
{
    return gFieldStream.source != NULL;
}

static void UploadTile(u32 tile, u32 slot)
{
    CpuFastCopy(&gFieldStream.source->tiles[tile * (TILE_SIZE_4BPP / 4)], sCharBase + slot * TILE_SIZE_4BPP, TILE_SIZE_4BPP);
    gFieldStream.uploads++;
}

static void Reset(const struct Tileset *tileset)
{
    u32 i;

    gFieldStream.source = tileset;
    gFieldStream.numTiles = tileset->numStreamTiles;
    gFieldStream.numPinned = tileset->numPinnedTiles;
    gFieldStream.hand = gFieldStream.numPinned;
    gFieldStream.gen = 1;
    gFieldStream.uploads = 0;
    gFieldStream.overflows = 0;
    gFieldStream.errors = 0;
    CpuFill16(0, gFieldStream.tileToSlot, sizeof(gFieldStream.tileToSlot));
    CpuFill16(FIELD_STREAM_NO_TILE, gFieldStream.slotTile, sizeof(gFieldStream.slotTile));
    CpuFill16(0, gFieldStream.slotRefs, sizeof(gFieldStream.slotRefs));
    memset(gFieldStream.slotFreedGen, 0, sizeof(gFieldStream.slotFreedGen));

    // Every cell's word is about to be released by the redraw, so the buffers must
    // hold nothing from before this reset.
    if (gOverworldTilemapBuffer_Bg1 != NULL)
        CpuFill16(0, gOverworldTilemapBuffer_Bg1, BG_SCREEN_SIZE);
    if (gOverworldTilemapBuffer_Bg2 != NULL)
        CpuFill16(0, gOverworldTilemapBuffer_Bg2, BG_SCREEN_SIZE);
    if (gOverworldTilemapBuffer_Bg3 != NULL)
        CpuFill16(0, gOverworldTilemapBuffer_Bg3, BG_SCREEN_SIZE);

    sCharBase = (u8 *)BG_CHAR_ADDR(GetBgAttribute(2, BG_ATTR_CHARBASEINDEX));
    for (i = 0; i < gFieldStream.numPinned; i++)
    {
        UploadTile(i, i);
        gFieldStream.slotTile[i] = i;
    }
}

bool32 FieldStream_OnTilesetLoad(const struct MapLayout *mapLayout)
{
    if (!FieldStream_IsLayoutStreamed(mapLayout))
    {
        gFieldStream.source = NULL;
        return FALSE;
    }
    Reset(mapLayout->primaryTileset);
    return TRUE;
}

void FieldStream_NewFrame(void)
{
    gFieldStream.gen++;
    if (gFieldStream.gen == 0)
        gFieldStream.gen = 1;
}

// Clock allocator over the managed slots. The first sweep skips slots freed this
// frame; the second takes any free slot rather than fail.
static u32 AllocSlot(void)
{
    u32 pass, n, slot;
    u32 first = gFieldStream.numPinned;
    u32 count = FIELD_STREAM_FIRST_DOOR_SLOT - first;

    for (pass = 0; pass < 2; pass++)
    {
        slot = gFieldStream.hand;
        for (n = 0; n < count; n++)
        {
            if (gFieldStream.slotRefs[slot] == 0
             && (pass == 1 || gFieldStream.slotFreedGen[slot] != gFieldStream.gen))
            {
                gFieldStream.hand = slot + 1 >= FIELD_STREAM_FIRST_DOOR_SLOT ? first : slot + 1;
                return slot;
            }
            slot++;
            if (slot >= FIELD_STREAM_FIRST_DOOR_SLOT)
                slot = first;
        }
    }
    return 0;
}

u16 FieldStream_Acquire(u32 wideWord)
{
    u32 tile = wideWord >> 16;
    u32 attrs = wideWord & 0xFC00;
    u32 slot, old;

    if (tile < gFieldStream.numPinned)
        return attrs | tile;
    if (tile >= gFieldStream.numTiles)
    {
        gFieldStream.errors++;
        return 0;
    }
    slot = gFieldStream.tileToSlot[tile];
    if (slot == 0)
    {
        slot = AllocSlot();
        if (slot == 0)
        {
            gFieldStream.overflows++;
            return 0;
        }
        old = gFieldStream.slotTile[slot];
        if (old != FIELD_STREAM_NO_TILE)
            gFieldStream.tileToSlot[old] = 0;
        gFieldStream.slotTile[slot] = tile;
        gFieldStream.tileToSlot[tile] = slot;
        UploadTile(tile, slot);
    }
    gFieldStream.slotRefs[slot]++;
    return attrs | slot;
}

void FieldStream_Release(u16 tilemapWord)
{
    u32 slot = tilemapWord & 0x3FF;

    if (slot < gFieldStream.numPinned || slot >= FIELD_STREAM_FIRST_DOOR_SLOT)
        return;
    if (gFieldStream.slotRefs[slot] == 0)
    {
        gFieldStream.errors++;
        return;
    }
    if (--gFieldStream.slotRefs[slot] == 0)
        gFieldStream.slotFreedGen[slot] = gFieldStream.gen;
}
// END RPG2GBA STREAMING
