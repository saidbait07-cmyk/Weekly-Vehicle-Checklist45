const CACHE = 'fleet-static-v2';
const ASSETS = [
  '/static/style.css',
  '/static/app.js',
  '/static/icon.svg',
  '/static/pwa-192x192.png',
  '/static/pwa-512x512.png',
  '/manifest.webmanifest'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (req.mode === 'navigate' && url.pathname.startsWith('/inspect/')) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() =>
          caches.match(req).then(
            (cached) =>
              cached ||
              new Response(
                'Open this assigned vehicle inspection once while connected to enable offline use.',
                { status: 503, headers: { 'Content-Type': 'text/plain' } }
              )
          )
        )
    );
    return;
  }

  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest') {
    event.respondWith(
      caches.match(req).then(
        (cached) =>
          cached ||
          fetch(req).then((res) => {
            if (res.ok) {
              caches.open(CACHE).then((c) => c.put(req, res.clone()));
            }
            return res;
          })
      )
    );
  }
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'CLEAR_PRIVATE_CACHE') {
    event.waitUntil(
      caches.open(CACHE).then(async (cache) => {
        for (const req of await cache.keys()) {
          if (new URL(req.url).pathname.startsWith('/inspect/')) {
            await cache.delete(req);
          }
        }
      })
    );
  }
});
