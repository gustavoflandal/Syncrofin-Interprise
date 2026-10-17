import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { registerServiceWorker } from '@/lib/register-sw'

/**
 * Load `public/sw.js` the way a worker would see it: a global `self` with a
 * location, no DOM. The file exposes its pure routing function for exactly this.
 */
function loadWorker() {
  const source = readFileSync(resolve(__dirname, '../../public/sw.js'), 'utf-8')
  const scope: Record<string, unknown> = {
    location: new URL('https://app.example.com/'),
    addEventListener: () => {},
  }
  new Function('self', source)(scope)
  return scope.__syncrofinClassify as (m: string, u: string, mode?: string) => string
}

describe('service worker routing', () => {
  const classify = loadWorker()
  const origin = 'https://app.example.com'

  it('never touches the API, whatever the method or mode', () => {
    // Financial data must not land in Cache Storage.
    expect(classify('GET', `${origin}/api/transactions`, 'cors')).toBe('pass')
    expect(classify('GET', `${origin}/api/auth/me`, 'navigate')).toBe('pass')
    expect(classify('POST', `${origin}/api/transactions`, 'cors')).toBe('pass')
  })

  it('caches hashed build assets', () => {
    expect(classify('GET', `${origin}/static/index-Ab12.js`, 'no-cors')).toBe('asset')
  })

  it('serves page navigations network-first', () => {
    expect(classify('GET', `${origin}/`, 'navigate')).toBe('navigate')
    expect(classify('GET', `${origin}/transactions`, 'navigate')).toBe('navigate')
  })

  it('leaves other origins, non-GETs and its own file alone', () => {
    expect(classify('GET', 'https://fonts.googleapis.com/css2?family=Geist', 'no-cors')).toBe('pass')
    expect(classify('GET', 'https://evil.example/static/x.js', 'no-cors')).toBe('pass')
    expect(classify('PUT', `${origin}/static/x.js`, 'cors')).toBe('pass')
    expect(classify('GET', `${origin}/sw.js`, 'no-cors')).toBe('pass')
  })
})

describe('registerServiceWorker', () => {
  afterEach(() => vi.restoreAllMocks())

  it('does nothing outside production', () => {
    const register = vi.fn()
    registerServiceWorker({ serviceWorker: { register } } as unknown as Navigator, false)
    expect(register).not.toHaveBeenCalled()
  })

  it('does nothing when the browser has no service workers', () => {
    expect(() => registerServiceWorker({} as Navigator, true)).not.toThrow()
  })

  it('registers /sw.js at the root in production once the page has loaded', () => {
    const register = vi.fn().mockResolvedValue(undefined)
    vi.spyOn(document, 'readyState', 'get').mockReturnValue('complete')
    registerServiceWorker({ serviceWorker: { register } } as unknown as Navigator, true)
    expect(register).toHaveBeenCalledWith('/sw.js', { scope: '/' })
  })

  it('swallows a refusal instead of surfacing it', async () => {
    const register = vi.fn().mockRejectedValue(new Error('blocked'))
    vi.spyOn(document, 'readyState', 'get').mockReturnValue('complete')
    registerServiceWorker({ serviceWorker: { register } } as unknown as Navigator, true)
    await Promise.resolve()
    expect(register).toHaveBeenCalled() // and no unhandled rejection
  })
})
