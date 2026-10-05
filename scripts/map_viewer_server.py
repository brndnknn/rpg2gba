# ruff: noqa: E501
"""Thin stdlib HTTP server for the Uranium map viewer (Phase B1).

Serves the shared MAP_VIEWER_HTML in SERVER mode with lazy tile/metatile
rendering via /api/* endpoints.  Zero external deps — stdlib only.

Routes:
  GET  /                            -> map listing
  GET  /map/<id>                    -> viewer HTML (server mode, lazy images)
  GET  /component/<id>              -> stitched viewer: all seam-connected maps as one canvas
  GET  /palettes/<id>               -> palette inspector HTML (server mode, lazy images)
  GET  /api/map/<id>                -> build_map_data JSON
  GET  /api/seamcheck/<id>          -> ROM seam check (neighbour strips missing from this map's pool)
  GET  /api/shared?maps=31,35,40    -> shared-tiles (RMXP id/image vs ROM metatile/8x8); or ?map=<id> = its seam component
  (?sp=1 on /map, /component, /palettes, /api/map, /api/metatile = seam-palette view)
  GET  /api/tile/<mapid>/<tid>.png  -> single RMXP tile PNG
  GET  /api/metatile/<mapid>/<idx>.png?layer=bottom|top -> metatile PNG
  GET  /api/atlas/<mapid>.png?layer=bottom|top|post_bottom|post_top -> every metatile of the
       map in one PNG (64-col grid of 16px cells; geometry in /api/map meta.atlas)
  GET  /api/feedback/<id>           -> this map's tile-feedback flags (JSON list)
  GET  /api/event/<mapid>/<eventid> -> per-event debug record (map_viewer_events.event_detail)
  GET  /api/beats/<mapid>           -> scenario beat markers for this map (map_viewer_events.beat_markers)
  POST /api/feedback                -> replace a map's flag list (body: {map_id, flags})
  POST /api/feedback/export         -> write a flag snapshot to output/map_feedback/ (server-side)
  POST /api/quantize                -> apply family-packer knobs (Advanced only)

Usage:
    python scripts/map_viewer_server.py --port 8765
"""
from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from map_graph import build_index, component_layout, map_relationships  # noqa: E402
import map_viewer_common  # noqa: E402
from map_viewer_common import (  # noqa: E402
    MAP_VIEWER_HTML,
    PALETTE_VIEWER_HTML,
    _load_dotenv,
    build_map_data,
    current_quantize_state,
    current_shared_palettes,
    shared_palettes_from_dict,
    export_feedback,
    get_quantize_params,
    load_feedback,
    params_from_dict,
    render_atlas_png,
    render_metatile_png,
    render_npc_png,
    render_tile_png,
    save_feedback,
    seam_check,
    shared_default_maps,
    shared_tiles,
    SeamSharedConflict,
    set_quantize_params,
)

# map_viewer_events is a sibling module owned by another agent; it may not
# exist on disk yet or may be mid-edit.  Import it defensively so a missing
# or broken module never takes down the whole viewer -- only the two routes
# that depend on it (/api/event, /api/beats) degrade, as a clean 503.
try:
    import map_viewer_events  # noqa: E402
except Exception as _exc:  # noqa: BLE001 - any import-time failure is fine here
    map_viewer_events = None
    _MAP_VIEWER_EVENTS_ERROR = str(_exc)
else:
    _MAP_VIEWER_EVENTS_ERROR = None

# Same defensive import for the chapter route viewer's data join: a broken
# module degrades only /api/chapter* to a 503.
try:
    import chapter_route_data  # noqa: E402
except Exception as _exc:  # noqa: BLE001
    chapter_route_data = None
    _CHAPTER_ROUTE_DATA_ERROR = str(_exc)
else:
    _CHAPTER_ROUTE_DATA_ERROR = None

