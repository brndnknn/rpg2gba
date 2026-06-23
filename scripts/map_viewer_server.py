# ruff: noqa: E501
"""Thin stdlib HTTP server for the Uranium map viewer (Phase B1).

Serves the shared MAP_VIEWER_HTML in SERVER mode with lazy tile/metatile
rendering via /api/* endpoints.  Zero external deps — stdlib only.

Routes:
  GET /                            -> map listing
  GET /map/<id>                    -> viewer HTML (server mode, lazy images)
  GET /palettes/<id>               -> palette inspector HTML (server mode, lazy images)
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
from map_graph import build_index, map_relationships  # noqa: E402
from map_viewer_common import (  # noqa: E402
    MAP_VIEWER_HTML,
    _load_dotenv,
    build_map_data,
    render_metatile_png,
    render_tile_png,
)
from palette_page import PALETTE_VIEWER_HTML  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_RE_MAP_PAGE = re.compile(r"^/map/(\d+)$")
_RE_PAL_PAGE = re.compile(r"^/palettes/(\d+)$")
_RE_API_MAP = re.compile(r"^/api/map/(\d+)$")
_RE_API_TILE = re.compile(r"^/api/tile/(\d+)/(\d+)\.png$")
_RE_API_META = re.compile(r"^/api/metatile/(\d+)/(\d+)\.png$")

_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"

# Landing page: searchable, tree-grouped map index.  Data (build_index()) is
# injected as JSON at __INDEX_DATA__ and rendered client-side, mirroring the
# config-blob pattern the map/palette pages use.
_INDEX_HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Uranium Map Index</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1a1a;color:#ddd;font:13px/1.5 monospace}
header{background:#252525;border-bottom:1px solid #444;padding:10px 14px;position:sticky;top:0;z-index:5}
h1{color:#8cf;font-size:16px;margin-bottom:8px}
#q{width:100%;max-width:480px;background:#111;border:1px solid #555;color:#eee;font:13px monospace;padding:6px 8px;border-radius:3px}
#meta{color:#777;font-size:11px;margin-top:6px}
#tree{padding:10px 14px 40px}
ul{list-style:none;margin:0;padding-left:18px}
#tree>ul{padding-left:0}
li{margin:1px 0}
.row{display:flex;align-items:center;gap:8px;padding:2px 4px;border-radius:3px}
.row:hover{background:#222}
.mid{color:#666;flex-shrink:0;width:50px}
.mname{color:#cde;flex:1;min-width:0;text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mname:hover{color:#fff;text-decoration:underline}
.lnk{color:#5af;text-decoration:none;font-size:11px;flex-shrink:0}
.lnk:hover{text-decoration:underline}
.toggle{cursor:pointer;color:#888;width:12px;flex-shrink:0;user-select:none;text-align:center}
.collapsed>ul{display:none}
.hidden{display:none}
@media (max-width:600px){.row{gap:5px;min-height:30px}.mid{width:42px}}
</style></head><body>
<header>
  <h1>Uranium Map Index</h1>
  <input id="q" type="search" placeholder="filter by map id or name… (e.g. 32, moki, gym)" autocomplete="off">
  <div id="meta"></div>
</header>
<div id="tree"></div>
<script>
const IDX = __INDEX_DATA__;
const pad = function(n){ return String(n).padStart(3,'0'); };
const esc = function(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
function nodeHTML(n){
  const hasKids = n.children && n.children.length;
  const tgl = hasKids ? '<span class="toggle" onclick="tog(this)">&#9662;</span>' : '<span class="toggle"></span>';
  let h = '<li data-id="'+n.id+'" data-name="'+esc((n.name||'').toLowerCase())+'">';
  h += '<div class="row">'+tgl;
  h += '<span class="mid">M'+pad(n.id)+'</span>';
  h += '<a class="mname" href="/map/'+n.id+'">'+esc(n.name||('Map'+pad(n.id)))+'</a>';
  h += '<a class="lnk" href="/map/'+n.id+'">map</a>';
  h += '<a class="lnk" href="/palettes/'+n.id+'">pal</a>';
  h += '</div>';
  if (hasKids){ h += '<ul>'; n.children.forEach(function(c){ h += nodeHTML(c); }); h += '</ul>'; }
  h += '</li>';
  return h;
}
function render(){
  let h = '<ul>';
  IDX.tree.forEach(function(n){ h += nodeHTML(n); });
  h += '</ul>';
  document.getElementById('tree').innerHTML = h;
  document.getElementById('meta').textContent = IDX.maps.length + ' maps · ' + IDX.tree.length + ' top-level groups';
}
function tog(el){
  const li = el.closest('li');
  li.classList.toggle('collapsed');
  el.innerHTML = li.classList.contains('collapsed') ? '▸' : '▾';
}
function filterTree(q){
  q = q.trim().toLowerCase();
  const lis = document.querySelectorAll('#tree li');
  if (!q){ lis.forEach(function(li){ li.classList.remove('hidden'); }); return; }
  lis.forEach(function(li){ li.classList.add('hidden'); });
  lis.forEach(function(li){
    const name = li.dataset.name || '';
    const idStr = pad(parseInt(li.dataset.id,10));
    const hit = name.indexOf(q) !== -1 || idStr.indexOf(q) !== -1 || String(li.dataset.id).indexOf(q) !== -1;
    if (hit){
      let cur = li;
      while (cur && cur.id !== 'tree'){
        if (cur.tagName === 'LI'){ cur.classList.remove('hidden'); cur.classList.remove('collapsed'); }
        cur = cur.parentElement;
      }
    }
  });
}
document.getElementById('q').addEventListener('input', function(e){ filterTree(e.target.value); });
render();
</script></body></html>
"""


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
            elif m := _RE_PAL_PAGE.match(path):
                self._serve_palette_page(int(m.group(1)))
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
        index_json = json.dumps(build_index(), separators=(",", ":"))
        html = _INDEX_HTML.replace("__INDEX_DATA__", index_json)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _serve_map_page(self, map_id: int) -> None:
        data = build_map_data(map_id)
        config = {"mode": "server", "data": data, "graph": map_relationships(map_id)}
        config_json = json.dumps(config, separators=(",", ":"))
        html = MAP_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _serve_palette_page(self, map_id: int) -> None:
        data = build_map_data(map_id)
        config = {"mode": "server", "data": data, "graph": map_relationships(map_id)}
        config_json = json.dumps(config, separators=(",", ":"))
        html = PALETTE_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)
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
