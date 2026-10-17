// BEGIN RPG2GBA STREAMING — the streaming tile cache (reference/streaming_prototype_plan.md §3.3)
#ifndef GUARD_FIELD_STREAM_H
#define GUARD_FIELD_STREAM_H

#include "fieldmap.h"

// Largest tile pool a streamed tileset may have (the pipeline fails loud above it).
#define FIELD_STREAM_MAX_TILES 3072
// First VRAM slot the cache never hands out: field_door.c draws door frames into
// NUM_TILES_TOTAL-16 .. NUM_TILES_TOTAL-1.
#define FIELD_STREAM_FIRST_DOOR_SLOT (NUM_TILES_TOTAL - 16)
#define FIELD_STREAM_NO_TILE 0xFFFF

// Exported (not static) so the emulator screen check can read it from the map file.
// The offsets are mirrored in rpg2gba/playtest/screen_check.py; keep them in step.
struct FieldStream
{
    /*0x00*/ const struct Tileset *source; // the streamed primary tileset, NULL = inactive
    /*0x04*/ u16 numTiles;
    /*0x06*/ u16 numPinned;
    /*0x08*/ u16 hand;                     // allocator clock hand
    /*0x0A*/ u8 gen;                       // frame generation (slots freed this frame are held)
    /*0x0B*/ u8 camTileX;                  // field_camera.c's ring-buffer tile offsets,
    /*0x0C*/ u8 camTileY;                  // mirrored every CameraUpdate
    /*0x0D*/ u8 padding[3];
    /*0x10*/ u32 uploads;                  // tiles copied to VRAM since the last reset
    /*0x14*/ u32 overflows;                // allocations that found no free slot (drew tile 0)
    /*0x18*/ u32 errors;                   // refcount underflows / out-of-range tile ids
    /*0x1C*/ u16 tileToSlot[FIELD_STREAM_MAX_TILES]; // 0 = not resident
             u16 slotTile[NUM_TILES_TOTAL];          // FIELD_STREAM_NO_TILE = empty
             u16 slotRefs[NUM_TILES_TOTAL];          // tilemap cells using the slot
             u8 slotFreedGen[NUM_TILES_TOTAL];
             // Seam swap (a connection crossing that changes tileset): see field_stream.c.
             u32 seamVisible[NUM_TILES_TOTAL / 32]; // slots the displayed frame shows
             const u32 *seamSrc[2];                 // stock tile ranges deferred to VBlank
             u16 seamFirst[2];
             u16 seamCount[2];
             u16 seamTiles;                         // tiles the last swap copied in VBlank
             u8 seamState;                          // FIELD_SEAM_*
             u8 seamStreamed;                       // the new layout is streamed
             u8 seamSavedPltDisabled;
             u8 seamVcountStart;                    // VCOUNT at the last swap's start/end
             u8 seamVcountEnd;
             u16 seamListCount;                     // tiles queued for the swap VBlank
             u16 seamListSlot[NUM_TILES_TOTAL];
             const u32 *seamListSrc[NUM_TILES_TOTAL];
};

#define FIELD_SEAM_IDLE  0
#define FIELD_SEAM_ARMED 1 // tilesets changing; the displayed frame is held
#define FIELD_SEAM_READY 2 // new view drawn; swap at the next VBlank

extern struct FieldStream gFieldStream;

bool32 FieldStream_IsLayoutStreamed(const struct MapLayout *mapLayout);
bool32 FieldStream_IsActive(void);
// Called where the stock engine copies a whole tileset to VRAM. Starts the cache for
// a streamed layout (uploads the pinned tiles, clears the overworld tilemap buffers);
// turns it off for any other layout. Returns TRUE if the layout is streamed, in
// which case the caller must skip its whole-tileset copy.
bool32 FieldStream_OnTilesetLoad(const struct MapLayout *mapLayout);
void FieldStream_NewFrame(void);
// Tilemap word for one u32 streamed word: makes its tile resident and counts the use.
u16 FieldStream_Acquire(u32 wideWord);
// Drops the use a tilemap word held (no-op for pinned, door and unmanaged slots).
void FieldStream_Release(u16 tilemapWord);

// Seam swap. A connection crossing that changes tileset rewrites tiles, palettes and
// the tilemap; done piecemeal, the frames in between show the old tilemap over new
// tiles (a flash). Instead: SeamBegin (before the tileset loads) records which slots
// the displayed frame shows; tiles for every other slot are written at once, the
// visible ones are deferred; SeamReady (end of CameraUpdate) marks the new view
// complete; SeamCommit (start of the field VBlank) writes the deferred tiles and the
// tilemaps, and releases the held palette transfer, all in that one VBlank.
void FieldStream_SeamBegin(void);
// Stock-tileset copy during a seam swap. Returns FALSE (caller copies as usual) when
// no swap is armed or the tileset is compressed.
bool32 FieldStream_SeamCopyTiles(const struct Tileset *tileset, u32 numTiles, u32 offset);
void FieldStream_SeamReady(void);
void FieldStream_SeamCommit(void);
// TRUE while the displayed frame is held (skip scroll and tile-animation transfers).
bool32 FieldStream_SeamHeld(void);

#endif // GUARD_FIELD_STREAM_H
// END RPG2GBA STREAMING
