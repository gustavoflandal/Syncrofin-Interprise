import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { MFA_REQUIRED_EVENT } from '@/lib/mfa-events'

/**
 * What the request layer does with a 401, now that the access token lasts minutes: renew it
 * from the refresh cookie and send the request again, once; only a session that cannot be
 * renewed sends the person back to the login screen.
 */

const refresh = vi.hoisted(() => vi.fn())
vi.mock('@/lib/access-token', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/access-token')>()),
  refreshAccessToken: refresh,
}))

type Handler = (config: InternalAxiosRequestConfig) => { status: number; data?: unknown }
let handler: Handler
const seen: InternalAxiosRequestConfig[] = []
// The header as it was when each request went out (a retry reuses, and mutates, the same config).
const sentAuth: unknown[] = []

// Set before `@/lib/api` is imported: `axios.create` copies the defaults at that moment.
axios.defaults.adapter = async (config) => {
  seen.push(config)
  sentAuth.push(config.headers.Authorization)
  const { status, data } = handler(config)
  const response = { data, status, statusText: String(status), headers: {}, config }
  if (status >= 400) throw new AxiosError('failed', String(status), config, null, response)
  return response
}

const { auth } = await import('@/lib/api')
const { getAccessToken, setAccessToken } = await import('@/lib/access-token')

const bearer = (config: InternalAxiosRequestConfig) => config.headers.Authorization

beforeEach(() => {
  seen.length = 0
  sentAuth.length = 0
  refresh.mockReset()
  setAccessToken('old')
  // jsdom: the redirect on a dead session is an assignment to location.href.
  Object.defineProperty(window, 'location', { value: { href: '/' }, writable: true })
})

describe('a request whose access token ran out', () => {
  it('renews the token and sends the request again with the new one', async () => {
    refresh.mockImplementation(async () => {
      setAccessToken('new')
      return 'new'
    })
    handler = (config) => (bearer(config) === 'Bearer new' ? { status: 200, data: { id: 'u1' } } : { status: 401 })

    const me = await auth.me()

    expect(me).toEqual({ id: 'u1' })
    expect(sentAuth).toEqual(['Bearer old', 'Bearer new'])
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(window.location.href).toBe('/')
  })

  it('asks only once per request: a 401 that survives the renewal is final', async () => {
    refresh.mockResolvedValue('new')
    handler = () => ({ status: 401 })

    await expect(auth.me()).rejects.toBeInstanceOf(AxiosError)

    expect(seen).toHaveLength(2)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(window.location.href).toBe('/login')
    expect(getAccessToken()).toBeNull()
  })

  it('goes to the login screen when there is no session left to renew', async () => {
    refresh.mockResolvedValue(null)
    handler = () => ({ status: 401 })

    await expect(auth.me()).rejects.toBeInstanceOf(AxiosError)

    expect(seen).toHaveLength(1)
    expect(window.location.href).toBe('/login')
    expect(getAccessToken()).toBeNull()
  })

  it('does not try to renew a request that carried no token (a login screen 401)', async () => {
    setAccessToken(null)
    handler = () => ({ status: 401 })

    await expect(auth.me()).rejects.toBeInstanceOf(AxiosError)

    expect(refresh).not.toHaveBeenCalled()
  })

  it('leaves other errors alone', async () => {
    handler = () => ({ status: 403 })

    await expect(auth.me()).rejects.toBeInstanceOf(AxiosError)

    expect(refresh).not.toHaveBeenCalled()
    expect(window.location.href).toBe('/')
  })
})

describe('logging out', () => {
  it('sends the token it is ending, even though the caller clears it right away', async () => {
    handler = () => ({ status: 200, data: { detail: 'Logged out' } })
    setAccessToken(null)

    await auth.logout('ending-token')

    expect(sentAuth[0]).toBe('Bearer ending-token')
    expect(seen[0].url).toBe('/auth/logout')
  })
})

describe('the second-factor rule', () => {
  it('tells the app when the server says this session still owes a second factor', async () => {
    const heard = vi.fn()
    window.addEventListener(MFA_REQUIRED_EVENT, heard)
    handler = () => ({ status: 403, data: { detail: 'MFA_ENROLLMENT_REQUIRED' } })

    await expect(auth.me()).rejects.toBeInstanceOf(AxiosError)

    window.removeEventListener(MFA_REQUIRED_EVENT, heard)
    expect(heard).toHaveBeenCalledTimes(1)
    expect(refresh).not.toHaveBeenCalled()
    expect(window.location.href).toBe('/')
  })

  it('stays quiet for any other 403', async () => {
    const heard = vi.fn()
    window.addEventListener(MFA_REQUIRED_EVENT, heard)
    handler = () => ({ status: 403, data: { detail: 'Read-only role' } })

    await expect(auth.me()).rejects.toBeInstanceOf(AxiosError)

    window.removeEventListener(MFA_REQUIRED_EVENT, heard)
    expect(heard).not.toHaveBeenCalled()
  })
})
