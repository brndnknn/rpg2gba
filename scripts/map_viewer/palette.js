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
  // `g` = quant generation: busts the browser's immutable cache after a knob Apply.
  const g = (V.quant && V.quant.generation) || 0;
  return '/api/metatile/' + D.meta.map_id + '/' + idx + '.png?layer=' + layer + '&g=' + g;
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

// ---- map nav strip (populated from V.graph) ----
function renderMapNav() {
  const nav = document.getElementById('mapnav');
  if (!nav) return;
  const g = V.graph;
  if (!g) { nav.classList.remove('show'); return; }
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
  const nav = document.getElementById('nav-map');
  nav.href = '/map/' + m.map_id;
  nav.style.display = '';
  renderMapNav();
  renderAll();
})();
/*KNOBBAR_JS*/
