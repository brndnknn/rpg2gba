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
};

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

#endif // GUARD_FIELD_STREAM_H
// END RPG2GBA STREAMING
