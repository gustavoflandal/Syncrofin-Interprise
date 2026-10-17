import { Capacitor } from '@capacitor/core'
import { Directory, Encoding, Filesystem } from '@capacitor/filesystem'
import type { Account, Category } from '@/lib/api'

interface CachedLookups {
  accounts: Account[]
  categories: Category[]
}

const CACHE_FILE = 'lookups-cache.json'

function native(): boolean {
  return Capacitor.isNativePlatform()
}

let memoryCache: Record<string, CachedLookups> = {}

function cacheKey(server: string, workspaceId: string | null): string {
  return `${server}|${workspaceId ?? ''}`
}

export async function saveLookups(
  server: string,
  workspaceId: string | null,
  accounts: Account[],
  categories: Category[],
): Promise<void> {
  const all = await readAllCaches()
  all[cacheKey(server, workspaceId)] = { accounts, categories }
  await writeAllCaches(all)
}

export async function loadLookups(
  server: string,
  workspaceId: string | null,
): Promise<CachedLookups | null> {
  const all = await readAllCaches()
  return all[cacheKey(server, workspaceId)] ?? null
}

async function readAllCaches(): Promise<Record<string, CachedLookups>> {
  if (!native()) return memoryCache
  try {
    const result = await Filesystem.readFile({ path: CACHE_FILE, directory: Directory.Data, encoding: Encoding.UTF8 })
    return JSON.parse(result.data as string) as Record<string, CachedLookups>
  } catch {
    return {}
  }
}

async function writeAllCaches(data: Record<string, CachedLookups>): Promise<void> {
  if (!native()) {
    memoryCache = data
    return
  }
  await Filesystem.writeFile({
    path: CACHE_FILE,
    directory: Directory.Data,
    data: JSON.stringify(data),
    encoding: Encoding.UTF8,
  })
}
