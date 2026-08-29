
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
  var apply = document.getElementById('k_apply');
  var status = document.getElementById('k_status');
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
