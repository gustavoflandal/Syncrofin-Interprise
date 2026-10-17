import { Capacitor } from '@capacitor/core'
import { SecureStorage } from '@aparajita/capacitor-secure-storage'

/**
 * Where the session lives: the token, the server address, the chosen workspace.
 *
 * On the phone this is the Android Keystore (encrypted at rest, not readable by other apps
 * or by a backup). In a browser (development and tests) there is no Keystore, so it falls
 * back to localStorage: fine there, and never used in the APK.
 */
export type StoredKey = 'token' | 'refresh' | 'server' | 'workspace'

const PREFIX = 'syncrofin_'
let prefixSet = false

function native(): boolean {
  return Capacitor.isNativePlatform()
}

async function ready(): Promise<void> {
  if (prefixSet) return
  await SecureStorage.setKeyPrefix(PREFIX)
  prefixSet = true
}

export async function getStored(key: StoredKey): Promise<string | null> {
  try {
    if (native()) {
      await ready()
      const value = await SecureStorage.get(key)
      return typeof value === 'string' ? value : null
    }
    return localStorage.getItem(PREFIX + key)
  } catch {
    // A missing key throws on some platforms; either way there is nothing stored.
    return null
  }
}

export async function setStored(key: StoredKey, value: string): Promise<void> {
  if (native()) {
    await ready()
    await SecureStorage.set(key, value)
    return
  }
  localStorage.setItem(PREFIX + key, value)
}

export async function removeStored(key: StoredKey): Promise<void> {
  try {
    if (native()) {
      await ready()
      await SecureStorage.remove(key)
      return
    }
    localStorage.removeItem(PREFIX + key)
  } catch {
    // already gone
  }
}
