/* Core app enhancements: tokens, toasts, shortcuts, state, skeletons */
(function(){
  // Design tokens fallback (in case CSS variables missing in older browsers)
  // No-op here since styles.css defines variables; kept for future JS reads.

  // State persistence helpers (localStorage + URL hash)
  var state = {
    get: function(key, def){
      try { var v = localStorage.getItem('mtg:'+key); return v !== null ? JSON.parse(v) : def; } catch(e){ return def; }
    },
    set: function(key, val){
      try { localStorage.setItem('mtg:'+key, JSON.stringify(val)); } catch(e){}
    },
    inHash: function(obj){
      // Merge obj into location.hash as query-like params
      try {
        var params = new URLSearchParams((location.hash||'').replace(/^#/, ''));
        Object.keys(obj||{}).forEach(function(k){ params.set(k, obj[k]); });
        location.hash = params.toString();
      } catch(e){}
    },
    readHash: function(){
      try { return new URLSearchParams((location.hash||'').replace(/^#/, '')); } catch(e){ return new URLSearchParams(); }
    }
  };
  window.__mtgState = state;

  // Toast system
  var toastHost;
  function ensureToastHost(){
    if (!toastHost){
      toastHost = document.createElement('div');
      toastHost.className = 'toast-host';
      document.body.appendChild(toastHost);
    }
    return toastHost;
  }
  function toast(msg, type, opts){
    ensureToastHost();
    var t = document.createElement('div');
    t.className = 'toast' + (type ? ' '+type : '');
    t.setAttribute('role','status');
    t.setAttribute('aria-live','polite');
    t.textContent = '';
    if (typeof msg === 'string') { t.textContent = msg; }
    else if (msg && msg.nodeType === 1) { t.appendChild(msg); }
    toastHost.appendChild(t);
    var delay = (opts && opts.duration) || 2600;
    setTimeout(function(){ t.classList.add('hide'); setTimeout(function(){ t.remove(); }, 300); }, delay);
    return t;
  }
  window.toast = toast;
  function toastHTML(html, type, opts){
    var container = document.createElement('div');
    container.innerHTML = html;
    return toast(container, type, opts);
  }
  window.toastHTML = toastHTML;

  // Global HTMX error handling => toast
  document.addEventListener('htmx:responseError', function(e){
    var detail = e.detail || {}; var xhr = detail.xhr || {};
    var rid = (xhr.getResponseHeader && xhr.getResponseHeader('X-Request-ID')) || '';
    var payload = (function(){ try { return JSON.parse(xhr.responseText || '{}'); } catch(_){ return {}; } })();
    var status = payload.status || xhr.status || '';
    var msg = payload.detail || payload.message || 'Action failed';
    var path = payload.path || (e && e.detail && e.detail.path) || '';
    var html = ''+
      '<div style="display:flex; align-items:center; gap:.5rem">'+
      '<span style="font-weight:600">'+String(msg)+'</span>'+ (status? ' <span class="muted">('+status+')</span>' : '')+
      (rid ? '<button class="btn small" style="margin-left:auto" type="button" data-copy-error>Copy details</button>' : '')+
      '</div>'+
      (rid ? '<div class="muted" style="font-size:11px; margin-top:2px">Request-ID: <code>'+rid+'</code></div>' : '');
    var t = toastHTML(html, 'error', { duration: 7000 });
    // Wire Copy
    var btn = t.querySelector('[data-copy-error]');
    if (btn){
      btn.addEventListener('click', function(){
        var lines = [
          'Error: '+String(msg),
          'Status: '+String(status),
          'Path: '+String(path || (xhr.responseURL||'')),
          'Request-ID: '+String(rid)
        ];
        try { navigator.clipboard.writeText(lines.join('\n')); btn.textContent = 'Copied'; setTimeout(function(){ btn.textContent = 'Copy details'; }, 1200); } catch(_){ }
      });
    }
    // Optional inline banner if a surface is available
    try {
      var target = e && e.target;
      var surface = (target && target.closest && target.closest('[data-error-surface]')) || document.querySelector('[data-error-surface]');
      if (surface){
        var banner = document.createElement('div');
        banner.className = 'inline-error-banner';
        banner.innerHTML = '<strong>'+String(msg)+'</strong>' + (rid? ' <span class="muted">(Request-ID: '+rid+')</span>' : '');
        surface.prepend(banner);
        setTimeout(function(){ banner.remove(); }, 8000);
      }
    } catch(_){ }
  });
  document.addEventListener('htmx:sendError', function(){ toast('Network error', 'error', { duration: 4000 }); });

  // Keyboard shortcuts
  var keymap = {
    ' ': function(){ var el = document.querySelector('[data-action="continue"], .btn-continue'); if (el) el.click(); },
    'r': function(){ var el = document.querySelector('[data-action="rerun"], .btn-rerun'); if (el) el.click(); },
    'b': function(){ var el = document.querySelector('[data-action="back"], .btn-back'); if (el) el.click(); },
    'l': function(){ var el = document.querySelector('[data-action="toggle-logs"], .btn-logs'); if (el) el.click(); },
  };
  document.addEventListener('keydown', function(e){
    if (e.target && (/input|textarea|select/i).test(e.target.tagName)) return; // don't hijack inputs
    var k = e.key.toLowerCase();
    if (keymap[k]){ e.preventDefault(); keymap[k](); }
  });

  // Focus ring visibility for keyboard nav
  function addFocusVisible(){
    var hadKeyboardEvent = false;
    function onKeyDown(){ hadKeyboardEvent = true; }
    function onPointer(){ hadKeyboardEvent = false; }
    function onFocus(e){ if (hadKeyboardEvent) e.target.classList.add('focus-visible'); }
    function onBlur(e){ e.target.classList.remove('focus-visible'); }
    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('mousedown', onPointer, true);
    window.addEventListener('pointerdown', onPointer, true);
    window.addEventListener('touchstart', onPointer, true);
    document.addEventListener('focusin', onFocus);
    document.addEventListener('focusout', onBlur);
  }
  addFocusVisible();

  // Skeleton utility: swap placeholders before HTMX swaps or on explicit triggers
  function showSkeletons(container){
    (container || document).querySelectorAll('[data-skeleton]')
      .forEach(function(el){ el.classList.add('is-loading'); });
  }
  function hideSkeletons(container){
    (container || document).querySelectorAll('[data-skeleton]')
      .forEach(function(el){ el.classList.remove('is-loading'); });
  }
  window.skeletons = { show: showSkeletons, hide: hideSkeletons };

  document.addEventListener('htmx:beforeRequest', function(e){ showSkeletons(e.target); });
  document.addEventListener('htmx:afterSwap', function(e){ hideSkeletons(e.target); });

  // Example: persist "show skipped" toggle if present
  document.addEventListener('change', function(e){
    var el = e.target;
    if (el && el.matches('[data-pref]')){
      var key = el.getAttribute('data-pref');
      var val = (el.type === 'checkbox') ? !!el.checked : el.value;
      state.set(key, val);
      state.inHash((function(o){ o[key] = val; return o; })({}));
    }
  });
  // On load, initialize any data-pref elements
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('[data-pref]').forEach(function(el){
      var key = el.getAttribute('data-pref');
      var saved = state.get(key, undefined);
      if (typeof saved !== 'undefined'){
        if (el.type === 'checkbox') el.checked = !!saved; else el.value = saved;
      }
    });
    hydrateProgress(document);
    syncShowSkipped(document);
    initCardFilters(document);
  });

  // Hydrate progress bars with width based on data-pct
  function hydrateProgress(root){
    (root || document).querySelectorAll('.progress[data-pct]')
      .forEach(function(p){
        var pct = parseInt(p.getAttribute('data-pct') || '0', 10);
        if (isNaN(pct) || pct < 0) pct = 0; if (pct > 100) pct = 100;
        var bar = p.querySelector('.bar'); if (!bar) return;
        // Animate width for a bit of delight
        requestAnimationFrame(function(){ bar.style.width = pct + '%'; });
      });
  }
  // Keep hidden inputs for show_skipped in sync with the sticky checkbox
  function syncShowSkipped(root){
    var cb = (root || document).querySelector('input[name="__toggle_show_skipped"][data-pref]');
    if (!cb) return;
    var val = cb.checked ? '1' : '0';
    (root || document).querySelectorAll('section form').forEach(function(f){
      var h = f.querySelector('input[name="show_skipped"]');
      if (h) h.value = val;
    });
  }
  document.addEventListener('htmx:afterSwap', function(e){
    hydrateProgress(e.target);
    syncShowSkipped(e.target);
    initCardFilters(e.target);
  });

  // --- Card grid filters, reasons, and collapsible groups ---
  function initCardFilters(root){
    var section = (root || document).querySelector('section');
    if (!section) return;
    var toolbar = section.querySelector('.cards-toolbar');
    if (!toolbar) return; // nothing to do
    var q = toolbar.querySelector('input[name="filter_query"]');
    var ownedSel = toolbar.querySelector('select[name="filter_owned"]');
    var showReasons = toolbar.querySelector('input[name="show_reasons"]');
    var collapseGroups = toolbar.querySelector('input[name="collapse_groups"]');
    var resultsEl = toolbar.querySelector('[data-results]');
  var emptyEl = section.querySelector('[data-empty]');
  var sortSel = toolbar.querySelector('select[name="filter_sort"]');
  var chipOwned = toolbar.querySelector('[data-chip-owned="owned"]');
  var chipNot = toolbar.querySelector('[data-chip-owned="not"]');
  var chipAll = toolbar.querySelector('[data-chip-owned="all"]');
  var chipClear = toolbar.querySelector('[data-chip-clear]');

    function getVal(el){ return el ? (el.type === 'checkbox' ? !!el.checked : (el.value||'')) : ''; }
    // Read URL hash on first init to hydrate controls
    try {
      var params = window.__mtgState.readHash();
      if (params){
        var hv = params.get('q'); if (q && hv !== null) q.value = hv;
        hv = params.get('owned'); if (ownedSel && hv) ownedSel.value = hv;
        hv = params.get('showreasons'); if (showReasons && hv !== null) showReasons.checked = (hv === '1');
        hv = params.get('collapse'); if (collapseGroups && hv !== null) collapseGroups.checked = (hv === '1');
        hv = params.get('sort'); if (sortSel && hv) sortSel.value = hv;
      }
    } catch(_){}
    function apply(){
      var query = (getVal(q)+ '').toLowerCase().trim();
      var ownedMode = (getVal(ownedSel) || 'all');
      var showR = !!getVal(showReasons);
      var collapse = !!getVal(collapseGroups);
      var sortMode = (getVal(sortSel) || 'az');
      // Toggle reasons visibility via section class
      section.classList.toggle('hide-reasons', !showR);
      // Collapse or expand all groups if toggle exists; when not collapsed, restore per-group stored state
      section.querySelectorAll('.group').forEach(function(wrapper){
        var grid = wrapper.querySelector('.group-grid'); if (!grid) return;
        var key = wrapper.getAttribute('data-group-key');
        if (collapse){
          grid.setAttribute('data-collapsed','1');
        } else {
          // restore stored
          if (key){
            var stored = state.get('cards:group:'+key, null);
            if (stored === true){ grid.setAttribute('data-collapsed','1'); }
            else { grid.removeAttribute('data-collapsed'); }
          } else {
            grid.removeAttribute('data-collapsed');
          }
        }
      });
      // Filter tiles
      var tiles = section.querySelectorAll('.card-grid .card-tile');
      var visible = 0;
      tiles.forEach(function(tile){
        var name = (tile.getAttribute('data-card-name')||'').toLowerCase();
        var role = (tile.getAttribute('data-role')||'').toLowerCase();
        var tags = (tile.getAttribute('data-tags')||'').toLowerCase();
        var owned = tile.getAttribute('data-owned') === '1';
        var text = name + ' ' + role + ' ' + tags;
        var qOk = !query || text.indexOf(query) !== -1;
        var oOk = (ownedMode === 'all') || (ownedMode === 'owned' && owned) || (ownedMode === 'not' && !owned);
        var show = qOk && oOk;
        tile.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      // Sort within each grid
      function keyFor(tile){
        var name = (tile.getAttribute('data-card-name')||'');
        var owned = tile.getAttribute('data-owned') === '1' ? 1 : 0;
        var gc = tile.classList.contains('game-changer') ? 1 : 0;
        return { name: name.toLowerCase(), owned: owned, gc: gc };
      }
      section.querySelectorAll('.card-grid').forEach(function(grid){
        var arr = Array.prototype.slice.call(grid.querySelectorAll('.card-tile'));
        arr.sort(function(a,b){
          var ka = keyFor(a), kb = keyFor(b);
          if (sortMode === 'owned'){
            if (kb.owned !== ka.owned) return kb.owned - ka.owned;
            if (kb.gc !== ka.gc) return kb.gc - ka.gc; // gc next
            return ka.name.localeCompare(kb.name);
          } else if (sortMode === 'gc'){
            if (kb.gc !== ka.gc) return kb.gc - ka.gc;
            if (kb.owned !== ka.owned) return kb.owned - ka.owned;
            return ka.name.localeCompare(kb.name);
          }
          // default A–Z
          return ka.name.localeCompare(kb.name);
        });
        arr.forEach(function(el){ grid.appendChild(el); });
      });
      // Update group counts based on visible tiles within each group
      section.querySelectorAll('.group').forEach(function(wrapper){
        var grid = wrapper.querySelector('.group-grid');
        var count = 0;
        if (grid){
          grid.querySelectorAll('.card-tile').forEach(function(t){ if (t.style.display !== 'none') count++; });
        }
        var cEl = wrapper.querySelector('[data-count]');
        if (cEl) cEl.textContent = count;
      });
  if (resultsEl) resultsEl.textContent = String(visible);
  if (emptyEl) emptyEl.hidden = (visible !== 0);
      // Persist prefs
      if (q && q.hasAttribute('data-pref')) state.set(q.getAttribute('data-pref'), q.value);
      if (ownedSel && ownedSel.hasAttribute('data-pref')) state.set(ownedSel.getAttribute('data-pref'), ownedSel.value);
      if (showReasons && showReasons.hasAttribute('data-pref')) state.set(showReasons.getAttribute('data-pref'), !!showReasons.checked);
      if (collapseGroups && collapseGroups.hasAttribute('data-pref')) state.set(collapseGroups.getAttribute('data-pref'), !!collapseGroups.checked);
  if (sortSel && sortSel.hasAttribute('data-pref')) state.set(sortSel.getAttribute('data-pref'), sortSel.value);
  // Update URL hash for shareability
  try { window.__mtgState.inHash({ q: query, owned: ownedMode, showreasons: showR ? 1 : 0, collapse: collapse ? 1 : 0, sort: sortMode }); } catch(_){ }
    }
    // Wire events
    if (q) q.addEventListener('input', apply);
    if (ownedSel) ownedSel.addEventListener('change', apply);
    if (showReasons) showReasons.addEventListener('change', apply);
    if (collapseGroups) collapseGroups.addEventListener('change', apply);
    if (chipOwned) chipOwned.addEventListener('click', function(){ if (ownedSel){ ownedSel.value = 'owned'; } apply(); });
    if (chipNot) chipNot.addEventListener('click', function(){ if (ownedSel){ ownedSel.value = 'not'; } apply(); });
    if (chipAll) chipAll.addEventListener('click', function(){ if (ownedSel){ ownedSel.value = 'all'; } apply(); });
    if (chipClear) chipClear.addEventListener('click', function(){ if (q) q.value=''; if (ownedSel) ownedSel.value='all'; apply(); });
    // Individual group toggles
    section.querySelectorAll('.group-header .toggle').forEach(function(btn){
      btn.addEventListener('click', function(){
        var wrapper = btn.closest('.group');
        var grid = wrapper && wrapper.querySelector('.group-grid');
        if (!grid) return;
  var key = wrapper.getAttribute('data-group-key');
        var willCollapse = !grid.getAttribute('data-collapsed');
        if (willCollapse) grid.setAttribute('data-collapsed','1'); else grid.removeAttribute('data-collapsed');
        if (key){ state.set('cards:group:'+key, !!willCollapse); }
  // ARIA
  btn.setAttribute('aria-expanded', willCollapse ? 'false' : 'true');
      });
    });
    // Per-card reason toggle: delegate clicks on .btn-why
    section.addEventListener('click', function(e){
      var t = e.target;
      if (!t || !t.classList || !t.classList.contains('btn-why')) return;
      e.preventDefault();
      var tile = t.closest('.card-tile');
      if (!tile) return;
      var globalHidden = section.classList.contains('hide-reasons');
      if (globalHidden){
        // Force-show overrides global hidden
        var on = tile.classList.toggle('force-show');
        if (on) tile.classList.remove('force-hide');
        t.textContent = on ? 'Hide why' : 'Why?';
      } else {
        // Hide this tile only
        var off = tile.classList.toggle('force-hide');
        if (off) tile.classList.remove('force-show');
        t.textContent = off ? 'Show why' : 'Hide why';
      }
    });
    // Initial apply on hydrate
    apply();

    // Keyboard helpers: '/' focuses query, Esc clears
    function onKey(e){
      // avoid when typing in inputs
      if (e.target && (/input|textarea|select/i).test(e.target.tagName)) return;
      if (e.key === '/'){
        if (q){ e.preventDefault(); q.focus(); q.select && q.select(); }
      } else if (e.key === 'Escape'){
        if (q && q.value){ q.value=''; apply(); }
      }
    }
    document.addEventListener('keydown', onKey);
  }
})();
