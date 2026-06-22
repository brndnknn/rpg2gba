"""Thin stdlib HTTP server for the Uranium map viewer (Phase B1).

Serves the shared MAP_VIEWER_HTML in SERVER mode with lazy tile/metatile
rendering via /api/* endpoints.  Zero external deps — stdlib only.

Routes:
  GET /                            -> map listing
  GET /map/<id>                    -> viewer HTML (server mode, lazy images)
  GET /api/map/<id>                -> build_map_data JSON
  GET /api/tile/<mapid>/<tid>.png  -> single RMXP tile PNG
  GET /api/metatile/<mapid>/<idx>.png?layer=bottom|top -> metatile PNG

Usage:
    python scripts/map_viewer_server.py --port 8765
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from map_viewer_common import (  # noqa: E402
    MAP_VIEWER_HTML,
    _load_dotenv,
    _maps_dir,
    build_map_data,
    render_metatile_png,
    render_tile_png,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_RE_MAP_PAGE = re.compile(r"^/map/(\d+)$")
_RE_API_MAP = re.compile(r"^/api/map/(\d+)$")
_RE_API_TILE = re.compile(r"^/api/tile/(\d+)/(\d+)\.png$")
_RE_API_META = re.compile(r"^/api/metatile/(\d+)/(\d+)\.png$")

_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:  # quieter logging
        log.debug(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if path in ("", "/"):
                self._serve_index()
            elif m := _RE_MAP_PAGE.match(path):
                self._serve_map_page(int(m.group(1)))
            elif m := _RE_API_MAP.match(path):
                self._serve_api_map(int(m.group(1)))
            elif m := _RE_API_TILE.match(path):
                self._serve_tile(int(m.group(1)), int(m.group(2)))
            elif m := _RE_API_META.match(path):
                layer = qs.get("layer", ["bottom"])[0]
                if layer not in ("bottom", "top", "post_bottom", "post_top"):
                    layer = "bottom"
                self._serve_metatile(int(m.group(1)), int(m.group(2)), layer)
            else:
                self._send(404, "text/plain", b"Not found")
        except (FileNotFoundError, KeyError, IndexError) as exc:
            log.warning("404 for %s: %s", self.path, exc)
            self._send(404, "text/plain", str(exc).encode())
        except Exception as exc:
            log.exception("500 for %s", self.path)
            self._send(500, "text/plain", str(exc).encode())

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    def _serve_index(self) -> None:
        maps_dir = _maps_dir()
        map_ids = sorted(
            int(p.stem.replace("Map", ""))
            for p in maps_dir.glob("Map*.json")
        )
        rows = "".join(f'<li><a href="/map/{mid}">Map{mid:03d}</a></li>\n' for mid in map_ids)
        body = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Map Viewer</title>"
            "<style>body{background:#1a1a1a;color:#ddd;font:14px monospace;padding:20px}"
            "a{color:#5af} li{margin:4px 0}</style></head><body>"
            f"<h2 style='color:#8cf'>Uranium Map Viewer</h2>"
            f"<p>{len(map_ids)} maps available</p><ul>{rows}</ul>"
            "</body></html>"
        )
        self._send(200, "text/html; charset=utf-8", body.encode("utf-8"))

    def _serve_map_page(self, map_id: int) -> None:
        data = build_map_data(map_id)
        config = {"mode": "server", "data": data}
        config_json = json.dumps(config, separators=(",", ":"))
        html = MAP_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _serve_api_map(self, map_id: int) -> None:
        data = build_map_data(map_id)
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self._send(200, "application/json", body)

    def _serve_tile(self, map_id: int, tile_id: int) -> None:
        png = render_tile_png(map_id, tile_id)
        self._send(200, "image/png", png, cache=_CACHE_IMMUTABLE)

    def _serve_metatile(self, map_id: int, idx: int, layer: str) -> None:
        png = render_metatile_png(map_id, idx, layer)
        self._send(200, "image/png", png, cache=_CACHE_IMMUTABLE)

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------

    def _send(
        self,
        status: int,
        content_type: str,
        body: bytes,
        cache: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    _load_dotenv()

    ap = argparse.ArgumentParser(description="Uranium map viewer local server (Phase B1).")
    ap.add_argument("--port", type=int, default=8765, help="TCP port (default: 8765)")
    ap.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    args = ap.parse_args()

    hostname = socket.gethostname()
    print("Map viewer server starting…")
    print(f"  http://{hostname}:{args.port}/   (LAN / Tailscale)")
    print(f"  http://localhost:{args.port}/")
    print("  Ctrl-C to stop.")

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
