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
#include "gpu_regs.h"
#include "overworld.h"
#include "palette.h"

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

static bool32 SeamVisible(u32 slot)
{
    return (gFieldStream.seamVisible[slot >> 5] >> (slot & 31)) & 1;
}

static void SeamQueue(const u32 *src, u32 slot)
{
    if (gFieldStream.seamListCount < NUM_TILES_TOTAL)
    {
        gFieldStream.seamListSrc[gFieldStream.seamListCount] = src;
        gFieldStream.seamListSlot[gFieldStream.seamListCount] = slot;
        gFieldStream.seamListCount++;
    }
}

static void UploadTile(u32 tile, u32 slot)
{
    // During a seam swap a slot the displayed frame shows is written by SeamCommit:
    // SeamReady queues every such slot; one written after that queues itself.
    if (gFieldStream.seamState != FIELD_SEAM_IDLE && SeamVisible(slot))
    {
        if (gFieldStream.seamState == FIELD_SEAM_READY)
            SeamQueue(&gFieldStream.source->tiles[tile * (TILE_SIZE_4BPP / 4)], slot);
        return;
    }
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
    if (gFieldStream.seamState != FIELD_SEAM_IDLE)
        gFieldStream.seamStreamed = TRUE;
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
// frame; the second takes any free slot rather than fail. During a seam swap the
// sweeps also avoid slots the displayed frame shows (their upload waits for the
// VBlank), and a last sweep takes one of those rather than fail.
static u32 AllocSlot(void)
{
    u32 pass, n, slot;
    u32 first = gFieldStream.numPinned;
    u32 count = FIELD_STREAM_FIRST_DOOR_SLOT - first;
    bool32 seam = gFieldStream.seamState != FIELD_SEAM_IDLE;

    for (pass = 0; pass < 3; pass++)
    {
        if (pass == 2 && !seam)
            break;
        slot = gFieldStream.hand;
        for (n = 0; n < count; n++)
        {
            if (gFieldStream.slotRefs[slot] == 0
             && (pass == 2 || !seam || !SeamVisible(slot))
             && (pass >= 1 || gFieldStream.slotFreedGen[slot] != gFieldStream.gen))
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
// Seam swap (field_stream.h). Slots are visible if any of BG1-3's on-screen cells
// (31x21 from the current scroll, wrapping the 32x32 map) uses them.
void FieldStream_SeamBegin(void)
{
    u32 bg, r, c, x0, y0, slot;
    const u16 *map;

    CpuFill32(0, gFieldStream.seamVisible, sizeof(gFieldStream.seamVisible));
    x0 = (GetGpuReg(REG_OFFSET_BG1HOFS) >> 3) & 31;
    y0 = (GetGpuReg(REG_OFFSET_BG1VOFS) >> 3) & 31;
    for (bg = 1; bg <= 3; bg++)
    {
        map = (const u16 *)BG_SCREEN_ADDR(GetBgAttribute(bg, BG_ATTR_MAPBASEINDEX));
        for (r = 0; r < 21; r++)
        {
            for (c = 0; c < 31; c++)
            {
                slot = map[((y0 + r) & 31) * 32 + ((x0 + c) & 31)] & 0x3FF;
                gFieldStream.seamVisible[slot >> 5] |= 1u << (slot & 31);
            }
        }
    }
    sCharBase = (u8 *)BG_CHAR_ADDR(GetBgAttribute(2, BG_ATTR_CHARBASEINDEX));
    gFieldStream.seamCount[0] = 0;
    gFieldStream.seamCount[1] = 0;
    gFieldStream.seamStreamed = FALSE;
    gFieldStream.seamSavedPltDisabled = gPaletteFade.bufferTransferDisabled;
    gPaletteFade.bufferTransferDisabled = TRUE;
    gFieldStream.seamState = FIELD_SEAM_ARMED;
}

bool32 FieldStream_SeamCopyTiles(const struct Tileset *tileset, u32 numTiles, u32 offset)
{
    u32 i, slot, range;

    if (gFieldStream.seamState == FIELD_SEAM_IDLE || tileset == NULL || tileset->isCompressed)
        return FALSE;
    for (i = 0; i < numTiles; i++)
    {
        slot = offset + i;
        if (slot >= NUM_TILES_TOTAL)
            break;
        if (!SeamVisible(slot))
            CpuFastCopy(&tileset->tiles[i * (TILE_SIZE_4BPP / 4)], sCharBase + slot * TILE_SIZE_4BPP, TILE_SIZE_4BPP);
    }
    range = gFieldStream.seamCount[0] == 0 ? 0 : 1;
    gFieldStream.seamSrc[range] = tileset->tiles;
    gFieldStream.seamFirst[range] = offset;
    gFieldStream.seamCount[range] = numTiles;
    return TRUE;
}

// Builds the copy list for the swap VBlank here, in main-loop time, so the VBlank
// does nothing but copy: each visible slot the new view uses, from its source.
void FieldStream_SeamReady(void)
{
    u32 w, bits, slot, range, tile;

    if (gFieldStream.seamState != FIELD_SEAM_ARMED)
        return;
    gFieldStream.seamListCount = 0;
    for (w = 0; w < NUM_TILES_TOTAL / 32; w++)
    {
        bits = gFieldStream.seamVisible[w];
        while (bits != 0)
        {
            slot = w * 32 + __builtin_ctz(bits);
            bits &= bits - 1;
            if (gFieldStream.seamStreamed && gFieldStream.source != NULL)
            {
                if (slot < gFieldStream.numPinned)
                    tile = slot;
                else if (slot < FIELD_STREAM_FIRST_DOOR_SLOT && gFieldStream.slotRefs[slot] != 0)
                    tile = gFieldStream.slotTile[slot];
                else
                    tile = FIELD_STREAM_NO_TILE;
                if (tile != FIELD_STREAM_NO_TILE)
                    SeamQueue(&gFieldStream.source->tiles[tile * (TILE_SIZE_4BPP / 4)], slot);
            }
            for (range = 0; range < 2; range++)
            {
                if (slot >= gFieldStream.seamFirst[range]
                 && slot < gFieldStream.seamFirst[range] + gFieldStream.seamCount[range])
                    SeamQueue(&gFieldStream.seamSrc[range][(slot - gFieldStream.seamFirst[range]) * (TILE_SIZE_4BPP / 4)], slot);
            }
        }
    }
    gFieldStream.seamState = FIELD_SEAM_READY;
}

bool32 FieldStream_SeamHeld(void)
{
    return gFieldStream.seamState != FIELD_SEAM_IDLE;
}

void FieldStream_SeamCommit(void)
{
    u32 i;
    u8 *charBase = sCharBase;

    if (gFieldStream.seamState != FIELD_SEAM_READY)
        return;
    gFieldStream.seamVcountStart = REG_VCOUNT;
    for (i = 0; i < gFieldStream.seamListCount; i++)
        DmaCopy32(3, gFieldStream.seamListSrc[i], charBase + gFieldStream.seamListSlot[i] * TILE_SIZE_4BPP, TILE_SIZE_4BPP);
    DmaCopy32(3, gOverworldTilemapBuffer_Bg1, BG_SCREEN_ADDR(GetBgAttribute(1, BG_ATTR_MAPBASEINDEX)), BG_SCREEN_SIZE);
    DmaCopy32(3, gOverworldTilemapBuffer_Bg2, BG_SCREEN_ADDR(GetBgAttribute(2, BG_ATTR_MAPBASEINDEX)), BG_SCREEN_SIZE);
    DmaCopy32(3, gOverworldTilemapBuffer_Bg3, BG_SCREEN_ADDR(GetBgAttribute(3, BG_ATTR_MAPBASEINDEX)), BG_SCREEN_SIZE);
    gPaletteFade.bufferTransferDisabled = gFieldStream.seamSavedPltDisabled;
    gFieldStream.seamTiles = gFieldStream.seamListCount;
    gFieldStream.seamState = FIELD_SEAM_IDLE;
    gFieldStream.seamVcountEnd = REG_VCOUNT;
}
// END RPG2GBA STREAMING
