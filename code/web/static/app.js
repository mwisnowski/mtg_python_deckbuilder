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
    // If focus is inside a card tile, defer 'r'/'l' to tile-scoped handlers (Alternatives/Lock)
    try {
      var active = document.activeElement;
      if (active && active.closest && active.closest('.card-tile') && (k === 'r' || k === 'l')) {
        return;
      }
    } catch(_) { /* noop */ }
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
  initVirtualization(document);
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
  initVirtualization(e.target);
  });

  // Scroll a card-tile into view (cooperates with virtualization by re-rendering first)
  function scrollCardIntoView(name){
    if (!name) return;
    try{
      var section = document.querySelector('section');
      var grid = section && section.querySelector('.card-grid');
      if (!grid) return;
      // If virtualized, force a render around the approximate match by searching stored children
      var target = grid.querySelector('.card-tile[data-card-name="'+CSS.escape(name)+'"]');
      if (!target) {
        // Trigger a render update and try again
        grid.dispatchEvent(new Event('scroll')); // noop but can refresh
        target = grid.querySelector('.card-tile[data-card-name="'+CSS.escape(name)+'"]');
      }
      if (target) {
        target.scrollIntoView({ block: 'center', behavior: 'smooth' });
        target.focus && target.focus();
      }
    }catch(_){}
  }
  window.scrollCardIntoView = scrollCardIntoView;

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

  // --- Lightweight virtualization (feature-flagged via data-virtualize) ---
  function initVirtualization(root){
    try{
  var body = document.body || document.documentElement;
  var DIAG = !!(body && body.getAttribute('data-diag') === '1');
      // Global diagnostics aggregator
      var GLOBAL = (function(){
        if (!DIAG) return null;
        if (window.__virtGlobal) return window.__virtGlobal;
        var store = { grids: [], summaryEl: null };
        function ensure(){
          if (!store.summaryEl){
            var el = document.createElement('div');
            el.id = 'virt-global-diag';
            el.style.position = 'fixed';
            el.style.right = '8px';
            el.style.bottom = '8px';
            el.style.background = 'rgba(17,24,39,.85)';
            el.style.border = '1px solid var(--border)';
            el.style.padding = '.25rem .5rem';
            el.style.borderRadius = '6px';
            el.style.fontSize = '12px';
            el.style.color = '#cbd5e1';
            el.style.zIndex = '50';
            el.style.boxShadow = '0 4px 12px rgba(0,0,0,.35)';
            el.style.cursor = 'default';
            // Hidden by default; toggle with 'v'
            el.style.display = 'none';
            document.body.appendChild(el);
            store.summaryEl = el;
          }
          return store.summaryEl;
        }
        function update(){
          var el = ensure(); if (!el) return;
          var g = store.grids;
          var total = 0, visible = 0, lastMs = 0;
          for (var i=0;i<g.length;i++){
            total += g[i].total||0;
            visible += (g[i].end||0) - (g[i].start||0);
            lastMs = Math.max(lastMs, g[i].lastMs||0);
          }
          el.textContent = 'virt sum: grids '+g.length+' • visible '+visible+'/'+total+' • last '+lastMs.toFixed ? lastMs.toFixed(1) : String(lastMs)+'ms';
        }
        function register(gridId, ref){
          store.grids.push({ id: gridId, ref: ref });
          update();
          return {
            set: function(stats){
              for (var i=0;i<store.grids.length;i++){
                if (store.grids[i].id === gridId){
                  store.grids[i] = Object.assign({ id: gridId, ref: ref }, stats);
                  break;
                }
              }
              update();
            },
            toggle: function(){ var el = ensure(); el.style.display = (el.style.display === 'none' ? '' : 'none'); }
          };
        }
        window.__virtGlobal = { register: register, toggle: function(){ var el = ensure(); el.style.display = (el.style.display === 'none' ? '' : 'none'); } };
        return window.__virtGlobal;
      })();
      // Support card grids and other scroll containers (e.g., #owned-box)
      var grids = (root || document).querySelectorAll('.card-grid[data-virtualize="1"], #owned-box[data-virtualize="1"]');
      if (!grids.length) return;
      grids.forEach(function(grid){
        if (grid.__virtBound) return;
        grid.__virtBound = true;
        // Basic windowing: assumes roughly similar tile heights; uses sentinel measurements.
        var container = grid;
        container.style.position = container.style.position || 'relative';
  var wrapper = document.createElement('div');
  wrapper.className = 'virt-wrapper';
  // Ensure wrapper itself is a grid to preserve multi-column layout inside
  // when the container (e.g., .card-grid) is virtualized.
  wrapper.style.display = 'grid';
        // Move children into a fragment store (for owned, children live under UL)
        var source = container;
        // If this is the owned box, use the UL inside as the source list
        var ownedGrid = container.id === 'owned-box' ? container.querySelector('#owned-grid') : null;
        if (ownedGrid) { source = ownedGrid; }
        var all = Array.prototype.slice.call(source.children);
        // Threshold: skip virtualization for small grids to avoid scroll jitter at end-of-list.
        // Empirically flicker was reported when reaching the bottom of short grids (e.g., < 80 tiles)
        // due to dynamic height adjustments (image loads + padding recalcs). Keeping full DOM
        // is cheaper than the complexity for small sets.
        var MIN_VIRT_ITEMS = 80;
        if (all.length < MIN_VIRT_ITEMS){
          // Mark as processed so we don't attempt again on HTMX swaps.
          return; // children remain in place; no virtualization applied.
        }
        var store = document.createElement('div');
        store.style.display = 'none';
        all.forEach(function(n){ store.appendChild(n); });
        var padTop = document.createElement('div');
        var padBottom = document.createElement('div');
        padTop.style.height = '0px'; padBottom.style.height = '0px';
        // For owned, keep the UL but render into it; otherwise append wrapper to container
        if (ownedGrid){
          ownedGrid.innerHTML = '';
          ownedGrid.appendChild(padTop);
          ownedGrid.appendChild(wrapper);
          ownedGrid.appendChild(padBottom);
          ownedGrid.appendChild(store);
        } else {
          container.appendChild(wrapper);
          container.appendChild(padBottom);
          container.appendChild(store);
        }
        var rowH = container.id === 'owned-box' ? 160 : 240; // estimate tile height
        var perRow = 1;
        // Optional diagnostics overlay
        var diagBox = null; var lastRenderAt = 0; var lastRenderMs = 0;
        var renderCount = 0; var measureCount = 0; var swapCount = 0;
        var gridId = (container.id || container.className || 'grid') + '#' + Math.floor(Math.random()*1e6);
        var globalReg = DIAG && GLOBAL ? GLOBAL.register(gridId, container) : null;
        function fmt(n){ try{ return (Math.round(n*10)/10).toFixed(1); }catch(_){ return String(n); } }
        function ensureDiag(){
          if (!DIAG) return null;
          if (diagBox) return diagBox;
          diagBox = document.createElement('div');
          diagBox.className = 'virt-diag';
          diagBox.style.position = 'sticky';
          diagBox.style.top = '0';
          diagBox.style.zIndex = '5';
          diagBox.style.background = 'rgba(17,24,39,.85)';
          diagBox.style.border = '1px solid var(--border)';
          diagBox.style.padding = '.25rem .5rem';
          diagBox.style.borderRadius = '6px';
          diagBox.style.fontSize = '12px';
          diagBox.style.margin = '0 0 .35rem 0';
          diagBox.style.color = '#cbd5e1';
          diagBox.style.display = 'none'; // hidden until toggled
          // Controls
          var controls = document.createElement('div');
          controls.style.display = 'flex';
          controls.style.gap = '.35rem';
          controls.style.alignItems = 'center';
          controls.style.marginBottom = '.25rem';
          var title = document.createElement('div'); title.textContent = 'virt diag'; title.style.fontWeight = '600'; title.style.fontSize = '11px'; title.style.color = '#9ca3af';
          var btnCopy = document.createElement('button'); btnCopy.type = 'button'; btnCopy.textContent = 'Copy'; btnCopy.className = 'btn small';
          btnCopy.addEventListener('click', function(){ try{ var payload = {
            id: gridId, rowH: rowH, perRow: perRow, start: start, end: end, total: total,
            renderCount: renderCount, measureCount: measureCount, swapCount: swapCount,
            lastRenderMs: lastRenderMs, lastRenderAt: lastRenderAt
          }; navigator.clipboard.writeText(JSON.stringify(payload, null, 2)); btnCopy.textContent = 'Copied'; setTimeout(function(){ btnCopy.textContent = 'Copy'; }, 1200); }catch(_){ }
          });
          var btnHide = document.createElement('button'); btnHide.type = 'button'; btnHide.textContent = 'Hide'; btnHide.className = 'btn small';
          btnHide.addEventListener('click', function(){ diagBox.style.display = 'none'; });
          controls.appendChild(title); controls.appendChild(btnCopy); controls.appendChild(btnHide);
          diagBox.appendChild(controls);
          var text = document.createElement('div'); text.className = 'virt-diag-text'; diagBox.appendChild(text);
          var host = (container.id === 'owned-box') ? container : container.parentElement || container;
          host.insertBefore(diagBox, host.firstChild);
          return diagBox;
        }
        function measure(){
          try {
            measureCount++;
            // create a temp tile to measure if none
            var probe = store.firstElementChild || all[0];
            if (probe){
              var fake = probe.cloneNode(true);
              fake.style.position = 'absolute'; fake.style.visibility = 'hidden'; fake.style.pointerEvents = 'none';
              (ownedGrid || container).appendChild(fake);
              var rect = fake.getBoundingClientRect();
              rowH = Math.max(120, Math.ceil(rect.height) + 16);
              (ownedGrid || container).removeChild(fake);
            }
            // Estimate perRow via computed styles of grid
            var style = window.getComputedStyle(ownedGrid || container);
            var cols = style.getPropertyValue('grid-template-columns');
            // Mirror grid settings onto the wrapper so its children still flow in columns
            try {
              if (cols && cols.trim()) wrapper.style.gridTemplateColumns = cols;
              var gap = style.getPropertyValue('gap') || style.getPropertyValue('grid-gap');
              if (gap && gap.trim()) wrapper.style.gap = gap;
              // Inherit justify/align if present
              var ji = style.getPropertyValue('justify-items');
              if (ji && ji.trim()) wrapper.style.justifyItems = ji;
              var ai = style.getPropertyValue('align-items');
              if (ai && ai.trim()) wrapper.style.alignItems = ai;
            } catch(_) {}
            perRow = Math.max(1, (cols && cols.split ? cols.split(' ').filter(function(x){return x && (x.indexOf('px')>-1 || x.indexOf('fr')>-1 || x.indexOf('minmax(')>-1);}).length : 1));
          } catch(_){}
        }
        measure();
        var total = all.length;
        var start = 0, end = 0;
        function render(){
          var t0 = DIAG ? performance.now() : 0;
          var scroller = container;
          var vh = scroller.clientHeight || window.innerHeight;
          var scrollTop = scroller.scrollTop;
          // If container isn’t scrollable, use window scroll offset
          var top = scrollTop || (scroller.getBoundingClientRect().top < 0 ? -scroller.getBoundingClientRect().top : 0);
          var rowsInView = Math.ceil(vh / rowH) + 2; // overscan
          var rowStart = Math.max(0, Math.floor(top / rowH) - 1);
          var rowEnd = Math.min(Math.ceil((top / rowH)) + rowsInView, Math.ceil(total / perRow));
          var newStart = rowStart * perRow;
          var newEnd = Math.min(total, rowEnd * perRow);
          if (newStart === start && newEnd === end) return; // no change
          start = newStart; end = newEnd;
          // Padding
          var beforeRows = Math.floor(start / perRow);
          var afterRows = Math.ceil((total - end) / perRow);
          padTop.style.height = (beforeRows * rowH) + 'px';
          padBottom.style.height = (afterRows * rowH) + 'px';
          // Render visible children
          wrapper.innerHTML = '';
          for (var i = start; i < end; i++) {
            var node = all[i];
            if (node) wrapper.appendChild(node);
          }
          if (DIAG){
            var box = ensureDiag();
            if (box){
              var dt = performance.now() - t0; lastRenderMs = dt; renderCount++; lastRenderAt = Date.now();
              var vis = end - start; var rowsTotal = Math.ceil(total / perRow);
              var textEl = box.querySelector('.virt-diag-text');
              var msg = 'range ['+start+'..'+end+') of '+total+' • vis '+vis+' • rows ~'+rowsTotal+' • perRow '+perRow+' • rowH '+rowH+'px • render '+fmt(dt)+'ms • renders '+renderCount+' • measures '+measureCount+' • swaps '+swapCount;
              textEl.textContent = msg;
              // Health hint
              var bad = (dt > 33) || (vis > 300);
              var warn = (!bad) && ((dt > 16) || (vis > 200));
              box.style.borderColor = bad ? '#ef4444' : (warn ? '#f59e0b' : 'var(--border)');
              box.style.boxShadow = bad ? '0 0 0 1px rgba(239,68,68,.35)' : (warn ? '0 0 0 1px rgba(245,158,11,.25)' : 'none');
              if (globalReg && globalReg.set){ globalReg.set({ total: total, start: start, end: end, lastMs: dt }); }
            }
          }
        }
        function onScroll(){ render(); }
        function onResize(){ measure(); render(); }
        container.addEventListener('scroll', onScroll);
        window.addEventListener('resize', onResize);
        // Initial size; ensure container is scrollable for our logic
        if (!container.style.maxHeight) container.style.maxHeight = '70vh';
        container.style.overflow = container.style.overflow || 'auto';
        render();
        // Re-render after filters resort or HTMX swaps
        document.addEventListener('htmx:afterSwap', function(ev){ if (container.contains(ev.target)) { swapCount++; all = Array.prototype.slice.call(store.children).concat(Array.prototype.slice.call(wrapper.children)); total = all.length; measure(); render(); } });
        // Keyboard toggle for overlays: 'v'
        if (DIAG && !window.__virtHotkeyBound){
          window.__virtHotkeyBound = true;
          document.addEventListener('keydown', function(e){
            try{
              if (e.target && (/input|textarea|select/i).test(e.target.tagName)) return;
              if (e.key && e.key.toLowerCase() === 'v'){
                e.preventDefault();
                // Toggle all virt-diag boxes and the global summary
                var shown = null;
                document.querySelectorAll('.virt-diag').forEach(function(b){ if (shown === null) shown = (b.style.display === 'none'); b.style.display = shown ? '' : 'none'; });
                if (GLOBAL && GLOBAL.toggle) GLOBAL.toggle();
              }
            }catch(_){ }
          });
        }
      });
    }catch(_){ }
  }

  // LQIP blur/fade-in for thumbnails marked with data-lqip
  document.addEventListener('DOMContentLoaded', function(){
    try{
      document.querySelectorAll('img[data-lqip]')
        .forEach(function(img){
          img.classList.add('lqip');
          img.addEventListener('load', function(){ img.classList.add('loaded'); }, { once: true });
        });
    }catch(_){ }
  });
})();
