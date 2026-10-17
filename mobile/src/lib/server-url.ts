export type ServerUrlResult = { ok: true; url: string } | { ok: false; error: 'empty' | 'invalid' | 'insecure' }

/** Hosts where plain http is acceptable: the emulator's alias for the PC, and the PC itself. */
function isLocalHost(host: string): boolean {
  return host === 'localhost' || host === '10.0.2.2' || /^127\./.test(host)
}

/**
 * The address the reader typed, turned into the server's base URL.
 *
 * https is required, because the app carries a password and financial data; http is
 * only allowed for the emulator and localhost (development). A bare "syncrofin.x.com"
 * gets https. Anything after the host is kept (a server behind a sub-path), a trailing
 * slash is not.
 */
export function normalizeServerUrl(input: string): ServerUrlResult {
  const raw = input.trim()
  if (!raw) return { ok: false, error: 'empty' }
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`
  let parsed: URL
  try {
    parsed = new URL(withScheme)
  } catch {
    return { ok: false, error: 'invalid' }
  }
  if (!parsed.hostname || !/^https?:$/.test(parsed.protocol)) return { ok: false, error: 'invalid' }
  if (parsed.protocol === 'http:' && !isLocalHost(parsed.hostname)) return { ok: false, error: 'insecure' }
  const path = parsed.pathname.replace(/\/+$/, '')
  return { ok: true, url: `${parsed.origin}${path}` }
}
