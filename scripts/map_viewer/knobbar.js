
(function(){
  var kb = document.getElementById('knobbar');
  if (!kb) return;
  var q = V.quant || {};
  var setv = function(id, val){ var e = document.getElementById(id); if (e != null && val != null) e.value = val; };
  setv('k_green', (q.green_cuts || []).join(','));
  setv('k_dark', q.dark_value);
  setv('k_neutral', q.neutral_sat);
  setv('k_floor', q.palette_floor);
  setv('k_maxpal', q.max_palettes);
  var ov = document.getElementById('k_overflow'); if (ov && q.overflow_weight) ov.value = q.overflow_weight;
  // Reduction select: injected here (next to overflow) so both pages that load the knob bar get it.
  var rd = document.getElementById('k_reduction');
  if (!rd && ov) {
    var lab = document.createElement('label');
    lab.title = 'Per-palette colour reduction: stock median cut, or usage-weighted Ward clustering';
    lab.appendChild(document.createTextNode('reduction '));
    rd = document.createElement('select'); rd.id = 'k_reduction';
    [['median_cut', 'median cut (stock)'], ['ward', 'Ward (P1)']].forEach(function(o){
      var op = document.createElement('option'); op.value = o[0]; op.textContent = o[1]; rd.appendChild(op);
    });
    lab.appendChild(rd);
    var ovl = ov.closest('label');
    (ovl || ov).insertAdjacentElement('afterend', lab);
  }
  if (rd && q.reduction) rd.value = q.reduction;
  // Shared palettes (P2 preview): injected next to Reduction, same pattern.
  var sh = document.getElementById('k_shared');
  if (!sh && rd) {
    var slab = document.createElement('label');
    slab.title = 'Preview: pin fixed game-wide rock + green palettes into maps that use enough of that art (viewer only; not in the ROM). Not combinable with seam palettes.';
    slab.appendChild(document.createTextNode('shared palettes (P2) '));
    sh = document.createElement('input'); sh.type = 'checkbox'; sh.id = 'k_shared';
    slab.appendChild(sh);
    var rdl = rd.closest('label');
    (rdl || rd).insertAdjacentElement('afterend', slab);
  }
  if (sh) sh.checked = !!q.shared_palettes;
  // Tile merge (game-wide near-duplicate 8x8 merge): injected next to shared palettes.
  var tm = document.getElementById('k_tilemerge');
  if (!tm && sh) {
    var tlab = document.createElement('label');
    tlab.title = 'Preview: game-wide lossy merge of near-duplicate 8x8 tiles + lossless metatile dedup, to fit big maps under the 1024-tile / 1024-metatile caps (viewer only until adopted by the ROM build). Not combinable with seam palettes.';
    tlab.appendChild(document.createTextNode('tile merge '));
    tm = document.createElement('input'); tm.type = 'checkbox'; tm.id = 'k_tilemerge';
    tlab.appendChild(tm);
    var shl = sh.closest('label');
    (shl || sh).insertAdjacentElement('afterend', tlab);
  }
  if (tm) tm.checked = !!q.tile_merge;
  var apply = document.getElementById('k_apply');
  var status = document.getElementById('k_status');
  // Badge text: default preview vs custom knobs (non_stock) vs ROM-equivalent (badge stays hidden).
  var badge = document.getElementById('nonstock-badge');
  if (badge && q.non_stock) {
    badge.textContent = q.viewer_default
      ? '\u26a0 preview: tile merge ON \u2014 not the ROM'
      : '\u26a0 custom quantize knobs \u2014 not the ROM';
  }
  // Reset (viewer default) / ROM view: Apply with an empty body = viewer default; explicit stock values = ROM.
  var post = function(body){
    status.textContent = 're-quantizing\u2026';
    fetch('/api/quantize', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(Object.assign({ map_id: D.meta.map_id }, body)) })
      .then(function(r){ return r.text().then(function(t){ return { ok:r.ok, t:t }; }); })
      .then(function(res){
        if (!res.ok) {
          var msg = res.t; try { msg = JSON.parse(res.t).error || res.t; } catch (e) {}
          status.textContent = 'error: ' + msg; return;
        }
        location.reload();
      })
      .catch(function(e){ status.textContent = 'error: ' + e; });
  };
  [['Reset', 'Viewer default: ROM quantizer + tile merge (preview)', {}],
   ['ROM view', 'ROM-equivalent: Ward + shared palettes, no tile merge (rom_quantize)',
    { reduction:'ward', shared_palettes:true, tile_merge:false }]].forEach(function(b){
    var btn = document.createElement('button'); btn.className = 'btn'; btn.textContent = b[0]; btn.title = b[1];
    btn.addEventListener('click', function(){ post(b[2]); });
    apply.insertAdjacentElement('afterend', btn);
  });
  apply.addEventListener('click', function(){
    var greens = (document.getElementById('k_green').value || '').split(',')
      .map(function(s){ return parseFloat(s.trim()); }).filter(function(n){ return !isNaN(n); });
    var body = {
      map_id: D.meta.map_id,
      green_cuts: greens,
      dark_value: parseInt(document.getElementById('k_dark').value, 10),
      neutral_sat: parseFloat(document.getElementById('k_neutral').value),
      palette_floor: parseInt(document.getElementById('k_floor').value, 10),
      overflow_weight: document.getElementById('k_overflow').value,
      reduction: rd ? rd.value : 'median_cut',
      shared_palettes: sh ? sh.checked : false,
      tile_merge: tm ? tm.checked : false,
      max_palettes: parseInt(document.getElementById('k_maxpal').value, 10)
    };
    status.textContent = 're-quantizing…'; apply.disabled = true;
    fetch('/api/quantize', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) })
      .then(function(r){ return r.text().then(function(t){ return { ok:r.ok, t:t }; }); })
      .then(function(res){
        if (!res.ok) {
          var msg = res.t; try { msg = JSON.parse(res.t).error || res.t; } catch (e) {}
          status.textContent = 'error: ' + msg; apply.disabled = false; return;
        }
        location.reload();  // re-render map + palettes from fresh state (new generation busts image cache)
      })
      .catch(function(e){ status.textContent = 'error: ' + e; apply.disabled = false; });
  });
})();
