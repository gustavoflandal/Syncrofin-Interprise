import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, createApi } from '@/lib/api'

const fetchMock = vi.fn()

function reply(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function makeApi(overrides: { token?: string | null; refresh?: string | null; workspaceId?: string | null } = {}) {
  const onUnauthorized = vi.fn()
  // Like the session provider: a renewal replaces what the next call sends.
  const held = {
    token: overrides.token === undefined ? 'tok' : overrides.token,
    refresh: overrides.refresh === undefined ? 'ref' : overrides.refresh,
  }
  const onTokens = vi.fn((tokens: { token: string; refreshToken: string }) => {
    held.token = tokens.token
    held.refresh = tokens.refreshToken
  })
  const api = createApi({
    server: () => 'https://fin.exemplo.com',
    token: () => held.token,
    refreshToken: () => held.refresh,
    onTokens,
    workspaceId: () => overrides.workspaceId ?? null,
    onUnauthorized,
  })
  return { api, onUnauthorized, onTokens }
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit]
  return { url, init, headers: init.headers as Record<string, string> }
}

beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe('login', () => {
  it('posts the form the server expects, without a bearer token', async () => {
    fetchMock.mockResolvedValue(reply(200, { access_token: 'abc', refresh_token: 'r1', token_type: 'bearer' }))
    const { api } = makeApi({ token: 'stale' })

    const result = await api.login('ana@exemplo.com', 'se&nha 1')

    expect(result).toEqual({ kind: 'token', token: 'abc', refreshToken: 'r1' })
    // The phone cannot hold the browser's httpOnly cookie: it asks for the refresh token in the body.
    expect(lastCall().headers['X-Refresh-Mode']).toBe('body')
    const { url, init, headers } = lastCall()
    expect(url).toBe('https://fin.exemplo.com/api/auth/login')
    expect(init.method).toBe('POST')
    expect(headers['Content-Type']).toBe('application/x-www-form-urlencoded')
    expect(headers.Authorization).toBeUndefined()
    // Special characters are encoded, not sent raw.
    expect(init.body).toBe('username=ana%40exemplo.com&password=se%26nha+1')
  })

  it('reports a second-factor challenge instead of a token', async () => {
    fetchMock.mockResolvedValue(reply(200, { requires_2fa: true, temp_token: 'tmp', available_methods: ['totp'] }))
    const { api } = makeApi()
    expect(await api.login('a@b.co', 'x')).toEqual({ kind: 'two-factor', tempToken: 'tmp', methods: ['totp'] })
  })

  it('does not end the session on a bad password', async () => {
    fetchMock.mockResolvedValue(reply(400, { detail: 'LOGIN_BAD_CREDENTIALS' }))
    const { api, onUnauthorized } = makeApi()
    await expect(api.login('a@b.co', 'x')).rejects.toMatchObject({ status: 400, detail: 'LOGIN_BAD_CREDENTIALS' })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('verifies the code with the temporary token', async () => {
    fetchMock.mockResolvedValue(reply(200, { access_token: 'final', refresh_token: 'r2' }))
    const { api } = makeApi()
    expect(await api.verifyTwoFactor('tmp', '123456')).toEqual({ token: 'final', refreshToken: 'r2' })
    expect(JSON.parse(lastCall().init.body as string)).toEqual({ temp_token: 'tmp', code: '123456' })
  })
})

describe('authenticated requests', () => {
  it('sends the token and the workspace', async () => {
    fetchMock.mockResolvedValue(reply(200, []))
    const { api } = makeApi({ workspaceId: 'ws-1' })
    await api.accounts()
    const { url, headers } = lastCall()
    expect(url).toBe('https://fin.exemplo.com/api/accounts')
    expect(headers.Authorization).toBe('Bearer tok')
    expect(headers['X-Workspace-Id']).toBe('ws-1')
  })

  it('omits the workspace header when none is chosen', async () => {
    fetchMock.mockResolvedValue(reply(200, []))
    const { api } = makeApi()
    await api.categories()
    expect(lastCall().headers['X-Workspace-Id']).toBeUndefined()
  })

  it('lists a month of transactions with the API query names', async () => {
    fetchMock.mockResolvedValue(reply(200, { items: [], total: 0, page: 2, limit: 30 }))
    const { api } = makeApi()
    await api.transactions({ from: '2026-09-01', to: '2026-09-30', page: 2 })
    const url = new URL(lastCall().url)
    expect(url.pathname).toBe('/api/transactions')
    expect(Object.fromEntries(url.searchParams)).toEqual({ from: '2026-09-01', to: '2026-09-30', page: '2', limit: '30' })
  })

  it('creates a transaction as JSON', async () => {
    fetchMock.mockResolvedValue(reply(201, { id: 't1' }))
    const { api } = makeApi()
    await api.createTransaction({ description: 'Almoço', amount: '45.90', date: '2026-09-20', type: 'debit', account_id: 'a1' })
    const { init, headers } = lastCall()
    expect(init.method).toBe('POST')
    expect(headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body as string)).toMatchObject({ amount: '45.90', type: 'debit', account_id: 'a1' })
  })

  it('uploads a receipt as multipart with the file under "file"', async () => {
    fetchMock.mockResolvedValue(reply(201, { id: 'att1' }))
    const { api } = makeApi()
    await api.uploadAttachment('t1', new Blob(['x'], { type: 'image/jpeg' }), 'comprovante.jpg')
    const { url, init, headers } = lastCall()
    expect(url).toBe('https://fin.exemplo.com/api/transactions/t1/attachments')
    expect(init.body).toBeInstanceOf(FormData)
    const file = (init.body as FormData).get('file') as File
    expect(file.name).toBe('comprovante.jpg')
    // fetch must set the multipart boundary itself.
    expect(headers['Content-Type']).toBeUndefined()
  })
})

describe('an access token that ran out', () => {
  it('renews it with the refresh token and repeats the call once, keeping the rotated pair', async () => {
    fetchMock
      .mockResolvedValueOnce(reply(401, { detail: 'Unauthorized' }))
      .mockResolvedValueOnce(reply(200, { access_token: 'new-tok', refresh_token: 'new-ref' }))
      .mockResolvedValueOnce(reply(200, [{ id: 'a1' }]))
    const { api, onTokens, onUnauthorized } = makeApi()

    expect(await api.accounts()).toEqual([{ id: 'a1' }])

    const [, refreshCall] = fetchMock.mock.calls as [string, RequestInit][]
    expect(refreshCall[0]).toBe('https://fin.exemplo.com/api/auth/refresh')
    expect(JSON.parse(refreshCall[1].body as string)).toEqual({ refresh_token: 'ref' })
    expect(onTokens).toHaveBeenCalledWith({ token: 'new-tok', refreshToken: 'new-ref' })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('shares one renewal among calls that fail together (the refresh token is single-use)', async () => {
    let refreshes = 0
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (url.endsWith('/api/auth/refresh')) {
        refreshes += 1
        return reply(200, { access_token: 'new-tok', refresh_token: 'new-ref' })
      }
      const auth = (init.headers as Record<string, string>).Authorization
      return auth === 'Bearer tok' ? reply(401, { detail: 'Unauthorized' }) : reply(200, [])
    })
    const { api } = makeApi()

    const settled = await Promise.allSettled([api.accounts(), api.categories()])

    expect(refreshes).toBe(1)
    expect(settled.map((s) => s.status)).toEqual(['fulfilled', 'fulfilled'])
  })

  it('keeps its own refresh token when the server did not rotate it (lost a race)', async () => {
    fetchMock
      .mockResolvedValueOnce(reply(401, {}))
      .mockResolvedValueOnce(reply(200, { access_token: 'new-tok' }))
      .mockResolvedValueOnce(reply(200, []))
    const { api, onTokens } = makeApi()
    await api.accounts()
    expect(onTokens).toHaveBeenCalledWith({ token: 'new-tok', refreshToken: 'ref' })
  })

  it('ends the session only when the renewal is refused', async () => {
    fetchMock.mockResolvedValueOnce(reply(401, {})).mockResolvedValueOnce(reply(401, { detail: 'Session ended' }))
    const { api, onUnauthorized, onTokens } = makeApi()
    await expect(api.accounts()).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(onTokens).not.toHaveBeenCalled()
  })

  it('does not end the session when the phone is simply offline during the renewal', async () => {
    fetchMock.mockResolvedValueOnce(reply(401, {})).mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const { api, onTokens } = makeApi()
    await expect(api.accounts()).rejects.toBeInstanceOf(ApiError)
    expect(onTokens).not.toHaveBeenCalled()
  })

  it('does not loop: a second 401 after a successful renewal ends the session', async () => {
    fetchMock
      .mockResolvedValueOnce(reply(401, {}))
      .mockResolvedValueOnce(reply(200, { access_token: 'new-tok', refresh_token: 'new-ref' }))
      .mockResolvedValueOnce(reply(401, {}))
    const { api, onUnauthorized } = makeApi()
    await expect(api.accounts()).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('asks the server to end the session on sign-out', async () => {
    fetchMock.mockResolvedValue(reply(200, { detail: 'Logged out' }))
    const { api } = makeApi()
    await api.logout()
    const { url, init } = lastCall()
    expect(url).toBe('https://fin.exemplo.com/api/auth/logout')
    expect(JSON.parse(init.body as string)).toEqual({ refresh_token: 'ref' })
  })
})

describe('failures', () => {
  it('treats "this session owes the server a second factor" as the end of the session (the app cannot enrol one)', async () => {
    fetchMock.mockResolvedValue(reply(403, { detail: 'MFA_ENROLLMENT_REQUIRED' }))
    const { api, onUnauthorized } = makeApi()
    await expect(api.accounts()).rejects.toMatchObject({ status: 403, detail: 'MFA_ENROLLMENT_REQUIRED' })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reads whether the server holds the session back', async () => {
    fetchMock.mockResolvedValue(reply(200, { blocked: true }))
    const { api } = makeApi()
    expect(await api.mfaStatus()).toEqual({ blocked: true })
    expect(lastCall().url).toBe('https://fin.exemplo.com/api/auth/mfa-status')
  })

  it('ends the session on a 401 that cannot be renewed', async () => {
    fetchMock.mockResolvedValue(reply(401, { detail: 'Unauthorized' }))
    const { api, onUnauthorized } = makeApi({ refresh: null })
    await expect(api.accounts()).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('reads FastAPI validation errors', async () => {
    fetchMock.mockResolvedValue(reply(422, { detail: [{ msg: 'amount must be positive' }, { msg: 'bad date' }] }))
    const { api } = makeApi()
    await expect(api.createTransaction({ description: 'x', amount: '1.00', date: 'x', type: 'debit', account_id: 'a' })).rejects.toMatchObject({
      status: 422,
      detail: 'amount must be positive; bad date',
    })
  })

  it('keeps a 403 apart from a 401 (a viewer is not logged out)', async () => {
    fetchMock.mockResolvedValue(reply(403, { detail: 'read-only' }))
    const { api, onUnauthorized } = makeApi()
    await expect(api.accounts()).rejects.toMatchObject({ status: 403 })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('turns a network failure into NetworkError', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const { api } = makeApi()
    await expect(api.accounts()).rejects.toBeInstanceOf(NetworkError)
  })

  it('gives up after the timeout even if fetch never settles', async () => {
    // CapacitorHttp's native fetch patch does not honor AbortSignal (see the comment in
    // `request()`), so on-device a hung call never rejects on its own — this is what actually
    // bounds the wait, and is what "the app does not open offline" turned out to be missing.
    vi.useFakeTimers()
    fetchMock.mockReturnValue(new Promise(() => {})) // never resolves, never rejects
    const { api } = makeApi()

    const call = expect(api.accounts()).rejects.toBeInstanceOf(NetworkError)
    await vi.advanceTimersByTimeAsync(30_000)
    await call

    vi.useRealTimers()
  })

  it('survives a non-JSON error page from a proxy', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 }))
    const { api } = makeApi()
    await expect(api.accounts()).rejects.toMatchObject({ status: 502, detail: '' })
  })

  it('fails as a network error when there is no server yet', async () => {
    const api = createApi({
      server: () => null,
      token: () => null,
      refreshToken: () => null,
      onTokens: vi.fn(),
      workspaceId: () => null,
      onUnauthorized: vi.fn(),
    })
    await expect(api.accounts()).rejects.toBeInstanceOf(NetworkError)
  })
})
