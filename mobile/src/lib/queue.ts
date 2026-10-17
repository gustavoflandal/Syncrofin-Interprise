import { Capacitor } from '@capacitor/core'
import { Directory, Encoding, Filesystem } from '@capacitor/filesystem'
import type { NewTransaction } from '@/lib/api'
import { base64ToBlob, blobToBase64 } from '@/lib/base64'

export type QueueStatus = 'pending' | 'syncing' | 'synced' | 'failed'

export interface QueuedPhoto {
  /** Filename inside the app's private storage, not a full path. */
  path: string
  filename: string
  contentType: string
}

export interface QueueItem {
  clientId: string
  /** Which server + workspace this belongs to, so switching accounts never mixes queues. */
  server: string
  workspaceId: string | null
  payload: NewTransaction
  photo: QueuedPhoto | null
  status: QueueStatus
  /** Set when `status` is 'failed': the server's reason, shown so the person can decide what to do. */
  error: string | null
  createdAt: string
}

const QUEUE_FILE = 'offline-queue.json'
const PHOTO_DIR = 'offline-photos'

function native(): boolean {
  return Capacitor.isNativePlatform()
}

// In a browser (dev, tests) there is no Filesystem plugin: keep the queue in memory instead. It
// does not survive a reload there, which is fine — nothing offline-related runs in that environment.
let memoryQueue: QueueItem[] = []
const memoryPhotos = new Map<string, Blob>()

async function readAll(): Promise<QueueItem[]> {
  if (!native()) return memoryQueue
  try {
    const result = await Filesystem.readFile({ path: QUEUE_FILE, directory: Directory.Data, encoding: Encoding.UTF8 })
    return JSON.parse(result.data as string) as QueueItem[]
  } catch {
    return [] // no queue file yet: nothing pending
  }
}

async function writeAll(items: QueueItem[]): Promise<void> {
  if (!native()) {
    memoryQueue = items
    return
  }
  await Filesystem.writeFile({
    path: QUEUE_FILE,
    directory: Directory.Data,
    data: JSON.stringify(items),
    encoding: Encoding.UTF8,
  })
}

type Listener = () => void
const listeners = new Set<Listener>()

/** Called whenever the queue changes, so a screen showing it can re-read and re-render. */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function notify(): void {
  for (const listener of listeners) listener()
}

/** Every item for this server + workspace, oldest first (the order they should sync in). */
export async function list(server: string, workspaceId: string | null): Promise<QueueItem[]> {
  const all = await readAll()
  return all
    .filter((item) => item.server === server && item.workspaceId === workspaceId)
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
}

async function savePhoto(clientId: string, photo: Blob): Promise<QueuedPhoto> {
  const filename = `${clientId}.jpg`
  const path = `${PHOTO_DIR}/${filename}`
  if (native()) {
    await Filesystem.writeFile({
      path,
      directory: Directory.Data,
      data: await blobToBase64(photo),
      recursive: true,
    })
  } else {
    memoryPhotos.set(path, photo)
  }
  return { path, filename, contentType: photo.type || 'image/jpeg' }
}

/** Reads a queued photo back as a `Blob`, ready to upload. Null if it was never saved. */
export async function readPhoto(photo: QueuedPhoto): Promise<Blob | null> {
  if (!native()) return memoryPhotos.get(photo.path) ?? null
  try {
    const result = await Filesystem.readFile({ path: photo.path, directory: Directory.Data })
    return base64ToBlob(result.data as string, photo.contentType)
  } catch {
    return null
  }
}

async function deletePhoto(photo: QueuedPhoto): Promise<void> {
  if (!native()) {
    memoryPhotos.delete(photo.path)
    return
  }
  await Filesystem.deleteFile({ path: photo.path, directory: Directory.Data }).catch(() => {
    // already gone
  })
}

/** Adds a transaction that could not reach the server right now. `clientId` is the id already
 * sent on the failed attempt, so a later sync replays the exact same create (see api.ts). */
export async function enqueue(entry: {
  clientId: string
  server: string
  workspaceId: string | null
  payload: NewTransaction
  photo: Blob | null
}): Promise<void> {
  const items = await readAll()
  items.push({
    clientId: entry.clientId,
    server: entry.server,
    workspaceId: entry.workspaceId,
    payload: entry.payload,
    photo: entry.photo ? await savePhoto(entry.clientId, entry.photo) : null,
    status: 'pending',
    error: null,
    createdAt: new Date().toISOString(),
  })
  await writeAll(items)
  notify()
}

export async function setStatus(clientId: string, status: QueueStatus, error: string | null = null): Promise<void> {
  const items = await readAll()
  const next = items.map((item) => (item.clientId === clientId ? { ...item, status, error } : item))
  await writeAll(next)
  notify()
}

/** Removes a synced item once it has been shown, or a pending/failed one the person deleted. */
export async function remove(clientId: string): Promise<void> {
  const items = await readAll()
  const found = items.find((item) => item.clientId === clientId)
  if (!found) return
  await writeAll(items.filter((item) => item.clientId !== clientId))
  if (found.photo) await deletePhoto(found.photo)
  notify()
}
