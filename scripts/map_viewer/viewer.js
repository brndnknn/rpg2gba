// ---- viewer config --------------------------------------------------------
const V = window.__VIEWER__;
let D = V.data;

// ---- members (stitched-component support) -----------------------------------
// Every mode renders a list of members [{id, ox, oy, w, h, data, flags,
// flaggedCells}] in one shared cell space; single-map = one member at (0,0).
// `D` stays the ACTIVE member's dataset so all inspector/feedback code keeps
// working unchanged; tapping a cell in another member switches the active one.
const stitched = !!V.component;
const members = (function() {
  if (!stitched) {
    return [{id: D.meta.map_id, name: D.meta.name || '', ox: 0, oy: 0,
             w: D.meta.xsize, h: D.meta.ysize, data: D, flags: [],
             flaggedCells: new Set()}];
  }
  return V.component.members.map(function(m) {
    return {id: m.id, name: m.name, ox: m.ox, oy: m.oy, w: m.w, h: m.h,
            data: m.id === D.meta.map_id ? D : null, flags: [],
            flaggedCells: new Set()};
  });
})();
let activeM = members.filter(function(m) { return m.id === D.meta.map_id; })[0] || members[0];
function worldW() { return stitched ? V.component.w : D.meta.xsize; }
function worldH() { return stitched ? V.component.h : D.meta.ysize; }
function memberAt(wx, wy) {  // last in listing order wins (overlap rule)
  for (let i = members.length - 1; i >= 0; i--) {
    const m = members[i];
    if (wx >= m.ox && wx < m.ox + m.w && wy >= m.oy && wy < m.oy + m.h) return m;
  }
  return null;
}

// ---- image URLs: getTileURL / getMetatileURL ----------------------------
// `g` = quant generation: bumped on every knob Apply AND on every server-detected
// stale reload (a pipeline rebuild while the server was running — see
// _invalidate_for_reload), so ALL image URLs (not just post-quant) carry it: every
// PNG is served with Cache-Control: immutable, and without the token a rebuilt map
// would keep showing pre-rebuild tiles from the browser cache after a page reload.
function getTileURL(tileId, mid) {
  mid = mid || D.meta.map_id;
  if (!tileId) return null;
  const g = (V.quant && V.quant.generation) || 0;
  return '/api/tile/' + mid + '/' + tileId + '.png?g=' + g;
}
function getMetatileURL(idx, layer, mid) {
  mid = mid || D.meta.map_id;
  const g = (V.quant && V.quant.generation) || 0;
  return '/api/metatile/' + mid + '/' + idx + '.png?layer=' + layer + '&g=' + g;
}
function getNpcURL(name) {
  if (!name) return null;
  return '/api/npc/' + encodeURIComponent(name) + '.png';
}

// ---- Events-mode data fetch -------------------------------------------------
function loadBeats(m) {
  if (!m || beatsByMember.get(m.id) === 'loading') return;
  beatsByMember.set(m.id, 'loading');
  fetch('/api/beats/' + m.id).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(data) {
    beatsByMember.set(m.id, data);
    if (m === activeM) { renderBeatPanel(); scheduleRender(); }
  }).catch(function(e) {
    console.error('beats load failed for map ' + m.id, e);
    beatsByMember.set(m.id, 'error');
    if (m === activeM) renderBeatPanel();
  });
}
function loadEventDetail(mapId, eventId) {
  const body = document.getElementById('event-inspector-body');
  body.innerHTML = '<span class="lbl">Loading…</span>';
  fetch('/api/event/' + mapId + '/' + eventId).then(function(r) {
    return r.json().then(function(j) { return {ok: r.ok, status: r.status, body: j}; });
  }).then(function(res) {
    if (!res.ok) {
      body.innerHTML = '<div class="mismatch">' + (res.status === 404 ? 'Unknown event.' :
        'Event detail unavailable (HTTP ' + res.status + '): ' + escHtml((res.body && res.body.error) || '')) + '</div>';
      return;
    }
    body.innerHTML = renderEventDetail(res.body);
  }).catch(function(e) {
    console.error('event detail failed', e);
    body.innerHTML = '<div class="mismatch">Event detail fetch failed: ' + escHtml(e.message) + '</div>';
  });
}

// ---- lazy image cache -----------------------------------------------------
const imgCache = new Map(); // url -> HTMLImageElement | 'loading' | 'err'
let renderPending = false;
function scheduleRender() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(function() { renderPending = false; render(); });
}
function drawImg(url, dx, dy, cp) {
  if (!url) return;
  const c = imgCache.get(url);
  if (!c) {
    imgCache.set(url, 'loading');
    const img = new Image();
    img.onload = function() { imgCache.set(url, img); scheduleRender(); };
    img.onerror = function() { imgCache.set(url, 'err'); };
    img.src = url;
    ctx.fillStyle = '#1c1c22'; ctx.fillRect(dx, dy, cp, cp);
    return;
  }
  if (c === 'loading') { ctx.fillStyle = '#1c1c22'; ctx.fillRect(dx, dy, cp, cp); return; }
  if (c === 'err') return;
  ctx.drawImage(c, dx, dy, cp, cp);
}
// NPC sprite: bottom-center anchored on the event's tile cell (the converted
// sheet's own frame is bottom-anchored/h-centered on its canvas -- see
// sprites.py `_anchor` -- so scaling by cp/16, the current-zoom size of one
// native 16px tile, and placing the frame's bottom edge on the cell's bottom
// edge reproduces that). No background fill while loading, unlike drawImg --
// an event cell with no sprite yet should show the fallback dot, not a box.
// Returns true if a sprite was actually drawn.
function drawNpcSprite(url, dx, dy, cp) {
  if (!url) return false;
  const c = imgCache.get(url);
  if (!c) {
    imgCache.set(url, 'loading');
    const img = new Image();
    img.onload = function() { imgCache.set(url, img); scheduleRender(); };
    img.onerror = function() { imgCache.set(url, 'err'); };
    img.src = url;
    return false;
  }
  if (c === 'loading' || c === 'err') return false;
  const scale = cp / 16;
  const w = c.naturalWidth * scale, h = c.naturalHeight * scale;
  ctx.drawImage(c, dx + (cp - w) / 2, dy + cp - h, w, h);
  return true;
}

// ---- state ----------------------------------------------------------------
let zoom = 2;
let panX = 0, panY = 0;
let currentLayer = 'post-quant';   // default view = the quantized GBA render
let overlays = {collision:false, diff:false, priority:false, merge:false, events:true, warps:true, animated:false};
// Max merge severity across this map's metatiles, for normalizing the Merge heat-map.
let maxMergeSeverity = 1;
(function() {
  const cps = D.colkey_palettes || [];
  for (const cp of cps) { if (cp && cp.merge_severity > maxMergeSeverity) maxMergeSeverity = cp.merge_severity; }
})();
let focusCell = null;          // last-tapped cell; drives the inspector readout
const selection = new Map();   // "x,y" -> cell object; the accumulating flag set
let flags = [];                // saved flags: [{cells:[[x,y],...], note}]
let flaggedCells = new Set();  // "x,y" of every cell covered by some flag (canvas markers)
let editingIndex = null;       // index in `flags` currently being edited, or null
let advanced = false;          // Advanced (quant/graphics-debug) controls revealed?
let ready = false;

// ---- Events mode state -----------------------------------------------------
// `viewMode`: 'graphics' (default, unchanged behaviour) or 'events' (event/
// trainer/beat debugging). One renderer either way -- everything below just
// gates what the shared render/tap paths do.
let viewMode = 'graphics';
let eventFilter = 'all';       // all | trainer | item | warp | conditional
let showBeats = true;
let showPlanned = true;
let showWalked = true;
let dimBase = true;
const KIND_COLORS = {
  warp: '#33e6ff', trainer: '#ff4444', item: '#ffcc00', npc: '#66ff66',
  sign: '#8888ff', autorun: '#ff66ff', parallel: '#55ccff', other: '#999999',
};
const KIND_LABELS = {
  warp: 'Warp', trainer: 'Trainer', item: 'Item', npc: 'NPC',
  sign: 'Sign', autorun: 'Autorun', parallel: 'Parallel', other: 'Other',
};
// Okabe-Ito colourblind-safe hues, one shape per status so colour is never
// the only signal (pass=circle, fail=square, flake=triangle, skipped=diamond-outline).
const STATUS_STYLE = {
  pass:    {color: '#2ca02c', shape: 'circle'},
  fail:    {color: '#d55e00', shape: 'square'},
  flake:   {color: '#cc79a7', shape: 'triangle'},
  skipped: {color: '#888888', shape: 'diamond'},
};
// Planned-route palette: Okabe-Ito blue for the route itself, Okabe-Ito
// orange for a crossed foreign trigger -- neither collides with the
// declared star (#ffe066) or the observed STATUS_STYLE hues above.
const PLANNED_ROUTE_COLOR = '#0072b2';
const PLANNED_CROSSING_COLOR = '#e69f00';
// Walked-route palette (Q13 slice 4): Okabe-Ito vermillion for the actually-
// walked line -- distinct from the planned route's blue and from every
// STATUS_STYLE hue -- with a hollow marker for an off-plan tile (evidence,
// non-blocking, Q8) and a louder ring+X for a trigger violation. A
// violation is the SAME class of event `PLANNED_CROSSING_COLOR` marks
// (a foreign trigger crossed), but observed rather than predicted, so it
// reads as more severe: solid fill under the X, not just an outline.
const WALKED_ROUTE_COLOR = '#d55e00';
const WALKED_VIOLATION_COLOR = '#ff2b2b';
let beatsByMember = new Map();   // member id -> {declared, observed, planned, walked, contradictions, conformance, notes} | 'loading' | 'error'
let focusEvent = null;           // event summary object last tapped, drives the inspector fetch

// pointer tracking
const pointers = new Map(); // pointerId -> {x,y}
let dragStartX = 0, dragStartY = 0, dragPanX = 0, dragPanY = 0;
let dragMoved = false;
let pinchRef = null; // {dist,zoom,midX,midY,panX,panY}

// ---- canvas ---------------------------------------------------------------
const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');
const wrap = document.getElementById('canvas-wrap');
ctx.imageSmoothingEnabled = false;

function resizeCanvas() {
  canvas.width = wrap.clientWidth;
  canvas.height = wrap.clientHeight;
  render();
}
new ResizeObserver(resizeCanvas).observe(wrap);

// ---- coordinate helpers ---------------------------------------------------
function cellPx() { return 16 * zoom; }
function canvasToCell(cx, cy) {
  const cp = cellPx();
  return {x: Math.floor((cx - panX) / cp), y: Math.floor((cy - panY) / cp)};
}
const ZMIN = stitched ? 0.15 : 0.5;  // stitched components need to fit far out
function fitMap() {
  // leave a margin when seam bands exist so they aren't clipped at fit zoom
  const pad = (!stitched && V.graph && (V.graph.connections || []).length) ? 22 : 0;
  const sx = (canvas.width  - 2 * pad) / (worldW() * 16);
  const sy = (canvas.height - 2 * pad) / (worldH() * 16);
  zoom = Math.max(ZMIN, Math.min(4, Math.min(sx, sy)));
  panX = Math.floor((canvas.width  - worldW() * cellPx()) / 2);
  panY = Math.floor((canvas.height - worldH() * cellPx()) / 2);
  updateZoomDisplay();
  render();
}
function centerOnCell(m, lx, ly, minZoom) {
  if (minZoom && zoom < minZoom) zoom = minZoom;
  const cp = cellPx();
  panX = Math.floor(canvas.width  / 2 - (m.ox + lx + 0.5) * cp);
  panY = Math.floor(canvas.height / 2 - (m.oy + ly + 0.5) * cp);
  updateZoomDisplay();
  scheduleRender();
}
function updateZoomDisplay() {
  document.getElementById('zoom-val').textContent =
    (zoom % 1 === 0 ? zoom : zoom.toFixed(1)) + 'x';
}

