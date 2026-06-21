"""Image pipeline step 2 — RMXP autotile flattener.

Render one RMXP autotile *variant* to a flat 32x32 RGBA tile, replicating
Uranium's own renderer (`reference/scripts_dump/039_TileDrawingHelper_v17.rb`
`bltSmallAutotile`). Uranium's map data stores the resolved variant baked into
the tile id (a cell holds `48*(slot+1) + variant`, variant 0..47), so we render
that variant directly — no neighbour recomputation.

Two template shapes (the discriminator in the original is *height*):
  - height == 32: an animation strip; every variant is just the 32x32 frame-0
    tile (`stretch_blt` of the whole tile). Variant is ignored.
  - otherwise (a 96x128 template, or N*96 wide when animated): the variant's 4
    quadrants are assembled from 16x16 pieces via the `AUTOTILE_TABLE`. We use
    frame 0 (anim offset 0).

The table is transcribed verbatim from the Ruby; it is indexed
`AUTOTILE_TABLE[variant >> 3][variant & 7]` -> [TL, TR, BL, BR], each a *1-based*
piece index into the template's 6-col x 8-row grid of 16x16 pieces.
"""
from __future__ import annotations

from PIL import Image

PIECE_PX = 16          # autotile template piece size
TEMPLATE_COLS = 6      # pieces per template row (96 px / 16)
TEMPLATE_ROWS = 8      # 128 px / 16
RMXP_TILE_PX = 32
FRAME_WIDTH = TEMPLATE_COLS * PIECE_PX  # 96 px per animation frame
STRIP_HEIGHT = 32      # a height-32 autotile is an animation strip

# Verbatim from 039_TileDrawingHelper_v17.rb lines 2-15. Outer index = variant>>3
# (0..5), inner = variant&7 (0..7); value = [TL, TR, BL, BR] 1-based piece ids.
AUTOTILE_TABLE: tuple[tuple[tuple[int, int, int, int], ...], ...] = (
    ((27, 28, 33, 34), (5, 28, 33, 34), (27, 6, 33, 34), (5, 6, 33, 34),
     (27, 28, 33, 12), (5, 28, 33, 12), (27, 6, 33, 12), (5, 6, 33, 12)),
    ((27, 28, 11, 34), (5, 28, 11, 34), (27, 6, 11, 34), (5, 6, 11, 34),
     (27, 28, 11, 12), (5, 28, 11, 12), (27, 6, 11, 12), (5, 6, 11, 12)),
    ((25, 26, 31, 32), (25, 6, 31, 32), (25, 26, 31, 12), (25, 6, 31, 12),
     (15, 16, 21, 22), (15, 16, 21, 12), (15, 16, 11, 22), (15, 16, 11, 12)),
    ((29, 30, 35, 36), (29, 30, 11, 36), (5, 30, 35, 36), (5, 30, 11, 36),
     (39, 40, 45, 46), (5, 40, 45, 46), (39, 6, 45, 46), (5, 6, 45, 46)),
    ((25, 30, 31, 36), (15, 16, 45, 46), (13, 14, 19, 20), (13, 14, 19, 12),
     (17, 18, 23, 24), (17, 18, 11, 24), (41, 42, 47, 48), (5, 42, 47, 48)),
    ((37, 38, 43, 44), (37, 6, 43, 44), (13, 18, 19, 24), (13, 14, 43, 44),
     (37, 42, 43, 48), (17, 18, 47, 48), (13, 18, 43, 48), (1, 2, 7, 8)),
)

# Quadrant draw order in the Ruby: i -> (i%2, i//2) -> TL, TR, BL, BR.
_QUADRANT_OFFSETS = ((0, 0), (PIECE_PX, 0), (0, PIECE_PX), (PIECE_PX, PIECE_PX))


def quad_pieces(variant: int) -> tuple[int, int, int, int]:
    """The 4 (1-based) template piece ids for an autotile variant (0..47)."""
    if not 0 <= variant < 48:
        raise ValueError(f"autotile variant {variant} out of range 0..47")
    return AUTOTILE_TABLE[variant >> 3][variant & 7]


def _piece_box(piece_1based: int) -> tuple[int, int, int, int]:
    """Frame-0 crop box for a 1-based template piece id."""
    pos = piece_1based - 1
    col, row = pos % TEMPLATE_COLS, pos // TEMPLATE_COLS
    x, y = col * PIECE_PX, row * PIECE_PX
    return (x, y, x + PIECE_PX, y + PIECE_PX)


def flatten_autotile(template: Image.Image, variant: int) -> Image.Image:
    """Render `variant` (0..47) of an autotile `template` to a 32x32 RGBA tile.

    Mirrors `bltSmallAutotile` at frame 0: a height-32 strip ignores the variant
    and returns its 32x32 frame-0 tile; a 96x128 template assembles 4 quadrants."""
    template = template.convert("RGBA")
    w, h = template.size

    if h == STRIP_HEIGHT:
        # Animation strip: frame 0 is the leading 32x32 tile; variant irrelevant.
        if w < RMXP_TILE_PX:
            raise ValueError(f"strip autotile too narrow: {w}x{h} (need >= 32 wide)")
        return template.crop((0, 0, RMXP_TILE_PX, RMXP_TILE_PX))

    # Standard template: must be at least one full 96x128 frame.
    if w < FRAME_WIDTH or h < TEMPLATE_ROWS * PIECE_PX:
        raise ValueError(
            f"autotile template {w}x{h} too small for a {FRAME_WIDTH}x"
            f"{TEMPLATE_ROWS * PIECE_PX} piece grid"
        )

    tile = Image.new("RGBA", (RMXP_TILE_PX, RMXP_TILE_PX), (0, 0, 0, 0))
    for piece, (ox, oy) in zip(quad_pieces(variant), _QUADRANT_OFFSETS):
        quad = template.crop(_piece_box(piece))
        tile.paste(quad, (ox, oy))
    return tile
