/**
 * Card Hover Panel System
 * 
 * Unified hover/tap card preview panel with mobile support.
 * Displays card images with metadata (role, tags, themes, overlaps).
 * 
 * Features:
 * - Desktop: Hover to show, follows mouse pointer
 * - Mobile: Tap to show, centered modal with close button
 * - Keyboard accessible with focus/escape handling
 * - Image prefetch LRU cache for performance
 * - DFC (double-faced card) flip support
 * - Tag overlap highlighting
 * - Curated-only and reasons toggles for preview modals
 * 
 * NOTE: This module exposes functions globally on window for browser compatibility
 */

interface PointerEventLike {
  clientX: number;
  clientY: number;
}

// Expose globally for browser usage (CommonJS exports don't work in browser without bundler)
(window as any).__initHoverCardPanel = function initHoverCardPanel(): void {
  // Global delegated curated-only & reasons controls (works after HTMX swaps and inline render)
  function findPreviewRoot(el: Element): Element | null {
    return el.closest('.preview-modal-content.theme-preview-expanded') || el.closest('.preview-modal-content');
  }

  function applyCuratedFor(root: Element): void {
    const checkbox = root.querySelector('#curated-only-toggle') as HTMLInputElement | null;
    const status = root.querySelector('#preview-status') as HTMLElement | null;
    if (!checkbox) return;

    // Persist
    try {
      localStorage.setItem('mtg:preview.curatedOnly', checkbox.checked ? '1' : '0');
    } catch (_) { }

    const curatedOnly = checkbox.checked;
    let hidden = 0;
    root.querySelectorAll('.card-sample').forEach((card) => {
      const role = card.getAttribute('data-role');
      const isCurated = role === 'example' || role === 'curated_synergy' || role === 'synthetic';
      if (curatedOnly && !isCurated) {
        (card as HTMLElement).style.display = 'none';
        hidden++;
      } else {
        (card as HTMLElement).style.display = '';
      }
    });

    if (status) status.textContent = curatedOnly ? (`Hid ${hidden} sampled cards`) : '';
  }

  function applyReasonsFor(root: Element): void {
    const cb = root.querySelector('#reasons-toggle') as HTMLInputElement | null;
    if (!cb) return;

    try {
      localStorage.setItem('mtg:preview.showReasons', cb.checked ? '1' : '0');
    } catch (_) { }

    const show = cb.checked;
    root.querySelectorAll('[data-reasons-block]').forEach((el) => {
      (el as HTMLElement).style.display = show ? '' : 'none';
    });
  }

  document.addEventListener('change', (e) => {
    if (e.target && (e.target as HTMLElement).id === 'curated-only-toggle') {
      const root = findPreviewRoot(e.target as HTMLElement);
      if (root) applyCuratedFor(root);
    }
  });

  document.addEventListener('change', (e) => {
    if (e.target && (e.target as HTMLElement).id === 'reasons-toggle') {
      const root = findPreviewRoot(e.target as HTMLElement);
      if (root) applyReasonsFor(root);
    }
  });

  document.addEventListener('htmx:afterSwap', (ev: any) => {
    const frag = ev.target;
    if (frag && frag.querySelector) {
      if (frag.querySelector('#curated-only-toggle')) applyCuratedFor(frag);
      if (frag.querySelector('#reasons-toggle')) applyReasonsFor(frag);
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.preview-modal-content').forEach((root) => {
      // Restore persisted states before applying
      try {
        const cVal = localStorage.getItem('mtg:preview.curatedOnly');
        if (cVal !== null) {
          const cb = root.querySelector('#curated-only-toggle') as HTMLInputElement | null;
          if (cb) cb.checked = cVal === '1';
        }
        const rVal = localStorage.getItem('mtg:preview.showReasons');
        if (rVal !== null) {
          const rb = root.querySelector('#reasons-toggle') as HTMLInputElement | null;
          if (rb) rb.checked = rVal === '1';
        }
      } catch (_) { }

      if (root.querySelector('#curated-only-toggle')) applyCuratedFor(root);
      if (root.querySelector('#reasons-toggle')) applyReasonsFor(root);
    });
  });

  function createPanel(): HTMLElement {
    const panel = document.createElement('div');
    panel.id = 'hover-card-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Card detail hover panel');
    panel.setAttribute('aria-hidden', 'true');
    panel.style.cssText = 'display:none;position:fixed;z-index:9999;width:560px;max-width:98vw;background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:18px;box-shadow:0 16px 42px rgba(0,0,0,.75);color:var(--text);font-size:14px;line-height:1.45;pointer-events:none;';
    panel.innerHTML = '' +
      '<div class="hcp-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:6px;">' +
      '<div class="hcp-name" style="font-weight:600;font-size:16px;flex:1;padding-right:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">&nbsp;</div>' +
      '<div class="hcp-rarity" style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.75;"></div>' +
      '<button type="button" class="hcp-close" aria-label="Close card details"><span aria-hidden="true">✕</span></button>' +
      '</div>' +
      '<div class="hcp-body">' +
      '<div class="hcp-img-wrap" style="text-align:center;display:flex;flex-direction:column;gap:12px;">' +
      '<img class="hcp-img" alt="Card image" style="max-width:320px;width:100%;height:auto;border-radius:10px;border:1px solid var(--border);background:var(--bg);opacity:1;" />' +
      '</div>' +
      '<div class="hcp-right" style="display:flex;flex-direction:column;min-width:0;">' +
      '<div style="display:flex;align-items:center;gap:6px;margin:0 0 4px;flex-wrap:wrap;">' +
      '<div class="hcp-role" style="display:inline-block;padding:3px 8px;font-size:11px;letter-spacing:.65px;border:1px solid var(--border);border-radius:12px;background:var(--bg);text-transform:uppercase;">&nbsp;</div>' +
      '<div class="hcp-overlaps" style="flex:1;min-height:14px;"></div>' +
      '</div>' +
      '<ul class="hcp-taglist" aria-label="Themes"></ul>' +
      '<div class="hcp-meta" style="font-size:12px;opacity:.85;margin:2px 0 6px;"></div>' +
      '<ul class="hcp-reasons" style="list-style:disc;margin:4px 0 8px 18px;padding:0;font-size:11px;line-height:1.35;"></ul>' +
      '<div class="hcp-tags" style="font-size:11px;opacity:.55;word-break:break-word;"></div>' +
      '</div>' +
      '</div>';
    document.body.appendChild(panel);
    return panel;
  }

  function ensurePanel(): HTMLElement {
    let panel = document.getElementById('hover-card-panel');
    if (panel) return panel;
    // Auto-create for direct theme pages where fragment-specific markup not injected
    return createPanel();
  }

  function setup(): void {
    const panel = ensurePanel();
    if (!panel || (panel as any).__hoverInit) return;
    (panel as any).__hoverInit = true;

    const imgEl = panel.querySelector('.hcp-img') as HTMLImageElement;
    const nameEl = panel.querySelector('.hcp-name') as HTMLElement;
    const rarityEl = panel.querySelector('.hcp-rarity') as HTMLElement;
    const metaEl = panel.querySelector('.hcp-meta') as HTMLElement;
    const reasonsList = panel.querySelector('.hcp-reasons') as HTMLElement;
    const tagsEl = panel.querySelector('.hcp-tags') as HTMLElement;
    const bodyEl = panel.querySelector('.hcp-body') as HTMLElement;
    const rightCol = panel.querySelector('.hcp-right') as HTMLElement;

    const coarseQuery = window.matchMedia('(pointer: coarse)');

    function isMobileMode(): boolean {
      return (coarseQuery && coarseQuery.matches) || window.innerWidth <= 768;
    }

    function refreshPosition(): void {
      if (panel.style.display === 'block') {
        move((window as any).__lastPointerEvent);
      }
    }

    if (coarseQuery) {
      const handler = () => { refreshPosition(); };
      if (coarseQuery.addEventListener) {
        coarseQuery.addEventListener('change', handler);
      } else if ((coarseQuery as any).addListener) {
        (coarseQuery as any).addListener(handler);
      }
    }

    window.addEventListener('resize', refreshPosition);

    const closeBtn = panel.querySelector('.hcp-close') as HTMLButtonElement;
    if (closeBtn && !(closeBtn as any).__bound) {
      (closeBtn as any).__bound = true;
      closeBtn.addEventListener('click', (ev) => {
        ev.preventDefault();
        hide();
      });
    }

    function positionPanel(evt: PointerEventLike): void {
      if (isMobileMode()) {
        panel.classList.add('mobile');
        panel.style.bottom = 'auto';
        panel.style.left = '50%';
        panel.style.top = '50%';
        panel.style.right = 'auto';
        panel.style.transform = 'translate(-50%, -50%)';
        panel.style.pointerEvents = 'auto';
      } else {
        panel.classList.remove('mobile');
        panel.style.pointerEvents = 'none';
        panel.style.transform = 'none';
        const pad = 18;
        let x = evt.clientX + pad, y = evt.clientY + pad;
        const vw = window.innerWidth, vh = window.innerHeight;
        const r = panel.getBoundingClientRect();
        if (x + r.width + 8 > vw) x = evt.clientX - r.width - pad;
        if (y + r.height + 8 > vh) y = evt.clientY - r.height - pad;
        if (x < 8) x = 8;
        if (y < 8) y = 8;
        panel.style.left = x + 'px';
        panel.style.top = y + 'px';
        panel.style.bottom = 'auto';
        panel.style.right = 'auto';
      }
    }

    function move(evt?: PointerEventLike): void {
      if (panel.style.display === 'none') return;
      if (!evt) evt = (window as any).__lastPointerEvent;
      if (!evt && lastCard) {
        const rect = lastCard.getBoundingClientRect();
        evt = { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
      }
      if (!evt) evt = { clientX: window.innerWidth / 2, clientY: window.innerHeight / 2 };
      positionPanel(evt);
    }

    // Lightweight image prefetch LRU cache (size 12)
    const imgLRU: string[] = [];
    function prefetch(src: string): void {
      if (!src) return;
      if (imgLRU.indexOf(src) === -1) {
        imgLRU.push(src);
        if (imgLRU.length > 12) imgLRU.shift();
        const im = new Image();
        im.src = src;
      }
    }

    const activationDelay = 120; // ms
    let hoverTimer: number | null = null;

    function schedule(card: Element, evt: PointerEventLike): void {
      if (hoverTimer !== null) clearTimeout(hoverTimer);
      hoverTimer = window.setTimeout(() => { show(card, evt); }, activationDelay);
    }

    function cancelSchedule(): void {
      if (hoverTimer !== null) {
        clearTimeout(hoverTimer);
        hoverTimer = null;
      }
    }

    let lastCard: Element | null = null;

    function show(card: Element, evt?: PointerEventLike): void {
      if (!card) return;

      // Prefer attributes on container, fallback to child (image) if missing
      function attr(name: string): string {
        return card.getAttribute(name) ||
          (card.querySelector(`[data-${name.slice(5)}]`)?.getAttribute(name)) || '';
      }

      let simpleSource: Element | null = null;
      if (card.closest) {
        simpleSource = card.closest('[data-hover-simple]');
      }

      const forceSimple = (card.hasAttribute && card.hasAttribute('data-hover-simple')) || !!simpleSource;
      const nm = attr('data-card-name') || attr('data-original-name') || 'Card';
      const rarity = (attr('data-rarity') || '').trim();
      const mana = (attr('data-mana') || '').trim();
      const role = (attr('data-role') || '').trim();
      let reasonsRaw = attr('data-reasons') || '';
      const tagsRaw = attr('data-tags') || '';
      const metadataTagsRaw = attr('data-metadata-tags') || '';
      const roleEl = panel.querySelector('.hcp-role') as HTMLElement;
      // Check for flip button on card or its parent container (for <img> elements in commander browser)
      let hasFlip = !!card.querySelector('.dfc-toggle');
      if (!hasFlip && card.parentElement) {
        hasFlip = !!card.parentElement.querySelector('.dfc-toggle');
      }
      const tagListEl = panel.querySelector('.hcp-taglist') as HTMLElement;
      const overlapsEl = panel.querySelector('.hcp-overlaps') as HTMLElement;
      const overlapsAttr = attr('data-overlaps') || '';

      function displayLabel(text: string): string {
        if (!text) return '';
        let label = String(text);
        label = label.replace(/[\u2022\-_]+/g, ' ');
        label = label.replace(/\s+/g, ' ').trim();
        return label;
      }

      function parseTagList(raw: string): string[] {
        if (!raw) return [];
        const trimmed = String(raw).trim();
        if (!trimmed) return [];
        let result: string[] = [];
        let candidate = trimmed;

        if (trimmed[0] === '[' && trimmed[trimmed.length - 1] === ']') {
          candidate = trimmed.slice(1, -1);
        }

        // Try JSON parsing after normalizing quotes
        try {
          let normalized = trimmed;
          if (trimmed.indexOf("'") > -1 && trimmed.indexOf('"') === -1) {
            normalized = trimmed.replace(/'/g, '"');
          }
          const parsed = JSON.parse(normalized);
          if (Array.isArray(parsed)) {
            result = parsed;
          }
        } catch (_) { /* fall back below */ }

        if (!result || !result.length) {
          result = candidate.split(/\s*,\s*/);
        }

        return result.map((t) => String(t || '').trim()).filter(Boolean);
      }

      function deriveTagsFromReasons(reasons: string): string[] {
        if (!reasons) return [];
        const out: string[] = [];

        // Grab bracketed or quoted lists first
        const m = reasons.match(/\[(.*?)\]/);
        if (m && m[1]) out.push(...m[1].split(/\s*,\s*/));

        // Common phrasing: "overlap(s) with A, B" or "by A, B"
        const rx = /(overlap(?:s)?(?:\s+with)?|by)\s+([^.;]+)/ig;
        let r;
        while ((r = rx.exec(reasons))) {
          out.push(...(r[2] || '').split(/\s*,\s*/));
        }

        const tagRx = /tag:\s*([^.;]+)/ig;
        let tMatch;
        while ((tMatch = tagRx.exec(reasons))) {
          out.push(...(tMatch[1] || '').split(/\s*,\s*/));
        }

        return out.map((s) => s.trim()).filter(Boolean);
      }

      let overlapArr: string[] = [];
      if (overlapsAttr) {
        const parsedOverlaps = parseTagList(overlapsAttr);
        if (parsedOverlaps.length) {
          overlapArr = parsedOverlaps;
        } else {
          overlapArr = [String(overlapsAttr).trim()];
        }
      }

      const derivedFromReasons = deriveTagsFromReasons(reasonsRaw);
      let allTags = parseTagList(tagsRaw);

      if (!allTags.length && derivedFromReasons.length) {
        // Fallback: try to derive tags from reasons text when tags missing
        allTags = derivedFromReasons.slice();
      }

      if ((!overlapArr || !overlapArr.length) && derivedFromReasons.length) {
        const normalizedAll = (allTags || []).map((t) => ({ raw: t, key: t.toLowerCase() }));
        const derivedKeys = new Set(derivedFromReasons.map((t) => t.toLowerCase()));
        let intersect = normalizedAll.filter((entry) => derivedKeys.has(entry.key)).map((entry) => entry.raw);

        if (!intersect.length) {
          intersect = derivedFromReasons.slice();
        }

        overlapArr = Array.from(new Set(intersect));
      }

      overlapArr = (overlapArr || []).map((t) => String(t || '').trim()).filter(Boolean);
      allTags = (allTags || []).map((t) => String(t || '').trim()).filter(Boolean);

      nameEl.textContent = nm;
      rarityEl.textContent = rarity;

      const roleLabel = displayLabel(role);
      const roleKey = (roleLabel || role || '').toLowerCase();
      const isCommanderRole = roleKey === 'commander';

      metaEl.textContent = [
        roleLabel ? ('Role: ' + roleLabel) : '',
        mana ? ('Mana: ' + mana) : ''
      ].filter(Boolean).join(' • ');

      reasonsList.innerHTML = '';
      reasonsRaw.split(';').map((r) => r.trim()).filter(Boolean).forEach((r) => {
        const li = document.createElement('li');
        li.style.margin = '2px 0';
        li.textContent = r;
        reasonsList.appendChild(li);
      });

      // Build inline tag list with overlap highlighting
      if (tagListEl) {
        tagListEl.innerHTML = '';
        tagListEl.style.display = 'none';
        tagListEl.setAttribute('aria-hidden', 'true');
      }

      if (overlapsEl) {
        if (overlapArr && overlapArr.length) {
          overlapsEl.innerHTML = overlapArr.map((o) => {
            const label = displayLabel(o);
            return `<span class="hcp-ov-chip" title="Overlapping synergy">${label}</span>`;
          }).join('');
        } else {
          overlapsEl.innerHTML = '';
        }
      }

      if (tagsEl) {
        if (isCommanderRole) {
          tagsEl.textContent = '';
          tagsEl.style.display = 'none';
        } else {
          let tagText = allTags.map(displayLabel).join(', ');

          // M5: Temporarily append metadata tags for debugging
          if (metadataTagsRaw && metadataTagsRaw.trim()) {
            const metaTags = metadataTagsRaw.split(',').map((t) => t.trim()).filter(Boolean);
            if (metaTags.length) {
              const metaText = metaTags.map(displayLabel).join(', ');
              tagText = tagText ? (tagText + ' | META: ' + metaText) : ('META: ' + metaText);
            }
          }

          tagsEl.textContent = tagText;
          tagsEl.style.display = tagText ? '' : 'none';
        }
      }

      if (roleEl) {
        roleEl.textContent = roleLabel || '';
        roleEl.style.display = roleLabel ? 'inline-block' : 'none';
      }

      panel.classList.toggle('is-payoff', role === 'payoff');
      panel.classList.toggle('is-commander', isCommanderRole);

      const hasDetails = !forceSimple && (
        !!roleLabel || !!mana || !!rarity ||
        (reasonsRaw && reasonsRaw.trim()) ||
        (overlapArr && overlapArr.length) ||
        (allTags && allTags.length)
      );

      panel.classList.toggle('hcp-simple', !hasDetails);

      if (rightCol) {
        rightCol.style.display = hasDetails ? 'flex' : 'none';
      }

      if (bodyEl) {
        if (!hasDetails) {
          bodyEl.style.display = 'flex';
          bodyEl.style.flexDirection = 'column';
          bodyEl.style.alignItems = 'center';
          bodyEl.style.gap = '12px';
        } else {
          bodyEl.style.display = '';
          bodyEl.style.flexDirection = '';
          bodyEl.style.alignItems = '';
          bodyEl.style.gap = '';
        }
      }

      const rawName = nm || '';
      let hasBack = rawName.indexOf('//') > -1 || (attr('data-original-name') || '').indexOf('//') > -1;
      if (hasBack) hasFlip = true;

      const storageKey = 'mtg:face:' + rawName.toLowerCase();
      const storedFace = (() => {
        try {
          return localStorage.getItem(storageKey);
        } catch (_) {
          return null;
        }
      })();

      if (storedFace === 'front' || storedFace === 'back') {
        card.setAttribute('data-current-face', storedFace);
      }

      const chosenFace = card.getAttribute('data-current-face') || 'front';
      lastCard = card;

      function renderHoverFace(face: string): void {
        const desiredVersion = 'normal';
        const currentKey = nm + ':' + face + ':' + desiredVersion;
        const prevFace = imgEl.getAttribute('data-face');
        const faceChanged = prevFace && prevFace !== face;

        if (imgEl.getAttribute('data-current') !== currentKey) {
          // For DFC cards, extract the specific face name for cache lookup
          let faceName = nm;
          const isDFC = nm.indexOf('//') > -1;
          if (isDFC) {
            const faces = nm.split('//');
            faceName = (face === 'back') ? faces[1].trim() : faces[0].trim();
          }

          let src = '/api/images/' + desiredVersion + '/' + encodeURIComponent(faceName);
          if (isDFC && face === 'back') {
            src += '?face=back';
          }

          if (faceChanged) imgEl.style.opacity = '0';
          prefetch(src);
          imgEl.src = src;
          imgEl.setAttribute('data-current', currentKey);
          imgEl.setAttribute('data-face', face);

          imgEl.addEventListener('load', function onLoad() {
            imgEl.removeEventListener('load', onLoad);
            requestAnimationFrame(() => { imgEl.style.opacity = '1'; });
          });
        }

        if (!(imgEl as any).__errBound) {
          (imgEl as any).__errBound = true;
          imgEl.addEventListener('error', () => {
            const cur = imgEl.getAttribute('src') || '';
            // Fallback from normal to small if image fails to load
            if (cur.indexOf('/api/images/normal/') > -1) {
              imgEl.src = cur.replace('/api/images/normal/', '/api/images/small/');
            }
          });
        }
      }

      renderHoverFace(chosenFace);

      // Add DFC flip button to popup panel ONLY on mobile
      const checkFlip = (window as any).__dfcHasTwoFaces || (() => false);
      if (hasFlip && imgEl && checkFlip(card) && isMobileMode()) {
        const imgWrap = imgEl.parentElement;
        if (imgWrap && !imgWrap.querySelector('.dfc-toggle')) {
          const flipBtn = document.createElement('button');
          flipBtn.type = 'button';
          flipBtn.className = 'dfc-toggle';
          flipBtn.setAttribute('aria-pressed', 'false');
          flipBtn.setAttribute('tabindex', '0');
          flipBtn.innerHTML = '<span class="icon" aria-hidden="true" style="font-size:18px;">⥮</span>';

          flipBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            if ((window as any).__dfcFlipCard && lastCard) {
              // For image elements, find the parent container with the flip button
              let cardToFlip = lastCard;
              if (lastCard.tagName === 'IMG' && lastCard.parentElement) {
                const parentWithButton = lastCard.parentElement.querySelector('.dfc-toggle');
                if (parentWithButton) {
                  cardToFlip = lastCard.parentElement;
                }
              }
              (window as any).__dfcFlipCard(cardToFlip);
            }
          });

          flipBtn.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'f' || ev.key === 'F') {
              ev.preventDefault();
              if ((window as any).__dfcFlipCard && lastCard) {
                // For image elements, find the parent container with the flip button
                let cardToFlip = lastCard;
                if (lastCard.tagName === 'IMG' && lastCard.parentElement) {
                  const parentWithButton = lastCard.parentElement.querySelector('.dfc-toggle');
                  if (parentWithButton) {
                    cardToFlip = lastCard.parentElement;
                  }
                }
                (window as any).__dfcFlipCard(cardToFlip);
              }
            }
          });

          imgWrap.classList.add('dfc-host');
          imgWrap.appendChild(flipBtn);
        }
      }

      (window as any).__dfcNotifyHover = hasFlip ? (cardRef: Element, face: string) => {
        if (cardRef === lastCard) renderHoverFace(face);
      } : null;

      if (evt) (window as any).__lastPointerEvent = evt;

      if (isMobileMode()) {
        panel.classList.add('mobile');
        panel.style.pointerEvents = 'auto';
        panel.style.maxHeight = '80vh';
      } else {
        panel.classList.remove('mobile');
        panel.style.pointerEvents = 'none';
        panel.style.maxHeight = '';
        panel.style.bottom = 'auto';
      }

      panel.style.display = 'block';
      panel.setAttribute('aria-hidden', 'false');
      move(evt);
    }

    function hide(): void {
      // Blur any focused element inside panel to avoid ARIA focus warning
      if (panel.contains(document.activeElement)) {
        (document.activeElement as HTMLElement)?.blur();
      }
      panel.style.display = 'none';
      panel.setAttribute('aria-hidden', 'true');
      cancelSchedule();
      panel.classList.remove('mobile');
      panel.style.pointerEvents = 'none';
      panel.style.transform = 'none';
      panel.style.bottom = 'auto';
      panel.style.maxHeight = '';
      (window as any).__dfcNotifyHover = null;
    }

    document.addEventListener('mousemove', move);

    function getCardFromEl(el: EventTarget | null): Element | null {
      if (!el || !(el instanceof Element)) return null;

      if (el.closest) {
        const altBtn = el.closest('.alts button[data-card-name]');
        if (altBtn) return altBtn;
      }

      // If inside flip button
      const btn = el.closest && el.closest('.dfc-toggle');
      if (btn) {
        return btn.closest('.card-sample, .commander-cell, .commander-thumb, .commander-card, .card-tile, .candidate-tile, .card-preview, .stack-card');
      }

      // For card-tile, ONLY trigger on .img-btn or the image itself (not entire tile)
      if (el.closest && el.closest('.card-tile')) {
        const imgBtn = el.closest('.img-btn');
        if (imgBtn) return imgBtn.closest('.card-tile');

        // If directly on the image
        if (el.matches && (el.matches('img.card-thumb') || el.matches('img[data-card-name]'))) {
          return el.closest('.card-tile');
        }

        // Don't trigger on other parts of the tile (buttons, text, etc.)
        return null;
      }

      // Recognized container classes
      const container = el.closest && el.closest('.card-sample, .commander-cell, .commander-thumb, .commander-card, .candidate-tile, .card-preview, .stack-card');
      if (container) return container;

      // Image-based detection (any card image carrying data-card-name)
      if (el.matches && (el.matches('img.card-thumb') || el.matches('img[data-card-name]') || el.classList.contains('commander-img'))) {
        const up = el.closest && el.closest('.stack-card');
        return up || el;
      }

      // List view spans (deck summary list mode, finished deck list, etc.)
      if (el.hasAttribute && el.hasAttribute('data-card-name')) return el;

      return null;
    }

    document.addEventListener('pointermove', (e) => { (window as any).__lastPointerEvent = e; });

    document.addEventListener('pointerover', (e) => {
      if (isMobileMode()) return;
      const card = getCardFromEl(e.target);
      if (!card) return;

      // If hovering flip button, refresh immediately (no activation delay)
      if (e.target instanceof Element && e.target.closest && e.target.closest('.dfc-toggle')) {
        show(card, e);
        return;
      }

      if (lastCard === card && panel.style.display === 'block') return;
      schedule(card, e);
    });

    document.addEventListener('pointerout', (e) => {
      if (isMobileMode()) return;
      const relCard = getCardFromEl(e.relatedTarget);
      if (relCard && lastCard && relCard === lastCard) return; // moving within same card (img <-> button)
      if (!panel.contains(e.relatedTarget as Node)) {
        cancelSchedule();
        if (!relCard) hide();
      }
    });

    document.addEventListener('click', (e) => {
      if (!isMobileMode()) return;
      if (panel.contains(e.target as Node)) return;
      if (e.target instanceof Element && e.target.closest && (e.target.closest('.dfc-toggle') || e.target.closest('.hcp-close'))) return;
      if (e.target instanceof Element && e.target.closest && e.target.closest('button, input, select, textarea, a')) return;

      const card = getCardFromEl(e.target);
      if (card) {
        cancelSchedule();
        const rect = card.getBoundingClientRect();
        const syntheticEvt = { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
        show(card, syntheticEvt);
      } else if (panel.style.display === 'block') {
        hide();
      }
    });

    // Expose show function for external refresh (flip updates)
    (window as any).__hoverShowCard = (card: Element) => {
      const ev = (window as any).__lastPointerEvent || {
        clientX: card.getBoundingClientRect().left + 12,
        clientY: card.getBoundingClientRect().top + 12
      };
      show(card, ev);
    };

    (window as any).hoverShowByName = (name: string) => {
      try {
        const el = document.querySelector('[data-card-name="' + CSS.escape(name) + '"]');
        if (el) {
          (window as any).__hoverShowCard(
            el.closest('.card-sample, .commander-cell, .commander-thumb, .commander-card, .card-tile, .candidate-tile, .card-preview, .stack-card') || el
          );
        }
      } catch (_) { }
    };

    // Keyboard accessibility & focus traversal
    document.addEventListener('focusin', (e) => {
      const card = e.target instanceof Element && e.target.closest && e.target.closest('.card-sample, .commander-cell, .commander-thumb');
      if (card) {
        show(card, {
          clientX: card.getBoundingClientRect().left + 10,
          clientY: card.getBoundingClientRect().top + 10
        });
      }
    });

    document.addEventListener('focusout', (e) => {
      const next = e.relatedTarget instanceof Element && e.relatedTarget.closest && e.relatedTarget.closest('.card-sample, .commander-cell, .commander-thumb');
      if (!next) hide();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') hide();
    });

    // Compact mode event listener
    document.addEventListener('mtg:hoverCompactToggle', () => {
      panel.classList.toggle('compact-img', !!(window as any).__hoverCompactMode);
    });
  }

  document.addEventListener('htmx:afterSwap', setup);
  document.addEventListener('DOMContentLoaded', setup);
  setup();
};

// Global compact mode toggle function
(window as any).__initHoverCompactMode = function initHoverCompactMode(): void {
  (window as any).toggleHoverCompactMode = (state?: boolean) => {
    if (typeof state === 'boolean') {
      (window as any).__hoverCompactMode = state;
    } else {
      (window as any).__hoverCompactMode = !(window as any).__hoverCompactMode;
    }
    document.dispatchEvent(new CustomEvent('mtg:hoverCompactToggle'));
  };
};

// Auto-initialize on load
if (typeof window !== 'undefined') {
  (window as any).__initHoverCardPanel();
  (window as any).__initHoverCompactMode();
}