// ---- rendering ------------------------------------------------------------
function drawCellBase(cell, dx, dy, cp, mid) {
  ctx.imageSmoothingEnabled = false;
  const lyr = currentLayer;
  if (lyr === 'rmxp') {
    for (const tid of cell.layers) { if (tid) drawImg(getTileURL(tid, mid), dx, dy, cp); }
  } else if (lyr === 'l0' || lyr === 'l1' || lyr === 'l2') {
    const tid = cell.layers[parseInt(lyr[1])];
    if (tid) drawImg(getTileURL(tid, mid), dx, dy, cp);
  } else if (lyr === 'gba') {
    drawImg(getMetatileURL(cell.colkey_idx, 'bottom', mid), dx, dy, cp);
    drawImg(getMetatileURL(cell.colkey_idx, 'top', mid),    dx, dy, cp);
  } else if (lyr === 'gba_bottom') {
    drawImg(getMetatileURL(cell.colkey_idx, 'bottom', mid), dx, dy, cp);
  } else if (lyr === 'gba_top') {
    drawImg(getMetatileURL(cell.colkey_idx, 'top', mid), dx, dy, cp);
  } else if (lyr === 'post-quant') {
    drawImg(getMetatileURL(cell.colkey_idx, 'post_bottom', mid), dx, dy, cp);
    drawImg(getMetatileURL(cell.colkey_idx, 'post_top', mid),    dx, dy, cp);
  }
}

function drawOverlayCell(cell, dx, dy, cp, m) {
  const isActive = !m || m === activeM;
  if (overlays.collision) {
    ctx.fillStyle = cell.collision_ours ? 'rgba(255,40,40,0.35)' : 'rgba(40,220,80,0.25)';
    ctx.fillRect(dx, dy, cp, cp);
  }
  if (overlays.diff && cell.mismatch) {
    ctx.strokeStyle = 'rgba(255,0,255,0.9)';
    ctx.lineWidth = Math.max(1, zoom);
    ctx.strokeRect(dx+1, dy+1, cp-2, cp-2);
  }
  if (overlays.priority && cell.priority_max > 0) {
    ctx.fillStyle = 'rgba(255,165,0,' + Math.min(0.85, cell.priority_max * 0.3) + ')';
    ctx.fillRect(dx, dy, cp, cp);
  }
  if (overlays.animated && cell.animated) {
    ctx.fillStyle = 'rgba(64,200,255,0.4)';
    ctx.fillRect(dx, dy, cp, cp);
  }
  if (overlays.merge) {
    const cpal = (((m ? m.data : D) || D).colkey_palettes || [])[cell.colkey_idx];
    const sev = cpal ? (cpal.merge_severity || 0) : 0;
    if (sev > 0) {
      // brightness scales with severity relative to this map's worst tile
      const a = 0.15 + 0.7 * Math.min(1, sev / maxMergeSeverity);
      ctx.fillStyle = 'rgba(255,40,200,' + a.toFixed(3) + ')';
      ctx.fillRect(dx, dy, cp, cp);
    }
  }
  if (cell.out_of_atlas) {
    // One layer of this cell had a stale RMXP tile id past the tileset atlas
    // bounds and was masked to empty (the rest of the cell renders normally —
    // see layout.mask_out_of_atlas) — a small corner marker, not a full
    // overlay, so the still-rendered cell underneath stays visible. Always
    // shown, not gated behind an overlay toggle.
    const s = Math.max(4, cp * 0.28);
    ctx.fillStyle = 'rgba(255,0,0,0.9)';
    ctx.beginPath();
    ctx.moveTo(dx + cp, dy);
    ctx.lineTo(dx + cp, dy + s);
    ctx.lineTo(dx + cp - s, dy);
    ctx.closePath();
    ctx.fill();
  }
  const ik = cell.x + ',' + cell.y;
  if ((m ? m.flaggedCells : flaggedCells).has(ik)) {
    ctx.fillStyle = 'rgba(255,120,0,0.45)'; ctx.fillRect(dx, dy, cp, cp);
    ctx.fillStyle = '#fa0';
    ctx.font = Math.max(8, cp-2) + 'px monospace';
    ctx.fillText('⚑', dx+1, dy+cp-1);
  }
  if (isActive && selection.has(ik)) {
    ctx.fillStyle = 'rgba(90,170,255,0.35)'; ctx.fillRect(dx, dy, cp, cp);
    ctx.strokeStyle = 'rgba(90,170,255,0.9)';
    ctx.lineWidth = Math.max(1, zoom);
    ctx.strokeRect(dx+0.5, dy+0.5, cp-1, cp-1);
  }
  if (isActive && focusCell && focusCell.x === cell.x && focusCell.y === cell.y) {
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = Math.max(1.5, zoom);
    ctx.strokeRect(dx+1, dy+1, cp-2, cp-2);
  }
}

function renderMember(m, cp) {
  const baseX = panX + m.ox * cp, baseY = panY + m.oy * cp;
  if (!m.data) {  // still fetching: gray placeholder with the map's name
    ctx.fillStyle = '#20222c';
    ctx.fillRect(baseX, baseY, m.w * cp, m.h * cp);
    ctx.strokeStyle = '#3a3d4d'; ctx.lineWidth = 1;
    ctx.strokeRect(baseX + 0.5, baseY + 0.5, m.w * cp - 1, m.h * cp - 1);
    ctx.fillStyle = '#5af'; ctx.font = '13px monospace';
    ctx.fillText('Loading Map' + String(m.id).padStart(3,'0') + '…', baseX + 8, baseY + 20);
    return;
  }
  const md = m.data.meta;
  for (let y = 0; y < md.ysize; y++) {
    const dy = baseY + y * cp;
    if (dy + cp < 0 || dy >= canvas.height) continue;
    for (let x = 0; x < md.xsize; x++) {
      const dx = baseX + x * cp;
      if (dx + cp < 0 || dx >= canvas.width) continue;
      drawCellBase(m.data.cells[y * md.xsize + x], dx, dy, cp, m.id);
    }
  }
  if (viewMode === 'events' && dimBase) {
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.fillRect(baseX, baseY, md.xsize * cp, md.ysize * cp);
  }
  for (let y = 0; y < md.ysize; y++) {
    const dy = baseY + y * cp;
    if (dy + cp < 0 || dy >= canvas.height) continue;
    for (let x = 0; x < md.xsize; x++) {
      const dx = baseX + x * cp;
      if (dx + cp < 0 || dx >= canvas.width) continue;
      drawOverlayCell(m.data.cells[y * md.xsize + x], dx, dy, cp, m);
    }
  }
  const dotR = Math.max(3, Math.floor(cp / 5));
  ctx.save();
  ctx.font = Math.max(8, cp-4) + 'px monospace';
  for (const evt of m.data.events) {
    const dx = baseX + evt.x * cp, dy = baseY + evt.y * cp;
    if (dx+cp < 0 || dx >= canvas.width || dy+cp < 0 || dy >= canvas.height) continue;
    if (viewMode === 'events') {
      if (!eventPassesFilter(evt)) continue;
      const kind = evt.kind || 'other';
      const ringColor = KIND_COLORS[kind] || KIND_COLORS.other;
      const drawn = evt.character_name && drawNpcSprite(getNpcURL(evt.character_name), dx, dy, cp);
      // kind-coloured ring: under/around the sprite (or standing in for it).
      ctx.strokeStyle = ringColor;
      ctx.lineWidth = Math.max(1.5, zoom * 0.6);
      const r = drawn ? dotR + Math.max(2, cp * 0.08) : dotR;
      ctx.beginPath(); ctx.arc(dx+cp/2, dy+cp/2, r, 0, Math.PI*2); ctx.stroke();
      if (!drawn) {
        ctx.fillStyle = ringColor;
        ctx.beginPath(); ctx.arc(dx+cp/2, dy+cp/2, dotR*0.7, 0, Math.PI*2); ctx.fill();
      }
      if (evt.has_conditions) {
        ctx.fillStyle = '#ffcc00';
        ctx.beginPath(); ctx.arc(dx+cp-4, dy+4, Math.max(2, cp*0.06), 0, Math.PI*2); ctx.fill();
        ctx.strokeStyle = '#332900'; ctx.lineWidth = 1; ctx.stroke();
      }
      // label-gate zoom: mush at tiny zoom, so require real screen room; trainers
      // (the most-debugged kind) get a slightly lower bar so they read first.
      const labelGate = kind === 'trainer' ? 20 : 26;
      if (cp >= labelGate) {
        const label = (evt.label || evt.name || '').slice(0, kind === 'trainer' ? 10 : 6);
        ctx.font = (kind === 'trainer' ? 'bold ' : '') + Math.max(8, Math.min(cp-4, 12)) + 'px monospace';
        ctx.fillStyle = '#000'; ctx.fillText(label, dx+2, dy+cp-1);
        ctx.fillStyle = kind === 'trainer' ? '#fff' : '#ddd'; ctx.fillText(label, dx+1, dy+cp-2);
        ctx.font = Math.max(8, cp-4) + 'px monospace';
      }
      continue;
    }
    if (evt.is_warp && overlays.warps) {
      ctx.fillStyle = '#0ff';
      ctx.beginPath(); ctx.arc(dx+cp/2, dy+cp/2, dotR, 0, Math.PI*2); ctx.fill();
    } else if (!evt.is_warp && overlays.events) {
      const drawn = evt.character_name && drawNpcSprite(getNpcURL(evt.character_name), dx, dy, cp);
      if (!drawn) {
        ctx.fillStyle = '#ff0';
        ctx.beginPath(); ctx.arc(dx+cp/2, dy+cp/2, dotR, 0, Math.PI*2); ctx.fill();
      }
    }
    if (overlays.events && cp >= 16) {
      ctx.fillStyle = '#fff';
      ctx.fillText(evt.name.slice(0,4), dx+1, dy+cp-2);
    }
  }
  ctx.restore();
  // Draw order: planned (underneath) -> walked -> declared/observed beat
  // markers (on top), so the predicted route reads first, the actual walk
  // draws over it, and the beat stars/status-shapes stay legible above both.
  if (viewMode === 'events' && showPlanned) drawPlannedRoute(m, cp, baseX, baseY);
  if (viewMode === 'events' && showWalked) drawWalkedRoute(m, cp, baseX, baseY);
  if (viewMode === 'events' && showBeats) drawBeatMarkers(m, cp, baseX, baseY);
}

