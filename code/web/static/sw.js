// Minimal service worker (stub). Controlled by ENABLE_PWA.
self.addEventListener('install', event => {
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(clients.claim());
});
self.addEventListener('fetch', event => {
  // Pass-through; caching strategy can be added later.
});
