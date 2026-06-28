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
#include "main.h"
#include "overworld.h"
#include "window.h"
#include "menu.h"
#include "text.h"
#include "string_util.h"
#include "constants/weather.h"
#include "constants/rgb.h"
#include "constants/maps.h"

#define UWALKER_CURSOR_TAG  0x4B57

static bool8 sWalkerActive = FALSE;

// ---------------------------------------------------------------------------
// L-toggle debug HUD
// ---------------------------------------------------------------------------

// Window template modeled on debug.c:741 (sDebugMenuWindowTemplateMain).
// bg=0: the field uses BG0 for overlay text windows (same as the debug menus).
// baseBlock=1: all in-field debug overlay windows in debug.c use baseBlock=1;
// no field tileset data occupies tile-slot 1 on BG0 — the tile allocator
// starts there for transient text windows (16*4=64 tiles consumed, slots 1-64).
// paletteNum=15: standard for in-field window overlays throughout the codebase.
static const struct WindowTemplate sHudWindowTemplate = {
	.bg          = 0,
	.tilemapLeft = 1,
	.tilemapTop  = 1,
	.width       = 16,
	.height      = 4,
	.paletteNum  = 15,
	.baseBlock   = 1,
};

// Pokeemerald charmap-encoded string fragments for HUD line construction.
// 'M'=0xC7 '-'=0xAE ' '=0x00 '('=0x5C ','=0xB8 ')'=0x5D  (charmap.txt)
static const u8 sHudTxtM[]     = _("M");
static const u8 sHudTxtDash[]  = _("-");
static const u8 sHudTxtSp2P[]  = _("  (");
static const u8 sHudTxtComma[] = _(",");
static const u8 sHudTxtClose[] = _(")");
static const u8 sHudTxtMt[]    = _("mt ");

// BSS state (zero-init at startup; sHudOn=FALSE means HUD never accessed before L press).
static u8    sHudWindowId;  // valid only while sHudOn == TRUE
static bool8 sHudOn;

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

// ---------------------------------------------------------------------------
// Warp follow (A) / back-stack (B)
// ---------------------------------------------------------------------------

#define UWALKER_STACK_MAX 32

struct UWalkerLoc
{
	u8  mapGroup;
	u8  mapNum;
	s16 x;       // map-local tile coords (no MAP_OFFSET)
	s16 y;
};

static EWRAM_DATA struct UWalkerLoc sBackStack[UWALKER_STACK_MAX] = {0};
static u8    sBackDepth;     // bss
static bool8 sWarpPending;   // bss: set after issuing a warp, cleared on next map load

// Cursor map-local coords = the (hidden) player anchor's coords minus MAP_OFFSET.
static void UraniumWalker_GetCursorCoords(s16 *x, s16 *y)
{
	u8 id = gPlayerAvatar.objectEventId;
	*x = gObjectEvents[id].currentCoords.x - MAP_OFFSET;
	*y = gObjectEvents[id].currentCoords.y - MAP_OFFSET;
}

// Index of the warp at the cursor tile, or -1.
static s32 UraniumWalker_WarpAtCursor(void)
{
	s16 cx, cy;
	u8  i;

	if (gMapHeader.events == NULL)
		return -1;
	UraniumWalker_GetCursorCoords(&cx, &cy);
	for (i = 0; i < gMapHeader.events->warpCount; i++)
	{
		if (gMapHeader.events->warps[i].x == cx && gMapHeader.events->warps[i].y == cy)
			return i;
	}
	return -1;
}

static void UraniumWalker_PushBack(void)
{
	s16 cx, cy;

	if (sBackDepth >= UWALKER_STACK_MAX)
		return;  // stack full: drop the push rather than overwrite (cap depth)
	UraniumWalker_GetCursorCoords(&cx, &cy);
	sBackStack[sBackDepth].mapGroup = gSaveBlock1Ptr->location.mapGroup;
	sBackStack[sBackDepth].mapNum   = gSaveBlock1Ptr->location.mapNum;
	sBackStack[sBackDepth].x        = cx;
	sBackStack[sBackDepth].y        = cy;
	sBackDepth++;
}

// DoWarp arms gFieldCallback = FieldCB_DefaultWarpExit; override it so the walker
// reinstalls (cursor/weather/task/player-hide) on the destination map.
static void UraniumWalker_RearmAfterWarp(void)
{
	gFieldCallback = UraniumWalker_FieldCB_MapLoad;
}

// A on a warp tile: push current location, fire the warp like normal play.
static bool8 UraniumWalker_DoWarpFollow(void)
{
	s32 i = UraniumWalker_WarpAtCursor();
	const struct WarpEvent *w;

	if (i < 0)
		return FALSE;
	w = &gMapHeader.events->warps[i];
	UraniumWalker_PushBack();
	SetWarpDestinationToMapWarp(w->mapGroup, w->mapNum, w->warpId);
	DoWarp();
	UraniumWalker_RearmAfterWarp();
	return TRUE;
}