// ---- Events mode: planned route (slice 3) -- the offline solver's walk,
// drawn as a connected polyline through the tiles it covers on this map
// plus a subtle per-tile mark, so it reads clearly UNDER the declared
// stars and observed status shapes drawn afterward. A crossed foreign
// trigger is the fail-loud signal this layer exists for, so it gets its
// own loud, shape-redundant marker (an X plus a ring, not just a colour).
function drawPlannedRoute(m, cp, baseX, baseY) {
  const data = beatsByMember.get(m.id);
  if (!data || data === 'loading' || data === 'error') return;
  const planned = data.planned || [];
  if (!planned.length) return;
  ctx.save();
  const dotR = Math.max(1.5, cp * 0.09);
  for (const item of planned) {
    const tiles = item.tiles || [];
    if (!tiles.length) continue;
    ctx.strokeStyle = 'rgba(0,114,178,0.6)';
    ctx.lineWidth = Math.max(2, cp * 0.16);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.beginPath();
    tiles.forEach(function(t, i) {
      const cx = baseX + t[0] * cp + cp / 2, cy = baseY + t[1] * cp + cp / 2;
      if (i === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
    });
    ctx.stroke();
    ctx.fillStyle = 'rgba(0,114,178,0.5)';
    tiles.forEach(function(t) {
      const cx = baseX + t[0] * cp + cp / 2, cy = baseY + t[1] * cp + cp / 2;
      ctx.beginPath(); ctx.arc(cx, cy, dotR, 0, Math.PI * 2); ctx.fill();
    });
    (item.crossings || []).forEach(function(c) {
      const cx = baseX + c.x * cp + cp / 2, cy = baseY + c.y * cp + cp / 2;
      const cr = Math.max(5, cp * 0.32);
      ctx.setLineDash(c.certainty === 'possible' ? [3, 2] : []);
      ctx.strokeStyle = PLANNED_CROSSING_COLOR;
      ctx.lineWidth = Math.max(2, cp * 0.13);
      ctx.beginPath();
      ctx.moveTo(cx - cr, cy - cr); ctx.lineTo(cx + cr, cy + cr);
      ctx.moveTo(cx + cr, cy - cr); ctx.lineTo(cx - cr, cy + cr);
      ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, cy, cr * 1.15, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
    });
  }
  ctx.restore();
}

// ---- Events mode: walked route (Q13 slice 4) -- the ACTUALLY-walked tile
// sequence, one row per beat (`beat_markers`'s `walked` layer), drawn the
// same way `drawPlannedRoute` draws its predicted route (polyline + per-tile
// dot) but in a visually distinct color so "predicted" and "actual" never
// get confused on the same map. `off_plan` tiles get a hollow marker (a
// non-blocking Q8 contradiction -- informational, not an error); `violations`
// get the loud ring+X treatment `PLANNED_CROSSING_COLOR` uses for a
// predicted crossing, but in a hotter color and filled, since an observed
// trigger violation is a beat FAILURE (divergence.py's `failed`), a more
// severe event than a merely-declared crossing.
function drawWalkedRoute(m, cp, baseX, baseY) {
  const data = beatsByMember.get(m.id);
  if (!data || data === 'loading' || data === 'error') return;
  const walked = data.walked || [];
  if (!walked.length) return;
  ctx.save();
  const dotR = Math.max(1.5, cp * 0.09);
  for (const item of walked) {
    const tiles = item.tiles || [];
    if (!tiles.length) continue;
    ctx.strokeStyle = 'rgba(213,94,0,0.75)';
    ctx.lineWidth = Math.max(2, cp * 0.14);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.beginPath();
    tiles.forEach(function(t, i) {
      const cx = baseX + t[0] * cp + cp / 2, cy = baseY + t[1] * cp + cp / 2;
      if (i === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
    });
    ctx.stroke();
    ctx.fillStyle = 'rgba(213,94,0,0.6)';
    tiles.forEach(function(t) {
      const cx = baseX + t[0] * cp + cp / 2, cy = baseY + t[1] * cp + cp / 2;
      ctx.beginPath(); ctx.arc(cx, cy, dotR, 0, Math.PI * 2); ctx.fill();
    });
    (item.off_plan || []).forEach(function(t) {
      // Hollow marker: evidence the offline graph may be wrong about the
      // engine (Q8 KIND_OFF_PLAN), carried and non-blocking -- deliberately
      // NOT drawn with the same loud fill as a violation below.
      const cx = baseX + t[0] * cp + cp / 2, cy = baseY + t[1] * cp + cp / 2;
      const r = Math.max(4, cp * 0.24);
      ctx.strokeStyle = WALKED_ROUTE_COLOR;
      ctx.lineWidth = Math.max(1.5, cp * 0.09);
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    });
    (item.violations || []).forEach(function(v) {
      const cx = baseX + v.x * cp + cp / 2, cy = baseY + v.y * cp + cp / 2;
      const cr = Math.max(5, cp * 0.34);
      ctx.fillStyle = 'rgba(255,43,43,0.35)';
      ctx.beginPath(); ctx.arc(cx, cy, cr * 1.15, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = WALKED_VIOLATION_COLOR;
      ctx.lineWidth = Math.max(2.5, cp * 0.16);
      ctx.beginPath();
      ctx.moveTo(cx - cr, cy - cr); ctx.lineTo(cx + cr, cy + cr);
      ctx.moveTo(cx + cr, cy - cr); ctx.lineTo(cx - cr, cy + cr);
      ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, cy, cr * 1.15, 0, Math.PI * 2); ctx.stroke();
    });
  }
  ctx.restore();
}

// ---- Events mode: beat markers (declared = star, observed = status-shaped
// dot; a connecting line between them is the whole declared-vs-actual point).
function starPath(cx, cy, r) {
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const rad = i % 2 === 0 ? r : r * 0.45;
    const ang = -Math.PI/2 + i * Math.PI/5;
    const px = cx + rad * Math.cos(ang), py = cy + rad * Math.sin(ang);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.closePath();
}
function statusShapePath(cx, cy, r, shape) {
  ctx.beginPath();
  if (shape === 'circle') { ctx.arc(cx, cy, r, 0, Math.PI*2); }
  else if (shape === 'square') { ctx.rect(cx-r, cy-r, r*2, r*2); }
  else if (shape === 'triangle') { ctx.moveTo(cx, cy-r); ctx.lineTo(cx+r, cy+r); ctx.lineTo(cx-r, cy+r); ctx.closePath(); }
  else { ctx.moveTo(cx, cy-r); ctx.lineTo(cx+r, cy); ctx.lineTo(cx, cy+r); ctx.lineTo(cx-r, cy); ctx.closePath(); }  // diamond
}
function drawBeatMarkers(m, cp, baseX, baseY) {
  const data = beatsByMember.get(m.id);
  if (!data || data === 'loading' || data === 'error') return;
  const declared = data.declared || [];
  const observed = data.observed || [];
  const byKey = new Map();
  function bucket(k) { if (!byKey.has(k)) byKey.set(k, {declared: [], observed: []}); return byKey.get(k); }
  declared.forEach(function(b) { bucket(beatKey(b)).declared.push(b); });
  observed.forEach(function(b) { bucket(beatKey(b)).observed.push(b); });
  ctx.save();
  ctx.font = Math.max(8, Math.min(cp-4, 11)) + 'px monospace';
  for (const [key, g] of byKey) {
    if (g.declared.length && g.observed.length) {
      const d0 = g.declared[0], o0 = g.observed[0];
      ctx.strokeStyle = 'rgba(255,255,255,0.5)';
      ctx.setLineDash([3,3]); ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(baseX + d0.x*cp + cp/2, baseY + d0.y*cp + cp/2);
      ctx.lineTo(baseX + o0.x*cp + cp/2, baseY + o0.y*cp + cp/2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }
  const r = Math.max(4, cp * 0.22);
  declared.forEach(function(b) {
    const cx = baseX + b.x*cp + cp/2, cy = baseY + b.y*cp + cp/2;
    starPath(cx, cy, r);
    // A DERIVED marker comes from a step-6a locations file, not an authored
    // chapter module: it is a proposal under review, so it is drawn hollow
    // with a dashed outline and must never read as a registered beat.
    if (b.derived) {
      ctx.fillStyle = 'rgba(255,224,102,0.25)'; ctx.fill();
      ctx.setLineDash([3,2]);
    } else {
      ctx.fillStyle = '#ffe066'; ctx.fill();
    }
    ctx.strokeStyle = '#7a5c00'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.setLineDash([]);
    if (cp >= 20) {
      // Label with the beat's OWN name, and its solved route position when
      // there is one. This used to print 'B' + the array index, which is
      // not the beat id and not the visit order -- beat ids are labels, not
      // an ordering (playtest/chapter.py `beat()`), so an index-derived
      // label was wrong twice over.
      const label = (b.order != null ? '#' + b.order + ' ' : '') + (b.beat || '?');
      ctx.fillStyle = '#000'; ctx.fillText(label, cx+r+1, cy+3);
      ctx.fillStyle = '#ffe066'; ctx.fillText(label, cx+r, cy+2);
    }
  });
  observed.forEach(function(b, i) {
    const st = STATUS_STYLE[b.status] || STATUS_STYLE.skipped;
    const cx = baseX + b.x*cp + cp/2, cy = baseY + b.y*cp + cp/2;
    statusShapePath(cx, cy, r*0.65, st.shape);
    if (b.status === 'skipped') { ctx.strokeStyle = st.color; ctx.lineWidth = 1.5; ctx.stroke(); }
    else { ctx.fillStyle = st.color; ctx.fill(); ctx.strokeStyle = '#111'; ctx.lineWidth = 1; ctx.stroke(); }
    if (cp >= 20) {
      const olabel = b.beat || ('N' + i);
      ctx.fillStyle = '#000'; ctx.fillText(olabel, cx+r*0.65+1, cy+3);
      ctx.fillStyle = st.color; ctx.fillText(olabel, cx+r*0.65, cy+2);
    }
  });
  ctx.restore();
}

// Seam-connection bands: thin clickable strips just OUTSIDE the connected edge
// (single-map only — in stitched mode the neighbor is drawn for real).
function seamBands() {
  if (stitched || !V.graph || !V.graph.connections) return [];
  const cp = cellPx();
  const th = Math.max(14, cp * 0.55);
  const w = D.meta.xsize, h = D.meta.ysize;
  const out = [];
  for (const c of V.graph.connections) {
    let r;
    if (c.edge === 'N')      r = {x: panX + c.band[0]*cp, y: panY - th,        w: (c.band[1]-c.band[0])*cp, h: th};
    else if (c.edge === 'S') r = {x: panX + c.band[0]*cp, y: panY + h*cp,      w: (c.band[1]-c.band[0])*cp, h: th};
    else if (c.edge === 'W') r = {x: panX - th,           y: panY + c.band[0]*cp, w: th, h: (c.band[1]-c.band[0])*cp};
    else                     r = {x: panX + w*cp,         y: panY + c.band[0]*cp, w: th, h: (c.band[1]-c.band[0])*cp};
    out.push({conn: c, rect: r});
  }
  return out;
}

function drawSeamBands() {
  const arrows = {N: '⇧', S: '⇩', W: '⇦', E: '⇨'};
  for (const b of seamBands()) {
    const r = b.rect, c = b.conn;
    ctx.fillStyle = 'rgba(170,110,255,0.5)';
    ctx.fillRect(r.x, r.y, r.w, r.h);
    ctx.strokeStyle = 'rgba(190,140,255,0.9)';
    ctx.lineWidth = 1;
    ctx.strokeRect(r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1);
    const label = arrows[c.edge] + ' Map' + String(c.id).padStart(3,'0') + ' ' + (c.name || '');
    ctx.fillStyle = '#dcf';
    ctx.font = '11px monospace';
    if (c.edge === 'N' || c.edge === 'S') {
      if (r.w > 70) ctx.fillText(label, r.x + 4, r.y + r.h/2 + 4, r.w - 8);
    } else {
      ctx.save();
      ctx.translate(r.x + r.w/2 + 4, r.y + 4);
      ctx.rotate(Math.PI/2);
      if (r.h > 70) ctx.fillText(label, 0, 0, r.h - 8);
      ctx.restore();
    }
  }
}

function render() {
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = '#111118';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!ready) {
    ctx.fillStyle = '#5af'; ctx.font = '14px monospace';
    ctx.fillText('Loading…', 10, 30);
    return;
  }
  const cp = cellPx();
  for (const m of members) renderMember(m, cp);
  if (stitched) {
    // member frames + name tags, active highlighted
    ctx.save();
    ctx.font = '12px monospace';
    for (const m of members) {
      const bx = panX + m.ox * cp, by = panY + m.oy * cp;
      ctx.strokeStyle = m === activeM ? 'rgba(90,170,255,0.9)' : 'rgba(255,255,255,0.22)';
      ctx.lineWidth = m === activeM ? 2 : 1;
      ctx.strokeRect(bx + 0.5, by + 0.5, m.w * cp - 1, m.h * cp - 1);
      const tag = 'M' + String(m.id).padStart(3,'0') + ' ' + (m.name || '');
      const tw = ctx.measureText(tag).width + 8;
      ctx.fillStyle = m === activeM ? 'rgba(30,60,100,0.85)' : 'rgba(20,20,28,0.75)';
      ctx.fillRect(bx, by, tw, 16);
      ctx.fillStyle = m === activeM ? '#bdf' : '#99a';
      ctx.fillText(tag, bx + 4, by + 12);
    }
    ctx.restore();
  }
  drawSeamBands();
}

// ---- pointer events (covers mouse + touch) --------------------------------
function ptrRect() { return canvas.getBoundingClientRect(); }
function ptDist(a, b) { return Math.hypot(b.x - a.x, b.y - a.y); }

canvas.addEventListener('pointerdown', function(e) {
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (pointers.size === 1) {
    dragStartX = e.clientX; dragStartY = e.clientY;
    dragPanX = panX; dragPanY = panY;
    dragMoved = false; pinchRef = null;
  } else if (pointers.size === 2) {
    const pts = [...pointers.values()];
    const rect = ptrRect();
    pinchRef = {
      dist: ptDist(pts[0], pts[1]),
      zoom: zoom, panX: panX, panY: panY,
      midX: (pts[0].x + pts[1].x) / 2 - rect.left,
      midY: (pts[0].y + pts[1].y) / 2 - rect.top,
    };
    dragMoved = true; // suppress tap on lift
  }
});

canvas.addEventListener('pointermove', function(e) {
  // status bar update (always, including mouse hover without button)
  if (pointers.size <= 1) {
    const rect = ptrRect();
    const {x, y} = canvasToCell(e.clientX - rect.left, e.clientY - rect.top);
    const hit = memberAt(x, y);
    if (hit && hit.data) {
      const md = hit.data.meta;
      document.getElementById('statusbar').textContent =
        'Map' + String(hit.id).padStart(3,'0') + ' (' + (x - hit.ox) + ', ' + (y - hit.oy) + ')  tileset ' + md.tileset_id;
    }
  }
  if (!pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (pointers.size === 1 && !pinchRef) {
    const ddx = e.clientX - dragStartX, ddy = e.clientY - dragStartY;
    if (Math.abs(ddx) > 4 || Math.abs(ddy) > 4) dragMoved = true;
    panX = dragPanX + ddx; panY = dragPanY + ddy;
    scheduleRender();
  } else if (pointers.size === 2 && pinchRef) {
    const pts = [...pointers.values()];
    const d = ptDist(pts[0], pts[1]);
    const newZoom = Math.max(ZMIN, Math.min(8, pinchRef.zoom * d / pinchRef.dist));
    const scale = (newZoom * 16) / (pinchRef.zoom * 16);
    panX = pinchRef.midX - (pinchRef.midX - pinchRef.panX) * scale;
    panY = pinchRef.midY - (pinchRef.midY - pinchRef.panY) * scale;
    zoom = newZoom;
    updateZoomDisplay(); scheduleRender();
  }
});

canvas.addEventListener('pointerup', function(e) {
  const wasTap = pointers.size === 1 && !dragMoved;
  const ex = e.clientX, ey = e.clientY;
  pointers.delete(e.pointerId);
  if (pointers.size === 0) pinchRef = null;
  if (wasTap) {
    const rect = ptrRect();
    const px = ex - rect.left, py = ey - rect.top;
    // seam-band click: navigate through the connection, landing at the
    // corresponding position on the neighbor's matching edge.
    for (const b of seamBands()) {
      const r = b.rect;
      if (px >= r.x && px < r.x + r.w && py >= r.y && py < r.y + r.h) {
        const c = b.conn, cp = cellPx();
        const wc = canvasToCell(px, py);  // world == local in single-map mode
        // "outside cell" rule: step one cell past my edge, map into the
        // neighbor's local space via the origin delta, clamp inside it.
        let ox, oy;
        if (c.edge === 'N')      { ox = wc.x - c.origin[0]; oy = -1        - c.origin[1]; }
        else if (c.edge === 'S') { ox = wc.x - c.origin[0]; oy = D.meta.ysize - c.origin[1]; }
        else if (c.edge === 'W') { ox = -1        - c.origin[0]; oy = wc.y - c.origin[1]; }
        else                     { ox = D.meta.xsize - c.origin[0]; oy = wc.y - c.origin[1]; }
        location.href = '/map/' + c.id + '?focus=' + ox + ',' + oy;
        return;
      }
    }
    const {x, y} = canvasToCell(px, py);
    const hitM = memberAt(x, y);
    if (hitM && hitM.data) {
      if (hitM !== activeM) setActive(hitM);
      const lx = x - hitM.ox, ly = y - hitM.oy;
      const md = hitM.data.meta;
      const cell = hitM.data.cells[ly * md.xsize + lx];
      const key = lx + ',' + ly;
      if (selection.has(key)) selection.delete(key);  // toggle off
      else selection.set(key, cell);                  // toggle on / accumulate
      focusCell = cell;                               // last-tapped drives the readout
      updateSidebar();
      updateSelectionUI();
      // Events mode: tapping a cell selects it AS TODAY (above) AND, if an
      // event occupies that cell, also loads it into the inspector below --
      // cell-selection and event-inspection are additive, never a fork.
      if (viewMode === 'events') {
        const evtsHere = (hitM.data.events || []).filter(function(ev) {
          return ev.x === lx && ev.y === ly && eventPassesFilter(ev);
        });
        if (evtsHere.length) {
          focusEvent = evtsHere[0];
          loadEventDetail(hitM.id, focusEvent.id);
        }
      }
      scheduleRender();
      // open sidebar on mobile tap
      const sb = document.getElementById('sidebar');
      if (sb.style.position === 'fixed' || window.innerWidth <= 720) sb.classList.add('open');
    }
  }
});

canvas.addEventListener('pointercancel', function(e) {
  pointers.delete(e.pointerId);
  if (pointers.size === 0) pinchRef = null;
});

canvas.addEventListener('wheel', function(e) {
  e.preventDefault();
  const rect = ptrRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const oldCp = cellPx();
  const step = e.deltaY < 0 ? 0.5 : -0.5;
  const newZoom = Math.max(ZMIN, Math.min(8, Math.round((zoom + step) * 2) / 2));
  if (newZoom === zoom) return;
  const newCp = newZoom * 16;
  panX = mx - (mx - panX) * newCp / oldCp;
  panY = my - (my - panY) * newCp / oldCp;
  zoom = newZoom;
  updateZoomDisplay(); scheduleRender();
}, {passive: false});

// ---- toolbar controls -----------------------------------------------------
document.querySelectorAll('input[name="layer"]').forEach(function(r) {
  r.addEventListener('change', function() { currentLayer = r.value; scheduleRender(); });
});
// 2-way RPG-Maker <-> Quantized(family) toggle: drives the same `currentLayer` as the
// dormant per-layer radios above (values 'rmxp' / 'post-quant').
document.querySelectorAll('input[name="view2"]').forEach(function(r) {
  r.addEventListener('change', function() { currentLayer = r.value; scheduleRender(); });
});
/*KNOBBAR_JS*/
['collision','diff','priority','merge','events','warps','animated'].forEach(function(name) {
  const el = document.getElementById('ov_' + name);
  el.addEventListener('change', function() { overlays[name] = el.checked; scheduleRender(); });
});

// ---- mode switch (Graphics | Events) --------------------------------------
// `viewMode` gates behaviour in the ONE shared renderer/tap-handler above; it
// never forks the render path. Persisted to localStorage and to `?mode=` so a
// shared link opens in the same mode; the existing `?g=` cache-buster (image
// URLs only, never the page URL) is untouched.
function applyModeUI() {
  document.body.classList.toggle('mode-events', viewMode === 'events');
  document.body.classList.toggle('mode-graphics', viewMode === 'graphics');
  document.getElementById('mode-btn-graphics').classList.toggle('on', viewMode === 'graphics');
  document.getElementById('mode-btn-events').classList.toggle('on', viewMode === 'events');
  renderLegend();
  if (viewMode === 'events') {
    loadBeats(activeM);
    renderBeatPanel();
  }
}
function setMode(next) {
  if (next !== 'events' && next !== 'graphics') return;
  viewMode = next;
  try { localStorage.setItem('mv_mode', viewMode); } catch (e) {}
  const params = new URLSearchParams(location.search);
  if (viewMode === 'graphics') params.delete('mode'); else params.set('mode', viewMode);
  const qs = params.toString();
  history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
  applyModeUI();
  scheduleRender();
}
document.getElementById('mode-btn-graphics').onclick = function() { setMode('graphics'); };
document.getElementById('mode-btn-events').onclick = function() { setMode('events'); };
document.getElementById('evt-filter').addEventListener('change', function(e) {
  eventFilter = e.target.value;
  renderBeatPanel();  // no beat/kind coupling today (beats carry no kind) but
                       // keep the redraw so anything filter-dependent stays in sync
  scheduleRender();
});
document.getElementById('ov_beats').addEventListener('change', function(e) { showBeats = e.target.checked; scheduleRender(); });
document.getElementById('ov_planned').addEventListener('change', function(e) { showPlanned = e.target.checked; scheduleRender(); });
document.getElementById('ov_walked').addEventListener('change', function(e) { showWalked = e.target.checked; scheduleRender(); });
document.getElementById('ov_dim').addEventListener('change', function(e) { dimBase = e.target.checked; scheduleRender(); });
document.getElementById('beat-head').onclick = function() {
  const list = document.getElementById('beat-list');
  const open = list.style.display !== 'none';
  list.style.display = open ? 'none' : 'block';
  document.getElementById('beat-tri').innerHTML = open ? '&#9656;' : '&#9662;';
};

// ---- Advanced (quant / graphics-debug) toggle -----------------------------
// Collapses the knob bar, palette link, debug overlays and worst-merges panel
// behind one button; `body.adv` drives their CSS visibility.  Leaving Advanced
// clears the debug overlays so the canvas returns to a clean feedback view.
document.getElementById('btn-advanced').onclick = function() {
  advanced = !advanced;
  document.body.classList.toggle('adv', advanced);
  this.classList.toggle('on', advanced);
  if (!advanced) {
    ['diff','priority','merge'].forEach(function(name) {
      overlays[name] = false;
      const el = document.getElementById('ov_' + name);
      if (el) el.checked = false;
    });
  }
  updateSidebar();  // reveal/hide the per-cell Palettes + quad-fit sections
  scheduleRender();
};
document.getElementById('zoom-in').onclick = function() {
  zoom = Math.min(8, Math.round((zoom + 0.5) * 2) / 2);
  updateZoomDisplay(); scheduleRender();
};
document.getElementById('zoom-out').onclick = function() {
  zoom = Math.max(0.5, Math.round((zoom - 0.5) * 2) / 2);
  updateZoomDisplay(); scheduleRender();
};
document.getElementById('zoom-fit').onclick = fitMap;

// ---- sidebar toggle (mobile) ----------------------------------------------
document.getElementById('sidebar-toggle').onclick = function() {
  document.getElementById('sidebar').classList.toggle('open');
};

// ---- cell inspector sidebar -----------------------------------------------
// ---- palette/swatch helpers -----------------------------------------------
let showAllColorChanges = false;

function swatchTitle(c) {
  const r = c[0], g = c[1], b = c[2];
  const hex = '#' + [r,g,b].map(function(v){return v.toString(16).padStart(2,'0');}).join('').toUpperCase();
  const r5 = r>>3, g5 = g>>3, b5 = b>>3;
  const bgr555 = (b5<<10)|(g5<<5)|r5;
  return 'rgb(' + r + ',' + g + ',' + b + ')  ' + hex + '  BGR555: 0x' + bgr555.toString(16).toUpperCase().padStart(4,'0') + ' (' + r5 + ',' + g5 + ',' + b5 + ')';
}
function swatchHtml(c) {
  const hex = '#' + c.map(function(v){return v.toString(16).padStart(2,'0');}).join('');
  return '<span class="swatch" style="background:' + hex + '" title="' + swatchTitle(c) + '"></span>';
}
function buildCCRows(colorChanges, showAll) {
  let h = '';
  for (const cc of colorChanges) {
    const orig = cc[0], final = cc[1];
    const changed = orig[0] !== final[0] || orig[1] !== final[1] || orig[2] !== final[2];
    if (!showAll && !changed) continue;
    h += '<div class="cc-row' + (changed ? ' changed' : '') + '">';
    h += swatchHtml(orig);
    h += '<span class="cc-arrow">&rarr;</span>';
    h += swatchHtml(final);
    h += '<span class="' + (changed ? 'cc-tag-changed' : 'cc-tag-same') + '">' + (changed ? 'changed' : 'same') + '</span>';
    h += '</div>';
  }
  if (!h) h = '<span class="lbl">' + (showAll ? '(none)' : '(no changes)') + '</span>';
  return h;
}
function updateCCSection() {
  const el = document.getElementById('cc-section');
  if (!el || !focusCell) return;
  const ckPal = D.colkey_palettes ? D.colkey_palettes[focusCell.colkey_idx] : null;
  if (!ckPal) return;
  const ccId = 'cc_toggle_' + focusCell.x + '_' + focusCell.y;
  const cb = document.getElementById(ccId);
  if (cb) showAllColorChanges = cb.checked;
  el.innerHTML = buildCCRows(ckPal.color_changes, showAllColorChanges);
}

function thumbHtml(url, label) {
  if (!url) return '<span class="lbl">[no img]</span>';
  return '<img class="thumb" src="' + url + '" title="' + label + '" loading="lazy">';
}
// Per-8x8-quadrant palette fit: how many of a quadrant's source colours had to be
// merged (snapped to a different palette colour) to fit its 15-colour sub-palette.
function quadFitHtml(cpal) {
  if (!cpal || !cpal.quadrant_fit || !cpal.quadrant_fit.length) return '';
  let h = '<div class="lbl" style="margin-top:5px">Palette fit (per 8&times;8 quadrant):</div>';
  for (const q of cpal.quadrant_fit) {
    const loc = (q.slot < 4 ? 'B' : 'T') + (q.slot % 4);  // Bottom/Top quadrant 0-3
    let cls = 'qfit-ok';
    if (q.merged > 0) cls = (q.max_shift >= 3 || q.merged >= 6) ? 'qfit-bad' : 'qfit-warn';
    const detail = q.merged > 0
      ? (q.merged + '/' + q.n + ' merged, &Delta;&le;' + q.max_shift)
      : (q.n + ' colours fit');
    h += '<div class="qfit ' + cls + '"><b>' + loc + '</b> pal' + q.pal + ' &middot; ' + detail + '</div>';
  }
  if (cpal.merge_colors > 0) {
    h += '<div class="lbl" style="margin-top:3px">metatile: <span class="qfit-bad-txt">' +
      cpal.merge_colors + ' colours merged</span>, severity ' + cpal.merge_severity + '</div>';
  } else {
    h += '<div class="lbl" style="margin-top:3px"><span class="qfit-ok-txt">no merge loss</span> (truncation only)</div>';
  }
  return h;
}
function passageStr(p) {
  if (!p) return '0x00 (open)';
  if ((p & 0x0F) === 0x0F) return '0x0F (blocked)';
  const dirs = [];
  if (p & 1) dirs.push('D'); if (p & 2) dirs.push('L');
  if (p & 4) dirs.push('R'); if (p & 8) dirs.push('U');
  return '0x' + p.toString(16).padStart(2,'0') + ' (' + (dirs.join(',') || 'open') + ')';
}

// ---- Events-mode: event inspector + beat panel rendering -------------------
function kindBadgeHtml(kind) {
  const c = KIND_COLORS[kind] || KIND_COLORS.other;
  const l = KIND_LABELS[kind] || kind;
  return '<span class="evt-kind-badge" style="background:' + c + '">' + escHtml(l) + '</span>';
}
function conditionHtml(label, cond) {
  if (!cond) return '';
  if ('valid' in cond && cond.valid === false && !('value' in cond)) return '';
  if (cond.ch !== undefined) {  // self-switch
    if (!cond.valid) return '';
    return '<div><span class="lbl">' + label + '</span> <span class="val">' + escHtml(cond.ch) + '</span></div>';
  }
  if (!cond.valid) return '';
  let v = '<span class="val">' + escHtml(cond.name || ('#' + cond.id)) + '</span>';
  if (cond.value !== undefined) v += ' == ' + cond.value;
  return '<div><span class="lbl">' + label + '</span> ' + v + '</div>';
}
function pagesHtml(pages) {
  if (!pages || !pages.length) return '<div class="lbl">(no pages)</div>';
  let h = '';
  for (const p of pages) {
    h += '<div class="layer-row" style="flex-direction:column;align-items:stretch">';
    h += '<div><span class="lbl">page ' + p.page + '</span> <span class="val">' + escHtml(p.trigger.name) + '</span>';
    if (p.priority_type) h += ' <span class="lbl">above-player</span>';
    h += '</div>';
    const c = p.condition || {};
    h += conditionHtml('switch1', c.switch1);
    h += conditionHtml('switch2', c.switch2);
    h += conditionHtml('self-switch', c.self_switch);
    h += conditionHtml('variable', c.variable);
    if (p.graphic && p.graphic.character_name) h += '<div><span class="lbl">graphic</span> <span class="val">' + escHtml(p.graphic.character_name) + '</span></div>';
    h += '<div><span class="lbl">move</span> <span class="val">' + escHtml(String(p.move_type)) + '</span> ' +
      '<span class="lbl">through</span> <span class="val">' + escHtml(String(p.through)) + '</span></div>';
    if (p.dialogue) h += '<div><span class="lbl">says</span> <span class="val">' + escHtml(p.dialogue) + '</span></div>';
    const cmdId = 'cmds_' + p.page + '_' + Math.random().toString(36).slice(2, 7);
    h += '<div><span class="lbl" style="cursor:pointer" onclick="var b=document.getElementById(\'' + cmdId +
      '\');b.style.display=b.style.display===\'none\'?\'block\':\'none\';">&#9656; ' + (p.commands || []).length + ' commands</span></div>';
    h += '<div id="' + cmdId + '" class="evt-cmd-block" style="display:none">' +
      escHtml(JSON.stringify(p.commands || [], null, 1)) + '</div>';
    h += '</div>';
  }
  return h;
}
function renderEventDetail(ev) {
  let h = '';
  h += '<div><span class="lbl">id</span> <span class="val">' + ev.id + '</span> ' + kindBadgeHtml(ev.kind) + '</div>';
  h += '<div><span class="lbl">label</span> <span class="val">' + escHtml(ev.label || ev.name) + '</span></div>';
  h += '<div><span class="lbl">rmxp name</span> <span class="val">' + escHtml(ev.name) + '</span></div>';
  h += '<div><span class="lbl">pos</span> <span class="val">(' + ev.x + ', ' + ev.y + ')</span> ' +
    '<span class="lbl">pages</span> <span class="val">' + ev.npages + '</span></div>';
  if (ev.trigger) h += '<div><span class="lbl">trigger</span> <span class="val">' + escHtml(ev.trigger.name) + '</span></div>';
  if (ev.warp) {
    h += '<div class="section-title" style="margin-top:8px">Warp destination</div>';
    h += '<div><span class="lbl">map</span> <span class="val">' + escHtml(String(ev.warp.map_id !== undefined ? ev.warp.map_id : JSON.stringify(ev.warp))) + '</span>';
    if (ev.warp.x !== undefined) h += ' <span class="lbl">at</span> <span class="val">(' + ev.warp.x + ', ' + ev.warp.y + ')</span>';
    h += '</div>';
  }
  if (ev.trainer) {
    const t = ev.trainer;
    h += '<div class="section-title" style="margin-top:8px">Trainer</div>';
    h += '<div><span class="lbl">constant</span> <span class="val">' + escHtml(t.trainer_constant || '') + '</span></div>';
    h += '<div><span class="lbl">display</span> <span class="val">' + escHtml(t.display_name || '') + '</span> ' +
      '<span class="lbl">class</span> <span class="val">' + escHtml(t.class_name || t.trainer_class_constant || '') + '</span></div>';
    h += '<div><span class="lbl">kind</span> <span class="val">' + escHtml(t.kind || '') + '</span> ' +
      '<span class="' + (t.staged ? 'evt-staged-yes' : 'evt-staged-no') + '">' + (t.staged ? 'in ROM' : 'not staged') + '</span></div>';
    if (t.party && t.party.length) {
      h += '<div class="lbl" style="margin-top:3px">party</div>';
      for (const p of t.party) h += '<div class="val">&middot; ' + escHtml(p.species || '') + ' Lv' + (p.level !== undefined ? p.level : '?') + '</div>';
    }
    if (t.items && t.items.length) h += '<div class="lbl">items</div><div class="val">' + escHtml(t.items.join(', ')) + '</div>';
  }
  h += '<div class="section-title" style="margin-top:8px">Pages</div>';
  h += pagesHtml(ev.pages);
  if (ev.notes && ev.notes.length) {
    h += '<div class="section-title" style="margin-top:8px">Notes</div>';
    for (const n of ev.notes) h += '<div class="lbl">' + escHtml(n) + '</div>';
  }
  return h;
}
function eventPassesFilter(ev) {
  if (eventFilter === 'all') return true;
  if (eventFilter === 'conditional') return !!ev.has_conditions;
  return ev.kind === eventFilter;
}
function beatKey(b) { return b.chapter + '::' + b.beat; }
function renderLegend() {
  const el = document.getElementById('legend');
  if (!el) return;
  let h = '<span class="lbl">kind:</span>';
  for (const k of Object.keys(KIND_COLORS)) {
    h += '<span><span class="legend-sw" style="background:' + KIND_COLORS[k] + '"></span>' + KIND_LABELS[k] + '</span>';
  }
  h += '<span class="lbl" style="margin-left:8px">beats:</span>';
  h += '<span>&#9733; declared</span>';
  for (const s of Object.keys(STATUS_STYLE)) {
    h += '<span><span class="legend-sw" style="background:' + STATUS_STYLE[s].color + ';border-radius:2px"></span>' + s + '</span>';
  }
  h += '<span class="lbl" style="margin-left:8px">planned:</span>';
  h += '<span><span class="legend-sw" style="background:' + PLANNED_ROUTE_COLOR + '"></span>route</span>';
  h += '<span style="color:' + PLANNED_CROSSING_COLOR + '">&#10006; crossing</span>';
  h += '<span class="lbl" style="margin-left:8px">walked:</span>';
  h += '<span><span class="legend-sw" style="background:' + WALKED_ROUTE_COLOR + '"></span>route</span>';
  h += '<span style="color:' + WALKED_ROUTE_COLOR + '">&#9711; off-plan</span>';
  h += '<span style="color:' + WALKED_VIOLATION_COLOR + '">&#10006; violation</span>';
  el.innerHTML = h;
  el.classList.toggle('show', viewMode === 'events');
}
function renderBeatPanel() {
  const listEl = document.getElementById('beat-list');
  const notesEl = document.getElementById('beat-notes');
  const countEl = document.getElementById('beat-count');
  if (!listEl) return;
  const data = beatsByMember.get(activeM.id);
  if (!data || data === 'loading') { listEl.innerHTML = '<span class="lbl">Loading…</span>'; notesEl.textContent = ''; return; }
  if (data === 'error') { listEl.innerHTML = '<span class="mismatch">Failed to load beats.</span>'; notesEl.textContent = ''; return; }
  const declared = data.declared || [];
  const observed = data.observed || [];
  const planned = data.planned || [];
  const walked = data.walked || [];
  const contradictions = data.contradictions || [];
  const conformance = data.conformance || {};
  countEl.textContent = '(' + declared.length + ' declared, ' + observed.length + ' observed, ' +
    planned.length + ' planned, ' + walked.length + ' walked)';
  notesEl.innerHTML = (data.notes || []).map(function(n) { return escHtml(n); }).join('<br>');
  const byChapter = new Map();
  function bucket(chapter) {
    if (!byChapter.has(chapter)) byChapter.set(chapter, {declared: [], observed: [], planned: [], walked: [], contradictions: []});
    return byChapter.get(chapter);
  }
  declared.forEach(function(b) { bucket(b.chapter).declared.push(b); });
  observed.forEach(function(b) { bucket(b.chapter).observed.push(b); });
  planned.forEach(function(p) { bucket(p.chapter).planned.push(p); });
  walked.forEach(function(w) { bucket(w.chapter).walked.push(w); });
  contradictions.forEach(function(c) { bucket(c.chapter).contradictions.push(c); });
  let h = '';
  if (!byChapter.size) h = '<span class="lbl">No beats declared for this map.</span>';
  for (const [chapter, g] of byChapter) {
    h += '<div class="beat-chapter">' + escHtml(chapter) + '</div>';
    // Derived rows sort by solved route position, not by beat id: the point
    // of reviewing them is the ORDER, and ids are labels (playtest/chapter.py
    // `beat()`), so id order would actively mislead. Authored rows keep
    // registration order, which already IS playthrough order.
    const declaredRows = g.declared.slice();
    if (declaredRows.length && declaredRows.every(function(b) { return b.order != null; })) {
      declaredRows.sort(function(a, b) { return a.order - b.order; });
    }
    declaredRows.forEach(function(b, i) {
      const cls = 'beat-row' + (b.derived ? ' beat-derived' : '');
      const pos = b.order != null ? '<span class="beat-order">#' + b.order + '</span> ' : '';
      h += '<div class="' + cls + '" onclick="focusBeat(' + JSON.stringify(chapter) + ',' + JSON.stringify(b.beat) + ',\'declared\',' + i + ')">' +
        '&#9733; ' + pos + '<b>' + escHtml(b.beat) + '</b> ' + escHtml(b.description || '') +
        (b.derived ? ' <span class="beat-derived-tag">derived</span>' : '') + '</div>';
    });
    g.observed.forEach(function(b, i) {
      const cls = 'beat-status-' + (b.status || 'skipped');
      h += '<div class="beat-row ' + cls + '" onclick="focusBeat(' + JSON.stringify(chapter) + ',' + JSON.stringify(b.beat) + ',\'observed\',' + i + ')">' +
        (STATUS_STYLE[b.status] ? '&#9679;' : '&#9671;') + ' <b>' + escHtml(b.beat) + '</b> ' + escHtml(b.status || '') + ' (' + escHtml(b.phase || '') + ')</div>';
    });
    g.planned.forEach(function(p) {
      const crossCount = (p.crossings || []).length;
      const cls = 'beat-row beat-planned' + (crossCount ? ' beat-planned-crossing' : '');
      h += '<div class="' + cls + '" onclick="focusPlanned(' + JSON.stringify(chapter) + ',' + p.segment + ')">' +
        '&#8594; seg ' + p.segment + ': ' + escHtml(String(p.from_node)) + ' &rarr; ' + escHtml(String(p.to_node)) +
        ' (' + p.tiles.length + ' tiles)' +
        (crossCount ? ' <span class="planned-crossing-tag">&#10006; ' + crossCount +
          ' crossing' + (crossCount > 1 ? 's' : '') + '</span>' : '') +
        '</div>';
    });
    g.walked.forEach(function(w) {
      const violCount = (w.violations || []).length;
      const offCount = (w.off_plan || []).length;
      const cls = 'beat-row beat-walked' + (violCount ? ' beat-walked-violation' : '');
      h += '<div class="' + cls + '" onclick="focusWalked(' + JSON.stringify(chapter) + ',' + JSON.stringify(w.beat) + ')">' +
        '&#8605; <b>' + escHtml(w.beat) + '</b> walked (' + w.tiles.length + ' tiles' +
        (w.compared ? '' : ', not compared') + ')' +
        (offCount ? ' <span class="walked-off-plan-tag">&#9711; ' + offCount + ' off-plan</span>' : '') +
        (violCount ? ' <span class="walked-violation-tag">&#10006; ' + violCount +
          ' violation' + (violCount > 1 ? 's' : '') + '</span>' : '') +
        '</div>';
    });
    // Contradictions render as INFORMATION, not error (Q8 decision 1: a
    // carried, non-blocking finding) -- a distinct class from every
    // beat-status-* / beat-*-crossing class above, deliberately never
    // colored red/orange the way a failure or violation is.
    g.contradictions.forEach(function(c) {
      h += '<div class="beat-row beat-contradiction">' +
        '&#9432; <b>' + escHtml(c.kind) + '</b>' +
        (c.scope === 'unscoped' ? ' <span class="lbl">(no map)</span>' : '') +
        (c.count > 1 ? ' <span class="lbl">&times;' + c.count + '</span>' : '') +
        '<div class="lbl" style="margin-left:14px">' + escHtml(c.detail || '') + '</div>' +
        '</div>';
    });
  }
  if (Object.keys(conformance).length) {
    h += '<div class="beat-chapter">conformance</div>';
    for (const chapter of Object.keys(conformance)) {
      const cf = conformance[chapter] || {};
      h += '<div class="beat-row beat-contradiction">' +
        '<b>' + escHtml(chapter) + '</b> <span class="lbl">oracle:</span> ' + escHtml(cf.oracle || '?') +
        ' <span class="lbl">walkability disagreements:</span> ' + (cf.walkability_disagreements || 0) +
        ' <span class="lbl">distinct cells:</span> ' + (cf.distinct_cells || 0) + '</div>';
    }
  }
  listEl.innerHTML = h;
}
function focusWalked(chapter, beatName) {
  const data = beatsByMember.get(activeM.id);
  if (!data) return;
  const item = (data.walked || []).find(function(w) { return w.chapter === chapter && w.beat === beatName; });
  if (!item || !item.tiles || !item.tiles.length) return;
  const t = item.tiles[0];
  centerOnCell(activeM, t[0], t[1], 3);
}
function focusBeat(chapter, beatName, which, idx) {
  const data = beatsByMember.get(activeM.id);
  if (!data) return;
  const list = which === 'declared' ? (data.declared || []) : (data.observed || []);
  const matches = list.filter(function(b) { return b.chapter === chapter && b.beat === beatName; });
  const b = matches[idx] || matches[0];
  if (!b || b.x === undefined || b.y === undefined) return;
  centerOnCell(activeM, b.x, b.y, 3);
}
function focusPlanned(chapter, segment) {
  const data = beatsByMember.get(activeM.id);
  if (!data) return;
  const item = (data.planned || []).find(function(p) { return p.chapter === chapter && p.segment === segment; });
  if (!item || !item.tiles || !item.tiles.length) return;
  const t = item.tiles[0];
  centerOnCell(activeM, t[0], t[1], 3);
}

function updateSidebar() {
  if (!focusCell) return;
  const cell = focusCell;
  const m = D.meta;
  const ck_str = D.colkeys_list ? D.colkeys_list[cell.colkey_idx] : '';
  const attrs = D.metatile_attrs ? D.metatile_attrs[cell.colkey_idx] : null;
  const ik = cell.x + ',' + cell.y;
  const covering = flags.filter(function(f){ return (f.cells||[]).some(function(c){ return c[0]===cell.x && c[1]===cell.y; }); });
  let html = '';
  html += '<div class="section-title">Cell (' + cell.x + ', ' + cell.y + ')' +
    (selection.has(ik) ? ' <span style="color:#5af">&#9632; selected</span>' : '') + '</div>';
  html += '<div class="lbl">Tileset ' + m.tileset_id + ': ' + m.name + ' / ' + m.tileset_name + '</div>';
  if (covering.length) html += '<div style="color:#fa0">&#9873; In ' + covering.length + ' flag' +
    (covering.length > 1 ? 's' : '') + ': ' + escHtml(covering.map(function(f){ return f.note || '(no note)'; }).join(' | ')) + '</div>';

  html += '<div class="section-title">RMXP Layers</div>';
  if (cell.layer_detail.length === 0) {
    html += '<div class="lbl">(empty cell)</div>';
  } else {
    for (const ld of cell.layer_detail) {
      html += '<div class="layer-row">';
      html += thumbHtml(getTileURL(ld.tile_id), 'tile ' + ld.tile_id);
      html += '<div>';
      html += '<div><span class="lbl">L' + ld.z + ' tid</span> <span class="val">' + ld.tile_id + '</span>';
      if (ld.autotile_name) html += ' <span class="lbl">(' + ld.autotile_name + ')</span>';
      html += '</div>';
      html += '<div><span class="lbl">pass</span> <span class="val">' + passageStr(ld.passage) + '</span></div>';
      html += '<div><span class="lbl">pri</span> <span class="val">' + ld.priority + '</span> ';
      html += '<span class="lbl">terrain</span> <span class="val">' + ld.terrain + '</span></div>';
      html += '</div></div>';
    }
  }

  html += '<div class="section-title">GBA Metatile</div>';
  html += '<div class="lbl">Column key: <code style="font-size:10px">' + ck_str + '</code></div>';
  if (ck_str && ck_str !== '[]') {
    html += '<div class="layer-row">';
    html += '<div>';
    html += '<div class="lbl">raw (pre-quant) &#8595;/&#8593;</div>';
    html += '<div class="thumb-pair">';
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'bottom'), 'raw bottom');
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'top'), 'raw top');
    html += '</div>';
    html += '<div class="lbl" style="margin-top:4px">post-quant (shipped) &#8595;/&#8593;</div>';
    html += '<div class="thumb-pair">';
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'post_bottom'), 'post-quant bottom');
    html += thumbHtml(getMetatileURL(cell.colkey_idx, 'post_top'), 'post-quant top');
    html += '</div>';
    html += '</div>';
    if (attrs) {
      html += '<div style="padding-left:8px">';
      html += '<div><span class="lbl">layer_type</span> <span class="val">' + attrs.layer_type + '</span></div>';
      html += '<div><span class="lbl">behavior</span> <span class="val">0x' + attrs.behavior.toString(16) + '</span></div>';
      html += '</div>';
    }
    html += '</div>';
    if (advanced) html += quadFitHtml(D.colkey_palettes ? D.colkey_palettes[cell.colkey_idx] : null);
  } else {
    html += '<div class="lbl">(void / no metatile)</div>';
  }

  html += '<div class="section-title">Collision</div>';
  html += '<div><span class="lbl">Ours: </span><span class="' + (cell.collision_ours ? 'blocked' : 'passable') + '">' + (cell.collision_ours ? 'BLOCKED' : 'passable') + '</span></div>';
  html += '<div><span class="lbl">Uranium: </span><span class="' + (cell.collision_uranium ? 'blocked' : 'passable') + '">' + (cell.collision_uranium ? 'BLOCKED' : 'passable') + '</span></div>';
  html += cell.mismatch ? '<div class="mismatch">&#9888; MISMATCH</div>' : '<div class="match">&#10003; Match</div>';
  html += '<div><span class="lbl">priority_max</span> <span class="val">' + cell.priority_max + '</span></div>';

  const evtsHere = D.events.filter(function(ev) { return ev.x === cell.x && ev.y === cell.y; });
  if (evtsHere.length > 0) {
    html += '<div class="section-title">Events</div>';
    for (const ev of evtsHere) {
      html += '<div><span class="lbl">' + ev.id + ': </span><span class="val">' + escHtml(ev.label || ev.name) + '</span>';
      html += ' <span class="lbl">(' + ev.npages + 'p' + (ev.is_warp ? ', warp' : '') + ')</span>';
      if (ev.kind) html += ' ' + kindBadgeHtml(ev.kind);
      if (ev.has_conditions) html += '<span class="evt-cond-badge" title="page-gated on a switch/variable">&#9888;gated</span>';
      html += '</div>';
    }
  }

  // ---- Palettes section (Advanced only — quant/graphics-debug detail) ----
  const ckPal = D.colkey_palettes ? D.colkey_palettes[cell.colkey_idx] : null;
  if (advanced && ck_str && ck_str !== '[]') {
    html += '<div class="section-title">Palettes</div>';

    // RMXP source colors: union of tile colors from this cell's layer_detail
    const rmxpColors = [];
    const rmxpSeen = new Set();
    if (D.rmxp_tile_colors) {
      for (const ld of cell.layer_detail) {
        const tColors = D.rmxp_tile_colors[String(ld.tile_id)] || [];
        for (const c of tColors) {
          const k = c.join(',');
          if (!rmxpSeen.has(k)) { rmxpSeen.add(k); rmxpColors.push(c); }
        }
      }
    }
    html += '<div class="lbl" style="margin-top:4px">RMXP source colors</div>';
    html += '<div class="pal-strip">';
    for (const c of rmxpColors) html += swatchHtml(c);
    if (!rmxpColors.length) html += '<span class="lbl">(none)</span>';
    html += '</div>';

    // GBA sub-palettes used by this metatile
    if (ckPal && ckPal.palette_indices.length > 0 && D.palettes) {
      html += '<div class="lbl" style="margin-top:4px">GBA sub-palettes</div>';
      for (const pi of ckPal.palette_indices) {
        const pal = D.palettes[pi] || [];
        html += '<div style="margin:2px 0;display:flex;align-items:center;flex-wrap:wrap">';
        html += '<span class="pal-label">Pal ' + pi + '</span>';
        html += '<span class="swatch swatch-checker" title="index 0 (transparent)"></span>';
        for (const c of pal) html += swatchHtml(c);
        html += '</div>';
      }
    }

    // Color changes
    if (ckPal && ckPal.color_changes.length > 0) {
      const ccId = 'cc_toggle_' + cell.x + '_' + cell.y;
      const nChanged = ckPal.color_changes.filter(function(cc){return cc[0][0]!==cc[1][0]||cc[0][1]!==cc[1][1]||cc[0][2]!==cc[1][2];}).length;
      html += '<div class="lbl" style="margin-top:4px;display:flex;align-items:center;gap:6px">';
      html += 'Color changes (' + nChanged + '/' + ckPal.color_changes.length + ')';
      html += '<label style="font-size:10px;cursor:pointer"><input type="checkbox" id="' + ccId + '" onchange="updateCCSection()"' + (showAllColorChanges ? ' checked' : '') + '> show all</label>';
      html += '</div>';
      html += '<div id="cc-section">';
      html += buildCCRows(ckPal.color_changes, showAllColorChanges);
      html += '</div>';
    } else if (ckPal) {
      html += '<div class="lbl" style="margin-top:2px">(no color changes)</div>';
    }
  }

  document.getElementById('cell-info').innerHTML = html;
}

