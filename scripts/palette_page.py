# ruff: noqa: E501
"""Palette-centric HTML inspector page for a Pokémon Uranium map.

For each GBA sub-palette, shows the 15 colour swatches (used vs. unused),
and a suspect-first grid of metatile thumbnails that draw from it.
Clicking a tile opens a detail popup: post-quant thumbnail (bottom + top stacked),
which palette slots the tile actually uses, and each colour change
(original source colour → snapped palette colour, changed ones highlighted).

Companion to build_map_viewer.py — call build_config() from that module to get
all data and inline images, then inject them into the PALETTE_VIEWER_HTML template.

Usage:
    python scripts/palette_page.py 32
    python scripts/palette_page.py 32 --out /tmp/pal.html
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_map_viewer import build_config  # noqa: E402

PALETTE_VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Palette Inspector</title>
<script>window.__VIEWER__=__VIEWER_CONFIG__;</script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1a1a;color:#ddd;font:12px/1.4 monospace}
#topbar{background:#252525;border-bottom:1px solid #444;padding:6px 10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;position:sticky;top:0;z-index:5}
#summary{color:#8cf;font-weight:bold;flex:1;min-width:0}
.sep{width:1px;background:#555;height:20px;margin:0 4px;flex-shrink:0}
.btn{background:#333;border:1px solid #555;color:#ddd;padding:2px 8px;cursor:pointer;font:11px monospace;border-radius:2px}
.btn:hover{background:#444}
.btn.active{background:#2a3a4a;border-color:#5af;color:#5af}
/* ---- map nav strip ---- */
#mapnav{display:none;background:#1c1c1c;border-bottom:1px solid #383838;padding:4px 8px;gap:6px;align-items:center;overflow-x:auto;white-space:nowrap;font-size:11px}
#mapnav.show{display:flex}
#mapnav .navcur{color:#8cf;font-weight:bold;flex-shrink:0}
#mapnav .navgrp{color:#777;flex-shrink:0;margin-left:2px}
#mapnav .navchip{display:inline-block;background:#2a2a2a;border:1px solid #4a4a4a;color:#bcd;text-decoration:none;padding:1px 7px;border-radius:10px;flex-shrink:0}
#mapnav .navchip:hover{background:#33414e;border-color:#5af;color:#cfe}
#mapnav .navchip.home{background:#243d2e;border-color:#475}
#mapnav .navsep{width:1px;height:16px;background:#444;flex-shrink:0;margin:0 2px}
#content{padding:10px}
.pal-section{background:#1e1e1e;border:1px solid #333;border-radius:4px;margin-bottom:14px;overflow:hidden}
.pal-header{background:#252525;padding:6px 10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-bottom:1px solid #333}
.pal-title{color:#5af;font-weight:bold;font-size:13px}
.pal-stats{color:#888;font-size:11px}
.pal-extra{color:#666;font-size:10px}
.pal-swatches{display:flex;align-items:flex-end;flex-wrap:wrap;gap:1px;padding:6px 10px 4px;border-bottom:1px solid #2a2a2a}
.swatch{display:inline-block;width:16px;height:16px;border:1px solid #555;vertical-align:middle;cursor:default;margin:0;flex-shrink:0}
.swatch-checker{background-image:repeating-conic-gradient(#777 0% 25%,#bbb 0% 50%);background-size:8px 8px}
.swatch-unused{opacity:0.2;filter:grayscale(0.6)}
.slot-wrap{display:flex;flex-direction:column;align-items:center;gap:1px}
.slot-label{font-size:9px;color:#555;text-align:center;width:18px;line-height:1.2}
.slot-label.used{color:#777}
.tile-grid{display:flex;flex-wrap:wrap;gap:6px;padding:8px 10px}
.tile-card{position:relative;display:flex;flex-direction:column;align-items:center;gap:2px;cursor:pointer;padding:3px;border:2px solid #2a2a2a;border-radius:3px;background:#141414;transition:border-color .12s,background .12s}
.tile-card:hover{background:#222;border-color:#555}
.tile-card.suspect{border-color:#fa0}
.tile-card.bad{border-color:#f44}
.tile-card.suspect.bad{border-color:#f84}
.tile-thumb{position:relative;width:32px;height:32px;flex-shrink:0;background:#000;border:1px solid #333}
.tile-thumb img{position:absolute;top:0;left:0;width:32px;height:32px;image-rendering:pixelated;image-rendering:crisp-edges}
.tile-caption{font-size:9px;color:#888;text-align:center;line-height:1.3;white-space:nowrap}
.tile-nc{color:#fc8;font-weight:bold}
.tile-nc-ok{color:#6b6}
.tile-sev{color:#f66;font-size:8px}
.empty-msg{color:#555;padding:8px 10px;font-size:11px}
/* ---- modal ---- */
#modal-backdrop{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:100;align-items:center;justify-content:center}
#modal-backdrop.open{display:flex}
#modal-box{background:#1e1e1e;border:1px solid #555;border-radius:6px;padding:14px;max-width:400px;width:92%;max-height:90vh;overflow-y:auto;position:relative}
#modal-close{position:absolute;top:8px;right:10px;cursor:pointer;color:#888;font-size:17px;line-height:1;padding:2px 4px}
#modal-close:hover{color:#fff}
.modal-title{color:#5af;font-weight:bold;margin-bottom:10px;font-size:13px;padding-right:22px}
.modal-top{display:flex;gap:10px;margin-bottom:10px;align-items:flex-start}
.modal-thumb-stack{position:relative;width:64px;height:64px;flex-shrink:0;border:1px solid #444;background:#000}
.modal-thumb-stack img{position:absolute;top:0;left:0;width:64px;height:64px;image-rendering:pixelated;image-rendering:crisp-edges}
.modal-stats{display:flex;flex-direction:column;gap:3px}
.section-title{color:#5af;font-weight:bold;margin:8px 0 4px;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.lbl{color:#888;font-size:11px}
.val{color:#eee}
.val-warn{color:#fc8;font-weight:bold}
.val-bad{color:#f66;font-weight:bold}
.slot-used-row{display:flex;flex-wrap:wrap;gap:2px;align-items:center;margin:4px 0}
.slot-hi{outline:2px solid #5af;outline-offset:0}
.cc-row{display:flex;align-items:center;gap:4px;padding:2px 0;font-size:10px;border-bottom:1px solid #1e1e1e}
.cc-row.changed .swatch{outline:2px solid #fa0}
.cc-arrow{color:#555}
.cc-tag-same{color:#445}
.cc-tag-changed{color:#fa0;font-weight:bold}
@media (max-width:600px){
  .tile-grid{gap:4px;padding:6px}
  .tile-card{padding:2px}
  #modal-box{padding:10px;max-width:100%;width:96%}
  #topbar{gap:4px}
}
</style>
</head>
<body>
<div id="topbar">
  <a class="btn" id="nav-map" href="#" style="display:none;text-decoration:none">&larr; Map</a>
  <span id="summary"></span>
  <div class="sep"></div>
  <button class="btn" id="btn-suspect" onclick="toggleSuspect()">Suspects only (&le;2c)</button>
  <button class="btn" id="btn-collapse" onclick="toggleCollapse()">Hide empty pals</button>
</div>
<div id="mapnav"></div>
<div id="content"></div>
<div id="modal-backdrop" onclick="handleBackdropClick(event)">
  <div id="modal-box">
    <span id="modal-close" onclick="closeModal()">&#10005;</span>
    <div id="modal-inner"></div>
  </div>
</div>
<script>
const V = window.__VIEWER__;
const D = V.data;

// ---- swatch helpers — matches map_viewer_common.py swatchTitle/swatchHtml ----
function swatchTitle(c) {
  const r = c[0], g = c[1], b = c[2];
  const hex = '#' + [r,g,b].map(function(v){return v.toString(16).padStart(2,'0');}).join('').toUpperCase();
  const r5 = r>>3, g5 = g>>3, b5 = b>>3;
  const bgr555 = (b5<<10)|(g5<<5)|r5;
  return 'rgb(' + r + ',' + g + ',' + b + ')  ' + hex + '  BGR555: 0x' + bgr555.toString(16).toUpperCase().padStart(4,'0') + ' (' + r5 + ',' + g5 + ',' + b5 + ')';
}
function swatchHtml(c, extraCls, extraStyle) {
  const hex = '#' + c.map(function(v){return v.toString(16).padStart(2,'0');}).join('');
  const cls = 'swatch' + (extraCls ? ' ' + extraCls : '');
  const sty = 'background:' + hex + (extraStyle ? ';' + extraStyle : '');
  return '<span class="' + cls + '" style="' + sty + '" title="' + swatchTitle(c) + '"></span>';
}
function getMetatileURL(idx, layer) {
  if (V.mode === 'static') {
    const m = (V.metatile_images || {})[String(idx)];
    return m ? m[layer] : null;
  }
  return '/api/metatile/' + D.meta.map_id + '/' + idx + '.png?layer=' + layer;
}

// ---- state ----
let suspectsOnly = false;
let collapseEmpty = false;

function toggleSuspect() {
  suspectsOnly = !suspectsOnly;
  document.getElementById('btn-suspect').classList.toggle('active', suspectsOnly);
  renderAll();
}
function toggleCollapse() {
  collapseEmpty = !collapseEmpty;
  document.getElementById('btn-collapse').classList.toggle('active', collapseEmpty);
  renderAll();
}

function countSuspects() {
  let n = 0;
  for (const pu of (D.palette_usage || [])) {
    for (const t of (pu.tiles || [])) { if (t.n_colors <= 2) n++; }
  }
  return n;
}

// ---- render palette sections ----
function renderAll() {
  const pu = D.palette_usage || [];
  const meta = D.meta;
  const nSuspects = countSuspects();

  document.getElementById('summary').textContent =
    'Map' + String(meta.map_id).padStart(3,'0') +
    ' · tileset ' + meta.tileset_id +
    (meta.tileset_name ? ' (' + meta.tileset_name + ')' : '') +
    ' · ' + pu.length + ' palette' + (pu.length === 1 ? '' : 's') +
    ' · ' + nSuspects + ' suspect tile' + (nSuspects === 1 ? '' : 's') + ' (≤2 colours)';

  let html = '';
  for (const entry of pu) {
    const visibleTiles = suspectsOnly
      ? entry.tiles.filter(function(t){ return t.n_colors <= 2; })
      : entry.tiles;

    if (collapseEmpty && visibleTiles.length === 0 && entry.n_tiles === 0) continue;
    if (suspectsOnly && visibleTiles.length === 0 && collapseEmpty) continue;

    const usedSlotSet = new Set(entry.used_slots);
    const nUsed = entry.used_slots.length;

    html += '<div class="pal-section">';

    // -- palette header --
    html += '<div class="pal-header">';
    html += '<span class="pal-title">Pal ' + entry.pal + '</span>';
    html += '<span class="pal-stats">used ' + nUsed + '/15 slots · ' + entry.n_tiles + ' tile' + (entry.n_tiles === 1 ? '' : 's') + '</span>';
    if (suspectsOnly && visibleTiles.length !== entry.tiles.length) {
      html += '<span class="pal-extra">(' + visibleTiles.length + ' suspect shown of ' + entry.tiles.length + ')</span>';
    }
    html += '</div>';

    // -- swatch row: slot 0 (transparent) + slots 1-15 --
    html += '<div class="pal-swatches">';
    html += '<div class="slot-wrap"><span class="swatch swatch-checker" title="slot 0 (transparent / index 0)"></span><span class="slot-label">0</span></div>';
    for (let j = 0; j < 15; j++) {
      const slot = j + 1;
      const used = usedSlotSet.has(slot);
      const color = entry.colors[j];
      const unusedCls = used ? '' : ' swatch-unused';
      const labelCls = used ? ' used' : '';
      if (color) {
        const hex = '#' + color.map(function(v){return v.toString(16).padStart(2,'0');}).join('');
        const titleStr = (used ? '[used] ' : '[unused] ') + swatchTitle(color);
        html += '<div class="slot-wrap"><span class="swatch' + unusedCls + '" style="background:' + hex + '" title="' + titleStr + '"></span><span class="slot-label' + labelCls + '">' + slot + '</span></div>';
      } else {
        html += '<div class="slot-wrap"><span class="swatch swatch-unused" style="background:#111" title="slot ' + slot + ' (empty)"></span><span class="slot-label">' + slot + '</span></div>';
      }
    }
    html += '</div>';

    // -- tile grid --
    if (visibleTiles.length === 0) {
      html += '<div class="empty-msg">' + (suspectsOnly ? 'No suspect tiles in this palette.' : 'No tiles use this palette.') + '</div>';
    } else {
      html += '<div class="tile-grid">';
      for (const t of visibleTiles) {
        const suspect = t.n_colors <= 2;
        const bad = t.merge_severity >= 5;
        let cardCls = 'tile-card';
        if (suspect) cardCls += ' suspect';
        if (bad) cardCls += ' bad';
        const botURL = getMetatileURL(t.idx, 'post_bottom');
        const topURL = getMetatileURL(t.idx, 'post_top');
        const tipText = '#' + t.idx + ' · ' + t.n_colors + ' colour' + (t.n_colors === 1 ? '' : 's') + ' · sev ' + t.merge_severity;
        html += '<div class="' + cardCls + '" onclick="openTile(' + t.idx + ',' + entry.pal + ')" title="' + tipText + '">';
        html += '<div class="tile-thumb">';
        if (botURL) html += '<img src="' + botURL + '" loading="lazy" alt="">';
        if (topURL) html += '<img src="' + topURL + '" loading="lazy" alt="">';
        html += '</div>';
        const ncCls = t.n_colors <= 2 ? 'tile-nc' : 'tile-nc-ok';
        html += '<div class="tile-caption">#' + t.idx + '<br><span class="' + ncCls + '">' + t.n_colors + 'c</span>';
        if (t.merge_severity > 0) html += '<span class="tile-sev"> s' + t.merge_severity + '</span>';
        html += '</div>';
        html += '</div>';
      }
      html += '</div>';
    }
    html += '</div>'; // pal-section
  }

  document.getElementById('content').innerHTML = html;
}

// ---- tile detail modal ----
function openTile(idx, palIdx) {
  const ckPal = D.colkey_palettes ? D.colkey_palettes[idx] : null;
  const puEntry = (D.palette_usage || []).find(function(p){ return p.pal === palIdx; });
  const tileEntry = puEntry ? puEntry.tiles.find(function(t){ return t.idx === idx; }) : null;

  const botURL = getMetatileURL(idx, 'post_bottom');
  const topURL = getMetatileURL(idx, 'post_top');

  let h = '<div class="modal-title">Metatile #' + idx + ' &mdash; Pal ' + palIdx + '</div>';

  // top row: thumbnail + quick stats
  h += '<div class="modal-top">';
  h += '<div class="modal-thumb-stack">';
  if (botURL) h += '<img src="' + botURL + '" alt="post-quant bottom">';
  if (topURL) h += '<img src="' + topURL + '" alt="post-quant top">';
  h += '</div>';
  h += '<div class="modal-stats">';
  if (tileEntry) {
    const ncCls = tileEntry.n_colors <= 2 ? 'val-warn' : 'val';
    const sevCls = tileEntry.merge_severity >= 5 ? 'val-bad' : (tileEntry.merge_severity > 0 ? 'val-warn' : 'val');
    h += '<div><span class="lbl">colours used </span><span class="' + ncCls + '">' + tileEntry.n_colors + '</span></div>';
    h += '<div><span class="lbl">merge severity </span><span class="' + sevCls + '">' + tileEntry.merge_severity + '</span></div>';
  }
  if (ckPal) {
    h += '<div><span class="lbl">merge colours </span><span class="val">' + (ckPal.merge_colors || 0) + '</span></div>';
    if (ckPal.palette_indices && ckPal.palette_indices.length > 1) {
      h += '<div><span class="lbl">all pals </span><span class="val">' + ckPal.palette_indices.join(', ') + '</span></div>';
    }
  }
  h += '</div>';
  h += '</div>'; // modal-top

  // palette slots used by this tile in this palette
  if (tileEntry && tileEntry.slots && tileEntry.slots.length > 0 && puEntry) {
    h += '<div class="section-title">Slots used in Pal ' + palIdx + '</div>';
    h += '<div class="slot-used-row">';
    h += '<span class="swatch swatch-checker" title="slot 0 (transparent)"></span>';
    const usedSet = new Set(tileEntry.slots);
    for (let j = 0; j < 15; j++) {
      const slot = j + 1;
      const color = puEntry.colors[j];
      const used = usedSet.has(slot);
      if (color) {
        const extraStyle = used ? 'outline:2px solid #5af;outline-offset:0' : '';
        const unusedCls = used ? '' : 'swatch-unused';
        h += swatchHtml(color, unusedCls, extraStyle);
      }
    }
    h += '</div>';
    h += '<div class="lbl">' + tileEntry.slots.length + ' slot' + (tileEntry.slots.length === 1 ? '' : 's') + ' used: ' + tileEntry.slots.join(', ') + '</div>';
  }

  // colour changes (all quadrants of the metatile)
  if (ckPal && ckPal.color_changes && ckPal.color_changes.length > 0) {
    const nChanged = ckPal.color_changes.filter(function(cc){
      return cc[0][0] !== cc[1][0] || cc[0][1] !== cc[1][1] || cc[0][2] !== cc[1][2];
    }).length;
    h += '<div class="section-title">Colour changes (' + nChanged + '/' + ckPal.color_changes.length + ' changed)</div>';
    for (const cc of ckPal.color_changes) {
      const orig = cc[0], fin = cc[1];
      const changed = orig[0] !== fin[0] || orig[1] !== fin[1] || orig[2] !== fin[2];
      h += '<div class="cc-row' + (changed ? ' changed' : '') + '">';
      h += swatchHtml(orig, '', '');
      h += '<span class="cc-arrow">&rarr;</span>';
      h += swatchHtml(fin, '', '');
      h += '<span class="' + (changed ? 'cc-tag-changed' : 'cc-tag-same') + '">' + (changed ? 'changed' : 'same') + '</span>';
      h += '</div>';
    }
  } else if (ckPal) {
    h += '<div class="lbl" style="margin-top:6px">(no colour changes)</div>';
  } else {
    h += '<div class="lbl" style="margin-top:6px">(colour data unavailable)</div>';
  }

  document.getElementById('modal-inner').innerHTML = h;
  document.getElementById('modal-backdrop').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-backdrop').classList.remove('open');
}
function handleBackdropClick(e) {
  if (e.target === document.getElementById('modal-backdrop')) closeModal();
}
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });

// ---- map nav strip (server mode only; populated from V.graph) ----
function renderMapNav() {
  const nav = document.getElementById('mapnav');
  if (!nav) return;
  const g = V.graph;
  if (V.mode !== 'server' || !g) { nav.classList.remove('show'); return; }
  const pad = function(n){ return String(n).padStart(3,'0'); };
  const esc = function(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
  const chip = function(id, name){
    return '<a class="navchip" href="/map/' + id + '" title="Map' + pad(id) + '">M' + pad(id) + ' ' + esc(name) + '</a>';
  };
  let h = '<a class="navchip home" href="/" title="Map index">&#8962; Index</a><span class="navsep"></span>';
  h += '<span class="navcur">Map' + pad(g.id) + ' &middot; ' + esc(g.name) + '</span>';
  const seen = new Set([g.id]);
  if (g.parent) { h += '<span class="navsep"></span><span class="navgrp">up</span>' + chip(g.parent.id, g.parent.name); seen.add(g.parent.id); }
  const kids = (g.children || []).filter(function(c){ return !seen.has(c.id); });
  if (kids.length) { h += '<span class="navsep"></span><span class="navgrp">sub</span>'; kids.forEach(function(c){ seen.add(c.id); h += chip(c.id, c.name); }); }
  const warps = (g.warps || []).filter(function(w){ return !seen.has(w.id); });
  if (warps.length) { h += '<span class="navsep"></span><span class="navgrp">warp&rarr;</span>'; warps.forEach(function(w){ seen.add(w.id); h += chip(w.id, w.name); }); }
  nav.innerHTML = h;
  nav.classList.add('show');
}

// ---- init ----
(function init() {
  const m = D.meta;
  document.title = 'Palette Inspector — Map' + String(m.map_id).padStart(3,'0');
  if (V.mode === 'server') {
    const nav = document.getElementById('nav-map');
    nav.href = '/map/' + m.map_id;
    nav.style.display = '';
  }
  renderMapNav();
  renderAll();
})();
</script>
</body>
</html>
"""


def build_palette_html(map_id: int) -> str:
    """Build a self-contained palette inspector HTML page for the given map.

    Calls build_config(map_id) from build_map_viewer (shared config + inline images),
    then injects the result into PALETTE_VIEWER_HTML.
    """
    config = build_config(map_id)
    config_json = json.dumps(config, separators=(",", ":"))
    return PALETTE_VIEWER_HTML.replace("__VIEWER_CONFIG__", config_json)


def main() -> None:
    from map_viewer_common import _load_dotenv, _output_base  # noqa: E402

    _load_dotenv()

    ap = argparse.ArgumentParser(
        description="Build a self-contained palette inspector HTML page for a Uranium map.",
    )
    ap.add_argument("map_id", type=int, metavar="MAP_ID", help="Map ID (e.g. 32)")
    ap.add_argument("--out", default=None, help="Output path (default: output/map_viewer/MapNNN_palettes.html)")
    args = ap.parse_args()

    html = build_palette_html(args.map_id)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = _output_base() / "map_viewer"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"Map{args.map_id:03d}_palettes.html"

    out_path.write_text(html, encoding="utf-8")
    print(f"Written: {out_path}  ({len(html.encode('utf-8')) // 1024} KB)")


if __name__ == "__main__":
    main()