// B: pop the back-stack, warp to the exact tile we left (literal coords, WARP_ID_NONE).
static bool8 UraniumWalker_DoBack(void)
{
	struct UWalkerLoc *loc;

	if (sBackDepth == 0)
		return FALSE;
	sBackDepth--;
	loc = &sBackStack[sBackDepth];
	SetWarpDestination(loc->mapGroup, loc->mapNum, WARP_ID_NONE, (s8)loc->x, (s8)loc->y);
	DoWarp();
	UraniumWalker_RearmAfterWarp();
	return TRUE;
}

// ---------------------------------------------------------------------------
// HUD helpers: create / draw / destroy
// ---------------------------------------------------------------------------

static void UraniumWalker_CreateHud(void)
{
	LoadMessageBoxAndBorderGfx();
	sHudWindowId = AddWindow(&sHudWindowTemplate);
	DrawStdWindowFrame(sHudWindowId, FALSE);
	PutWindowTilemap(sHudWindowId);
	CopyWindowToVram(sHudWindowId, COPYWIN_FULL);
}

static void UraniumWalker_DestroyHud(void)
{
	ClearStdWindowAndFrameToTransparent(sHudWindowId, TRUE);
	RemoveWindow(sHudWindowId);
	sHudWindowId = WINDOW_NONE;
}

static void UraniumWalker_DrawHud(void)
{
	s16 cx, cy;
	u32 metatileId;
	u8 *p;

	UraniumWalker_GetCursorCoords(&cx, &cy);
	metatileId = MapGridGetMetatileIdAt(cx + MAP_OFFSET, cy + MAP_OFFSET);

	FillWindowPixelBuffer(sHudWindowId, PIXEL_FILL(1));

	// Line 1: M{group}-{num}  ({x},{y})
	p = StringCopy(gStringVar1, sHudTxtM);
	p = ConvertIntToDecimalStringN(p, gSaveBlock1Ptr->location.mapGroup, STR_CONV_MODE_LEFT_ALIGN, 3);
	p = StringCopy(p, sHudTxtDash);
	p = ConvertIntToDecimalStringN(p, gSaveBlock1Ptr->location.mapNum,   STR_CONV_MODE_LEFT_ALIGN, 3);
	p = StringCopy(p, sHudTxtSp2P);
	p = ConvertIntToDecimalStringN(p, (s32)cx,                           STR_CONV_MODE_LEFT_ALIGN, 3);
	p = StringCopy(p, sHudTxtComma);
	p = ConvertIntToDecimalStringN(p, (s32)cy,                           STR_CONV_MODE_LEFT_ALIGN, 3);
	StringCopy(p, sHudTxtClose);
	AddTextPrinterParameterized(sHudWindowId, FONT_SMALL, gStringVar1, 2, 2, TEXT_SKIP_DRAW, NULL);

	// Line 2: mt {metatileId}
	p = StringCopy(gStringVar2, sHudTxtMt);
	ConvertIntToDecimalStringN(p, (s32)metatileId, STR_CONV_MODE_LEFT_ALIGN, 5);
	AddTextPrinterParameterized(sHudWindowId, FONT_SMALL, gStringVar2, 2, 16, TEXT_SKIP_DRAW, NULL);

	PutWindowTilemap(sHudWindowId);
	CopyWindowToVram(sHudWindowId, COPYWIN_FULL);
}

// Walker task -- handles walker-specific input. Movement is driven by the normal
// field control; collision override (event_object_movement.c) clamps to map bounds.
// R reveal / L HUD / Start jump menu are added here in step 6.
static void Task_UraniumWalker(u8 taskId)
{
	if (sWarpPending)
		return;  // ignore input during a warp transition until the next map loads

	if (JOY_NEW(A_BUTTON))
	{
		if (UraniumWalker_DoWarpFollow())
			sWarpPending = TRUE;
	}
	else if (JOY_NEW(B_BUTTON))
	{
		if (UraniumWalker_DoBack())
			sWarpPending = TRUE;
	}
	else if (JOY_NEW(L_BUTTON))
	{
		sHudOn = !sHudOn;
		if (sHudOn)
			UraniumWalker_CreateHud();
		else
			UraniumWalker_DestroyHud();
	}

	// Redraw HUD every frame so coords + metatile stay current.
	if (sHudOn)
		UraniumWalker_DrawHud();
}

// Called as gFieldCallback on walker boot (replaces FieldCB_WarpExitFadeFromBlack).
void UraniumWalker_FieldCB_MapLoad(void)
{
	FadeInFromBlack();
	sWalkerActive = TRUE;
	sWarpPending = FALSE;         // new map ready: accept input again
	SetUpFieldTasks();            // installs step machinery for smooth movement
	UnlockPlayerFieldControls();
	SetPlayerInvisibility(TRUE);  // cursor replaces the player sprite
	if (FindTaskIdByFunc(Task_UraniumWalker) == TASK_NONE)
		CreateTask(Task_UraniumWalker, 80);
	SetCurrentAndNextWeatherNoDelay(WEATHER_NONE);  // raw display: no weather overlay
	UraniumWalker_CreateCursor();
	// The window system is reset on every map load, so the HUD windowId is stale
	// after any warp.  If the HUD was on, drop the stale id and reopen the window.
	if (sHudOn)
	{
		sHudWindowId = WINDOW_NONE;
		UraniumWalker_CreateHud();
	}
}

#endif // URANIUM_MAP_WALKER == TRUE
// END URANIUM MAP WALKER