// ---- tile feedback (grouped flags) ----------------------------------------
// A flag = {cells:[[x,y],...], note}.  One note covers a whole selection set
// (tap-to-toggle + Expand similar), so it can span many cells / several metatile
// identities.  The full list is persisted to reference/map_feedback/MapNNN.json
// on every change (gitignored, always tiny, so a whole-list PUT is fine).
function escHtml(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function saveFeedback() {
  recomputeFlaggedCells();
  fetch('/api/feedback', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({map_id: D.meta.map_id, flags: flags}),
  }).catch(function(e) { console.error('feedback save failed', e); });
}
function recomputeFlaggedCells() {
  flaggedCells = new Set();
  for (const f of flags) for (const c of (f.cells || [])) flaggedCells.add(c[0] + ',' + c[1]);
  activeM.flaggedCells = flaggedCells;  // keep the member's copy in sync
}

// Switch the ACTIVE member (stitched mode): D and the feedback aliases follow,
// the in-progress selection clears (selections never span maps), and the
// per-map UI (title, palettes link, merge panel) rebinds.
function setActive(m) {
  if (m === activeM || !m.data) return;
  activeM = m;
  D = m.data;
  flags = m.flags;
  flaggedCells = m.flaggedCells;
  selection.clear();
  focusCell = null;
  editingIndex = null;
  document.getElementById('note-text').value = '';
  maxMergeSeverity = 1;
  for (const cp of (D.colkey_palettes || [])) { if (cp && cp.merge_severity > maxMergeSeverity) maxMergeSeverity = cp.merge_severity; }
  worstBuilt = false;
  const mm = D.meta;
  document.title = 'Map Inspector — Map' + String(mm.map_id).padStart(3,'0');
  const oobN = (D.out_of_atlas || []).length;
  document.getElementById('map-title').textContent =
    (stitched ? 'Stitched · active ' : '') + 'Map' + String(mm.map_id).padStart(3,'0') + ' — ' + (mm.name || '') +
    ' (' + mm.xsize + '\xd7' + mm.ysize + ')' +
    (oobN ? ' · ' + oobN + ' out-of-atlas cell' + (oobN === 1 ? '' : 's') : '');
  const navp = document.getElementById('nav-palettes');
  if (navp) navp.href = '/palettes/' + mm.map_id;
  const mergeN = (D.colkey_palettes || []).filter(function(cp) { return cp && cp.merge_severity > 0; }).length;
  document.getElementById('merge-count').textContent = '(' + mergeN + ' tiles)';
  focusEvent = null;
  document.getElementById('event-inspector-body').innerHTML = '<span class="lbl">Tap a cell with an event marker to inspect it.</span>';
  if (viewMode === 'events') loadBeats(m);
  renderBeatPanel();
  updateFlagList(); updateSelectionUI(); updateSidebar(); scheduleRender();
}
function selectionCells() {
  const arr = [];
  for (const c of selection.values()) arr.push([c.x, c.y]);
  arr.sort(function(a, b){ return a[1] - b[1] || a[0] - b[0]; });
  return arr;
}
function updateSelectionUI() {
  const n = selection.size;
  document.getElementById('sel-summary').innerHTML = n
    ? '<span id="sel-count">' + n + '</span> cell' + (n > 1 ? 's' : '') + ' selected' +
      (editingIndex !== null ? ' <span style="color:#fa0">(editing flag ' + (editingIndex + 1) + ')</span>' : '')
    : 'No cells selected.';
  document.getElementById('btn-clear').disabled = n === 0;
  document.getElementById('btn-save-flag').disabled = n === 0;
  // Expand similar needs a focused cell with a real (non-void) metatile identity.
  const ck = focusCell ? (D.colkeys_list ? D.colkeys_list[focusCell.colkey_idx] : '') : '';
  document.getElementById('btn-expand').disabled = !focusCell || !ck || ck === '[]';
}