# Serializes knob Applies: re-quantization mutates the shared module-level caches in
# map_viewer_common, so two concurrent POSTs (ThreadingHTTPServer) must not interleave.
_quant_lock = threading.Lock()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_RE_MAP_PAGE = re.compile(r"^/map/(\d+)$")
_RE_COMPONENT_PAGE = re.compile(r"^/component/(\d+)$")
_RE_PAL_PAGE = re.compile(r"^/palettes/(\d+)$")
_RE_API_MAP = re.compile(r"^/api/map/(\d+)$")
_RE_API_TILE = re.compile(r"^/api/tile/(\d+)/(\d+)\.png$")
_RE_API_META = re.compile(r"^/api/metatile/(\d+)/(\d+)\.png$")
_RE_API_ATLAS = re.compile(r"^/api/atlas/(\d+)\.png$")
# Sheet-name charset only (no '.' or '/'): closes off path traversal via the
# character_name URL segment before it ever reaches _resolve_sheet.
_RE_API_NPC = re.compile(r"^/api/npc/([A-Za-z0-9_\-]+)\.png$")
_RE_API_FEEDBACK = re.compile(r"^/api/feedback/(\d+)$")
_RE_API_SEAMCHECK = re.compile(r"^/api/seamcheck/(\d+)$")
# Segments captured loosely (not \d+) so a non-integer id falls through to our
# own 400 JSON response instead of the generic 404 catch-all.
_RE_API_EVENT = re.compile(r"^/api/event/([^/]+)/([^/]+)$")
_RE_API_BEATS = re.compile(r"^/api/beats/([^/]+)$")
# Chapter route viewer (reference/viewer/chapter_route_viewer.md).
_RE_CHAPTER_PAGE = re.compile(r"^/chapter/(CH\d+)$")
_RE_API_CHAPTER = re.compile(r"^/api/chapter/(CH\d+)$")
_RE_API_MAPPNG = re.compile(r"^/api/mappng/(\d+)\.png$")
_RE_CHAPTER_ASSET = re.compile(r"^/chapter-assets/(chapter\.(?:js|css))$")
_CHAPTER_ASSET_DIR = Path(__file__).parent / "map_viewer"
_CHAPTER_ASSET_TYPES = {"js": "text/javascript; charset=utf-8",
                        "css": "text/css; charset=utf-8"}

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
@media (max-width:600px){.row{gap:8px;min-height:40px}.mid{width:42px}.mname{padding:6px 0}.lnk{padding:8px 6px}.toggle{min-width:24px;padding:8px 0}}
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
    # Keep-alive: one TCP connection serves many requests (a page load is hundreds of
    # fetches over a high-latency link).  Requires Content-Length on EVERY response and
    # a fully-read request body on every POST, else the stream desyncs.
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:  # quieter logging
        log.debug(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        # Seam-palette toggle (?sp=1), threaded through every route whose output depends on it.
        sp = qs.get("sp", ["0"])[0] == "1"

        try:
            if path in ("", "/"):
                self._serve_index()
            elif m := _RE_MAP_PAGE.match(path):
                self._serve_map_page(int(m.group(1)), sp)
            elif m := _RE_COMPONENT_PAGE.match(path):
                self._serve_component_page(int(m.group(1)), sp)
            elif m := _RE_PAL_PAGE.match(path):
                self._serve_palette_page(int(m.group(1)), sp)
            elif m := _RE_API_MAP.match(path):
                self._serve_api_map(int(m.group(1)), sp)
            elif m := _RE_API_TILE.match(path):
                self._serve_tile(int(m.group(1)), int(m.group(2)))
            elif m := _RE_API_META.match(path):
                layer = qs.get("layer", ["bottom"])[0]
                if layer not in ("bottom", "top", "post_bottom", "post_top"):
                    layer = "bottom"
                self._serve_metatile(int(m.group(1)), int(m.group(2)), layer, sp)
            elif m := _RE_API_ATLAS.match(path):
                layer = qs.get("layer", ["bottom"])[0]
                if layer not in ("bottom", "top", "post_bottom", "post_top"):
                    layer = "bottom"
                self._serve_atlas(int(m.group(1)), layer, sp)
            elif m := _RE_API_SEAMCHECK.match(path):
                self._serve_seamcheck(int(m.group(1)))
            elif path == "/api/shared":
                self._serve_shared(qs)
            elif m := _RE_API_NPC.match(path):
                self._serve_npc(m.group(1))
            elif m := _RE_API_FEEDBACK.match(path):
                self._serve_feedback(int(m.group(1)))
            elif m := _RE_API_EVENT.match(path):
                self._serve_event(m.group(1), m.group(2))
            elif m := _RE_API_BEATS.match(path):
                self._serve_beats(m.group(1))
            elif m := _RE_CHAPTER_PAGE.match(path):
                self._serve_chapter_asset("chapter.html", "text/html; charset=utf-8")
            elif m := _RE_CHAPTER_ASSET.match(path):
                name = m.group(1)
                self._serve_chapter_asset(name, _CHAPTER_ASSET_TYPES[name.rsplit(".", 1)[1]])
            elif path == "/api/chapters":
                self._serve_chapter_api(None)
            elif m := _RE_API_CHAPTER.match(path):
                self._serve_chapter_api(m.group(1))
            elif m := _RE_API_MAPPNG.match(path):
                self._serve_mappng(int(m.group(1)))
            else:
                self._send(404, "text/plain", b"Not found")
        except (BrokenPipeError, ConnectionResetError):
            # The browser dropped the request (navigated away, or cancelled a
            # superseded image load) — nobody is left to send an error to.
            log.debug("client went away during %s", self.path)
        except SeamSharedConflict as exc:
            self._send(400, "text/plain", str(exc).encode())
        except (FileNotFoundError, KeyError, IndexError) as exc:
            log.warning("404 for %s: %s", self.path, exc)
            self._send(404, "text/plain", str(exc).encode())
        except Exception as exc:
            log.exception("500 for %s", self.path)
            self._send(500, "text/plain", str(exc).encode())

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        # Drain the body up front, whatever the route: an unread body on a keep-alive
        # connection would be parsed as the next request line.
        self._post_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if path == "/api/quantize":
                self._handle_quantize()
            elif path == "/api/feedback":
                self._handle_feedback()
            elif path == "/api/feedback/export":
                self._handle_feedback_export()
            else:
                self._send(404, "text/plain", b"Not found")
        except Exception as exc:
            log.exception("500 POST %s", self.path)
            self._send(500, "text/plain", str(exc).encode())

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    def _handle_quantize(self) -> None:
        """Apply new family-packer knobs, eagerly re-quantize the requesting map (so a
        bad value surfaces as a clean 400 instead of breaking the page reload), and
        return the new generation token.  On failure the previous params are restored."""
        body = json.loads(self._post_body or b"{}")
        params, max_pals = params_from_dict(body)
        map_id = int(body.get("map_id", 0))
        with _quant_lock:
            prev_params, prev_max = current_quantize_state()
            prev_shared = current_shared_palettes()
            gen = set_quantize_params(
                params, max_pals, shared_palettes=shared_palettes_from_dict(body)
            )
            try:
                build_map_data(map_id)  # eager re-quant; raises ValueError on bad knobs
            except ValueError as exc:
                set_quantize_params(prev_params, prev_max, shared_palettes=prev_shared)  # roll back; keep tool usable
                self._send(400, "application/json",
                           json.dumps({"error": str(exc)}).encode("utf-8"))
                return
        self._send(200, "application/json",
                   json.dumps({"generation": gen}).encode("utf-8"))

    def _handle_feedback(self) -> None:
        """Replace this map's whole tile-feedback flag list, persisted immediately to
        reference/map_feedback/MapNNN.json (whole-file rewrite; the list per map is
        always tiny). The client sends the full list on every Save/delete, so there is
        no per-flag key to manage. Responds with the now-persisted list."""
        body = json.loads(self._post_body or b"{}")
        map_id = int(body["map_id"])
        flags = body.get("flags", [])
        if not isinstance(flags, list):
            self._send(400, "application/json",
                       json.dumps({"error": "flags must be a list"}).encode("utf-8"))
            return
        save_feedback(map_id, flags)
        self._send(200, "application/json", json.dumps(flags).encode("utf-8"))

    def _handle_feedback_export(self) -> None:
        """Dump this map's flag list to output/map_feedback/MapNNN_feedback.json on the
        machine running the server — the viewer is usually driven from a phone, and the
        export is only useful next to the rest of the pipeline's output. Responds with
        the written path so the page can show where it landed."""
        body = json.loads(self._post_body or b"{}")
        map_id = int(body["map_id"])
        flags = body.get("flags", [])
        if not isinstance(flags, list):
            self._send(400, "application/json",
                       json.dumps({"error": "flags must be a list"}).encode("utf-8"))
            return
        path = export_feedback(map_id, flags)
        log.info("exported %d flag(s) for Map%03d -> %s", len(flags), map_id, path)
        self._send(200, "application/json",
                   json.dumps({"path": str(path), "count": len(flags)}).encode("utf-8"))

    def _serve_feedback(self, map_id: int) -> None:
        body = json.dumps(load_feedback(map_id)).encode("utf-8")
        self._send(200, "application/json", body)

    def _serve_event(self, map_id_str: str, event_id_str: str) -> None:
        """Per-event debug record from map_viewer_events.  Bad integers are a
        400, an unknown event is a clean 404, and the module being missing/
        broken is a 503 -- none of these should look like a server crash."""
        try:
            map_id = int(map_id_str)
            event_id = int(event_id_str)
        except ValueError:
            self._send(400, "application/json",
                       json.dumps({"error": "map_id and event_id must be integers"}).encode("utf-8"))
            return
        if map_viewer_events is None:
            self._send(503, "application/json",
                       json.dumps({"error": f"map_viewer_events unavailable: {_MAP_VIEWER_EVENTS_ERROR}"}).encode("utf-8"))
            return
        try:
            data = map_viewer_events.event_detail(map_id, event_id)
        except KeyError as exc:
            self._send(404, "application/json",
                       json.dumps({"error": str(exc)}).encode("utf-8"))
            return
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self._send(200, "application/json", body)

    def _serve_beats(self, map_id_str: str) -> None:
        """Scenario beat markers for a map from map_viewer_events.  Reads
        playtest run artifacts that change between runs -- never cached."""
        try:
            map_id = int(map_id_str)
        except ValueError:
            self._send(400, "application/json",
                       json.dumps({"error": "map_id must be an integer"}).encode("utf-8"))
            return
        if map_viewer_events is None:
            self._send(503, "application/json",
                       json.dumps({"error": f"map_viewer_events unavailable: {_MAP_VIEWER_EVENTS_ERROR}"}).encode("utf-8"))
            return
        data = map_viewer_events.beat_markers(map_id)
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self._send(200, "application/json", body)

    def _serve_chapter_asset(self, name: str, content_type: str) -> None:
        """Chapter route viewer page/assets, read per request (no inlining, no
        cache) so a front-end edit shows on the next reload."""
        body = (_CHAPTER_ASSET_DIR / name).read_bytes()
        self._send(200, content_type, body, cache="no-cache")

    def _serve_chapter_api(self, chapter: str | None) -> None:
        """/api/chapters (list) or /api/chapter/<CHnn> (joined payload).  Reads
        generator and playtest artifacts that change between runs -- never cached."""
        if chapter_route_data is None:
            self._send(503, "application/json",
                       json.dumps({"error": f"chapter_route_data unavailable: {_CHAPTER_ROUTE_DATA_ERROR}"}).encode("utf-8"))
            return
        data = (chapter_route_data.list_chapters() if chapter is None
                else chapter_route_data.chapter_payload(chapter))
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self._send(200, "application/json", body, cache="no-cache")

    def _serve_mappng(self, map_id: int) -> None:
        """Whole-map composite for the chapter page.  Not immutable: a knob
        Apply re-quantizes, so let the browser revalidate."""
        render = getattr(map_viewer_common, "render_map_png", None)
        if render is None:
            self._send(503, "text/plain", b"render_map_png not available")
            return
        self._send(200, "image/png", render(map_id), cache="no-cache")

    def _serve_index(self) -> None:
        index_json = json.dumps(build_index(), separators=(",", ":"))
        html = _INDEX_HTML.replace("__INDEX_DATA__", index_json)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _serve_map_page(self, map_id: int, seam: bool = False) -> None:
        data = build_map_data(map_id, seam)
        config = {"data": data, "graph": map_relationships(map_id),
                  "quant": get_quantize_params(), "seam": seam}
        config_json = json.dumps(config, separators=(",", ":"))
        html = MAP_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _serve_component_page(self, map_id: int, seam: bool = False) -> None:
        """Stitched view: every seam-connected map drawn in one shared cell space.

        The page ships the requested map's full data plus the component layout;
        the client fetches the other members via /api/map/<id> as they're needed.
        A map with no seam connections redirects to its single-map page.
        """
        layout = component_layout(map_id)
        if len(layout["members"]) <= 1:
            self.send_response(302)
            self.send_header("Location", f"/map/{map_id}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = build_map_data(map_id, seam)
        config = {"data": data, "graph": map_relationships(map_id),
                  "quant": get_quantize_params(), "component": layout, "seam": seam}
        config_json = json.dumps(config, separators=(",", ":"))
        html = MAP_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _serve_palette_page(self, map_id: int, seam: bool = False) -> None:
        data = build_map_data(map_id, seam)
        config = {"data": data, "graph": map_relationships(map_id),
                  "quant": get_quantize_params()}
        config_json = json.dumps(config, separators=(",", ":"))
        html = PALETTE_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _serve_api_map(self, map_id: int, seam: bool = False) -> None:
        data = build_map_data(map_id, seam)
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self._send(200, "application/json", body)

    def _serve_tile(self, map_id: int, tile_id: int) -> None:
        png = render_tile_png(map_id, tile_id)
        self._send(200, "image/png", png, cache=_CACHE_IMMUTABLE)

    def _serve_metatile(self, map_id: int, idx: int, layer: str, seam: bool = False) -> None:
        png = render_metatile_png(map_id, idx, layer, seam)
        self._send(200, "image/png", png, cache=_CACHE_IMMUTABLE)

    def _serve_atlas(self, map_id: int, layer: str, seam: bool = False) -> None:
        png = render_atlas_png(map_id, layer, seam)
        self._send(200, "image/png", png, cache=_CACHE_IMMUTABLE)

    def _serve_seamcheck(self, map_id: int) -> None:
        """ROM seam check JSON. Depends on on-disk maps, so never cached."""
        body = json.dumps(seam_check(map_id), separators=(",", ":")).encode("utf-8")
        self._send(200, "application/json", body, cache="no-cache")

    def _serve_shared(self, qs: dict[str, list[str]]) -> None:
        """Shared-tiles JSON: ``?maps=31,35,40`` or ``?map=31`` (its seam component)."""
        try:
            if "maps" in qs:
                ids = [int(s) for s in qs["maps"][0].split(",") if s.strip()]
            else:
                ids = shared_default_maps(int(qs["map"][0]))
            if len(set(ids)) < 2:
                raise ValueError("need at least two maps (?maps=a,b[,c] or ?map=<id> in a component)")
        except (ValueError, KeyError, IndexError) as exc:
            self._send(400, "text/plain", f"bad request: {exc}".encode())
            return
        body = json.dumps(shared_tiles(ids), separators=(",", ":")).encode("utf-8")
        self._send(200, "application/json", body, cache="no-cache")

    def _serve_npc(self, character_name: str) -> None:
        png = render_npc_png(character_name)
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
# Hot reload: watch imported source files, self-restart via os.execv on change.
#
# Watch set is re-derived from sys.modules on every poll rather than a
# hardcoded file list, so it automatically covers this script, the sibling
# scripts it imports, and whatever rpg2gba.tileset_converter.* modules it
# actually pulled in from src/ -- and picks up modules imported lazily after
# startup.  An edit to an unrelated converter the server never imported does
# not trigger a restart.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WATCH_EXCLUDE_PARTS = {".venv", "venv", "__pycache__"}
_WATCH_POLL_INTERVAL = 1.0
_WATCH_SETTLE_DELAY = 0.3
_BIND_RETRY_ATTEMPTS = 20
_BIND_RETRY_DELAY = 0.25


def _watched_files(root: Path) -> list[Path]:
    """Resolved paths of every currently-imported module's source file that
    lives under `root`, excluding .venv/venv/__pycache__ path components, plus
    the web-asset files under scripts/map_viewer/ (not Python, so not in
    sys.modules -- editing viewer.css/js should still trigger a restart).

    Re-derived fresh on every poll (see module docstring above) rather than
    cached, so lazily-imported modules join the watch set on a later cycle.
    """
    root = root.resolve()
    out: list[Path] = []
    asset_dir = Path(__file__).resolve().parent / "map_viewer"
    for asset in sorted(asset_dir.glob("*")):
        if asset.is_file():
            out.append(asset)
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if not file:
            continue
        path = Path(file)
        if path.suffix != ".py":
            continue
        try:
            path = path.resolve()
        except OSError:
            continue
        if _WATCH_EXCLUDE_PARTS & set(path.parts):
            continue
        try:
            path.relative_to(root)
        except ValueError:
            continue
        out.append(path)
    return out


def _snapshot(paths: list[Path]) -> dict[str, tuple[int, int]]:
    """Map path (as str) -> (mtime_ns, size) for each path that currently
    stats successfully.  A path that can't be stat'd (deleted, permission
    error) is simply omitted from the result -- not recorded as a sentinel.
    """
    snap: dict[str, tuple[int, int]] = {}
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            continue
        snap[str(path)] = (st.st_mtime_ns, st.st_size)
    return snap


def _changed_paths(
    old: dict[str, tuple[int, int]], new: dict[str, tuple[int, int]]
) -> list[str]:
    """Paths (from `old`) whose stats differ in `new`, or that vanished from
    `new` entirely.  A path present in `new` but not `old` is the watch set
    legitimately growing (a lazy import) and is NOT reported as a change --
    otherwise a mid-session lazy import would trigger a spurious restart.
    """
    changed: list[str] = []
    for path, stats in old.items():
        if new.get(path) != stats:
            changed.append(path)
    return changed


def _watch_loop(restart_argv: list[str], root: Path) -> None:
    """Background thread body: poll the watch set forever; on any change,
    settle briefly (multi-file editor saves land in a burst), flush output,
    and exec-replace this process with `restart_argv`.  Never returns.
    """
    snapshot = _snapshot(_watched_files(root))
    while True:
        time.sleep(_WATCH_POLL_INTERVAL)
        current = _snapshot(_watched_files(root))
        changed = _changed_paths(snapshot, current)
        if not changed:
            snapshot = current
            continue
        log.info("source change detected (%s) -- restarting", ", ".join(changed))
        time.sleep(_WATCH_SETTLE_DELAY)
        # Settle pass: take one more snapshot so a file mid-write during the
        # burst is captured at its final stats.  We're restarting regardless;
        # this only avoids logging a half-written file next cycle -- moot
        # since we exec below, but keeps the loop's invariant honest.
        _snapshot(_watched_files(root))
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(restart_argv[0], restart_argv)


def _create_server(host: str, port: int) -> ThreadingHTTPServer:
    """Construct the ThreadingHTTPServer, retrying on EADDRINUSE.

    After an os.execv-based restart the new process re-binds the same port;
    the old listener closes on exec (sockets are CLOEXEC by default) and
    allow_reuse_address is already on, but a still-shutting-down connection
    can briefly hold the port.  Retry a few times before giving up.
    """
    attempt = 0
    while True:
        try:
            return ThreadingHTTPServer((host, port), _Handler)
        except OSError as exc:
            attempt += 1
            if exc.errno != errno.EADDRINUSE or attempt >= _BIND_RETRY_ATTEMPTS:
                raise
            time.sleep(_BIND_RETRY_DELAY)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    # Captured before argument parsing / dotenv loading can touch anything,
    # so a later os.execv restarts with exactly how this process was invoked.
    restart_argv = [sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]

    _load_dotenv()

    ap = argparse.ArgumentParser(description="Uranium map viewer local server (Phase B1).")
    ap.add_argument("--port", type=int, default=8765, help="TCP port (default: 8765)")
    ap.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    ap.add_argument(
        "--no-watch",
        action="store_true",
        help="Disable the source-change watcher/self-restart",
    )
    args = ap.parse_args()

    hostname = socket.gethostname()
    print("Map viewer server starting…")
    print(f"  http://{hostname}:{args.port}/   (LAN / Tailscale)")
    print(f"  http://localhost:{args.port}/")
    print("  Ctrl-C to stop.")

    if not args.no_watch:
        watched = _watched_files(_REPO_ROOT)
        print(f"  watching {len(watched)} source files for changes (--no-watch to disable)")
        watch_thread = threading.Thread(
            target=_watch_loop, args=(restart_argv, _REPO_ROOT), daemon=True
        )
        watch_thread.start()

    server = _create_server(args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
