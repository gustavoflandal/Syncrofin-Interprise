import { Network } from '@capacitor/network'
import { ApiError, NetworkError, type Api } from '@/lib/api'
import * as queue from '@/lib/queue'

const BASE_DELAY_MS = 5_000
const MAX_DELAY_MS = 60_000

/**
 * Sends every pending item to the server, in the order it was queued. Stops (leaving the rest
 * `pending`) the moment the server is unreachable or the session is gone — either way the next
 * trigger (reconnect, app open, the manual button, or signing back in) picks up where this left
 * off. A rejection from the server itself (not a connectivity problem) marks just that one item
 * `failed` and moves on, so one bad row never blocks the ones after it.
 */
export async function drainQueue(api: Api, server: string, workspaceId: string | null): Promise<void> {
  const items = await queue.list(server, workspaceId)
  for (const item of items) {
    if (item.status === 'synced') continue
    await queue.setStatus(item.clientId, 'syncing')
    try {
      const created = await api.createTransaction(item.payload)
      if (item.photo) {
        const blob = await queue.readPhoto(item.photo)
        if (blob) {
          // The transaction itself is what matters; a photo that fails to upload here behaves
          // the same as it does online (attached_no_photo) — it can be retried from the detail
          // screen once the item shows up in the regular list.
          await api.uploadAttachment(created.id, blob, item.photo.filename).catch(() => {})
        }
      }
      await queue.setStatus(item.clientId, 'synced')
    } catch (error) {
      // No connection, or the session expired while offline: leave this (and everything after
      // it) `pending` and stop — nothing here was rejected, there was just no way to ask yet.
      if (error instanceof NetworkError || (error instanceof ApiError && error.status === 401)) {
        await queue.setStatus(item.clientId, 'pending')
        return
      }
      const message = error instanceof ApiError && error.detail ? error.detail : 'unknown'
      await queue.setStatus(item.clientId, 'failed', message)
    }
  }
}

let running = false
let retryDelay = BASE_DELAY_MS
let retryTimer: ReturnType<typeof setTimeout> | null = null

/** Runs `drainQueue` at most once at a time; a trigger that arrives mid-run is dropped, not
 * queued — the run in progress already covers whatever prompted it. */
async function runOnce(api: Api, server: string, workspaceId: string | null): Promise<void> {
  if (running) return
  running = true
  try {
    await drainQueue(api, server, workspaceId)
    const remaining = await queue.list(server, workspaceId)
    retryDelay = BASE_DELAY_MS
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    // Something is still pending (the drain stopped early): try again later, backing off so a
    // phone stuck offline for hours isn't polling every five seconds the whole time.
    if (remaining.some((item) => item.status === 'pending')) {
      retryTimer = setTimeout(() => void runOnce(api, server, workspaceId), retryDelay)
      retryDelay = Math.min(retryDelay * 2, MAX_DELAY_MS)
    }
  } finally {
    running = false
  }
}

let unsubscribeNetwork: (() => void) | null = null

/**
 * Wires up the automatic triggers (reconnect, and the backoff retry above) and does one run
 * right away. Call once per signed-in session; call `stopAutoSync` when it ends. `api`,
 * `server` and `workspaceId` are read fresh on every trigger via the getters, since the person
 * can switch workspaces or sign out while a phone is offline.
 */
export function startAutoSync(get: () => { api: Api; server: string | null; workspaceId: string | null }): void {
  const trigger = () => {
    const { api, server, workspaceId } = get()
    if (server) void runOnce(api, server, workspaceId)
  }
  trigger()
  void Network.addListener('networkStatusChange', (status) => {
    if (status.connected) trigger()
  }).then((handle) => {
    unsubscribeNetwork = () => void handle.remove()
  })
}

export function stopAutoSync(): void {
  if (retryTimer) {
    clearTimeout(retryTimer)
    retryTimer = null
  }
  unsubscribeNetwork?.()
  unsubscribeNetwork = null
  retryDelay = BASE_DELAY_MS
}

/** The manual "Sync now" button: same as an automatic trigger, just on demand. */
export function syncNow(api: Api, server: string, workspaceId: string | null): Promise<void> {
  return runOnce(api, server, workspaceId)
}