document.getElementById('btn-expand').onclick = function() {
  if (!focusCell) return;
  // Pixel-equivalence class, not raw colkey: autotile shape-variants that render
  // identically (e.g. the flower autotile's interior shapes) group as one.
  const cls = D.pix_class[focusCell.colkey_idx];
  for (const c of D.cells) {
    if (D.pix_class[c.colkey_idx] === cls) selection.set(c.x + ',' + c.y, c);  // additive; multi-identity accumulates
  }
  updateSelectionUI(); updateSidebar(); scheduleRender();
};
document.getElementById('btn-clear').onclick = function() {
  selection.clear();
  editingIndex = null;
  document.getElementById('note-text').value = '';
  updateSelectionUI(); updateFlagList(); updateSidebar(); scheduleRender();
};
document.getElementById('btn-save-flag').onclick = function() {
  if (selection.size === 0) return;
  const note = document.getElementById('note-text').value.trim();
  const flag = {cells: selectionCells(), note: note};
  if (editingIndex !== null && editingIndex < flags.length) flags[editingIndex] = flag;
  else flags.push(flag);
  editingIndex = null;
  selection.clear();
  document.getElementById('note-text').value = '';
  saveFeedback();
  updateFlagList(); updateSelectionUI(); updateSidebar(); scheduleRender();
};
// Export writes SERVER-SIDE (output/map_feedback/MapNNN_feedback.json): the viewer
// is normally driven from a phone, and the file is only useful on the machine
// holding the rest of the pipeline output.
function setExportStatus(msg, bad) {
  const el = document.getElementById('export-status');
  if (!el) return;
  el.textContent = msg || '';
  el.style.color = bad ? '#f66' : '';
}
document.getElementById('btn-export').onclick = function() {
  setExportStatus('Exporting…');
  fetch('/api/feedback/export', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({map_id: D.meta.map_id, flags: flags}),
  }).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(j) {
    setExportStatus('Saved ' + j.count + ' flag' + (j.count === 1 ? '' : 's') + ' → ' + j.path);
  }).catch(function(e) {
    console.error('export failed', e);
    setExportStatus('Export failed: ' + e.message, true);
  });
};
function updateFlagList() {
  recomputeFlaggedCells();
  const el = document.getElementById('flag-list');
  if (!flags.length) { el.innerHTML = '<span class="lbl">No flags yet.</span>'; return; }
  el.innerHTML = flags.map(function(f, i) {
    const n = (f.cells || []).length;
    return '<div class="flag-item' + (editingIndex === i ? ' editing' : '') + '" onclick="editFlag(' + i + ')" title="click to edit / re-select its cells">' +
      '<span class="flag-del" onclick="event.stopPropagation();deleteFlag(' + i + ')">&#10005;</span>' +
      '<span class="flag-cells">' + n + ' cell' + (n > 1 ? 's' : '') + '</span> ' + escHtml(f.note || '(no note)') +
      '</div>';
  }).join('');
}
function editFlag(i) {
  const f = flags[i];
  if (!f) return;
  selection.clear();
  for (const c of (f.cells || [])) {
    const cell = D.cells[c[1] * D.meta.xsize + c[0]];
    if (cell) { selection.set(c[0] + ',' + c[1], cell); focusCell = cell; }
  }
  editingIndex = i;
  document.getElementById('note-text').value = f.note || '';
  updateFlagList(); updateSelectionUI(); updateSidebar(); scheduleRender();
  const sb = document.getElementById('sidebar');
  if (sb.style.position === 'fixed' || window.innerWidth <= 720) sb.classList.add('open');
}
function deleteFlag(i) {
  flags.splice(i, 1);
  if (editingIndex === i) editingIndex = null;
  else if (editingIndex !== null && editingIndex > i) editingIndex--;
  saveFeedback();
  updateFlagList(); updateSelectionUI(); scheduleRender();
}

