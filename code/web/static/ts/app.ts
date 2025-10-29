/* Core app enhancements: tokens, toasts, shortcuts, state, skeletons */
// Type definitions moved inline to avoid module system
interface StateManager {
  get(key: string, def?: any): any;
  set(key: string, val: any): void;
  inHash(obj: Record<string, any>): void;
  readHash(): URLSearchParams;
}

interface ToastOptions {
  duration?: number;
}

interface TelemetryManager {
  send(eventName: string, data?: Record<string, any>): void;
}

interface SkeletonManager {
  show(context?: HTMLElement | Document): void;
  hide(context?: HTMLElement | Document): void;
}

(function(){
  // Design tokens fallback (in case CSS variables missing in older browsers)
  // No-op here since styles.css defines variables; kept for future JS reads.

  // State persistence helpers (localStorage + URL hash)
  const state: StateManager = {
    get: function(key: string, def?: any): any {
      try { const v = localStorage.getItem('mtg:'+key); return v !== null ? JSON.parse(v) : def; } catch(e){ return def; }
    },
    set: function(key: string, val: any): void {
      try { localStorage.setItem('mtg:'+key, JSON.stringify(val)); } catch(e){}
    },
    inHash: function(obj: Record<string, any>): void {
      // Merge obj into location.hash as query-like params
      try {
        const params = new URLSearchParams((location.hash||'').replace(/^#/, ''));
        Object.keys(obj||{}).forEach(function(k: string){ params.set(k, obj[k]); });
        location.hash = params.toString();
      } catch(e){}
    },
    readHash: function(): URLSearchParams {
      try { return new URLSearchParams((location.hash||'').replace(/^#/, '')); } catch(e){ return new URLSearchParams(); }
    }
  };
  window.__mtgState = state;

  // Toast system
  let toastHost: HTMLElement | null = null;
  function ensureToastHost(): HTMLElement {
    if (!toastHost){
      toastHost = document.createElement('div');
      toastHost.className = 'toast-host';
      document.body.appendChild(toastHost);
    }
    return toastHost;
  }
  function toast(msg: string | HTMLElement, type?: string, opts?: ToastOptions): HTMLElement {
    ensureToastHost();
    const t = document.createElement('div');
    t.className = 'toast' + (type ? ' '+type : '');
    t.setAttribute('role','status');
    t.setAttribute('aria-live','polite');
    t.textContent = '';
    if (typeof msg === 'string') { t.textContent = msg; }
    else if (msg && msg.nodeType === 1) { t.appendChild(msg); }
    toastHost!.appendChild(t);
    const delay = (opts && opts.duration) || 2600;
    setTimeout(function(){ t.classList.add('hide'); setTimeout(function(){ t.remove(); }, 300); }, delay);
    return t;
  }
  window.toast = toast;
  function toastHTML(html: string, type?: string, opts?: ToastOptions): HTMLElement {
    const container = document.createElement('div');
    container.innerHTML = html;
    return toast(container, type, opts);
  }
  window.toastHTML = toastHTML;

  const telemetryEndpoint: string = (function(): string {
    if (typeof window.__telemetryEndpoint === 'string' && window.__telemetryEndpoint.trim()){
      return window.__telemetryEndpoint.trim();
    }
    return '/telemetry/events';
  })();
  const telemetry: TelemetryManager = {
    send: function(eventName: string, data?: Record<string, any>): void {
      if (!telemetryEndpoint || !eventName) return;
      let payload: string;
      try {
        payload = JSON.stringify({ event: eventName, data: data || {}, ts: Date.now() });
      } catch(_){ return; }
      try {
        if (navigator.sendBeacon){
          const blob = new Blob([payload], { type: 'application/json' });
          navigator.sendBeacon(telemetryEndpoint, blob);
        } else if (window.fetch){
          fetch(telemetryEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: payload,
            keepalive: true,
          }).catch(function(){ /* noop */ });
        }
      } catch(_){ }
    }
  };
  window.appTelemetry = telemetry;

  // Global HTMX error handling => toast
  document.addEventListener('htmx:responseError', function(e){
    const detail = e.detail || {} as any;
    const xhr = detail.xhr || {} as any;
    const rid = (xhr.getResponseHeader && xhr.getResponseHeader('X-Request-ID')) || '';
    const payload = (function(){ try { return JSON.parse(xhr.responseText || '{}'); } catch(_){ return {}; } })() as any;
    const status = payload.status || xhr.status || '';
    const msg = payload.detail || payload.message || 'Action failed';
    const path = payload.path || (e && e.detail && e.detail.path) || '';
    const html = ''+
      '<div style="display:flex; align-items:center; gap:.5rem">'+
      '<span style="font-weight:600">'+String(msg)+'</span>'+ (status? ' <span class="muted">('+status+')</span>' : '')+
      (rid ? '<button class="btn small" style="margin-left:auto" type="button" data-copy-error>Copy details</button>' : '')+
      '</div>'+
      (rid ? '<div class="muted" style="font-size:11px; margin-top:2px">Request-ID: <code>'+rid+'</code></div>' : '');
    const t = toastHTML(html, 'error', { duration: 7000 });
    // Wire Copy
    const btn = t.querySelector('[data-copy-error]') as HTMLButtonElement;
    if (btn){
      btn.addEventListener('click', function(){
        const lines = [
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
      const target = e && e.target as HTMLElement;
      const surface = (target && target.closest && target.closest('[data-error-surface]')) || document.querySelector('[data-error-surface]');
      if (surface){
        const banner = document.createElement('div');
        banner.className = 'inline-error-banner';
        banner.innerHTML = '<strong>'+String(msg)+'</strong>' + (rid? ' <span class="muted">(Request-ID: '+rid+')</span>' : '');
        surface.prepend(banner);
        setTimeout(function(){ banner.remove(); }, 8000);
      }
    } catch(_){ }
  });
  document.addEventListener('htmx:sendError', function(){ toast('Network error', 'error', { duration: 4000 }); });

  // Keyboard shortcuts
  const keymap: Record<string, () => void> = {
    ' ': function(){ const el = document.querySelector('[data-action="continue"], .btn-continue') as HTMLElement; if (el) el.click(); },
    'r': function(){ const el = document.querySelector('[data-action="rerun"], .btn-rerun') as HTMLElement; if (el) el.click(); },
    'b': function(){ const el = document.querySelector('[data-action="back"], .btn-back') as HTMLElement; if (el) el.click(); },
    'l': function(){ const el = document.querySelector('[data-action="toggle-logs"], .btn-logs') as HTMLElement; if (el) el.click(); },
  };
  document.addEventListener('keydown', function(e){
    const target = e.target as HTMLElement;
    if (target && (/input|textarea|select/i).test(target.tagName)) return; // don't hijack inputs
    const k = e.key.toLowerCase();
    // If focus is inside a card tile, defer 'r'/'l' to tile-scoped handlers (Alternatives/Lock)
    try {
      const active = document.activeElement as HTMLElement;
      if (active && active.closest && active.closest('.card-tile') && (k === 'r' || k === 'l')) {
        return;
      }
    } catch(_) { /* noop */ }
    if (keymap[k]){ e.preventDefault(); keymap[k](); }
  });

  // Focus ring visibility for keyboard nav
  function addFocusVisible(){
    let hadKeyboardEvent = false;
    function onKeyDown(){ hadKeyboardEvent = true; }
    function onPointer(){ hadKeyboardEvent = false; }
    function onFocus(e: FocusEvent){ if (hadKeyboardEvent) (e.target as HTMLElement).classList.add('focus-visible'); }
    function onBlur(e: FocusEvent){ (e.target as HTMLElement).classList.remove('focus-visible'); }
    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('mousedown', onPointer, true);
    window.addEventListener('pointerdown', onPointer, true);
    window.addEventListener('touchstart', onPointer, true);
    document.addEventListener('focusin', onFocus);
    document.addEventListener('focusout', onBlur);
  }
  addFocusVisible();

  // Skeleton utility: defer placeholders until the request lasts long enough to be noticeable
  let SKELETON_DELAY_DEFAULT = 400;
  let skeletonTimers = new WeakMap();
  function gatherSkeletons(root){
    if (!root){ return []; }
    let list = [];
    let scope = (root.nodeType === 9) ? root.documentElement : root;
    if (scope && scope.matches && scope.hasAttribute('data-skeleton')){
      list.push(scope);
    }
    if (scope && scope.querySelectorAll){
      scope.querySelectorAll('[data-skeleton]').forEach(function(el){
        if (list.indexOf(el) === -1){ list.push(el); }
      });
    }
    return list;
  }
  function scheduleSkeleton(el){
    let delayAttr = parseInt(el.getAttribute('data-skeleton-delay') || '', 10);
    let delay = isNaN(delayAttr) ? SKELETON_DELAY_DEFAULT : Math.max(0, delayAttr);
    clearSkeleton(el, false);
    const timer = setTimeout(function(){
      el.classList.add('is-loading');
      el.setAttribute('aria-busy', 'true');
      skeletonTimers.set(el, null);
    }, delay);
    skeletonTimers.set(el, timer);
  }
  function clearSkeleton(el: HTMLElement, removeBusy?: boolean): void {
    let timer = skeletonTimers.get(el);
    if (typeof timer === 'number'){
      clearTimeout(timer);
    }
    skeletonTimers.delete(el);
    el.classList.remove('is-loading');
    if (removeBusy !== false){ el.removeAttribute('aria-busy'); }
  }
  function showSkeletons(context?: HTMLElement | Document): void {
    gatherSkeletons(context || document).forEach(function(el){ scheduleSkeleton(el); });
  }
  function hideSkeletons(context?: HTMLElement | Document): void {
    gatherSkeletons(context || document).forEach(function(el){ clearSkeleton(el, true); });
  }
  window.skeletons = { show: showSkeletons, hide: hideSkeletons };

  document.addEventListener('htmx:beforeRequest', function(e){
    const detail = e.detail as any;
    const target = detail.target || detail.elt || e.target;
    showSkeletons(target);
  });
  document.addEventListener('htmx:afterSwap', function(e){
    const detail = e.detail as any;
    const target = detail.target || detail.elt || e.target;
    hideSkeletons(target);
  });
  document.addEventListener('htmx:afterRequest', function(e){
    const detail = e.detail as any;
    const target = detail.target || detail.elt || e.target;
    hideSkeletons(target);
  });

  // Commander catalog image lazy loader
  (function(){
    let PLACEHOLDER_PIXEL = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';
    let observer = null;
    let supportsIO = 'IntersectionObserver' in window;

    function ensureObserver(){
      if (observer || !supportsIO) return observer;
      observer = new IntersectionObserver(function(entries){
        entries.forEach(function(entry){
          if (entry.isIntersecting || entry.intersectionRatio > 0){
            let img = entry.target;
            load(img);
            if (observer) observer.unobserve(img);
          }
        });
      }, { rootMargin: '160px 0px', threshold: 0.05 });
      return observer;
    }

    function load(img){
      if (!img || img.__lazyLoaded) return;
      let src = img.getAttribute('data-lazy-src');
      if (src){ img.setAttribute('src', src); }
      let srcset = img.getAttribute('data-lazy-srcset');
      if (srcset){ img.setAttribute('srcset', srcset); }
      let sizes = img.getAttribute('data-lazy-sizes');
      if (sizes){ img.setAttribute('sizes', sizes); }
      img.classList.remove('is-placeholder');
      img.removeAttribute('data-lazy-image');
      img.removeAttribute('data-lazy-src');
      img.removeAttribute('data-lazy-srcset');
      img.removeAttribute('data-lazy-sizes');
      img.__lazyLoaded = true;
    }

    function prime(img){
      if (!img || img.__lazyPrimed) return;
      let desired = img.getAttribute('data-lazy-src');
      if (!desired) return;
      img.__lazyPrimed = true;
      let placeholder = img.getAttribute('data-lazy-placeholder') || PLACEHOLDER_PIXEL;
      img.setAttribute('loading', 'lazy');
      img.setAttribute('decoding', 'async');
      img.classList.add('is-placeholder');
      img.removeAttribute('srcset');
      img.removeAttribute('sizes');
      img.setAttribute('src', placeholder);
      if (supportsIO){
        ensureObserver().observe(img);
      } else {
        const loader = window.requestIdleCallback || window.requestAnimationFrame || function(cb){ return setTimeout(cb, 0); };
        loader(function(){ load(img); });
      }
    }

    function collect(scope){
      if (!scope) scope = document;
      if (scope === document){
        return Array.prototype.slice.call(document.querySelectorAll('[data-lazy-image]'));
      }
      if (scope.matches && scope.hasAttribute && scope.hasAttribute('data-lazy-image')){
        return [scope];
      }
      if (scope.querySelectorAll){
        return Array.prototype.slice.call(scope.querySelectorAll('[data-lazy-image]'));
      }
      return [];
    }

    function process(scope){
      collect(scope).forEach(function(img){
        if (img.__lazyLoaded) return;
        prime(img);
      });
    }

    if (document.readyState === 'loading'){
      document.addEventListener('DOMContentLoaded', function(){ process(document); });
    } else {
      process(document);
    }

    document.addEventListener('htmx:afterSwap', function(evt){
      let target = evt && evt.detail ? evt.detail.target : null;
      process(target || document);
    });
  })();

  const htmxCache = (function(){
    let store = new Map();
    function ttlFor(elt){
      let raw = parseInt((elt && elt.getAttribute && elt.getAttribute('data-hx-cache-ttl')) || '', 10);
      if (isNaN(raw) || raw <= 0){ return 30000; }
      return Math.max(1000, raw);
    }
    function buildKey(detail, elt){
      if (!detail) detail = {};
      if (elt && elt.getAttribute){
        let explicit = elt.getAttribute('data-hx-cache-key');
        if (explicit && explicit.trim()){ return explicit.trim(); }
      }
      let verb = (detail.verb || 'GET').toUpperCase();
      let path = detail.path || '';
      let params = detail.parameters && Object.keys(detail.parameters).length ? JSON.stringify(detail.parameters) : '';
      return verb + ' ' + path + ' ' + params;
    }
    function set(key, html, ttl, meta){
      if (!key || typeof html !== 'string') return;
      store.set(key, {
        key: key,
        html: html,
        expires: Date.now() + (ttl || 30000),
        meta: meta || {},
      });
    }
    function get(key){
      if (!key) return null;
      let entry = store.get(key);
      if (!entry) return null;
      if (entry.expires && entry.expires <= Date.now()){
        store.delete(key);
        return null;
      }
      return entry;
    }
    function applyCached(elt, detail, entry){
      if (!entry) return;
      let target = detail && detail.target ? detail.target : elt;
      if (!target) return;
      dispatchHtmx(target, 'htmx:beforeSwap', { elt: elt, target: target, cache: true, cacheKey: entry.key });
      let swapSpec = '';
      try { swapSpec = (elt && elt.getAttribute && elt.getAttribute('hx-swap')) || ''; } catch(_){ }
      swapSpec = (swapSpec || 'innerHTML').toLowerCase();
      if (swapSpec.indexOf('outer') === 0){
        if (target.outerHTML !== undefined){
          target.outerHTML = entry.html;
        }
      } else if (target.innerHTML !== undefined){
        target.innerHTML = entry.html;
      }
      if (window.htmx && typeof window.htmx.process === 'function'){
        window.htmx.process(target);
      }
      dispatchHtmx(target, 'htmx:afterSwap', { elt: elt, target: target, cache: true, cacheKey: entry.key });
      dispatchHtmx(target, 'htmx:afterRequest', { elt: elt, target: target, cache: true, cacheKey: entry.key });
    }
    function prefetch(url, opts){
      if (!url) return;
      opts = opts || {};
      let key = opts.key || ('GET ' + url);
      if (get(key)) return;
      try {
        fetch(url, {
          headers: { 'HX-Request': 'true', 'Accept': 'text/html' },
          cache: 'no-store',
        }).then(function(resp){
          if (!resp.ok) throw new Error('prefetch failed');
          return resp.text();
        }).then(function(html){
          set(key, html, opts.ttl || opts.cacheTtl || 30000, { url: url, prefetch: true });
          telemetry.send('htmx.cache.prefetch', { key: key, url: url });
        }).catch(function(){ /* noop */ });
      } catch(_){ }
    }
    return {
      set: set,
      get: get,
      apply: applyCached,
      buildKey: buildKey,
      ttlFor: ttlFor,
      prefetch: prefetch,
    };
  })();
  window.htmxCache = htmxCache;

  document.addEventListener('htmx:configRequest', function(e: any){
    const detail = e && e.detail ? e.detail : {} as any;
    const elt = detail.elt as HTMLElement;
    if (!elt || !elt.getAttribute || !elt.hasAttribute('data-hx-cache')) return;
    const verb = (detail.verb || 'GET').toUpperCase();
    if (verb !== 'GET') return;
    const key = htmxCache.buildKey(detail, elt);
    elt.__hxCacheKey = key;
    elt.__hxCacheTTL = htmxCache.ttlFor(elt);
    detail.headers = detail.headers || {};
    try { detail.headers['X-HTMX-Cache-Key'] = key; } catch(_){ }
  });

  document.addEventListener('htmx:beforeRequest', function(e: any){
    const detail = e && e.detail ? e.detail : {} as any;
    const elt = detail.elt as HTMLElement;
    if (!elt || !elt.__hxCacheKey) return;
    const entry = htmxCache.get(elt.__hxCacheKey);
    if (entry){
      telemetry.send('htmx.cache.hit', { key: elt.__hxCacheKey, path: detail.path || '' });
      e.preventDefault();
      htmxCache.apply(elt, detail, entry);
    } else {
      telemetry.send('htmx.cache.miss', { key: elt.__hxCacheKey, path: detail.path || '' });
    }
  });

  document.addEventListener('htmx:afterSwap', function(e: any){
    const detail = e && e.detail ? e.detail : {} as any;
    const elt = detail.elt as HTMLElement;
    if (!elt || !elt.__hxCacheKey) return;
    try {
      const xhr = detail.xhr;
      const status = xhr && xhr.status ? xhr.status : 0;
      if (status >= 200 && status < 300 && xhr && typeof xhr.responseText === 'string'){
        const ttl = elt.__hxCacheTTL || 30000;
        htmxCache.set(elt.__hxCacheKey, xhr.responseText, ttl, { path: detail.path || '' });
        telemetry.send('htmx.cache.store', { key: elt.__hxCacheKey, path: detail.path || '', ttl: ttl });
      }
    } catch(_){ }
    elt.__hxCacheKey = undefined;
    elt.__hxCacheTTL = undefined;
  });

  (function(){
    function handlePrefetch(evt: Event){
      try {
        const el = (evt.target as HTMLElement)?.closest ? (evt.target as HTMLElement).closest('[data-hx-prefetch]') : null;
        if (!el || el.__hxPrefetched) return;
        let url = el.getAttribute('data-hx-prefetch');
        if (!url) return;
        el.__hxPrefetched = true;
        let key = el.getAttribute('data-hx-cache-key') || el.getAttribute('data-hx-prefetch-key') || ('GET ' + url);
        let ttlAttr = parseInt((el.getAttribute('data-hx-cache-ttl') || el.getAttribute('data-hx-prefetch-ttl') || ''), 10);
        let ttl = isNaN(ttlAttr) ? 30000 : Math.max(1000, ttlAttr);
        htmxCache.prefetch(url, { key: key, ttl: ttl });
      } catch(_){ }
    }
    document.addEventListener('pointerenter', handlePrefetch, true);
    document.addEventListener('focusin', handlePrefetch, true);
  })();

  // Centralized HTMX debounce helper (applies to inputs tagged with data-hx-debounce)
  let hxDebounceGroups = new Map();
  function dispatchHtmx(el, evtName, detail){
    if (!el) return;
    if (window.htmx && typeof window.htmx.trigger === 'function'){
      window.htmx.trigger(el, evtName, detail);
    } else {
      try { el.dispatchEvent(new CustomEvent(evtName, { bubbles: true, detail: detail })); } catch(_){ }
    }
  }
  function bindHtmxDebounce(el){
    if (!el || el.__hxDebounceBound) return;
    el.__hxDebounceBound = true;
    let delayRaw = parseInt(el.getAttribute('data-hx-debounce') || '', 10);
    let delay = isNaN(delayRaw) ? 250 : Math.max(0, delayRaw);
    let eventsAttr = el.getAttribute('data-hx-debounce-events') || 'input';
    let events = eventsAttr.split(',').map(function(v){ return v.trim(); }).filter(Boolean);
    if (!events.length){ events = ['input']; }
    let trigger = el.getAttribute('data-hx-debounce-trigger') || 'debouncedinput';
    let group = el.getAttribute('data-hx-debounce-group') || '';
    let flushAttr = (el.getAttribute('data-hx-debounce-flush') || '').toLowerCase();
    let flushOnBlur = (flushAttr === 'blur') || (flushAttr === '1') || (flushAttr === 'true');
    function clearTimer(){
      if (el.__hxDebounceTimer){
        clearTimeout(el.__hxDebounceTimer);
        el.__hxDebounceTimer = null;
      }
    }
    function schedule(){
      clearTimer();
      if (group){
        let prev = hxDebounceGroups.get(group);
        if (prev && prev !== el && prev.__hxDebounceTimer){
          clearTimeout(prev.__hxDebounceTimer);
          prev.__hxDebounceTimer = null;
        }
        hxDebounceGroups.set(group, el);
      }
      el.__hxDebounceTimer = setTimeout(function(){
        el.__hxDebounceTimer = null;
        dispatchHtmx(el, trigger, {});
      }, delay);
    }
    events.forEach(function(evt){
      el.addEventListener(evt, schedule, { passive: true });
    });
    if (flushOnBlur){
      el.addEventListener('blur', function(){
        if (el.__hxDebounceTimer){
          clearTimer();
          dispatchHtmx(el, trigger, {});
        }
      });
    }
    el.addEventListener('htmx:beforeRequest', clearTimer);
  }
  function initHtmxDebounce(root){
    let scope = root || document;
    if (scope === document){ scope = document.body || document; }
    if (!scope) return;
    let seen = new Set();
    function collect(candidate){
      if (!candidate || seen.has(candidate)) return;
      seen.add(candidate);
      bindHtmxDebounce(candidate);
    }
    if (scope.matches && scope.hasAttribute && scope.hasAttribute('data-hx-debounce')){
      collect(scope);
    }
    if (scope.querySelectorAll){
      scope.querySelectorAll('[data-hx-debounce]').forEach(collect);
    }
  }
  window.initHtmxDebounce = () => initHtmxDebounce(document.body);

  // Example: persist "show skipped" toggle if present
  document.addEventListener('change', function(e){
    const el = e.target as HTMLInputElement;
    if (el && el.matches('[data-pref]')){
      let key = el.getAttribute('data-pref');
      let val = (el.type === 'checkbox') ? !!el.checked : el.value;
      state.set(key, val);
      state.inHash((function(o){ o[key] = val; return o; })({}));
    }
  });
  // On load, initialize any data-pref elements
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('[data-pref]').forEach(function(el){
      let key = el.getAttribute('data-pref');
      let saved = state.get(key, undefined);
      if (typeof saved !== 'undefined'){
        if ((el as HTMLInputElement).type === 'checkbox') (el as HTMLInputElement).checked = !!saved; else (el as HTMLInputElement).value = saved;
      }
    });
    hydrateProgress(document);
    syncShowSkipped(document);
    initCardFilters(document);
    initVirtualization(document);
    initHtmxDebounce(document);
    initMustHaveControls(document);
  });

  // Hydrate progress bars with width based on data-pct
  function hydrateProgress(root){
    (root || document).querySelectorAll('.progress[data-pct]')
      .forEach(function(p){
        let pct = parseInt(p.getAttribute('data-pct') || '0', 10);
        if (isNaN(pct) || pct < 0) pct = 0; if (pct > 100) pct = 100;
        let bar = p.querySelector('.bar'); if (!bar) return;
        // Animate width for a bit of delight
        requestAnimationFrame(function(){ bar.style.width = pct + '%'; });
      });
  }
  // Keep hidden inputs for show_skipped in sync with the sticky checkbox
  function syncShowSkipped(root){
    let cb = (root || document).querySelector('input[name="__toggle_show_skipped"][data-pref]');
    if (!cb) return;
    let val = cb.checked ? '1' : '0';
    (root || document).querySelectorAll('section form').forEach(function(f){
      let h = f.querySelector('input[name="show_skipped"]');
      if (h) h.value = val;
    });
  }
  document.addEventListener('htmx:afterSwap', function(e){
    hydrateProgress(e.target as HTMLElement);
    syncShowSkipped(e.target as HTMLElement);
    initCardFilters(e.target as HTMLElement);
    initVirtualization(e.target as HTMLElement);
    initHtmxDebounce(e.target as HTMLElement);
    initMustHaveControls(e.target as HTMLElement);
  });

  // Scroll a card-tile into view (cooperates with virtualization by re-rendering first)
  function scrollCardIntoView(name){
    if (!name) return;
    try{
      let section = document.querySelector('section');
      let grid = section && section.querySelector('.card-grid');
      if (!grid) return;
      // If virtualized, force a render around the approximate match by searching stored children
      let target = grid.querySelector('.card-tile[data-card-name="'+CSS.escape(name)+'"]');
      if (!target) {
        // Trigger a render update and try again
        grid.dispatchEvent(new Event('scroll')); // noop but can refresh
        target = grid.querySelector('.card-tile[data-card-name="'+CSS.escape(name)+'"]');
      }
      if (target) {
        target.scrollIntoView({ block: 'center', behavior: 'smooth' });
        (target as HTMLElement).focus && (target as HTMLElement).focus();
      }
    }catch(_){}
  }
  window.scrollCardIntoView = scrollCardIntoView;

  // --- Card grid filters, reasons, and collapsible groups ---
  function initCardFilters(root){
    let section = (root || document).querySelector('section');
    if (!section) return;
    let toolbar = section.querySelector('.cards-toolbar');
    if (!toolbar) return; // nothing to do
    let q = toolbar.querySelector('input[name="filter_query"]');
    let ownedSel = toolbar.querySelector('select[name="filter_owned"]');
    let showReasons = toolbar.querySelector('input[name="show_reasons"]');
    let collapseGroups = toolbar.querySelector('input[name="collapse_groups"]');
    let resultsEl = toolbar.querySelector('[data-results]');
  let emptyEl = section.querySelector('[data-empty]');
  let sortSel = toolbar.querySelector('select[name="filter_sort"]');
  let chipOwned = toolbar.querySelector('[data-chip-owned="owned"]');
  let chipNot = toolbar.querySelector('[data-chip-owned="not"]');
  let chipAll = toolbar.querySelector('[data-chip-owned="all"]');
  let chipClear = toolbar.querySelector('[data-chip-clear]');

    function getVal(el){ return el ? (el.type === 'checkbox' ? !!el.checked : (el.value||'')) : ''; }
    // Read URL hash on first init to hydrate controls
    try {
      let params = window.__mtgState.readHash();
      if (params){
        let hv = params.get('q'); if (q && hv !== null) q.value = hv;
        hv = params.get('owned'); if (ownedSel && hv) ownedSel.value = hv;
        hv = params.get('showreasons'); if (showReasons && hv !== null) showReasons.checked = (hv === '1');
        hv = params.get('collapse'); if (collapseGroups && hv !== null) collapseGroups.checked = (hv === '1');
        hv = params.get('sort'); if (sortSel && hv) sortSel.value = hv;
      }
    } catch(_){}
    function apply(){
      let query = (getVal(q)+ '').toLowerCase().trim();
      let ownedMode = (getVal(ownedSel) || 'all');
      let showR = !!getVal(showReasons);
      let collapse = !!getVal(collapseGroups);
      let sortMode = (getVal(sortSel) || 'az');
      // Toggle reasons visibility via section class
      section.classList.toggle('hide-reasons', !showR);
      // Collapse or expand all groups if toggle exists; when not collapsed, restore per-group stored state
      section.querySelectorAll('.group').forEach(function(wrapper){
        let grid = wrapper.querySelector('.group-grid'); if (!grid) return;
        let key = wrapper.getAttribute('data-group-key');
        if (collapse){
          grid.setAttribute('data-collapsed','1');
        } else {
          // restore stored
          if (key){
            let stored = state.get('cards:group:'+key, null);
            if (stored === true){ grid.setAttribute('data-collapsed','1'); }
            else { grid.removeAttribute('data-collapsed'); }
          } else {
            grid.removeAttribute('data-collapsed');
          }
        }
      });
      // Filter tiles
  let tiles = section.querySelectorAll('.card-grid .card-tile');
      let visible = 0;
      tiles.forEach(function(tile){
        let name = (tile.getAttribute('data-card-name')||'').toLowerCase();
        let role = (tile.getAttribute('data-role')||'').toLowerCase();
  let tags = (tile.getAttribute('data-tags')||'').toLowerCase();
  let tagsSlug = (tile.getAttribute('data-tags-slug')||'').toLowerCase();
        let owned = tile.getAttribute('data-owned') === '1';
  let text = name + ' ' + role + ' ' + tags + ' ' + tagsSlug;
        let qOk = !query || text.indexOf(query) !== -1;
        let oOk = (ownedMode === 'all') || (ownedMode === 'owned' && owned) || (ownedMode === 'not' && !owned);
        let show = qOk && oOk;
        tile.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      // Sort within each grid
      function keyFor(tile){
        let name = (tile.getAttribute('data-card-name')||'');
        let owned = tile.getAttribute('data-owned') === '1' ? 1 : 0;
        let gc = tile.classList.contains('game-changer') ? 1 : 0;
        return { name: name.toLowerCase(), owned: owned, gc: gc };
      }
      section.querySelectorAll('.card-grid').forEach(function(grid){
  const arr = Array.prototype.slice.call(grid.querySelectorAll('.card-tile'));
        arr.sort(function(a,b){
          let ka = keyFor(a), kb = keyFor(b);
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
        let grid = wrapper.querySelector('.group-grid');
        let count = 0;
        if (grid){
          grid.querySelectorAll('.card-tile').forEach(function(t){ if (t.style.display !== 'none') count++; });
        }
        let cEl = wrapper.querySelector('[data-count]');
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
        let wrapper = btn.closest('.group');
        let grid = wrapper && wrapper.querySelector('.group-grid');
        if (!grid) return;
  let key = wrapper.getAttribute('data-group-key');
        let willCollapse = !grid.getAttribute('data-collapsed');
        if (willCollapse) grid.setAttribute('data-collapsed','1'); else grid.removeAttribute('data-collapsed');
        if (key){ state.set('cards:group:'+key, !!willCollapse); }
  // ARIA
  btn.setAttribute('aria-expanded', willCollapse ? 'false' : 'true');
      });
    });
    // Per-card reason toggle: delegate clicks on .btn-why
    section.addEventListener('click', function(e){
      let t = e.target;
      if (!t || !t.classList || !t.classList.contains('btn-why')) return;
      e.preventDefault();
      let tile = t.closest('.card-tile');
      if (!tile) return;
      let globalHidden = section.classList.contains('hide-reasons');
      if (globalHidden){
        // Force-show overrides global hidden
        let on = tile.classList.toggle('force-show');
        if (on) tile.classList.remove('force-hide');
        t.textContent = on ? 'Hide why' : 'Why?';
      } else {
        // Hide this tile only
        let off = tile.classList.toggle('force-hide');
        if (off) tile.classList.remove('force-show');
        t.textContent = off ? 'Show why' : 'Hide why';
      }
    });
    // Initial apply on hydrate
    apply();

    // Keyboard helpers: '/' focuses query, Esc clears
    function onKey(e){
      // avoid when typing in inputs
      if (e.target && (/input|textarea|select/i).test((e.target as HTMLElement).tagName)) return;
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
      let body = document.body || document.documentElement;
      const DIAG = !!(body && body.getAttribute('data-diag') === '1');
      const GLOBAL = (function(){
        if (!DIAG) return null;
        if (window.__virtGlobal) return window.__virtGlobal;
        let store = { grids: [], summaryEl: null };
        function ensure(){
          if (!store.summaryEl){
            let el = document.createElement('div');
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
            el.style.display = 'none';
            document.body.appendChild(el);
            store.summaryEl = el;
          }
          return store.summaryEl;
        }
        function update(){
          let el = ensure(); if (!el) return;
          let g = store.grids;
          let total = 0, visible = 0, lastMs = 0;
          for (let i=0;i<g.length;i++){
            total += g[i].total||0;
            visible += (g[i].end||0) - (g[i].start||0);
            lastMs = Math.max(lastMs, g[i].lastMs||0);
          }
          el.textContent = 'virt sum: grids '+g.length+' • visible '+visible+'/'+total+' • last '+(lastMs.toFixed ? lastMs.toFixed(1) : String(lastMs))+'ms';
        }
        function register(gridId, ref){
          store.grids.push({ id: gridId, ref: ref });
          update();
          return {
            set: function(stats){
              for (let i=0;i<store.grids.length;i++){
                if (store.grids[i].id === gridId){
                  store.grids[i] = Object.assign({ id: gridId, ref: ref }, stats);
                  break;
                }
              }
              update();
            },
            toggle: function(){
              const el = ensure();
              el.style.display = ((el as HTMLElement).style.display === 'none' ? '' : 'none');
            }
          };
        }
        window.__virtGlobal = {
          register: register,
          toggle: function(){
            let el = ensure();
            el.style.display = (el.style.display === 'none' ? '' : 'none');
          }
        };
        return window.__virtGlobal;
      })();

      let scope = root || document;
      if (!scope || !scope.querySelectorAll) return;
      let grids = scope.querySelectorAll('[data-virtualize]');
      if (!grids.length) return;

      grids.forEach(function(grid){
        if (!grid || grid.__virtBound) return;
        let attrVal = (grid.getAttribute('data-virtualize') || '').trim();
        if (!attrVal || /^0|false$/i.test(attrVal)) return;

        let container = grid;
        container.style.position = container.style.position || 'relative';

        let mode = attrVal.toLowerCase();
        let minItemsAttr = parseInt(grid.getAttribute('data-virtualize-min') || (grid.dataset ? grid.dataset.virtualizeMin : ''), 10);
        let rowAttr = parseInt(grid.getAttribute('data-virtualize-row') || (grid.dataset ? grid.dataset.virtualizeRow : ''), 10);
        let colAttr = parseInt(grid.getAttribute('data-virtualize-columns') || (grid.dataset ? grid.dataset.virtualizeColumns : ''), 10);
        let maxHeightAttr = grid.getAttribute('data-virtualize-max-height') || (grid.dataset ? grid.dataset.virtualizeMaxHeight : '');
        let overflowAttr = grid.getAttribute('data-virtualize-overflow') || (grid.dataset ? grid.dataset.virtualizeOverflow : '');

        let source = container;
        let ownedGrid = container.id === 'owned-box' ? container.querySelector('#owned-grid') : null;
        if (ownedGrid) { source = ownedGrid; }
        if (!source || !source.children || !source.children.length) return;

        let all = Array.prototype.slice.call(source.children);
        all.forEach(function(node, idx){ try{ node.__virtIndex = idx; }catch(_){ } });
        let minItems = !isNaN(minItemsAttr) ? Math.max(0, minItemsAttr) : 80;
        if (all.length < minItems) return;

        grid.__virtBound = true;

        let store = document.createElement('div');
        store.style.display = 'none';
        all.forEach(function(node){ store.appendChild(node); });

        let padTop = document.createElement('div');
        let padBottom = document.createElement('div');
        padTop.style.height = '0px';
        padBottom.style.height = '0px';

        let wrapper = document.createElement('div');
        wrapper.className = 'virt-wrapper';

        if (ownedGrid){
          ownedGrid.innerHTML = '';
          ownedGrid.appendChild(padTop);
          ownedGrid.appendChild(wrapper);
          ownedGrid.appendChild(padBottom);
          ownedGrid.appendChild(store);
        } else {
          container.appendChild(padTop);
          container.appendChild(wrapper);
          container.appendChild(padBottom);
          container.appendChild(store);
        }

        if (maxHeightAttr){
          container.style.maxHeight = maxHeightAttr;
        } else if (!container.style.maxHeight){
          container.style.maxHeight = '70vh';
        }
        if (overflowAttr){
          container.style.overflow = overflowAttr;
        } else if (!container.style.overflow){
          container.style.overflow = 'auto';
        }

        let baseRow = container.id === 'owned-box' ? 160 : (mode.indexOf('list') > -1 ? 110 : 240);
        let minRowH = !isNaN(rowAttr) && rowAttr > 0 ? rowAttr : baseRow;
        let rowH = minRowH;
        let explicitCols = (!isNaN(colAttr) && colAttr > 0) ? colAttr : null;
        let perRow = explicitCols || 1;

        let diagBox = null; let lastRenderAt = 0; let lastRenderMs = 0;
        let renderCount = 0; let measureCount = 0; let swapCount = 0;
        let gridId = (container.id || container.className || 'grid') + '#' + Math.floor(Math.random()*1e6);
        let globalReg = DIAG && GLOBAL ? GLOBAL.register(gridId, container) : null;

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
          diagBox.style.display = 'none';
          let controls = document.createElement('div');
          controls.style.display = 'flex';
          controls.style.gap = '.35rem';
          controls.style.alignItems = 'center';
          controls.style.marginBottom = '.25rem';
          let title = document.createElement('div'); title.textContent = 'virt diag'; title.style.fontWeight = '600'; title.style.fontSize = '11px'; title.style.color = '#9ca3af';
          let btnCopy = document.createElement('button'); btnCopy.type = 'button'; btnCopy.textContent = 'Copy'; btnCopy.className = 'btn small';
          btnCopy.addEventListener('click', function(){
            try{
              let payload = {
                id: gridId,
                rowH: rowH,
                perRow: perRow,
                start: start,
                end: end,
                total: total,
                renderCount: renderCount,
                measureCount: measureCount,
                swapCount: swapCount,
                lastRenderMs: lastRenderMs,
                lastRenderAt: lastRenderAt,
              };
              navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
              btnCopy.textContent = 'Copied';
              setTimeout(function(){ btnCopy.textContent = 'Copy'; }, 1200);
            }catch(_){ }
          });
          let btnHide = document.createElement('button'); btnHide.type = 'button'; btnHide.textContent = 'Hide'; btnHide.className = 'btn small';
          btnHide.addEventListener('click', function(){ diagBox.style.display = 'none'; });
          controls.appendChild(title);
          controls.appendChild(btnCopy);
          controls.appendChild(btnHide);
          diagBox.appendChild(controls);
          let text = document.createElement('div'); text.className = 'virt-diag-text'; diagBox.appendChild(text);
          let host = (container.id === 'owned-box') ? container : container.parentElement || container;
          host.insertBefore(diagBox, host.firstChild);
          return diagBox;
        }

        function measure(){
          try {
            measureCount++;
            let probe = store.firstElementChild || all[0];
            if (probe){
              let fake = probe.cloneNode(true);
              fake.style.position = 'absolute';
              fake.style.visibility = 'hidden';
              fake.style.pointerEvents = 'none';
              (ownedGrid || container).appendChild(fake);
              let rect = fake.getBoundingClientRect();
              rowH = Math.max(minRowH, Math.ceil(rect.height) + 16);
              (ownedGrid || container).removeChild(fake);
            }
            let style = window.getComputedStyle(ownedGrid || container);
            let cols = style.getPropertyValue('grid-template-columns');
            try {
              let displayMode = style.getPropertyValue('display');
              if (displayMode && displayMode.trim()){
                wrapper.style.display = displayMode;
              } else if (!wrapper.style.display){
                wrapper.style.display = 'grid';
              }
              if (cols && cols.trim()) wrapper.style.gridTemplateColumns = cols;
              let gap = style.getPropertyValue('gap') || style.getPropertyValue('grid-gap');
              if (gap && gap.trim()) wrapper.style.gap = gap;
              let ji = style.getPropertyValue('justify-items');
              if (ji && ji.trim()) wrapper.style.justifyItems = ji;
              let ai = style.getPropertyValue('align-items');
              if (ai && ai.trim()) wrapper.style.alignItems = ai;
            } catch(_){ }
            const derivedCols = (cols && cols.split ? cols.split(' ').filter(function(x){
              return x && (x.indexOf('px')>-1 || x.indexOf('fr')>-1 || x.indexOf('minmax(')>-1);
            }).length : 0);
            if (explicitCols){
              perRow = explicitCols;
            } else if (derivedCols){
              perRow = Math.max(1, derivedCols);
            } else {
              perRow = Math.max(1, perRow);
            }
          } catch(_){ }
        }

        measure();
        let total = all.length;
        let start = 0, end = 0;

        function render(){
          let t0 = DIAG ? performance.now() : 0;
          let scroller = container;
          let vh, scrollTop, top;
          
          if (useWindowScroll) {
            // Window-scroll mode: measure relative to viewport
            vh = window.innerHeight;
            let rect = container.getBoundingClientRect();
            top = Math.max(0, -rect.top);
            scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
          } else {
            // Container-scroll mode: measure relative to container
            vh = scroller.clientHeight || window.innerHeight;
            scrollTop = scroller.scrollTop;
            top = scrollTop || (scroller.getBoundingClientRect().top < 0 ? -scroller.getBoundingClientRect().top : 0);
          }
          
          let rowsInView = Math.ceil(vh / Math.max(1, rowH)) + 2;
          let rowStart = Math.max(0, Math.floor(top / Math.max(1, rowH)) - 1);
          let rowEnd = Math.min(Math.ceil(top / Math.max(1, rowH)) + rowsInView, Math.ceil(total / Math.max(1, perRow)));
          let newStart = rowStart * Math.max(1, perRow);
          let newEnd = Math.min(total, rowEnd * Math.max(1, perRow));
          if (newStart === start && newEnd === end) return;
          start = newStart;
          end = newEnd;
          let beforeRows = Math.floor(start / Math.max(1, perRow));
          let afterRows = Math.ceil((total - end) / Math.max(1, perRow));
          padTop.style.height = (beforeRows * rowH) + 'px';
          padBottom.style.height = (afterRows * rowH) + 'px';
          wrapper.innerHTML = '';
          for (let i = start; i < end; i++){
            let node = all[i];
            if (node) wrapper.appendChild(node);
          }
          if (DIAG){
            let box = ensureDiag();
            if (box){
              let dt = performance.now() - t0;
              lastRenderMs = dt;
              renderCount++;
              lastRenderAt = Date.now();
              let vis = end - start;
              let rowsTotal = Math.ceil(total / Math.max(1, perRow));
              let textEl = box.querySelector('.virt-diag-text');
              let msg = 'range ['+start+'..'+end+') of '+total+' • vis '+vis+' • rows ~'+rowsTotal+' • perRow '+perRow+' • rowH '+rowH+'px • render '+fmt(dt)+'ms • renders '+renderCount+' • measures '+measureCount+' • swaps '+swapCount;
              textEl.textContent = msg;
              let bad = (dt > 33) || (vis > 300);
              let warn = (!bad) && ((dt > 16) || (vis > 200));
              box.style.borderColor = bad ? '#ef4444' : (warn ? '#f59e0b' : 'var(--border)');
              box.style.boxShadow = bad ? '0 0 0 1px rgba(239,68,68,.35)' : (warn ? '0 0 0 1px rgba(245,158,11,.25)' : 'none');
              if (globalReg && globalReg.set){
                globalReg.set({ total: total, start: start, end: end, lastMs: dt });
              }
            }
          }
        }

        function onScroll(){ render(); }
        function onResize(){ measure(); render(); }

        // Support both container-scroll (default) and window-scroll modes
        let scrollMode = overflowAttr || container.style.overflow || 'auto';
        let useWindowScroll = (scrollMode === 'visible' || scrollMode === 'window');
        
        if (useWindowScroll) {
          // Window-scroll mode: listen to window scroll events
          window.addEventListener('scroll', onScroll, { passive: true });
        } else {
          // Container-scroll mode: listen to container scroll events
          container.addEventListener('scroll', onScroll, { passive: true });
        }
        window.addEventListener('resize', onResize);

        render();

        // Track cleanup for disconnected containers
        grid.__virtCleanup = function(){
          try {
            if (useWindowScroll) {
              window.removeEventListener('scroll', onScroll);
            } else {
              container.removeEventListener('scroll', onScroll);
            }
            window.removeEventListener('resize', onResize);
          } catch(_){}
        };

        document.addEventListener('htmx:afterSwap', function(ev){
          if (!container.isConnected) return;
          if (!container.contains(ev.target)) return;
          swapCount++;
          let merged = Array.prototype.slice.call(store.children).concat(Array.prototype.slice.call(wrapper.children));
          const known = new Map();
          all.forEach(function(node, idx){
            let index = (typeof node.__virtIndex === 'number') ? node.__virtIndex : idx;
            known.set(node, index);
          });
          let nextIndex = known.size;
          merged.forEach(function(node){
            if (!known.has(node)){
              node.__virtIndex = nextIndex;
              known.set(node, nextIndex);
              nextIndex++;
            }
          });
          merged.sort(function(a, b){
            let ia = known.get(a);
            const ib = known.get(b);
            return (ia - ib);
          });
          merged.forEach(function(node, idx){ node.__virtIndex = idx; });
          all = merged;
          total = all.length;
          measure();
          render();
        });

        if (DIAG && !window.__virtHotkeyBound){
          window.__virtHotkeyBound = true;
          document.addEventListener('keydown', function(e){
            try{
              if (e.target && (/input|textarea|select/i).test((e.target as HTMLElement).tagName)) return;
              if (e.key && e.key.toLowerCase() === 'v'){
                e.preventDefault();
                let shown = null;
                document.querySelectorAll('.virt-diag').forEach(function(b){
                  if (shown === null) shown = ((b as HTMLElement).style.display === 'none');
                  (b as HTMLElement).style.display = shown ? '' : 'none';
                });
                if (GLOBAL && GLOBAL.toggle) GLOBAL.toggle();
              }
            }catch(_){ }
          });
        }
      });
    }catch(_){ }
  }

  function setTileState(tile, type, active){
    if (!tile) return;
    let attr = 'data-must-' + type;
    tile.setAttribute(attr, active ? '1' : '0');
    tile.classList.toggle('must-' + type, !!active);
    let selector = '.must-have-btn.' + (type === 'include' ? 'include' : 'exclude');
    try {
      let btn = tile.querySelector(selector);
      if (btn){
        btn.setAttribute('data-active', active ? '1' : '0');
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.classList.toggle('is-active', !!active);
      }
    } catch(_){ }
  }

  function restoreMustHaveState(tile, state){
    if (!tile || !state) return;
    setTileState(tile, 'include', state.include ? 1 : 0);
    setTileState(tile, 'exclude', state.exclude ? 1 : 0);
  }

  function applyLocalMustHave(tile, type, enabled){
    if (!tile) return;
    if (type === 'include'){
      setTileState(tile, 'include', enabled ? 1 : 0);
      if (enabled){ setTileState(tile, 'exclude', 0); }
    } else if (type === 'exclude'){
      setTileState(tile, 'exclude', enabled ? 1 : 0);
      if (enabled){ setTileState(tile, 'include', 0); }
    }
  }

  function sendMustHaveRequest(tile, type, enabled, cardName, prevState){
    if (!window.htmx){
      restoreMustHaveState(tile, prevState);
      tile.setAttribute('data-must-pending', '0');
      toast('Offline: cannot update preference', 'error', { duration: 4000 });
      return;
    }
    let summaryTarget = document.getElementById('include-exclude-summary');
    let ajaxOptions = {
      source: tile,
      target: summaryTarget || tile,
      swap: summaryTarget ? 'outerHTML' : 'none',
      values: {
        card_name: cardName,
        list_type: type,
        enabled: enabled ? '1' : '0',
      },
    };
    let xhr;
    try {
      xhr = window.htmx.ajax('POST', '/build/must-haves/toggle', ajaxOptions);
    } catch(_){
      restoreMustHaveState(tile, prevState);
      tile.setAttribute('data-must-pending', '0');
      toast('Unable to submit preference update', 'error', { duration: 4500 });
      telemetry.send('must_have.toggle_error', { card: cardName, list: type, status: 'exception' });
      return;
    }
    if (!xhr || !xhr.addEventListener){
      tile.setAttribute('data-must-pending', '0');
      return;
    }
    xhr.addEventListener('load', function(evt){
      tile.setAttribute('data-must-pending', '0');
      let request = evt && evt.currentTarget ? evt.currentTarget : xhr;
      let status = request.status || 0;
      if (status >= 400){
        restoreMustHaveState(tile, prevState);
        let msg = 'Failed to update preference';
        try {
          let data = JSON.parse(request.responseText || '{}');
          if (data && data.error) msg = data.error;
        } catch(_){ }
        toast(msg, 'error', { duration: 5000 });
        telemetry.send('must_have.toggle_error', { card: cardName, list: type, status: status });
        return;
      }
      let message;
      if (enabled){
        message = (type === 'include') ? 'Pinned as must include' : 'Pinned as must exclude';
      } else {
        message = (type === 'include') ? 'Removed must include' : 'Removed must exclude';
      }
      toast(message + ': ' + cardName, 'success', { duration: 2400 });
      telemetry.send('must_have.toggle', {
        card: cardName,
        list: type,
        enabled: enabled,
        requestId: request.getResponseHeader ? request.getResponseHeader('X-Request-ID') : null,
      });
    });
    xhr.addEventListener('error', function(){
      tile.setAttribute('data-must-pending', '0');
      restoreMustHaveState(tile, prevState);
      toast('Network error updating preference', 'error', { duration: 5000 });
      telemetry.send('must_have.toggle_error', { card: cardName, list: type, status: 'network' });
    });
  }

  function initMustHaveControls(root){
    let scope = root && root.querySelectorAll ? root : document;
    if (scope === document && document.body) scope = document.body;
    if (!scope || !scope.querySelectorAll) return;
    scope.querySelectorAll('.must-have-btn').forEach(function(btn){
      if (!btn || btn.__mustHaveBound) return;
      btn.__mustHaveBound = true;
      let active = btn.getAttribute('data-active') === '1';
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
      btn.addEventListener('click', function(ev){
        ev.preventDefault();
        let tile = btn.closest('.card-tile');
        if (!tile) return;
        if (tile.getAttribute('data-must-pending') === '1') return;
        let type = btn.getAttribute('data-toggle');
        if (!type) return;
        let prevState = {
          include: tile.getAttribute('data-must-include') === '1',
          exclude: tile.getAttribute('data-must-exclude') === '1',
        };
        let nextEnabled = !(type === 'include' ? prevState.include : prevState.exclude);
        let label = btn.getAttribute('data-card-label') || btn.getAttribute('data-card-name') || tile.getAttribute('data-card-name') || '';
        tile.setAttribute('data-must-pending', '1');
        applyLocalMustHave(tile, type, nextEnabled);
        sendMustHaveRequest(tile, type, nextEnabled, label, prevState);
      });
    });
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

  // --- Lazy-loading analytics accordions ---
  function initLazyAccordions(root){
    try {
      let scope = root || document;
      if (!scope || !scope.querySelectorAll) return;
      
      scope.querySelectorAll('.analytics-accordion[data-lazy-load]').forEach(function(details){
        if (!details || details.__lazyBound) return;
        details.__lazyBound = true;
        
        let loaded = false;
        
        details.addEventListener('toggle', function(){
          if (!details.open || loaded) return;
          loaded = true;
          
          // Mark as loaded to prevent re-initialization
          let content = details.querySelector('.analytics-content');
          if (!content) return;
          
          // Remove placeholder if present
          let placeholder = content.querySelector('.analytics-placeholder');
          if (placeholder) {
            placeholder.remove();
          }
          
          // Content is already rendered in the template, just need to initialize any scripts
          // Re-run virtualization if needed
          try {
            initVirtualization(content);
          } catch(_){}
          
          // Re-attach chart interactivity if this is mana overview
          let type = details.getAttribute('data-analytics-type');
          if (type === 'mana') {
            try {
              // Tooltip and highlight logic is already in the template scripts
              // Just trigger a synthetic event to re-attach if needed
              let event = new CustomEvent('analytics:loaded', { detail: { type: 'mana' } });
              details.dispatchEvent(event);
            } catch(_){}
          }
          
          // Send telemetry
          telemetry.send('analytics.accordion_expand', {
            type: type || 'unknown',
            accordion: details.id || 'unnamed',
          });
        });
      });
    } catch(_){}
  }

  // Initialize on load and after HTMX swaps
  document.addEventListener('DOMContentLoaded', function(){ initLazyAccordions(document.body); });
  document.addEventListener('htmx:afterSwap', function(e){ initLazyAccordions(e.target); });

  // =============================================================================
  // UTILITIES EXTRACTED FROM BASE.HTML INLINE SCRIPTS (Phase 3)
  // =============================================================================

  /**
   * Poll setup status endpoint for progress updates
   * Shows dynamic status message in #banner-status element
   */
  function initSetupStatusPoller(): void {
    let statusEl: HTMLElement | null = null;

    function ensureStatusEl(): HTMLElement | null {
      if (!statusEl) statusEl = document.getElementById('banner-status');
      return statusEl;
    }

    function renderSetupStatus(data: any): void {
      const el = ensureStatusEl();
      if (!el) return;

      if (data && data.running) {
        const msg = data.message || 'Preparing data...';
        const pct = (typeof data.percent === 'number') ? data.percent : null;

        // Suppress banner if we're effectively finished (>=99%) or message is purely theme catalog refreshed
        let suppress = false;
        if (pct !== null && pct >= 99) suppress = true;
        const lm = (msg || '').toLowerCase();
        if (lm.indexOf('theme catalog refreshed') >= 0) suppress = true;

        if (suppress) {
          if (el.innerHTML) {
            el.innerHTML = '';
            el.classList.remove('busy');
          }
          return;
        }

        el.innerHTML = '<strong>Setup/Tagging:</strong> ' + msg + ' <a href="/setup/running" style="margin-left:.5rem;">View progress</a>';
        el.classList.add('busy');
      } else if (data && data.phase === 'done') {
        el.innerHTML = '';
        el.classList.remove('busy');
      } else if (data && data.phase === 'error') {
        el.innerHTML = '<span class="error">Setup error.</span>';
        setTimeout(function(){
          el.innerHTML = '';
          el.classList.remove('busy');
        }, 5000);
      } else {
        if (!el.innerHTML.trim()) el.innerHTML = '';
        el.classList.remove('busy');
      }
    }

    function pollStatus(): void {
      try {
        fetch('/status/setup', { cache: 'no-store' })
          .then(function(r){ return r.json(); })
          .then(renderSetupStatus)
          .catch(function(){ /* noop */ });
      } catch(_){}
    }

    // Poll every 10 seconds to reduce server load (only for header indicator)
    setInterval(pollStatus, 10000);
    pollStatus(); // Initial poll
  }

  /**
   * Highlight active navigation link based on current path
   * Matches exact or prefix paths, prioritizing longer matches
   */
  function initActiveNavHighlighter(): void {
    try {
      const path = window.location.pathname || '/';
      const nav = document.getElementById('primary-nav');
      if (!nav) return;

      const links = nav.querySelectorAll('a');
      let best: HTMLAnchorElement | null = null;
      let bestLen = -1;

      links.forEach(function(a){
        const href = a.getAttribute('href') || '';
        if (!href) return;
        // Exact match or prefix match (ignoring trailing slash)
        if (path === href || path === href + '/' || (href !== '/' && path.startsWith(href))){
          if (href.length > bestLen){ 
            best = a as HTMLAnchorElement; 
            bestLen = href.length; 
          }
        }
      });

      if (best) best.classList.add('active');
    } catch(_){}
  }

  /**
   * Initialize theme selector dropdown and persistence
   * Handles localStorage, URL overrides, and system preference tracking
   */
  function initThemeSelector(enableThemes: boolean, defaultTheme: string): void {
    if (!enableThemes) return;

    try {
      const sel = document.getElementById('theme-select') as HTMLSelectElement | null;
      const resetBtn = document.getElementById('theme-reset');
      const root = document.documentElement;
      const KEY = 'mtg:theme';
      const SERVER_DEFAULT = defaultTheme;

      function mapLight(v: string): string {
        return v === 'light' ? 'light-blend' : v;
      }

      function resolveSystem(): string {
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        return prefersDark ? 'dark' : 'light-blend';
      }

      function normalizeUiValue(v: string): string {
        const x = (v || 'system').toLowerCase();
        if (x === 'light-blend' || x === 'light-slate' || x === 'light-parchment') return 'light';
        return x;
      }

      function apply(val: string): void {
        let v = (val || 'system').toLowerCase();
        if (v === 'system') v = resolveSystem();
        v = mapLight(v);
        root.setAttribute('data-theme', v);
      }

      // Optional URL override: ?theme=system|light|dark|high-contrast|cb-friendly
      const params = new URLSearchParams(window.location.search || '');
      const urlTheme = (params.get('theme') || '').toLowerCase();
      if (urlTheme) {
        // Persist the UI value, not the mapped CSS token
        localStorage.setItem(KEY, normalizeUiValue(urlTheme));
        // Clean the URL so reloads don't keep overriding
        try {
          const u = new URL(window.location.href);
          u.searchParams.delete('theme');
          window.history.replaceState({}, document.title, u.toString());
        } catch(_){}
      }

      // Determine initial selection: URL -> localStorage -> server default -> system
      const stored = localStorage.getItem(KEY);
      const initial = urlTheme || ((stored && stored.trim()) ? stored : (SERVER_DEFAULT || 'system'));
      apply(initial);

      if (sel) {
        sel.value = normalizeUiValue(initial);
        sel.addEventListener('change', function(){
          const v = sel.value || 'system';
          localStorage.setItem(KEY, v);
          apply(v);
        });
      }

      if (resetBtn) {
        resetBtn.addEventListener('click', function(){
          try { localStorage.removeItem(KEY); } catch(_){}
          const v = SERVER_DEFAULT || 'system';
          apply(v);
          if (sel) sel.value = normalizeUiValue(v);
        });
      }

      // React to system changes when set to system
      if (window.matchMedia) {
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        mq.addEventListener && mq.addEventListener('change', function(){
          const cur = localStorage.getItem(KEY) || (SERVER_DEFAULT || 'system');
          if (cur === 'system') apply('system');
        });
      }
    } catch(_){}
  }

  /**
   * Apply theme from environment variable when selector is disabled
   * Resolves 'system' to OS preference
   */
  function initThemeEnvOnly(enableThemes: boolean, defaultTheme: string): void {
    if (enableThemes) return; // Only run when themes are disabled

    try {
      const root = document.documentElement;
      const SERVER_DEFAULT = defaultTheme;

      function resolveSystem(): string {
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        return prefersDark ? 'dark' : 'light-blend';
      }

      let v = (SERVER_DEFAULT || 'system').toLowerCase();
      if (v === 'system') v = resolveSystem();
      if (v === 'light') v = 'light-blend';
      root.setAttribute('data-theme', v);

      // Track OS changes when using system
      if ((SERVER_DEFAULT || 'system').toLowerCase() === 'system' && window.matchMedia) {
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        mq.addEventListener && mq.addEventListener('change', function(){
          root.setAttribute('data-theme', resolveSystem());
        });
      }
    } catch(_){}
  }

  /**
   * Register PWA service worker and handle updates
   * Automatically reloads when new version is available
   */
  function initServiceWorker(enablePwa: boolean, catalogHash: string): void {
    if (!enablePwa) return;

    try {
      if ('serviceWorker' in navigator) {
        const ver = catalogHash || 'dev';
        const url = '/static/sw.js?v=' + encodeURIComponent(ver);

        navigator.serviceWorker.register(url).then(function(reg){
          (window as any).__pwaStatus = { registered: true, scope: reg.scope, version: ver };

          // Listen for updates (new worker installing)
          if (reg.waiting) {
            reg.waiting.postMessage({ type: 'SKIP_WAITING' });
          }

          reg.addEventListener('updatefound', function(){
            try {
              const nw = reg.installing;
              if (!nw) return;

              nw.addEventListener('statechange', function(){
                if (nw.state === 'installed' && navigator.serviceWorker.controller) {
                  // New version available; reload silently for freshness
                  try {
                    sessionStorage.setItem('mtg:swUpdated', '1');
                  } catch(_){}
                  window.location.reload();
                }
              });
            } catch(_){}
          });
        }).catch(function(){
          (window as any).__pwaStatus = { registered: false };
        });
      }
    } catch(_){}
  }

  /**
   * Show toast after page reload
   * Used when actions replace the whole document
   */
  function initToastAfterReload(): void {
    try {
      const raw = sessionStorage.getItem('mtg:toastAfterReload');
      if (raw) {
        sessionStorage.removeItem('mtg:toastAfterReload');
        const data = JSON.parse(raw);
        if (data && data.msg) {
          window.toast && window.toast(data.msg, data.type || '');
        }
      }
    } catch(_){}
  }

  // Initialize all utilities on DOMContentLoaded
  document.addEventListener('DOMContentLoaded', function(){
    initSetupStatusPoller();
    initActiveNavHighlighter();
    initToastAfterReload();

    // Theme and PWA initialization require server-injected values
    // These will be called from base.html inline scripts that pass the values
    // window.__initThemeSelector, window.__initThemeEnvOnly, window.__initServiceWorker
  });

  // Expose functions globally for inline script calls (with server values)
  (window as any).__initThemeSelector = initThemeSelector;
  (window as any).__initThemeEnvOnly = initThemeEnvOnly;
  (window as any).__initServiceWorker = initServiceWorker;
})();
