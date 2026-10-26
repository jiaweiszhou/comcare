// ComCare Service Worker
// Strategy:
//   Static assets  → Cache First (serve instantly, update in background)
//   GET /api/*     → Network First with cache fallback (fresh data when online, readable offline)
//   POST/PUT/DELETE → Network only (mutations need the server)

const STATIC_CACHE = 'comcare-static-v1';
const API_CACHE    = 'comcare-api-v1';

const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/apple-touch-icon.png',
];

// ── Install: pre-cache static shell ───────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: clean up old caches ─────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== STATIC_CACHE && k !== API_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // API GET → network first, cache fallback
  if (url.pathname.startsWith('/api/') && request.method === 'GET') {
    event.respondWith(networkFirstCache(request, API_CACHE));
    return;
  }

  // API mutations → network only (never cache POSTs)
  if (url.pathname.startsWith('/api/')) return;

  // Everything else (HTML, static files) → cache first, network fallback
  event.respondWith(cacheFirstNetwork(request, STATIC_CACHE));
});

// ── Strategies ────────────────────────────────────────────────────────────────
async function cacheFirstNetwork(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('<h2>ComCare is offline</h2><p>Connect to the network to load the app.</p>', {
      headers: { 'Content-Type': 'text/html' }
    });
  }
}

async function networkFirstCache(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'offline', cached: false }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
}
