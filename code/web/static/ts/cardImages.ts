/**
 * Card Image URL Builders & Retry Logic
 * 
 * Utilities for constructing card image URLs and handling image load failures
 * with automatic fallback to different image sizes.
 * 
 * Features:
 * - Build card image URLs with face (front/back) support
 * - Build Scryfall image URLs with version control
 * - Automatic retry on image load failure (different sizes)
 * - Cache-busting support for failed loads
 * - HTMX swap integration for dynamic content
 * 
 * NOTE: This module exposes functions globally on window for browser compatibility
 */

interface ImageRetryState {
  vi: number;           // Current version index
  nocache: number;      // Cache-busting flag (0 or 1)
  versions: string[];   // Image versions to try ['small', 'normal', 'large']
}

const IMG_FLAG = '__cardImgRetry';

/**
 * Normalize card name by removing synergy suffixes
 */
function normalizeCardName(raw: string): string {
  if (!raw) return raw;
  const normalize = (window as any).__normalizeCardName || ((name: string) => {
    if (!name) return name;
    const m = /(.*?)(\s*-\s*Synergy\s*\(.*\))$/i.exec(name);
    if (m) return m[1].trim();
    return name;
  });
  return normalize(raw);
}

/**
 * Build card image URL with face support (front/back)
 * @param name - Card name
 * @param version - Image version ('small', 'normal', 'large')
 * @param nocache - Add cache-busting timestamp
 * @param face - Card face ('front' or 'back')
 */
function buildCardUrl(name: string, version?: string, nocache?: boolean, face?: string): string {
  name = normalizeCardName(name);
  const q = encodeURIComponent(name || '');
  let url = '/api/images/' + (version || 'normal') + '/' + q;
  if (face === 'back') url += '?face=back';
  if (nocache) url += (face === 'back' ? '&' : '?') + 't=' + Date.now();
  return url;
}

/**
 * Build Scryfall image URL
 * @param name - Card name
 * @param version - Image version ('small', 'normal', 'large')
 * @param nocache - Add cache-busting timestamp
 */
function buildScryfallImageUrl(name: string, version?: string, nocache?: boolean): string {
  name = normalizeCardName(name);
  const q = encodeURIComponent(name || '');
  let url = '/api/images/' + (version || 'normal') + '/' + q;
  if (nocache) url += '?t=' + Date.now();
  return url;
}

/**
 * Bind error handler to an image element for automatic retry with fallback versions
 * @param img - Image element with data-card-name attribute
 * @param versions - Array of image versions to try in order
 */
function bindCardImageRetry(img: HTMLImageElement, versions?: string[]): void {
  try {
    if (!img || (img as any)[IMG_FLAG]) return;
    const name = img.getAttribute('data-card-name') || '';
    if (!name) return;

    // Default versions: normal -> large
    const versionList = versions && versions.length ? versions.slice() : ['normal', 'large'];
    (img as any)[IMG_FLAG] = { 
      vi: 0, 
      nocache: 0, 
      versions: versionList 
    } as ImageRetryState;

    img.addEventListener('error', function() {
      const st = (img as any)[IMG_FLAG] as ImageRetryState;
      if (!st) return;

      // Try next version
      if (st.vi < st.versions.length - 1) {
        st.vi += 1;
        img.src = buildScryfallImageUrl(name, st.versions[st.vi], false);
      } 
      // Try cache-busting current version
      else if (!st.nocache) {
        st.nocache = 1;
        img.src = buildScryfallImageUrl(name, st.versions[st.vi], true);
      }
    });

    // If initial load already failed before binding, try next immediately
    if (img.complete && img.naturalWidth === 0) {
      const st = (img as any)[IMG_FLAG] as ImageRetryState;
      const current = img.src || '';
      const first = buildScryfallImageUrl(name, st.versions[0], false);
      
      // Check if current src matches first version
      if (current.indexOf(encodeURIComponent(name)) !== -1 && 
          current.indexOf('version=' + st.versions[0]) !== -1) {
        st.vi = Math.min(1, st.versions.length - 1);
        img.src = buildScryfallImageUrl(name, st.versions[st.vi], false);
      } else {
        // Re-trigger current request (may succeed if transient error)
        img.src = current;
      }
    }
  } catch (_) {
    // Silently fail - image retry is a nice-to-have feature
  }
}

/**
 * Bind retry handlers to all card images in the document
 */
function bindAllCardImageRetries(): void {
  document.querySelectorAll('img[data-card-name]').forEach((img) => {
    // Use thumbnail fallbacks for card-thumb, otherwise preview fallbacks
    const versions = (img.classList && img.classList.contains('card-thumb')) 
      ? ['small', 'normal', 'large'] 
      : ['normal', 'large'];
    bindCardImageRetry(img as HTMLImageElement, versions);
  });
}

// Expose globally for browser usage
(window as any).__initCardImages = function initCardImages(): void {
  // Expose retry binding globally for dynamic content
  (window as any).bindAllCardImageRetries = bindAllCardImageRetries;

  // Initial bind
  bindAllCardImageRetries();

  // Re-bind after HTMX swaps
  document.addEventListener('htmx:afterSwap', bindAllCardImageRetries);
};

// Auto-initialize on load
if (typeof window !== 'undefined') {
  (window as any).__initCardImages();
}
