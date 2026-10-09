// Hand-split planner (/split/<id>): paint the map into pieces and watch each piece's
// GBA tileset budget. Data comes from /api/split/<id> (map_viewer_common.split_data):
// a metatile id per cell and the 8x8 tile ids per metatile, so every repaint is
// counted here without a round trip.
(function () {
  'use strict';

  const MAP_ID = parseInt(location.pathname.split('/').pop(), 10);
  const COLORS = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
                  '#42d4f4', '#f032e6', '#bfef45', '#fabed4', '#469990'];
  const MAX_PIECES = COLORS.length;
  const LS_KEY = 'split:' + MAP_ID;

  const $ = (id) => document.getElementById(id);
  const cv = $('cv');
  const ctx = cv.getContext('2d');

  let D = null;          // split_data payload
  let W = 0, H = 0;
  let assign = null;     // Int8Array, piece per cell
  let nPieces = 2;
  let cur = 0;
  let tool = 'pan';
  let cp = 8;            // canvas px per cell
  let img = null;
  let stats = [];        // per piece, from compute()
  let exact = null;      // per piece {tiles, metatiles, over} | null; cleared on edit
  let undoStack = [];
  let drag = null;       // rect tool: {x0, y0, x1, y1}
  let painting = false;
  let wholeProxy = null;
  let budget = null;     // /api/budget payload (merge_on / merge_off)

  // ---------------------------------------------------------------- counting

  // 1 where any cell of `mask` lies within h columns and v rows (box dilation).
  function dilate(mask, h, v) {
    const dh = new Uint8Array(W * H);
    const row = new Int32Array(W + 1);
    for (let y = 0; y < H; y++) {
      const o = y * W;
      for (let x = 0; x < W; x++) row[x + 1] = row[x] + mask[o + x];
      for (let x = 0; x < W; x++) {
        const a = Math.max(0, x - h), b = Math.min(W, x + h + 1);
        dh[o + x] = row[b] - row[a] > 0 ? 1 : 0;
      }
    }
    const out = new Uint8Array(W * H);
    const col = new Int32Array(H + 1);
    for (let x = 0; x < W; x++) {
      for (let y = 0; y < H; y++) col[y + 1] = col[y] + dh[y * W + x];
      for (let y = 0; y < H; y++) {
        const a = Math.max(0, y - v), b = Math.min(H, y + v + 1);
        out[y * W + x] = col[b] - col[a] > 0 ? 1 : 0;
      }
    }
    return out;
  }

  function components(mask) {
    const seen = new Uint8Array(W * H);
    let n = 0;
    const stack = [];
    for (let i = 0; i < W * H; i++) {
      if (!mask[i] || seen[i]) continue;
      n++;
      seen[i] = 1;
      stack.push(i);
      while (stack.length) {
        const j = stack.pop(), x = j % W, y = (j / W) | 0;
        const nb = [x > 0 ? j - 1 : -1, x < W - 1 ? j + 1 : -1, y > 0 ? j - W : -1, y < H - 1 ? j + W : -1];
        for (const k of nb) if (k >= 0 && mask[k] && !seen[k]) { seen[k] = 1; stack.push(k); }
      }
    }
    return n;
  }

  function countArt(own, seen) {
    const mtMark = new Uint8Array(D.mt_tiles.length);
    const tileMark = new Uint8Array(D.n_tiles);
    const ids = [];
    let ownMt = 0, seenMt = 0, tiles = 0;
    for (let i = 0; i < W * H; i++) {
      const m = D.cells[i];
      if (m < 0 || mtMark[m]) continue;
      if (own[i]) { mtMark[m] = 1; ownMt++; ids.push(m); }
    }
    if (seen) {
      for (let i = 0; i < W * H; i++) {
        const m = D.cells[i];
        if (m < 0 || mtMark[m] || !seen[i]) continue;
        mtMark[m] = 2; seenMt++; ids.push(m);
      }
    }
    for (const m of ids) {
      for (const t of D.mt_tiles[m]) if (!tileMark[t]) { tileMark[t] = 1; tiles++; }
    }
    // +1 void metatile, +1 transparent tile 0 (both always emitted).
    return { ownMt, seenMt, metatiles: ownMt + seenMt + 1, tiles: tiles + 1, ids };
  }

  function compute() {
    const hd = clampInt($('hdepth').value, 1, 7), vd = clampInt($('vdepth').value, 1, 7);
    stats = [];
    for (let p = 0; p < nPieces; p++) {
      const mask = new Uint8Array(W * H);
      let n = 0, x0 = W, y0 = H, x1 = -1, y1 = -1;
      for (let i = 0; i < W * H; i++) {
        if (assign[i] !== p) continue;
        mask[i] = 1; n++;
        const x = i % W, y = (i / W) | 0;
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
      if (!n) { stats.push({ p, n: 0 }); continue; }
      // own = this piece's cells that need real art; seen = other pieces' cells in view.
      // Sight only: both come from the camera box around the cells the player can
      // stand on in this piece; the rest of the piece is void.
      let own = mask, lit, walk = 0;
      if ($('sight').checked) {
        const stand = new Uint8Array(W * H);
        for (let i = 0; i < W * H; i++) if (mask[i] && D.reach[i]) { stand[i] = 1; walk++; }
        lit = dilate(stand, hd, vd);
        own = new Uint8Array(W * H);
        for (let i = 0; i < W * H; i++) own[i] = mask[i] & lit[i];
      } else {
        lit = dilate(mask, hd, vd);
        for (let i = 0; i < W * H; i++) walk += mask[i] & D.reach[i];
      }
      const seen = new Uint8Array(W * H);
      for (let i = 0; i < W * H; i++) seen[i] = lit[i] && !mask[i] ? 1 : 0;
      const art = countArt(own, seen);
      const bw = x1 - x0 + 1, bh = y1 - y0 + 1;
      stats.push({ p, n, mask, own, seen, walk, x0, y0, x1: x1 + 1, y1: y1 + 1, bw, bh,
                   rect: n === bw * bh, parts: components(mask), undrawn: [], ...art });
    }
    engineCheck();
  }

  // With every piece a rectangle, each piece is one GBA map and its N/S/E/W
  // connections are the pieces sharing an edge segment with it. fieldmap.c fills a
  // connected map across the whole margin band on that side (corners included), so a
  // seen cell is drawn iff its piece is a neighbour on a side the cell lies past.
  function engineCheck() {
    const used = stats.filter((s) => s.n);
    if (!used.every((s) => s.rect)) return false;
    const by = {};
    for (const s of used) by[s.p] = s;
    for (const P of used) {
      const nb = {};
      for (const Q of used) {
        if (Q === P) continue;
        const ox = Q.x0 < P.x1 && Q.x1 > P.x0, oy = Q.y0 < P.y1 && Q.y1 > P.y0;
        nb[Q.p] = { N: Q.y1 === P.y0 && ox, S: Q.y0 === P.y1 && ox,
                    W: Q.x1 === P.x0 && oy, E: Q.x0 === P.x1 && oy };
      }
      for (let i = 0; i < W * H; i++) {
        if (!P.seen[i]) continue;
        const x = i % W, y = (i / W) | 0, s = nb[assign[i]];
        const drawn = (y < P.y0 && s.N) || (y >= P.y1 && s.S) || (x < P.x0 && s.W) || (x >= P.x1 && s.E);
        if (!drawn) P.undrawn.push(i);
      }
    }
    return true;
  }

  // ---------------------------------------------------------------- drawing

  function draw() {
    cv.width = W * cp; cv.height = H * cp;
    ctx.imageSmoothingEnabled = false;
    if (img) ctx.drawImage(img, 0, 0, W * cp, H * cp);

    ctx.globalAlpha = 0.22;
    for (let i = 0; i < W * H; i++) {
      ctx.fillStyle = COLORS[assign[i]];
      ctx.fillRect((i % W) * cp, ((i / W) | 0) * cp, cp, cp);
    }
    ctx.globalAlpha = 1;

    const S = stats[cur];
    if ($('showview').checked && S && S.n) {
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      for (let i = 0; i < W * H; i++) {
        if (!S.own[i] && !S.seen[i]) ctx.fillRect((i % W) * cp, ((i / W) | 0) * cp, cp, cp);
      }
      if ($('sight').checked && cp >= 6) {
        ctx.fillStyle = 'rgba(255,255,255,0.75)';
        const r = Math.max(1, cp / 8);
        for (let i = 0; i < W * H; i++) {
          if (S.mask[i] && D.reach[i]) ctx.fillRect((i % W + 0.5) * cp - r / 2, (((i / W) | 0) + 0.5) * cp - r / 2, r, r);
        }
      }
      ctx.strokeStyle = '#f33'; ctx.lineWidth = Math.max(1, cp / 8);
      ctx.beginPath();
      for (const i of S.undrawn) {
        const x = (i % W) * cp, y = ((i / W) | 0) * cp, m = cp * 0.2;
        ctx.moveTo(x + m, y + m); ctx.lineTo(x + cp - m, y + cp - m);
        ctx.moveTo(x + cp - m, y + m); ctx.lineTo(x + m, y + cp - m);
      }
      ctx.stroke();
    }

    // Piece boundaries: dark under-stroke, piece-coloured line on top.
    for (const [w, col] of [[Math.max(3, cp / 3), '#000'], [Math.max(1, cp / 8), '#fff']]) {
      ctx.strokeStyle = col; ctx.lineWidth = w;
      ctx.beginPath();
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          const a = assign[y * W + x];
          if (x < W - 1 && assign[y * W + x + 1] !== a) { ctx.moveTo((x + 1) * cp, y * cp); ctx.lineTo((x + 1) * cp, (y + 1) * cp); }
          if (y < H - 1 && assign[(y + 1) * W + x] !== a) { ctx.moveTo(x * cp, (y + 1) * cp); ctx.lineTo((x + 1) * cp, (y + 1) * cp); }
        }
      }
      ctx.stroke();
    }

    if ($('showcoll').checked) {
      for (let i = 0; i < W * H; i++) {
        if (D.blocked[i]) ctx.fillStyle = 'rgba(255,40,40,0.42)';
        else if (!D.reach[i]) ctx.fillStyle = 'rgba(255,180,0,0.45)';
        else continue;
        ctx.fillRect((i % W) * cp, ((i / W) | 0) * cp, cp, cp);
      }
    }

    if ($('showevents').checked) {
      for (const e of D.events) {
        ctx.fillStyle = e.warp ? '#ff0' : '#0ff';
        ctx.strokeStyle = '#000'; ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc((e.x + 0.5) * cp, (e.y + 0.5) * cp, Math.max(2, cp * 0.22), 0, Math.PI * 2);
        ctx.fill(); ctx.stroke();
      }
    }

    if (drag) {
      const [ax, bx] = [Math.min(drag.x0, drag.x1), Math.max(drag.x0, drag.x1)];
      const [ay, by] = [Math.min(drag.y0, drag.y1), Math.max(drag.y0, drag.y1)];
      ctx.strokeStyle = COLORS[cur]; ctx.lineWidth = 2;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(ax * cp + 1, ay * cp + 1, (bx - ax + 1) * cp - 2, (by - ay + 1) * cp - 2);
      ctx.setLineDash([]);
    }
  }

  function renderPanel() {
    const capT = D.cap_tiles, capM = D.cap_metatiles;
    const tb = document.querySelector('#tbl tbody');
    let h = '';
    for (const s of stats) {
      if (!s.n) continue;
      const ex = exact && exact[s.p];
      const exs = ex ? `<span class="${ex.over ? 'over' : 'ok'}">${ex.tiles}/${ex.metatiles}</span>` : '<span class="stale">-</span>';
      h += `<tr data-p="${s.p}" class="${s.p === cur ? 'on' : ''}">` +
        `<td><span class="sw" style="background:${COLORS[s.p]}"></span>${s.p + 1}</td>` +
        `<td title="cells (of which the player can stand on)">${s.n} (${s.walk})</td><td>${s.bw}&times;${s.bh}</td><td>${s.ownMt}</td><td>+${s.seenMt}</td>` +
        `<td class="${s.metatiles > capM ? 'over' : 'ok'}">${s.metatiles}</td>` +
        `<td class="${s.tiles > capT ? 'over' : 'ok'}">${s.tiles}</td><td>${exs}</td></tr>`;
    }
    tb.innerHTML = h;
    tb.querySelectorAll('tr').forEach((tr) => tr.addEventListener('click', () => selectPiece(+tr.dataset.p)));

    const warn = [];
    const used = stats.filter((s) => s.n);
    for (const s of used) {
      const name = 'piece ' + (s.p + 1);
      if (!s.rect) warn.push(`${name}: not a rectangle. Its GBA map would be the ${s.bw}×${s.bh} bounding box, and ${s.bw * s.bh - s.n} cells inside that box belong to other pieces.`);
      if (s.parts > 1) warn.push(`${name}: ${s.parts} separate parts.`);
      if ($('sight').checked && !s.walk) warn.push(`${name}: no cell the player can stand on, so it needs no art (all void).`);
      if (s.undrawn.length) warn.push(`${name}: ${s.undrawn.length} visible cells the engine draws as border block (red ×).`);
    }
    if (used.length > 1 && !used.every((s) => s.rect)) warn.push('engine draw check skipped: some piece is not a rectangle.');
    $('warn').innerHTML = warn.map((w) => `<li>${esc(w)}</li>`).join('');

    let st = `Map${String(MAP_ID).padStart(3, '0')} ${W}×${H}, tile merge ${D.tile_merge ? 'on' : 'off'}\n` +
      `whole map, proxy: ${wholeProxy.tiles} t / ${wholeProxy.metatiles} mt`;
    const b = budget && budget[D.tile_merge ? 'merge_on' : 'merge_off'];
    if (b) st += `\nwhole map, exact (incl. tileset-group pool): ${b.tiles} t / ${b.metatiles} mt`;
    $('status').textContent = st;
  }

  function refresh() {
    compute();
    draw();
    renderPanel();
    scheduleLocalSave();
  }

  // ---------------------------------------------------------------- editing

  function cellAt(e) {
    const r = cv.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left) / cp), y = Math.floor((e.clientY - r.top) / cp);
    return [Math.max(0, Math.min(W - 1, x)), Math.max(0, Math.min(H - 1, y))];
  }

  function pushUndo() {
    undoStack.push(assign.slice());
    if (undoStack.length > 60) undoStack.shift();
  }

  function edited() { exact = null; }

  function paintAt(x, y) {
    const r = (parseInt($('brush').value, 10) - 1) / 2;
    for (let yy = y - r; yy <= y + r; yy++) {
      for (let xx = x - r; xx <= x + r; xx++) {
        if (xx >= 0 && yy >= 0 && xx < W && yy < H) assign[yy * W + xx] = cur;
      }
    }
  }

  function floodFill(x, y) {
    const from = assign[y * W + x];
    if (from === cur) return;
    const stack = [y * W + x];
    while (stack.length) {
      const j = stack.pop();
      if (assign[j] !== from) continue;
      assign[j] = cur;
      const jx = j % W;
      if (jx > 0) stack.push(j - 1);
      if (jx < W - 1) stack.push(j + 1);
      if (j >= W) stack.push(j - W);
      if (j < W * (H - 1)) stack.push(j + W);
    }
  }

  cv.addEventListener('pointerdown', (e) => {
    if (tool === 'pan' || !D) return;
    e.preventDefault();
    cv.setPointerCapture(e.pointerId);
    const [x, y] = cellAt(e);
    pushUndo();
    if (tool === 'rect') { drag = { x0: x, y0: y, x1: x, y1: y }; draw(); }
    else if (tool === 'fill') { floodFill(x, y); edited(); refresh(); }
    else { painting = true; paintAt(x, y); draw(); }
  });
  cv.addEventListener('pointermove', (e) => {
    if (!drag && !painting) return;
    const [x, y] = cellAt(e);
    if (drag) { drag.x1 = x; drag.y1 = y; }
    else paintAt(x, y);
    draw();
  });
  const finish = () => {
    if (drag) {
      for (let y = Math.min(drag.y0, drag.y1); y <= Math.max(drag.y0, drag.y1); y++) {
        for (let x = Math.min(drag.x0, drag.x1); x <= Math.max(drag.x0, drag.x1); x++) assign[y * W + x] = cur;
      }
      drag = null;
    } else if (!painting) return;
    painting = false;
    edited();
    refresh();
  };
  cv.addEventListener('pointerup', finish);
  cv.addEventListener('pointercancel', finish);

  function undo() {
    if (!undoStack.length) return;
    assign = undoStack.pop();
    nPieces = Math.max(nPieces, Math.max(...assign) + 1);  // undoing a reset
    renderPieceButtons();
    edited();
    refresh();
  }

  // ---------------------------------------------------------------- controls

  function setTool(t) {
    tool = t;
    document.querySelectorAll('.tool').forEach((b) => b.classList.toggle('on', b.dataset.tool === t));
    cv.style.touchAction = t === 'pan' ? 'auto' : 'none';
    cv.style.cursor = t === 'pan' ? 'grab' : 'crosshair';
  }

  function renderPieceButtons() {
    let h = '';
    for (let p = 0; p < nPieces; p++) {
      h += `<button type="button" class="pc${p === cur ? ' on' : ''}" data-p="${p}" style="background:${COLORS[p]}">${p + 1}</button>`;
    }
    $('pieces').innerHTML = h;
    $('pieces').querySelectorAll('.pc').forEach((b) => b.addEventListener('click', () => selectPiece(+b.dataset.p)));
    $('addpiece').disabled = nPieces >= MAX_PIECES;
  }

  function selectPiece(p) {
    cur = p;
    renderPieceButtons();
    draw();
    renderPanel();
  }

  function zoom(f) {
    const st = $('stage');
    const cx = (st.scrollLeft + st.clientWidth / 2) / cp, cy = (st.scrollTop + st.clientHeight / 2) / cp;
    cp = Math.max(2, Math.min(32, Math.round(cp * f) || cp + (f > 1 ? 1 : -1)));
    draw();
    st.scrollLeft = cx * cp - st.clientWidth / 2;
    st.scrollTop = cy * cp - st.clientHeight / 2;
  }

  document.querySelectorAll('.tool').forEach((b) => b.addEventListener('click', () => setTool(b.dataset.tool)));
  $('addpiece').addEventListener('click', () => {
    if (nPieces < MAX_PIECES) { nPieces++; selectPiece(nPieces - 1); scheduleLocalSave(); }
  });
  $('undo').addEventListener('click', undo);
  $('reset').addEventListener('click', () => {
    if (!D || !confirm('Reset: put every cell back in piece 1? (undo restores it)')) return;
    pushUndo();
    assign = new Int8Array(W * H);
    nPieces = 2;
    cur = 0;
    renderPieceButtons();
    edited();
    refresh();
  });
  $('zin').addEventListener('click', () => zoom(1.25));
  $('zout').addEventListener('click', () => zoom(0.8));
  ['hdepth', 'vdepth'].forEach((id) => $(id).addEventListener('change', () => { edited(); refresh(); }));
  ['showview', 'showevents', 'showcoll'].forEach((id) => $(id).addEventListener('change', draw));
  $('sight').addEventListener('change', () => { edited(); refresh(); });
  $('merge').addEventListener('change', async () => {
    const box = $('merge');
    box.disabled = true;
    $('status').textContent = 'loading merge ' + (box.checked ? 'on' : 'off') + '…';
    try {
      const r = await fetch('/api/split/' + MAP_ID + '?merge=' + (box.checked ? 1 : 0));
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      for (const k of ['cells', 'mt_tiles', 'n_tiles', 'tile_merge', 'generation']) D[k] = d[k];
      wholeProxy = countArt(new Uint8Array(W * H).fill(1), null);
      edited();
      refresh();
    } catch (err) {
      box.checked = D.tile_merge;
      alert('merge toggle failed: ' + err.message);
      renderPanel();
    }
    box.disabled = false;
  });
  $('save').addEventListener('click', saveServer);
  $('exact').addEventListener('click', runExact);

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); undo(); return; }
    if (/^[1-9]$/.test(e.key) && +e.key <= nPieces) selectPiece(+e.key - 1);
    else if (e.key === '0' && nPieces >= 10) selectPiece(9);
    else if (e.key === 'r') setTool('rect');
    else if (e.key === 'b') setTool('paint');
    else if (e.key === 'f') setTool('fill');
    else if (e.key === 'h') setTool('pan');
    else if (e.key === '+' || e.key === '=') zoom(1.25);
    else if (e.key === '-') zoom(0.8);
  });

  // ---------------------------------------------------------------- persistence

  function layout() {
    return { pieces: nPieces, assign: Array.from(assign),
             hdepth: clampInt($('hdepth').value, 1, 7), vdepth: clampInt($('vdepth').value, 1, 7),
             width: W, height: H, saved_at: Date.now() };
  }

  let lsTimer = 0;
  function scheduleLocalSave() {
    clearTimeout(lsTimer);
    lsTimer = setTimeout(() => {
      try { localStorage.setItem(LS_KEY, JSON.stringify(layout())); } catch (_) { /* quota: ignore */ }
    }, 400);
  }

  function applyLayout(L) {
    if (!L || L.width !== W || L.height !== H || !Array.isArray(L.assign) || L.assign.length !== W * H) return false;
    nPieces = Math.max(1, Math.min(MAX_PIECES, L.pieces | 0));
    assign = Int8Array.from(L.assign.map((a) => Math.max(0, Math.min(nPieces - 1, a | 0))));
    if (L.hdepth) $('hdepth').value = L.hdepth;
    if (L.vdepth) $('vdepth').value = L.vdepth;
    return true;
  }

  async function saveServer() {
    const b = $('save');
    b.disabled = true; b.textContent = 'saving…';
    try {
      const r = await fetch('/api/split/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ map_id: MAP_ID, layout: layout() }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.status);
      b.textContent = 'saved ✓';
    } catch (err) {
      b.textContent = 'save failed';
      alert('save failed: ' + err.message);
    }
    setTimeout(() => { b.textContent = 'save'; b.disabled = false; }, 1500);
  }

  async function runExact() {
    const b = $('exact');
    const used = stats.filter((s) => s.n);
    b.disabled = true; b.textContent = 'running…';
    try {
      const r = await fetch('/api/split/exact', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ map_id: MAP_ID, pieces: used.map((s) => s.ids), merge: D.tile_merge }) });
      if (!r.ok) throw new Error(await r.text());
      const res = await r.json();
      exact = {};
      used.forEach((s, k) => { exact[s.p] = res[k]; });
      renderPanel();
    } catch (err) {
      alert('exact failed: ' + err.message);
    }
    b.textContent = 'exact'; b.disabled = false;
  }

  // ---------------------------------------------------------------- boot

  function clampInt(v, lo, hi) { return Math.max(lo, Math.min(hi, parseInt(v, 10) || lo)); }
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  async function boot() {
    const r = await fetch('/api/split/' + MAP_ID);
    if (!r.ok) { $('status').textContent = 'failed to load: ' + (await r.text()); return; }
    D = await r.json();
    W = D.width; H = D.height;
    document.title = 'Split Map' + String(MAP_ID).padStart(3, '0');
    $('title').textContent = 'Split M' + String(MAP_ID).padStart(3, '0');
    assign = new Int8Array(W * H);

    const all = new Uint8Array(W * H).fill(1);
    wholeProxy = countArt(all, null);

    let local = null;
    try { local = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (_) { local = null; }
    const saved = D.saved;
    const pick = [local, saved].filter(Boolean).sort((a, b) => (b.saved_at || 0) - (a.saved_at || 0));
    for (const L of pick) if (applyLayout(L)) break;

    cp = Math.max(4, Math.min(16, Math.floor($('stage').clientWidth / W)));
    setTool('pan');
    renderPieceButtons();

    img = new Image();
    img.onload = draw;
    img.src = '/api/mappng/' + MAP_ID + '.png?g=' + D.generation;
    refresh();

    $('merge').checked = D.tile_merge;
    fetch('/api/budget/' + MAP_ID).then((r) => (r.ok ? r.json() : null)).then((b) => {
      if (b) { budget = b; renderPanel(); }
    }).catch(() => {});
  }

  boot();
})();
