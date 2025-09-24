// Service Worker for MTG Deckbuilder
// Versioned via ?v=<catalog_hash> appended at registration time.
// Strategies:
// 1. Precache core shell assets (app shell + styles + manifest).
// 2. Runtime cache (stale-while-revalidate) for theme list & preview fragments.
// 3. Version bump (catalog hash change) triggers old cache purge.

const VERSION = (new URL(self.location.href)).searchParams.get('v') || 'dev';
const PRECACHE = `precache-v${VERSION}`;
const RUNTIME = `runtime-v${VERSION}`;
const CORE_ASSETS = [
  '/',
  '/themes/',
  '/static/styles.css',
  '/static/app.js',
  '/static/manifest.webmanifest',
  '/static/favicon.png'
];

// Utility: limit entries in a cache (simple LRU-esque trim by deletion order)
async function trimCache(cacheName, maxEntries){
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if(keys.length <= maxEntries) return;
  const remove = keys.slice(0, keys.length - maxEntries);
  await Promise.all(remove.map(k => cache.delete(k)));
}

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(PRECACHE).then(cache => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    // Remove old versioned caches
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => (k.startsWith('precache-v') || k.startsWith('runtime-v')) && !k.endsWith(VERSION)).map(k => caches.delete(k)));
    await clients.claim();
  })());
});

function isPreviewRequest(url){
  return /\/themes\/preview\//.test(url.pathname);
}
function isThemeList(url){
  return url.pathname === '/themes/' || url.pathname.startsWith('/themes?');
}

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if(req.method !== 'GET') return; // Non-GET pass-through

  // Core assets: cache-first
  if(CORE_ASSETS.includes(url.pathname)){
    event.respondWith(
      caches.open(PRECACHE).then(cache => cache.match(req).then(found => {
        return found || fetch(req).then(resp => { cache.put(req, resp.clone()); return resp; });
      }))
    );
    return;
  }

  // Theme list / preview fragments: stale-while-revalidate
  if(isPreviewRequest(url) || isThemeList(url)){
    event.respondWith((async () => {
      const cache = await caches.open(RUNTIME);
      const cached = await cache.match(req);
      const fetchPromise = fetch(req).then(resp => {
        if(resp && resp.status === 200){ cache.put(req, resp.clone()); trimCache(RUNTIME, 120).catch(()=>{}); }
        return resp;
      }).catch(() => cached);
      return cached || fetchPromise;
    })());
    return;
  }
});

self.addEventListener('message', event => {
  if(event.data && event.data.type === 'SKIP_WAITING'){
    self.skipWaiting();
  }
});
