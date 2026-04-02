/**
 * prefetch-hover.ts — Hover-intent prefetch/prerender for key navigation targets.
 *
 * Enabled server-side via WEB_PREFETCH=1. Elements opt in with:
 *   data-prefetch="1"           — enable prefetch on this element
 *   data-prefetch-url="<url>"   — URL to prefetch (falls back to el.href)
 *   data-prerender-ok="1"       — allow Chrome Speculation Rules prerender
 *                                  (only safe GET routes with no side effects)
 *
 * Strategy selection (per element):
 *   data-prerender-ok="1" + Chrome Speculation Rules support → prerender
 *   otherwise                                                → rel=prefetch
 *
 * Progressive enhancement: degrades gracefully when unsupported.
 * Respects navigator.connection.saveData and slow (2G) effective connections.
 */
(function () {
  'use strict';

  const MAX_CONCURRENT = 2;
  const MAX_PRERENDERS = 2;
  const DELAY_MS = 100;
  let _inflight = 0;
  const _prefetched: Record<string, boolean> = {};

  // Speculation Rules API detection (Chrome 108+)
  const _supportsSpeculation: boolean = (function () {
    try {
      return typeof HTMLScriptElement !== 'undefined' &&
        'supports' in HTMLScriptElement &&
        typeof (HTMLScriptElement as any).supports === 'function' &&
        (HTMLScriptElement as any).supports('speculationrules');
    } catch (_) { return false; }
  })();

  let _speculationEl: HTMLScriptElement | null = null;
  const _prerenderQueued: string[] = [];

  function _saverMode(): boolean {
    try {
      const conn: any = (navigator as any).connection || (navigator as any).mozConnection || (navigator as any).webkitConnection || {};
      if (conn.saveData === true) return true;
      const et: string = conn.effectiveType || '';
      return et === '2g' || et === 'slow-2g';
    } catch (_) { return false; }
  }

  /** Inject/update a single <script type="speculationrules"> for prerender. */
  function _addSpeculationPrerender(url: string): void {
    if (_prerenderQueued.indexOf(url) !== -1) return;
    // Cap queued prerenders to avoid excess memory
    if (_prerenderQueued.length >= MAX_PRERENDERS) {
      _prerenderQueued.shift();
    }
    _prerenderQueued.push(url);
    const rules = { prerender: [{ source: 'list', urls: _prerenderQueued.slice(), eagerness: 'immediate' }] };
    if (!_speculationEl) {
      _speculationEl = document.createElement('script');
      _speculationEl.type = 'speculationrules';
      document.head.appendChild(_speculationEl);
    }
    _speculationEl.textContent = JSON.stringify(rules);
  }

  function _injectPrefetch(url: string): void {
    if (_prefetched[url]) return;
    if (_inflight >= MAX_CONCURRENT) return;
    _prefetched[url] = true;
    _inflight++;
    const link = document.createElement('link');
    link.rel = 'prefetch';
    link.href = url;
    link.as = 'document';
    link.addEventListener('load', function () { if (_inflight > 0) _inflight--; });
    link.addEventListener('error', function () { if (_inflight > 0) _inflight--; });
    document.head.appendChild(link);
  }

  const _wired: WeakSet<Element> = new WeakSet();

  function _attach(el: Element): void {
    if (_wired.has(el)) return;
    _wired.add(el);
    let timer: ReturnType<typeof setTimeout> | null = null;
    el.addEventListener('mouseenter', function () {
      if (_saverMode()) return;
      const url = (el as HTMLElement).getAttribute('data-prefetch-url') || (el as HTMLAnchorElement).href || '';
      if (!url) return;
      const prerenderOk = (el as HTMLElement).getAttribute('data-prerender-ok') === '1';
      timer = setTimeout(function () {
        timer = null;
        if (_saverMode()) return;
        if (_supportsSpeculation && prerenderOk) {
          _addSpeculationPrerender(url);
        } else {
          if (_inflight >= MAX_CONCURRENT) return;
          _injectPrefetch(url);
        }
      }, DELAY_MS);
    });
    el.addEventListener('mouseleave', function () {
      if (timer !== null) { clearTimeout(timer); timer = null; }
    });
  }

  function _init(): void {
    document.querySelectorAll('[data-prefetch="1"]').forEach(_attach);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

  // Re-scan after HTMX partial updates so dynamically-added elements are wired
  document.addEventListener('htmx:afterSettle', _init);
})();