// ---- worst-merge ranking --------------------------------------------------
let worstBuilt = false;
function buildWorstList() {
  const el = document.getElementById('merge-list');
  const cps = D.colkey_palettes || [];
  const ranked = [];
  for (let i = 0; i < cps.length; i++) {
    const cp = cps[i];
    if (cp && cp.merge_severity > 0) ranked.push({idx: i, sev: cp.merge_severity, merged: cp.merge_colors});
  }
  ranked.sort(function(a, b) { return b.sev - a.sev; });
  const top = ranked.slice(0, 20);
  if (!top.length) { el.innerHTML = '<span class="lbl">No palette-merge loss on this map.</span>'; return; }
  let h = '';
  for (const r of top) {
    const url = getMetatileURL(r.idx, 'post_bottom');
    h += '<div class="merge-item" onclick="jumpToColkey(' + r.idx + ')" title="jump to a tile using this metatile">';
    h += (url ? '<img class="thumb" src="' + url + '" loading="lazy">' : '');
    h += '<span class="lbl">sev <b class="qfit-bad-txt">' + r.sev + '</b> &middot; ' + r.merged + ' merged</span>';
    h += '</div>';
  }
  el.innerHTML = h;
}
function jumpToColkey(idx) {
  let target = null;
  for (const c of D.cells) { if (c.colkey_idx === idx) { target = c; break; } }
  if (!target) return;
  focusCell = target;
  const cp = cellPx();
  panX = Math.floor(canvas.width / 2 - (activeM.ox + target.x + 0.5) * cp);
  panY = Math.floor(canvas.height / 2 - (activeM.oy + target.y + 0.5) * cp);
  updateSidebar();
  updateSelectionUI();
  scheduleRender();
  const sb = document.getElementById('sidebar');
  if (sb.style.position === 'fixed' || window.innerWidth <= 720) sb.classList.add('open');
}
document.getElementById('merge-head').onclick = function() {
  const list = document.getElementById('merge-list');
  const open = list.style.display === 'none';
  if (open && !worstBuilt) { buildWorstList(); worstBuilt = true; }
  list.style.display = open ? 'block' : 'none';
  document.getElementById('merge-tri').innerHTML = open ? '&#9662;' : '&#9656;';
};

