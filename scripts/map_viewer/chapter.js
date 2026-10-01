'use strict';
// Chapter route viewer. Screen space = world cell * z + pan (css px); canvas backing store is css*dpr.

// ---- state ----------------------------------------------------------------
const C_TO = '#0072B2', C_FROM = '#E69F00', C_VIOL = '#D55E00';
const ZMIN = 1.5, ZMAX = 96, PAD = 16;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const chapterId = (location.pathname.match(/\/chapter\/([^\/?#]+)/) || [])[1] || '';
let D = null;                 // payload
let mapById = new Map();      // String(id) -> map record
let steps = [];               // [{gi, bi, label}]
let cur = 0;                  // current step index
let walkMode = false;
let cssW = 0, cssH = 0, dpr = 1;
let z = 8, panX = 0, panY = 0;   // camera
let anim = null;              // {t0, dur, from:[z,x,y], to:[z,x,y]}
const images = new Map();     // map id -> {img, ok}
const pointers = new Map();
let dragStart = null, dragMoved = false, pinchRef = null;
let badges = [];              // [{gi, wx, wy}] world positions (cells)

// ---- render scheduling (rAF-coalesced) -------------------------------------
let raf = 0;
function scheduleRender() { if (!raf) raf = requestAnimationFrame(frame); }
function frame(ts) {
  raf = 0;
  if (anim) {
    const t = Math.min(1, (ts - anim.t0) / anim.dur), e = 1 - Math.pow(1 - t, 3);
    z = anim.from[0] + (anim.to[0] - anim.from[0]) * e;
    panX = anim.from[1] + (anim.to[1] - anim.from[1]) * e;
    panY = anim.from[2] + (anim.to[2] - anim.from[2]) * e;
    if (t >= 1) anim = null; else scheduleRender();
  }
  draw();
}
function sizeCanvas() {
  dpr = window.devicePixelRatio || 1;
  const st = document.getElementById('stage');
  cssW = st.clientWidth; cssH = st.clientHeight;
  cv.width = Math.max(1, Math.round(cssW * dpr)); cv.height = Math.max(1, Math.round(cssH * dpr));
  scheduleRender();
}

// ---- data load ------------------------------------------------------------
function fetchJSON(u) { return fetch(u).then(function(r) { if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); }); }
function init() {
  fetchJSON('/api/chapters').then(function(list) {
    const sel = document.getElementById('chsel');
    list.forEach(function(id) { const o = document.createElement('option'); o.value = o.textContent = id; if (id === chapterId) o.selected = true; sel.appendChild(o); });
    sel.addEventListener('change', function() { location.href = '/chapter/' + sel.value; });
  }).catch(function() {});
  fetchJSON('/api/chapter/' + encodeURIComponent(chapterId)).then(onData).catch(function(e) { toast('load failed: ' + e.message, 6000); });
}
function onData(d) {
  D = d;
  mapById = new Map(d.maps.map(function(m) { return [String(m.id), m]; }));
  steps = [];
  d.groups.forEach(function(g, gi) {
    if (!g.beats.length) steps.push({gi: gi, bi: -1, label: String(g.number)});
    g.beats.forEach(function(b, bi) { steps.push({gi: gi, bi: bi, label: String(b.step || g.number)}); });
  });
  computeBadges();
  const wb = document.getElementById('mode-walk');
  if (!d.walked_available) wb.setAttribute('aria-disabled', 'true');
  if (d.notes && d.notes.length) {
    document.getElementById('notes-btn').hidden = false;
    document.getElementById('notes-n').textContent = d.notes.length;
    const nb = document.getElementById('notes');
    d.notes.forEach(function(n) { const p = document.createElement('p'); p.textContent = n; nb.appendChild(p); });
  }
  sizeCanvas();
  fitAll(false);
  const h = stepFromHash();
  if (h >= 0) cur = h;
  setStep(cur, false, false);
  if (steps.length) frameGroup(D.groups[steps[cur].gi]);
}

// ---- layout / camera ------------------------------------------------------
function cellOf(mapId, c) {  // map-local cell -> canvas cell (center)
  const m = mapById.get(String(mapId));
  if (!m) return null;
  const k = m.crop || [0, 0];  // (ox, oy) is where map-local cell `crop` is drawn
  return [m.ox + c[0] - k[0] + 0.5, m.oy + c[1] - k[1] + 0.5];
}
function computeBadges() {  // fan out badges sharing a cell
  const byCell = new Map();
  D.groups.forEach(function(g, gi) {
    const p = cellOf(g.map_id, g.cell); if (!p) return;
    const k = p[0] + ',' + p[1];
    if (!byCell.has(k)) byCell.set(k, []);
    byCell.get(k).push({gi: gi, wx: p[0], wy: p[1]});
  });
  badges = [];
  byCell.forEach(function(arr) {
    arr.forEach(function(b, i) {
      if (arr.length > 1) { const a = -Math.PI / 2 + 2 * Math.PI * i / arr.length; b.wx += 0.5 * Math.cos(a); b.wy += 0.5 * Math.sin(a); }
      badges.push(b);
    });
  });
}
function clampZ(v) { return Math.max(ZMIN, Math.min(ZMAX, v)); }
function camFor(x0, y0, x1, y1, keepZ) {  // camera showing world bbox (cells) centered; zoom kept if it fits
  const w = Math.max(1, x1 - x0), h = Math.max(1, y1 - y0);
  let nz = clampZ(Math.min((cssW - 2 * PAD) / w, (cssH - 2 * PAD) / h));
  if (keepZ && z <= nz) nz = z;
  return [nz, cssW / 2 - (x0 + x1) / 2 * nz, cssH / 2 - (y0 + y1) / 2 * nz];
}
function animateTo(c, smooth) {
  if (!smooth) { z = c[0]; panX = c[1]; panY = c[2]; anim = null; scheduleRender(); return; }
  anim = {t0: performance.now(), dur: 320, from: [z, panX, panY], to: c};
  scheduleRender();
}
function fitAll(smooth) {
  if (!D || !D.maps.length) return;
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  D.maps.forEach(function(m) { x0 = Math.min(x0, m.ox); y0 = Math.min(y0, m.oy); x1 = Math.max(x1, m.ox + m.w); y1 = Math.max(y1, m.oy + m.h); });
  animateTo(camFor(x0, y0, x1, y1, false), smooth);
}
function groupPaths(g) {  // [to, from] leg lists for the active path source
  if (walkMode && g.walked) return [g.walked.to || [], g.walked.from || []];
  return [g.to || [], g.from || []];
}
function groupBox(g) {  // world bbox (cells) of the group's to/from paths + its badge, or null
  const ps = groupPaths(g);
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, n = 0;
  function add(p) { if (!p) return; n++; x0 = Math.min(x0, p[0] - .5); y0 = Math.min(y0, p[1] - .5); x1 = Math.max(x1, p[0] + .5); y1 = Math.max(y1, p[1] + .5); }
  ps[0].concat(ps[1]).forEach(function(leg) { leg.tiles.forEach(function(t) { add(cellOf(leg.map_id, t)); }); });
  add(cellOf(g.map_id, g.cell));
  return n ? [x0, y0, x1, y1] : null;
}
function focusGroup(g, smooth) {  // keep the to/from paths in view; zoom only changes if they cannot fit
  const b = groupBox(g);
  if (!b) return;
  // already fully inside the viewport (with margin)? leave the camera alone.
  const inView = b[0] * z + panX >= PAD && b[1] * z + panY >= PAD && b[2] * z + panX <= cssW - PAD && b[3] * z + panY <= cssH - PAD;
  if (inView) return;
  animateTo(camFor(b[0], b[1], b[2], b[3], true), smooth);
}
function frameGroup(g) {  // initial view: zoom onto the group's paths (not the whole chapter -- badges crowd on a phone)
  const b = groupBox(g);
  if (!b) return;
  const pad = 6;  // cells of context around the paths
  const c = camFor(b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad, false);
  const nz = Math.min(c[0], 24);  // a one-tile group would otherwise zoom to ZMAX
  animateTo([nz, cssW / 2 - (b[0] + b[2]) / 2 * nz, cssH / 2 - (b[1] + b[3]) / 2 * nz], false);
}

// ---- images ---------------------------------------------------------------
function mapImage(id) {
  let e = images.get(String(id));
  if (!e) {
    e = {img: new Image(), ok: false};
    e.img.onload = function() { e.ok = true; scheduleRender(); };
    e.img.src = '/api/mappng/' + encodeURIComponent(id) + '.png';
    images.set(String(id), e);
  }
  return e;
}

// ---- draw passes ----------------------------------------------------------
function sx(wx) { return wx * z + panX; }
function sy(wy) { return wy * z + panY; }
function draw() {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, cssW, cssH);
  if (!D) return;
  drawMaps(); drawConnectors(); drawBackgroundRoute();
  const st = steps[cur], g = st ? D.groups[st.gi] : null;
  if (g) drawSelected(g);
  drawBadges();
}
function visible(x, y, w, h) { return x + w >= 0 && y + h >= 0 && x <= cssW && y <= cssH; }
function drawMaps() {
  D.maps.forEach(function(m) {
    const x = sx(m.ox), y = sy(m.oy), w = m.w * z, h = m.h * z;
    if (!visible(x, y, w, h)) return;
    const e = mapImage(m.id);
    const c = m.crop || [0, 0];  // borrowed maps are cropped to their relevant area
    if (e.ok) ctx.drawImage(e.img, c[0] * 16, c[1] * 16, m.w * 16, m.h * 16, x, y, w, h);
    else { ctx.fillStyle = '#232734'; ctx.fillRect(x, y, w, h); }
    ctx.strokeStyle = '#667'; ctx.lineWidth = 1; ctx.strokeRect(x + .5, y + .5, w - 1, h - 1);
    // thin name tag; font scales with zoom (min 9px) so it stays readable
    const fs = Math.max(9, Math.min(0.9 * z, 28)), tag = m.name + ' (' + m.id + ')';
    ctx.font = '600 ' + fs + 'px system-ui, sans-serif';
    const tw = Math.min(ctx.measureText(tag).width + 8, w);
    ctx.fillStyle = 'rgba(0,0,0,.72)'; ctx.fillRect(x, y, tw, fs + 6);
    ctx.fillStyle = '#fff'; ctx.textBaseline = 'top'; ctx.fillText(tag, x + 4, y + 3, tw - 6);
  });
}
function drawConnectors() {
  ctx.save();
  ctx.setLineDash([6, 5]); ctx.lineWidth = 2; ctx.strokeStyle = '#b9c7ff'; ctx.fillStyle = '#b9c7ff';
  (D.connectors || []).forEach(function(c) {
    const a = cellOf(c.from.map_id, c.from.cell), b = cellOf(c.to.map_id, c.to.cell);
    if (!a || !b) return;
    ctx.beginPath(); ctx.moveTo(sx(a[0]), sy(a[1])); ctx.lineTo(sx(b[0]), sy(b[1])); ctx.stroke();
    [a, b].forEach(function(p) { ctx.beginPath(); ctx.arc(sx(p[0]), sy(p[1]), 3, 0, 7); ctx.fill(); });
  });
  ctx.restore();
}
function drawBackgroundRoute() {  // one polyline per leg; never joins across maps/warps
  ctx.save();
  const lw = Math.max(2, 0.14 * z);
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  // Two passes -- dark casing, then a light core -- so the line reads on grass, water and sand alike.
  [['rgba(0,0,0,.5)', lw + 2], ['rgba(255,255,255,.6)', lw]].forEach(function(pass) {
    ctx.strokeStyle = pass[0]; ctx.lineWidth = pass[1];
    (D.route || []).forEach(function(leg) {
      const pts = [];
      leg.tiles.forEach(function(t) { const p = cellOf(leg.map_id, t); if (p) pts.push(p); });
      if (!pts.length) return;
      ctx.beginPath();
      pts.forEach(function(p, i) { if (i) ctx.lineTo(sx(p[0]), sy(p[1])); else ctx.moveTo(sx(p[0]), sy(p[1])); });
      if (pts.length === 1) ctx.lineTo(sx(pts[0][0]) + .01, sy(pts[0][1]));
      ctx.stroke();
    });
  });
  ctx.restore();
}
function tileKeys(legs) {
  const s = new Set();
  legs.forEach(function(l) { l.tiles.forEach(function(t) { s.add(l.map_id + ':' + t[0] + ',' + t[1]); }); });
  return s;
}
// Normal for an edge from the tile pair in CANONICAL (lexicographically sorted) order, so a stretch
// walked in opposite directions gets the same normal; `to` takes +k and `from` -k, hence they separate.
function canonNormal(a, b) {
  let p = a, q = b;
  if (a[0] > b[0] || (a[0] === b[0] && a[1] > b[1])) { p = b; q = a; }
  const dx = q[0] - p[0], dy = q[1] - p[1], L = Math.hypot(dx, dy) || 1;
  return [-dy / L, dx / L];
}
function arrow(x, y, ang, sz, color) {  // filled triangle, tip at (x,y)
  ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-sz, -sz * .6); ctx.lineTo(-sz, sz * .6); ctx.closePath();
  ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = '#000'; ctx.lineWidth = 1; ctx.stroke(); ctx.restore();
}
function drawPath(legs, otherKeys, sign, color) {
  const k = Math.max(0.18 * z, 3), lw = Math.max(4, 0.2 * z), asz = Math.max(8, 0.3 * z);
  ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineCap = 'round';
  ctx.shadowColor = 'rgba(0,0,0,.85)'; ctx.shadowBlur = 3;  // lifts the highlight off the map art
  legs.forEach(function(leg) {
    const t = leg.tiles, n = t.length;
    if (n === 1) { const p = cellOf(leg.map_id, t[0]); if (p) { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(sx(p[0]), sy(p[1]), lw, 0, 7); ctx.fill(); } return; }
    for (let i = 0; i < n - 1; i++) {
      const pa = cellOf(leg.map_id, t[i]), pb = cellOf(leg.map_id, t[i + 1]);
      if (!pa || !pb) continue;
      const nm = canonNormal(t[i], t[i + 1]);
      const sa = otherKeys.has(leg.map_id + ':' + t[i][0] + ',' + t[i][1]) ? sign * k : 0;  // offset only on shared tiles
      const sb = otherKeys.has(leg.map_id + ':' + t[i + 1][0] + ',' + t[i + 1][1]) ? sign * k : 0;
      const ax = sx(pa[0]) + nm[0] * sa, ay = sy(pa[1]) + nm[1] * sa, bx = sx(pb[0]) + nm[0] * sb, by = sy(pb[1]) + nm[1] * sb;
      if (!visible(Math.min(ax, bx) - 20, Math.min(ay, by) - 20, Math.abs(bx - ax) + 40, Math.abs(by - ay) + 40)) continue;
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
      if (i === n - 2 || i % 3 === 1) arrow((ax + bx) / 2 + Math.cos(Math.atan2(by - ay, bx - ax)) * asz / 2, (ay + by) / 2 + Math.sin(Math.atan2(by - ay, bx - ax)) * asz / 2, Math.atan2(by - ay, bx - ax), asz, color);
    }
  });
  ctx.restore();
}
function drawX(x, y, r, color, dashed, ring) {
  ctx.save(); ctx.lineWidth = Math.max(2.5, r * .3); ctx.strokeStyle = color;
  ctx.beginPath(); ctx.moveTo(x - r, y - r); ctx.lineTo(x + r, y + r); ctx.moveTo(x + r, y - r); ctx.lineTo(x - r, y + r); ctx.stroke();
  if (ring) { ctx.setLineDash(dashed ? [4, 3] : []); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r * 1.5, 0, 7); ctx.stroke(); }
  ctx.restore();
}
function drawSelected(g) {
  const ps = groupPaths(g), to = ps[0], from = ps[1];
  const kt = tileKeys(to), kf = tileKeys(from);
  drawPath(to, kf, +1, C_TO);
  drawPath(from, kt, -1, C_FROM);
  const r = Math.max(5, 0.28 * z);
  (g.to_crossings || []).concat(g.from_crossings || []).forEach(function(c) {
    const p = cellOf(c.map_id, c.cell); if (p) drawX(sx(p[0]), sy(p[1]), r, C_FROM, c.certainty === 'possible', true);
  });
  if (walkMode && g.walked) {
    (g.walked.off_plan || []).forEach(function(c) {
      const p = cellOf(c.map_id, c.cell); if (!p) return;
      ctx.save(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(sx(p[0]), sy(p[1]), 0.32 * z + 2, 0, 7); ctx.stroke();
      ctx.strokeStyle = C_VIOL; ctx.lineWidth = 1.5; ctx.stroke(); ctx.restore();
    });
    (g.walked.violations || []).forEach(function(c) { const p = cellOf(c.map_id, c.cell); if (p) drawX(sx(p[0]), sy(p[1]), r, C_VIOL, false, false); });
  }
}
function badgeRadius() { return Math.max(0.55 * z, 11); }  // world 1.1 cell diameter, min 22 css px
function drawBadges() {
  const r = badgeRadius(), sel = steps[cur] ? steps[cur].gi : -1;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  // selected last so it stays on top
  badges.slice().sort(function(a, b) { return (a.gi === sel) - (b.gi === sel); }).forEach(function(b) {
    const x = sx(b.wx), y = sy(b.wy);
    if (!visible(x - r, y - r, 2 * r, 2 * r)) return;
    const g = D.groups[b.gi], s = b.gi === sel, txt = String(g.number);
    ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
    ctx.fillStyle = s ? '#ffe14d' : 'rgba(10,12,18,.8)'; ctx.fill();
    ctx.lineWidth = s ? 3 : 2; ctx.strokeStyle = s ? '#000' : '#fff'; ctx.stroke();
    ctx.fillStyle = s ? '#000' : '#fff';
    ctx.font = '700 ' + Math.round(r * (txt.length > 2 ? 0.8 : 1.05)) + 'px system-ui, sans-serif';
    ctx.fillText(txt, x, y + 1);
  });
  ctx.textAlign = 'start';
}
function badgeAt(px, py) {  // nearest badge within max(radius, 22px)
  const hr = Math.max(badgeRadius(), 22); let best = null, bd = 1e9;
  badges.forEach(function(b) { const d = Math.hypot(sx(b.wx) - px, sy(b.wy) - py); if (d <= hr && d < bd) { bd = d; best = b; } });
  return best;
}

// ---- stepping / UI --------------------------------------------------------
function setStep(i, smooth, noCamera) {
  if (!steps.length) { document.getElementById('steplbl').textContent = '-'; return; }
  const prevG = steps[cur] ? steps[cur].gi : -1;
  cur = Math.max(0, Math.min(steps.length - 1, i));
  const st = steps[cur], g = D.groups[st.gi], b = st.bi >= 0 ? g.beats[st.bi] : null;
  document.getElementById('steplbl').textContent = st.label + ' / ' + D.groups.length;
  document.getElementById('stepname').textContent = b ? b.name : '';
  history.replaceState(null, '', '#' + st.label);
  if (!noCamera && (st.gi !== prevG || smooth === false)) focusGroup(g, smooth !== false);
  renderCard();
  scheduleRender();
}
function stepFromHash() {
  const h = location.hash.replace('#', '');
  const idx = steps.findIndex(function(s) { return s.label === h; });
  if (idx >= 0) return idx;
  const m = /^(\d+)/.exec(h);  // "7b" on a one-beat group -> group 7
  return m ? steps.findIndex(function(s) { return D.groups[s.gi].number === +m[1]; }) : -1;
}
function selectGroup(gi) {
  if (steps[cur] && steps[cur].gi === gi) return;
  setStep(steps.findIndex(function(s) { return s.gi === gi; }), true);
}
let toastT = 0;
function toast(msg, ms) {
  const t = document.getElementById('toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(function() { t.hidden = true; }, ms || 2800);
}
function setMode(walk) {
  if (walk && !D.walked_available) { toast('No generated-suite run on record; re-run with --suite gen'); return; }
  walkMode = walk;
  document.getElementById('mode-plan').classList.toggle('on', !walk);
  document.getElementById('mode-walk').classList.toggle('on', walk);
  scheduleRender();
}

// ---- card -----------------------------------------------------------------
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
function section(body, title) { body.appendChild(el('h3', '', title)); }
function list(body, title, items, ordered, fill) {
  if (!items || !items.length) return;
  section(body, title);
  const ul = el(ordered ? 'ol' : 'ul');
  items.forEach(function(it) { const li = el('li'); fill(li, it); ul.appendChild(li); });
  body.appendChild(ul);
}
function renderCard() {
  const body = document.getElementById('card-body'); body.textContent = '';
  if (!steps[cur]) return;
  const st = steps[cur], g = D.groups[st.gi], b = st.bi >= 0 ? g.beats[st.bi] : null, c = b && b.card;
  body.appendChild(el('h2', '', st.label + '  ' + (b ? b.name : 'group ' + g.number)));
  if (!c) { body.appendChild(el('p', 'empty', 'no beat sidecar — re-run beat_gen generate')); }
  else {
    const kv = el('div', 'kv');
    function row(k, v) { if (v == null || v === '') return; kv.appendChild(el('span', '', k)); kv.appendChild(el('span', '', v)); }
    row('template', c.template);
    row('map', (c.map_name || '') + (c.map_id != null ? ' (' + c.map_id + ')' : '') + (c.cell ? ' @ ' + c.cell.join(',') : ''));
    row('group', g.number + ' @ ' + (g.cell ? g.cell.join(',') : '?') + ' on ' + g.map_id);
    row('side', g.side); row('pick', c.pick);
    body.appendChild(kv);
    if (c.description) { section(body, 'Description'); body.appendChild(el('p', '', c.description)); }
    const call = c.call || {}, keys = Object.keys(call);
    if (keys.length) { section(body, 'Call'); const k2 = el('div', 'kv'); keys.forEach(function(k) { k2.appendChild(el('span', '', k)); const v = el('span'); v.appendChild(el('code', '', JSON.stringify(call[k]))); k2.appendChild(v); }); body.appendChild(k2); }
    list(body, 'Rows', c.rows, true, function(li, r) { li.textContent = typeof r === 'string' ? r : JSON.stringify(r); });
    list(body, 'Assertions', c.assertions, false, function(li, a) {
      li.appendChild(document.createTextNode((a.row != null ? 'row ' + a.row + ': ' : '') + a.kind));
      li.appendChild(el('span', 'chip ' + (a.offline ? 'offline' : 'rom'), a.offline ? 'offline' : 'ROM'));
    });
  }
  if (b) {
    list(body, 'Order-dependent writes', b.order_dependent_writes, false, function(li, w) { li.textContent = (w.rows != null ? '[' + [].concat(w.rows).join(', ') + '] ' : '') + w.text; });
    list(body, 'Refusals', b.refusals, false, function(li, r) { li.className = 'warn'; li.textContent = (r.row != null ? 'row ' + r.row + ': ' : '') + r.text; });
    if (b.status) { section(body, 'Last run'); body.appendChild(el('p', '', b.status)); }
  }
  if (walkMode && g.walked && (g.walked.violations || []).length) body.appendChild(el('p', 'warn', g.walked.violations.length + ' walk violation(s) in this group'));
}
const card = document.getElementById('card');
function cardOpen(v) { card.classList.toggle('open', v); }
function isNarrow() { return window.innerWidth < 900; }

// ---- input ----------------------------------------------------------------
function dist(a, b) { return Math.hypot(b.x - a.x, b.y - a.y); }
cv.addEventListener('pointerdown', function(e) {
  cv.setPointerCapture(e.pointerId); anim = null;
  pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (pointers.size === 1) { dragStart = {x: e.clientX, y: e.clientY, px: panX, py: panY}; dragMoved = false; pinchRef = null; }
  else if (pointers.size === 2) {
    const p = [...pointers.values()], r = cv.getBoundingClientRect();
    pinchRef = {d: dist(p[0], p[1]), z: z, px: panX, py: panY, mx: (p[0].x + p[1].x) / 2 - r.left, my: (p[0].y + p[1].y) / 2 - r.top};
    dragMoved = true;  // a pinch is never a tap
  }
});
cv.addEventListener('pointermove', function(e) {
  if (!pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, {x: e.clientX, y: e.clientY});
  if (pointers.size === 1 && !pinchRef) {
    const dx = e.clientX - dragStart.x, dy = e.clientY - dragStart.y;
    if (Math.abs(dx) > 6 || Math.abs(dy) > 6) dragMoved = true;
    if (dragMoved) { panX = dragStart.px + dx; panY = dragStart.py + dy; scheduleRender(); }
  } else if (pointers.size === 2 && pinchRef) {
    const p = [...pointers.values()], nz = clampZ(pinchRef.z * dist(p[0], p[1]) / pinchRef.d), s = nz / pinchRef.z;
    panX = pinchRef.mx - (pinchRef.mx - pinchRef.px) * s; panY = pinchRef.my - (pinchRef.my - pinchRef.py) * s; z = nz;
    scheduleRender();
  }
});
cv.addEventListener('pointerup', function(e) {
  const tap = pointers.size === 1 && !dragMoved;
  pointers.delete(e.pointerId);
  if (pointers.size === 0) pinchRef = null;
  else if (pointers.size === 1) { const p = [...pointers.values()][0]; dragStart = {x: p.x, y: p.y, px: panX, py: panY}; pinchRef = null; dragMoved = true; }
  if (!tap) return;
  const r = cv.getBoundingClientRect(), b = badgeAt(e.clientX - r.left, e.clientY - r.top);
  if (b) selectGroup(b.gi); else if (isNarrow()) cardOpen(false);  // tap-outside closes the sheet
});
cv.addEventListener('pointercancel', function(e) { pointers.delete(e.pointerId); if (!pointers.size) pinchRef = null; });
cv.addEventListener('wheel', function(e) {
  e.preventDefault(); anim = null;
  const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const nz = clampZ(z * Math.exp(-e.deltaY * 0.0015)), s = nz / z;
  panX = mx - (mx - panX) * s; panY = my - (my - panY) * s; z = nz; scheduleRender();
}, {passive: false});

document.getElementById('prev').addEventListener('click', function() { setStep(cur - 1, true); });
document.getElementById('next').addEventListener('click', function() { setStep(cur + 1, true); });
document.getElementById('cardbtn').addEventListener('click', function() { cardOpen(!card.classList.contains('open')); });
document.getElementById('card-x').addEventListener('click', function() { cardOpen(false); });
document.getElementById('fit').addEventListener('click', function() { fitAll(true); });
document.getElementById('mode-plan').addEventListener('click', function() { setMode(false); });
document.getElementById('mode-walk').addEventListener('click', function() { setMode(true); });
document.getElementById('notes-btn').addEventListener('click', function() { const n = document.getElementById('notes'); n.hidden = !n.hidden; sizeCanvas(); });
window.addEventListener('keydown', function(e) {
  if (e.target && e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft') setStep(cur - 1, true);
  else if (e.key === 'ArrowRight') setStep(cur + 1, true);
  else if (e.key === 'c') cardOpen(!card.classList.contains('open'));
  else if (e.key === 'f') fitAll(true);
  else if (e.key === 'Escape') cardOpen(false);
});
// swipe-down on the sheet header closes it
let swipeY = null;
const head = document.getElementById('card-head');
head.addEventListener('pointerdown', function(e) { if (e.target.id === 'card-x') return; swipeY = e.clientY; head.setPointerCapture(e.pointerId); });
head.addEventListener('pointermove', function(e) { if (swipeY != null && e.clientY - swipeY > 40) { swipeY = null; cardOpen(false); } });
head.addEventListener('pointerup', function() { swipeY = null; });
window.addEventListener('hashchange', function() { const i = stepFromHash(); if (i >= 0 && i !== cur) setStep(i, true); });
new ResizeObserver(sizeCanvas).observe(document.getElementById('stage'));
window.addEventListener('resize', sizeCanvas);

sizeCanvas();
init();
