# ruff: noqa: E501
"""Build a self-contained HTML map viewer for one or more Uranium maps.

Delegates data extraction and rendering to map_viewer_common; this script only
adds base64 encoding of all used tiles/metatiles and injects them as a STATIC-
mode config blob into the shared MAP_VIEWER_HTML template.

The emitted HTML is fully self-contained (no server, no external files) and
opens in any browser, surviving Taildrop to a phone as a fallback.

Usage:
    python scripts/build_map_viewer.py 32 49 48
    python scripts/build_map_viewer.py --all
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

# map_viewer_common is in the same scripts/ directory.
sys.path.insert(0, str(Path(__file__).parent))
from map_viewer_common import (  # noqa: E402
    MAP_VIEWER_HTML,
    _load_dotenv,
    _maps_dir,
    _output_base,
    build_map_data,
    render_metatile_png,
    render_tile_png,
)


def _b64_png(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def build_config(map_id: int) -> dict:
    """Build the STATIC-mode viewer config: map data + base64 tile/metatile images.

    Shared by the map viewer (build_html_static) and the palette inspector page
    (palette_page.build_palette_html) so both draw the exact same post-quant
    thumbnails without re-rendering.
    """
    data = build_map_data(map_id)

    # Collect distinct tile_ids used across all cells.
    used_tile_ids: set[int] = set()
    for cell in data["cells"]:
        for tid in cell["layers"]:
            if tid:
                used_tile_ids.add(tid)

    tile_images: dict[str, str] = {}
    for tid in sorted(used_tile_ids):
        try:
            tile_images[str(tid)] = _b64_png(render_tile_png(map_id, tid))
        except Exception as exc:
            print(f"    WARN: tile {tid} render failed: {exc}")

    # Render every metatile index that has a non-empty column key.
    metatile_images: dict[str, dict[str, str]] = {}
    colkeys_list: list[str] = data["colkeys_list"]
    for idx, ck_str in enumerate(colkeys_list):
        if ck_str == "[]":  # empty column -> skip (transparent, not rendered)
            continue
        try:
            bot = render_metatile_png(map_id, idx, "bottom")
            top = render_metatile_png(map_id, idx, "top")
            post_bot = render_metatile_png(map_id, idx, "post_bottom")
            post_top = render_metatile_png(map_id, idx, "post_top")
            metatile_images[str(idx)] = {
                "bottom": _b64_png(bot),
                "top": _b64_png(top),
                "post_bottom": _b64_png(post_bot),
                "post_top": _b64_png(post_top),
            }
        except Exception as exc:
            print(f"    WARN: metatile {idx} render failed: {exc}")

    return {
        "mode": "static",
        "data": data,
        "tile_images": tile_images,
        "metatile_images": metatile_images,
    }


def build_html_static(map_id: int) -> str:
    """Render all used tiles/metatiles to base64 and inject as STATIC-mode config."""
    config_json = json.dumps(build_config(map_id), separators=(",", ":"))
    return MAP_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    _load_dotenv()

    ap = argparse.ArgumentParser(
        description="Build self-contained HTML map viewer(s) for Uranium maps."
    )
    ap.add_argument("map_ids", nargs="*", type=int, metavar="MAP_ID",
                    help="One or more map IDs (e.g. 32 49 48)")
    ap.add_argument("--all", action="store_true", dest="all_maps",
                    help="Build viewers for all available maps")
    ap.add_argument("--out-dir", default=None,
                    help="Output directory (default: output/map_viewer/)")
    args = ap.parse_args()

    maps_dir = _maps_dir()
    out_dir = Path(args.out_dir) if args.out_dir else _output_base() / "map_viewer"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.all_maps:
        map_ids = sorted(
            int(p.stem.replace("Map", ""))
            for p in maps_dir.glob("Map*.json")
        )
        print(f"Building viewers for all {len(map_ids)} maps...")
    elif args.map_ids:
        map_ids = args.map_ids
    else:
        ap.error("Provide map IDs or --all")

    from palette_page import build_palette_html  # noqa: E402  (sibling scripts/ module)

    for map_id in map_ids:
        try:
            print(f"Processing Map{map_id:03d}...")
            html = build_html_static(map_id)
            out_path = out_dir / f"Map{map_id:03d}.html"
            out_path.write_text(html, encoding="utf-8")
            size_kb = len(html.encode("utf-8")) // 1024
            print(f"  -> {out_path}  ({size_kb} KB)")

            pal_html = build_palette_html(map_id)
            pal_path = out_dir / f"Map{map_id:03d}_palettes.html"
            pal_path.write_text(pal_html, encoding="utf-8")
            pal_kb = len(pal_html.encode("utf-8")) // 1024
            print(f"  -> {pal_path}  ({pal_kb} KB)")
        except Exception as exc:
            print(f"  ERROR Map{map_id:03d}: {exc}")
            raise

    print("Done.")


if __name__ == "__main__":
    main()