// ---- map nav strip (populated from V.graph) -------------------------------
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
  h += '<span class="navcur">' + (stitched ? 'Stitched &middot; ' : '') + 'Map' + pad(g.id) + ' &middot; ' + esc(g.name) + '</span>';
  const seen = new Set([g.id]);
  if (stitched) {
    h += '<span class="navsep"></span><span class="navgrp">members</span>';
    members.forEach(function(mem){
      h += '<a class="navchip" href="/map/' + mem.id + '" title="open single-map view">M' + pad(mem.id) + ' ' + esc(mem.name) + '</a>';
      seen.add(mem.id);
    });
    nav.innerHTML = h;
    nav.classList.add('show');
    return;
  }
  if (g.parent) { h += '<span class="navsep"></span><span class="navgrp">up</span>' + chip(g.parent.id, g.parent.name); seen.add(g.parent.id); }
  const kids = (g.children || []).filter(function(c){ return !seen.has(c.id); });
  if (kids.length) { h += '<span class="navsep"></span><span class="navgrp">sub</span>'; kids.forEach(function(c){ seen.add(c.id); h += chip(c.id, c.name); }); }
  const warps = (g.warps || []).filter(function(w){ return !seen.has(w.id); });
  if (warps.length) { h += '<span class="navsep"></span><span class="navgrp">warp&rarr;</span>'; warps.forEach(function(w){ seen.add(w.id); h += chip(w.id, w.name); }); }
  const conns = g.connections || [];
  if (conns.length) {
    const arrows = {N: '&#8679;', S: '&#8681;', W: '&#8678;', E: '&#8680;'};
    h += '<span class="navsep"></span><span class="navgrp">seam&rarr;</span>';
    conns.forEach(function(c){
      h += '<a class="navchip" href="/map/' + c.id + '" title="seamless connection on the ' + c.edge + ' edge">' +
           arrows[c.edge] + ' M' + pad(c.id) + ' ' + esc(c.name) + '</a>';
    });
    h += '<a class="navchip" href="/component/' + g.id + '" style="border-color:#86f;color:#cbf" ' +
         'title="view all seam-connected maps as one canvas">&#8862; Stitched view</a>';
  }
  nav.innerHTML = h;
  nav.classList.add('show');
}

