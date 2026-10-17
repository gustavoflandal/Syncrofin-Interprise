/* SyncroFin service worker.
 *
 * Its one job is to make the app *installable* and its shell available
 * offline. It is deliberately NOT a data cache:
 *
 *   /api/*       never cached, never intercepted. This is somebody's financial
 *                data; a copy sitting in Cache Storage would outlive their
 *                logout and be readable by anyone with the device. Offline, the
 *                app opens and says it cannot reach the server, which is true.
 *   /static/*    hashed build assets (see `assetsDir` in vite.config.ts), so a
 *                cached copy can never be stale: cache-first.
 *   navigations  network-first, falling back to the cached shell so the app
 *                opens without a connection. A fresh deploy is picked up on the
 *                next online load.
 *   everything else passes through untouched.
 *
 * Bump CACHE_VERSION to drop every old cache on the next activation.
 */
const CACHE_VERSION = 'v1'
const SHELL_CACHE = `syncrofin-shell-${CACHE_VERSION}`
const ASSET_CACHE = `syncrofin-assets-${CACHE_VERSION}`
const SHELL_URLS = ['/', '/manifest.webmanifest', '/pwa-192x192.png', '/favicon.ico']

/** What to do with a request. Pure, so it can be tested without a browser. */
function classify(method, url, mode) {
  if (method !== 'GET') return 'pass'
  const { origin, pathname } = new URL(url)
  if (origin !== self.location.origin) return 'pass'
  if (pathname.startsWith('/api/')) return 'pass'
  if (pathname === '/sw.js') return 'pass'
  if (pathname.startsWith('/static/')) return 'asset'
  if (mode === 'navigate') return 'navigate'
  return 'pass'
}

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith('syncrofin-') && k !== SHELL_CACHE && k !== ASSET_CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const kind = classify(request.method, request.url, request.mode)

  if (kind === 'asset') {
    event.respondWith(
      caches.open(ASSET_CACHE).then(async (cache) => {
        const hit = await cache.match(request)
        if (hit) return hit
        const response = await fetch(request)
        if (response.ok) cache.put(request, response.clone())
        return response
      }),
    )
    return
  }

  if (kind === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) caches.open(SHELL_CACHE).then((cache) => cache.put('/', response.clone()))
          return response
        })
        .catch(() => caches.match('/').then((hit) => hit || Response.error())),
    )
  }
})

// Exposed for tests only; harmless in the worker scope.
self.__syncrofinClassify = classify
