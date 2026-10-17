/**
 * Register the service worker that makes SyncroFin installable and lets the
 * app shell open offline (see `public/sw.js` for what it does and, more
 * importantly, what it refuses to cache).
 *
 * Production only. In development a worker caching assets fights hot reload
 * and turns "why is my change not showing" into an afternoon.
 */
export function registerServiceWorker(
  nav: Pick<Navigator, 'serviceWorker'> | undefined = typeof navigator === 'undefined' ? undefined : navigator,
  isProd: boolean = import.meta.env.PROD,
): void {
  if (!isProd || !nav || !('serviceWorker' in nav)) return
  const register = () => {
    nav.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {
      // Installability is a convenience. A browser that refuses the worker
      // (private mode, blocked storage) must not surface an error to the user.
    })
  }
  if (typeof document !== 'undefined' && document.readyState === 'complete') register()
  else window.addEventListener('load', register, { once: true })
}