// ---- init -----------------------------------------------------------------
function loadMemberFeedback(mem) {
  return fetch('/api/feedback/' + mem.id).then(function(r) { return r.json(); }).then(function(saved) {
    const list = Array.isArray(saved) ? saved : [];
    mem.flags.length = 0;
    for (const f of list) mem.flags.push(f);   // mutate in place: aliases survive
    mem.flaggedCells = new Set();
    for (const f of mem.flags) for (const c of (f.cells || [])) mem.flaggedCells.add(c[0] + ',' + c[1]);
    if (mem === activeM) { flaggedCells = mem.flaggedCells; updateFlagList(); updateSelectionUI(); updateSidebar(); }
    scheduleRender();
  }).catch(function(e) { console.error('feedback load failed for map ' + mem.id, e); });
}

(function initModeFromURL() {
  const qp = new URLSearchParams(location.search).get('mode');
  let m = null;
  if (qp === 'events' || qp === 'graphics') m = qp;
  if (!m) { try { m = localStorage.getItem('mv_mode'); } catch (e) {} }
  viewMode = (m === 'events') ? 'events' : 'graphics';
  applyModeUI();
})();
(function init() {
  const m = D.meta;
  activeM.flags = flags;               // alias the active member's feedback state
  activeM.flaggedCells = flaggedCells;
  document.title = 'Map Inspector — Map' + String(m.map_id).padStart(3,'0');
  const oobN0 = (D.out_of_atlas || []).length;
  document.getElementById('map-title').textContent =
    (stitched ? 'Stitched · active ' : '') + 'Map' + String(m.map_id).padStart(3,'0') + ' — ' + (m.name || '') +
    ' (' + m.xsize + '\xd7' + m.ysize + ')' +
    (oobN0 ? ' · ' + oobN0 + ' out-of-atlas cell' + (oobN0 === 1 ? '' : 's') : '');
  document.getElementById('statusbar').textContent =
    'Map' + String(m.map_id).padStart(3,'0') + ' — ' + m.xsize + '\xd7' + m.ysize +
    ' cells, tileset ' + m.tileset_id + ' (' + m.tileset_name + ')';
  updateFlagList();
  updateSelectionUI();
  // merge-panel count: how many distinct metatiles on this map lose colour to merging
  const mergeN = (D.colkey_palettes || []).filter(function(cp) { return cp && cp.merge_severity > 0; }).length;
  document.getElementById('merge-count').textContent = '(' + mergeN + ' tiles)';
  // always-visible warning: live quant knobs differ from stock, even with Advanced hidden
  if (V.quant && V.quant.non_stock) {
    document.getElementById('nonstock-badge').classList.add('show');
  }
  renderMapNav();
  const navp = document.getElementById('nav-palettes');
  navp.href = '/palettes/' + m.map_id;
  navp.style.display = '';
  // load previously-saved flags (every member's, so stitched view shows all ⚑)
  for (const mem of members) loadMemberFeedback(mem);
  // stitched: fetch the other members' datasets; they pop in as they arrive
  for (const mem of members) {
    if (mem.data) continue;
    fetch('/api/map/' + mem.id).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(data) {
      mem.data = data;
      scheduleRender();
    }).catch(function(e) { console.error('map load failed for ' + mem.id, e); });
  }
  ready = true;
  setTimeout(function() {
    canvas.width = wrap.clientWidth; canvas.height = wrap.clientHeight; fitMap();
    // ?focus=x,y — center + focus a cell (seam click-throughs land here)
    const fp = new URLSearchParams(location.search).get('focus');
    if (fp) {
      const parts = fp.split(',');
      let fx = parseInt(parts[0], 10), fy = parseInt(parts[1], 10);
      if (!isNaN(fx) && !isNaN(fy)) {
        fx = Math.max(0, Math.min(D.meta.xsize - 1, fx));
        fy = Math.max(0, Math.min(D.meta.ysize - 1, fy));
        focusCell = D.cells[fy * D.meta.xsize + fx];
        centerOnCell(activeM, fx, fy, 2);
        updateSidebar(); updateSelectionUI();
      }
    }
  }, 0);
})();
document.addEventListener('keydown', function(e) {
  if (['INPUT','TEXTAREA','SELECT'].indexOf(document.activeElement.tagName) !== -1) return;
  if (e.key === 'q') {
    const next = currentLayer === 'rmxp' ? 'post-quant' : 'rmxp';
    currentLayer = next;
    document.querySelectorAll('input[name="view2"]').forEach(function(r) { r.checked = r.value === next; });
    scheduleRender();
    return;
  }
  if (e.key === 'e') {  // toggle Graphics <-> Events mode; see #mode-switch
    setMode(viewMode === 'events' ? 'graphics' : 'events');
  }
});
