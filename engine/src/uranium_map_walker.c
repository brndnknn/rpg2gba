// BEGIN URANIUM MAP WALKER
#include "global.h"
#include "uranium_map_walker.h"
#include "task.h"
#include "field_screen_effect.h"
#include "field_tasks.h"
#include "script.h"
#include "field_player_avatar.h"

#if URANIUM_MAP_WALKER == TRUE

#include "event_object_movement.h"
#include "fieldmap.h"
#include "sprite.h"
#include "field_weather.h"
#include "constants/weather.h"
#include "constants/rgb.h"

#define UWALKER_CURSOR_TAG  0x4B57

static bool8 sWalkerActive = FALSE;

// ---------------------------------------------------------------------------
// Cursor graphics (built into EWRAM at first map load, reused on warps)
// ---------------------------------------------------------------------------

EWRAM_DATA u8 sCursorTileBuffer[3 * 128] = {0};
static u16 sCursorPal[16];

// Pack a 16x16 4bpp image into 4 GBA 8x8 tiles (tile order: row-major).
// dst must be 128 bytes.  px[y][x] holds palette indices 0-15.
static void PackImage16(u8 *dst, const u8 px[16][16])
{
	int tileY, tileX, row, col;
	for (tileY = 0; tileY < 2; tileY++)
	{
		for (tileX = 0; tileX < 2; tileX++)
		{
			u8 *t = dst + (tileY * 2 + tileX) * 32;
			for (row = 0; row < 8; row++)
			{
				for (col = 0; col < 8; col += 2)
				{
					u8 lo = px[tileY * 8 + row][tileX * 8 + col]     & 0xF;
					u8 hi = px[tileY * 8 + row][tileX * 8 + col + 1] & 0xF;
					*t++ = lo | (hi << 4);
				}
			}
		}
	}
}

// ---------------------------------------------------------------------------
// OAM / anim / template
// ---------------------------------------------------------------------------

static const struct OamData sCursorOam = {
	.shape    = SPRITE_SHAPE(16x16),
	.size     = SPRITE_SIZE(16x16),
	.priority = 1,
};

// ANIMCMD_FRAME's value is a raw TILE offset, not a frame index (region_map's 16x16
// cursor uses FRAME(0)/FRAME(4)). 16x16 = 4 tiles per image, so: image0 (transparent) =
// tiles 0-3, image1 (ring) = tiles 4-7, image2 (white) = tiles 8-11.
// anim 0: transparent ↔ ring blink (normal tile)
static const union AnimCmd sCursorAnim0[] = {
	ANIMCMD_FRAME(0, 16),
	ANIMCMD_FRAME(4, 16),
	ANIMCMD_JUMP(0),
};

// anim 1: transparent ↔ solid-white flash (warp tile)
static const union AnimCmd sCursorAnim1[] = {
	ANIMCMD_FRAME(0, 16),
	ANIMCMD_FRAME(8, 16),
	ANIMCMD_JUMP(0),
};

static const union AnimCmd *const sCursorAnimTable[] = {
	sCursorAnim0,
	sCursorAnim1,
};

// const (-> ROM/.rodata): the data pointers are link-time-constant addresses of the
// runtime-filled EWRAM/bss buffers, so this is a valid const initializer. Keeping these
// non-const would place them in .data, which the GBA link script discards (link error).
static const struct SpriteSheet    sCursorSheet   = {sCursorTileBuffer, 3 * 128, UWALKER_CURSOR_TAG};
static const struct SpritePalette  sCursorPalette = {sCursorPal,                 UWALKER_CURSOR_TAG};

static void SpriteCB_UraniumCursor(struct Sprite *sprite);  // forward decl

static const struct SpriteTemplate sCursorSpriteTemplate = {
	.tileTag     = UWALKER_CURSOR_TAG,
	.paletteTag  = UWALKER_CURSOR_TAG,
	.oam         = &sCursorOam,
	.anims       = sCursorAnimTable,
	.images      = NULL,
	.affineAnims = gDummySpriteAffineAnimTable,
	.callback    = SpriteCB_UraniumCursor,
};

// ---------------------------------------------------------------------------
// Sprite callback: pins cursor to screen centre, switches anim on warp tiles
// ---------------------------------------------------------------------------

