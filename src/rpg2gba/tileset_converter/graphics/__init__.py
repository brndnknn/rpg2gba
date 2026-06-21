"""Image pipeline (BUILD_PLAN §7) — quantize Uranium's real tileset art to GBA.

Greenfield PNG -> GBA-4bpp pipeline, built in stages:
  1. sources  — resolve an Uranium tileset_id to its on-disk art (tileset PNG +
                7 autotile templates).
  2. autotile — flatten an RMXP autotile (template + baked variant) to a 32x32 tile.
  3. raster   — render any Uranium tile_id to a 16x16 GBA-native tile (/2 downscale).
  4. quantize/pack (not yet built) — palettes + 4bpp + metatiles.bin.

Steps 1-3 are pure-PIL and produce 16x16 RGBA tiles; the quantization step (4)
is where GBA palette constraints + dependency choices get decided.
"""
