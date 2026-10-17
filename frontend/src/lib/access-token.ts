import axios from 'axios'

/**
 * The access token lives here, in memory, and nowhere else.
 *
 * It used to be in `localStorage`, where any script that ever ran on the page (an XSS, a
 * compromised dependency) could read it and keep it for a day. Now it is a 15-minute token
 * that dies with the tab; what keeps a person signed in across reloads is the refresh token,
 * an `httpOnly` cookie that JavaScript cannot read at all. Reloading the page trades that
 * cookie for a fresh access token (`restoreSession`).
 */
let accessToken: string | null = null
let inflight: Promise<string | null> | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

/**
 * Ask the server for a new access token using the refresh cookie.
 *
 * Single flight: a screen that fires ten requests as its token expires gets ten 401s, and
 * they must share one refresh. The refresh token rotates on every use, so two refreshes in
 * a row would be one too many. Resolves `null` when there is no session (no cookie, expired,
 * revoked): the caller decides what "signed out" looks like.
 */
export function refreshAccessToken(): Promise<string | null> {
  if (!inflight) {
    inflight = axios
      .post<{ access_token: string }>('/api/auth/refresh')
      .then((response) => {
        accessToken = response.data.access_token
        return accessToken
      })
      .catch(() => {
        accessToken = null
        return null
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

// --- other tabs -----------------------------------------------------------------------------
// Signing out in one tab must end the others, and signing in in one should not leave the next
// tab on the login screen. `localStorage` events reach every *other* tab of the origin.
const CHANNEL_KEY = 'syncrofin_session_event'

export type SessionEvent = 'signed-in' | 'signed-out'

export function announceSessionEvent(event: SessionEvent): void {
  try {
    localStorage.setItem(CHANNEL_KEY, `${event}:${Date.now()}`)
  } catch {
    // storage blocked: the other tabs will find out on their next request
  }
}

export function onSessionEvent(listener: (event: SessionEvent) => void): () => void {
  const handler = (e: StorageEvent) => {
    if (e.key !== CHANNEL_KEY || !e.newValue) return
    const kind = e.newValue.split(':')[0]
    if (kind === 'signed-in' || kind === 'signed-out') listener(kind)
  }
  window.addEventListener('storage', handler)
  return () => window.removeEventListener('storage', handler)
}