static void SpriteCB_UraniumCursor(struct Sprite *sprite)
{
	u8    id = gPlayerAvatar.objectEventId;
	s16   cx = gObjectEvents[id].currentCoords.x - MAP_OFFSET;
	s16   cy = gObjectEvents[id].currentCoords.y - MAP_OFFSET;
	bool8 onWarp = FALSE;
	u8    wantAnim;
	u8    i;

	// Pin to screen centre (exact pixel offset tuned by eye at boot gate)
	sprite->x = 120;
	sprite->y = 80;

	// Warp check
	if (gMapHeader.events != NULL)
	{
		for (i = 0; i < gMapHeader.events->warpCount; i++)
		{
			if (gMapHeader.events->warps[i].x == cx &&
			    gMapHeader.events->warps[i].y == cy)
			{
				onWarp = TRUE;
				break;
			}
		}
	}

	wantAnim = onWarp ? 1 : 0;
	if (sprite->data[0] != (s16)wantAnim)
	{
		sprite->data[0] = (s16)wantAnim;
		StartSpriteAnim(sprite, wantAnim);
	}
}

// ---------------------------------------------------------------------------
// Cursor create / destroy (safe to call on every map load / warp)
// ---------------------------------------------------------------------------

// Zero-init (bss); set to SPRITE_NONE at runtime on first build. A nonzero file-scope
// initializer would land in the discarded .data section (link error).
static u8 sCursorSpriteId;

static void UraniumWalker_CreateCursor(void)
{
	static bool8 sBuilt = FALSE;
	u8 px[16][16];
	u8 x, y;

	if (!sBuilt)
	{
		sCursorSpriteId = SPRITE_NONE;

		// image 0: fully transparent (index 0 everywhere)
		for (y = 0; y < 16; y++)
			for (x = 0; x < 16; x++)
				px[y][x] = 0;
		PackImage16(sCursorTileBuffer, px);

		// image 1: 2px black ring (index 1 on outer two pixels of all edges)
		for (y = 0; y < 16; y++)
			for (x = 0; x < 16; x++)
				px[y][x] = (x < 2 || x > 13 || y < 2 || y > 13) ? 1 : 0;
		PackImage16(sCursorTileBuffer + 128, px);

		// image 2: solid white (index 2 everywhere)
		for (y = 0; y < 16; y++)
			for (x = 0; x < 16; x++)
				px[y][x] = 2;
		PackImage16(sCursorTileBuffer + 256, px);

		// palette: slot 0 = transparent placeholder, 1 = black, 2 = white
		for (x = 0; x < 16; x++)
			sCursorPal[x] = 0x0000;
		sCursorPal[1] = 0x0000;  // black (GBA BGR555)
		sCursorPal[2] = 0x7FFF;  // white (GBA BGR555)

		sBuilt = TRUE;
	}

	// Free any stale sprite + VRAM tiles/palette from a prior map load
	if (sCursorSpriteId != SPRITE_NONE && sCursorSpriteId < MAX_SPRITES)
	{
		DestroySprite(&gSprites[sCursorSpriteId]);
		sCursorSpriteId = SPRITE_NONE;
	}
	FreeSpriteTilesByTag(UWALKER_CURSOR_TAG);
	FreeSpritePaletteByTag(UWALKER_CURSOR_TAG);

	LoadSpriteSheet(&sCursorSheet);
	LoadSpritePalette(&sCursorPalette);
	sCursorSpriteId = CreateSprite(&sCursorSpriteTemplate, 120, 80, 0);
	if (sCursorSpriteId < MAX_SPRITES)
		gSprites[sCursorSpriteId].data[0] = 0xFF;  // sentinel: force first-frame anim set
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// Flip the walker on BEFORE the map load (called from CB2_StartUraniumSlice), so the
// runtime gates (NPC spawn, collision clamp, step scripts) apply during the load itself.
void UraniumWalker_Begin(void)
{
	sWalkerActive = TRUE;
}

bool8 UraniumWalker_IsActive(void)
{
	return sWalkerActive;
}

// Walker task -- handles walker-specific input (A/B/R/L/Start).
// Movement is driven by the normal field control; collision override
// in event_object_movement.c clamps movement to map bounds.
static void Task_UraniumWalker(u8 taskId)
{
	// Steps 4-6 (cursor sprite, warp A/B, R reveal, L HUD, Start menu)
	// are added here in later phases.
}

// Called as gFieldCallback on walker boot (replaces FieldCB_WarpExitFadeFromBlack).
void UraniumWalker_FieldCB_MapLoad(void)
{
	FadeInFromBlack();
	sWalkerActive = TRUE;
	SetUpFieldTasks();            // installs step machinery for smooth movement
	UnlockPlayerFieldControls();
	SetPlayerInvisibility(TRUE);  // cursor replaces the player sprite
	CreateTask(Task_UraniumWalker, 80);
	SetCurrentAndNextWeatherNoDelay(WEATHER_NONE);  // raw display: no weather overlay
	UraniumWalker_CreateCursor();
}

#endif // URANIUM_MAP_WALKER == TRUE
// END URANIUM MAP WALKER
