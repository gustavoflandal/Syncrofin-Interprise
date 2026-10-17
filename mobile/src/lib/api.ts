import { Capacitor, CapacitorHttp } from '@capacitor/core'

// ---------------------------------------------------------------------------
// Types: only what the four screens read, as the server sends them.
// ---------------------------------------------------------------------------
export interface Workspace {
  id: string
  name: string
  kind: string
  is_archived?: boolean
}

export interface Account {
  id: string
  name: string
  type: string
  currency: string
}

export interface Category {
  id: string
  name: string
  color?: string
}

export interface Transaction {
  id: string
  description: string
  /** The API sends a decimal; depending on the route it arrives as a string or a number. */
  amount: number | string
  date: string
  /** "debit" (expense) or "credit" (income). */
  type: string
  currency: string
  status: string
  notes?: string | null
  account_id?: string | null
  category?: { id: string; name: string } | null
  payee_name?: string | null
  attachment_count: number
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  limit: number
}

export interface Attachment {
  id: string
  transaction_id: string
  filename: string
  content_type: string
  size: number
}

export interface NewTransaction {
  description: string
  /** Positive decimal string ("12.50"); the direction is `type`. */
  amount: string
  date: string
  type: 'debit' | 'credit'
  account_id: string
  category_id?: string | null
  currency?: string
  notes?: string | null
  /**
   * An id the app generated itself, before the request was ever sent. Resending a create with
   * the same id (the offline queue retrying one that may have gone through the first time, just
   * without the response ever reaching the app) hands back the transaction that already exists
   * instead of creating a second one — see the backend's `client_id` on `Transaction`.
   */
  client_id?: string
}

/** The two tokens of a session: the short-lived one that authorises calls, and the one that renews it. */
export interface Tokens {
  token: string
  refreshToken: string
}

export type LoginResult =
  | ({ kind: 'token' } & Tokens)
  | { kind: 'two-factor'; tempToken: string; methods: string[] }

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(`${status} ${detail}`)
    this.status = status
    this.detail = detail
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  // In chunks: spreading a whole photo into String.fromCharCode overflows the call stack.
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(binary)
}

/** The request never got an answer: offline, wrong address, server down, timeout. */
export class NetworkError extends Error {}

function detailOf(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : '')).filter(Boolean).join('; ')
    }
  }
  return ''
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------
export interface ApiContext {
  server: () => string | null
  token: () => string | null
  workspaceId: () => string | null
  /** The refresh token of the stored session, if any. */
  refreshToken: () => string | null
  /** A refresh worked: keep the new pair (the refresh token rotates on every use). */
  onTokens: (tokens: Tokens) => void
  /** Called when the server says the session is over (the token expired and could not be renewed). */
  onUnauthorized: () => void
}

const TIMEOUT_MS = 30_000
const UPLOAD_TIMEOUT_MS = 120_000

/** Tells the server which client this is, so the device list can say "App SyncroFin". */
const CLIENT_HEADERS = { 'X-Client': 'syncrofin-mobile', 'X-Refresh-Mode': 'body' }

export function createApi(ctx: ApiContext) {
  // One renewal at a time: the refresh token is single-use, so two calls that both find the
  // access token expired must share a single refresh, not spend the token twice.
  let renewing: Promise<boolean> | null = null

  function renew(server: string): Promise<boolean> {
    if (!renewing) {
      renewing = (async () => {
        const refreshToken = ctx.refreshToken()
        if (!refreshToken) return false
        try {
          const response = await fetch(`${server}/api/auth/refresh`, {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...CLIENT_HEADERS },
            body: JSON.stringify({ refresh_token: refreshToken }),
          })
          if (!response.ok) return false
          const data = (await response.json()) as { access_token?: string; refresh_token?: string }
          if (!data.access_token) return false
          // A refresh that lost a race with another one carries no new refresh token: keep ours.
          ctx.onTokens({ token: data.access_token, refreshToken: data.refresh_token ?? refreshToken })
          return true
        } catch {
          // Offline is not "signed out": leave the session for the next try.
          return false
        }
      })().finally(() => {
        renewing = null
      })
    }
    return renewing
  }

  async function request<T>(
    method: string,
    path: string,
    options: { query?: Record<string, string | number | undefined>; json?: unknown; form?: string; multipart?: FormData; timeout?: number; auth?: boolean; retried?: boolean } = {},
  ): Promise<T> {
    const server = ctx.server()
    if (!server) throw new NetworkError('no server configured')

    const url = new URL(`${server}${path}`)
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined && value !== '') url.searchParams.set(key, String(value))
    }

    const headers: Record<string, string> = { Accept: 'application/json', ...CLIENT_HEADERS }
    const token = ctx.token()
    if (token && options.auth !== false) headers.Authorization = `Bearer ${token}`
    const workspace = ctx.workspaceId()
    if (workspace) headers['X-Workspace-Id'] = workspace

    let body: BodyInit | undefined
    if (options.json !== undefined) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(options.json)
    } else if (options.form !== undefined) {
      // A string, not URLSearchParams: the native HTTP layer sends a string body as it is.
      headers['Content-Type'] = 'application/x-www-form-urlencoded'
      body = options.form
    } else if (options.multipart) {
      body = options.multipart // the content type (with its boundary) is set by fetch
    }

    const controller = new AbortController()
    const timeoutMs = options.timeout ?? TIMEOUT_MS
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    let response: Response
    try {
      // `CapacitorHttp: { enabled: true }` (capacitor.config.ts) replaces `window.fetch` with a
      // patch that proxies to a native HTTP call and never looks at `signal` — confirmed by
      // reading @capacitor/android's native-bridge.js, which builds a `Request` and reads
      // headers/body/method off it but never `AbortSignal`. So on-device, `controller.abort()`
      // above does not cancel or reject anything: without this race, a call made while offline
      // (or over a connection that never completes the handshake) hangs on whatever timeout the
      // native Android HTTP layer uses internally, which is outside this app's control and can
      // far exceed `timeoutMs` — which is exactly what left the app stuck on "loading" instead of
      // opening. The race is what actually bounds the wait everywhere `request()` is used.
      response = await Promise.race([
        fetch(url.toString(), { method, headers, body, signal: controller.signal }),
        new Promise<Response>((_, reject) => {
          setTimeout(() => reject(new NetworkError('timeout')), timeoutMs)
        }),
      ])
    } catch (error) {
      throw error instanceof NetworkError ? error : new NetworkError(error instanceof Error ? error.message : 'network error')
    } finally {
      clearTimeout(timer)
    }

    if (response.status === 204) return undefined as T
    let parsed: unknown = null
    try {
      parsed = await response.json()
    } catch {
      // not JSON: an HTML error page from a proxy, or an empty body
    }

    if (!response.ok) {
      // A 401 on a call that carried a token means the token ran out (they last minutes): renew it
      // and send the call again, once. Only when the session cannot be renewed is it over. On
      // login a 401 just means "wrong password", which the caller handles.
      // The server holds back a session that still owes the instance a second factor. The app cannot enrol one,
      // so it is the same as being signed out (the next sign-in says why).
      if (response.status === 403 && detailOf(parsed) === 'MFA_ENROLLMENT_REQUIRED' && token && options.auth !== false) {
        ctx.onUnauthorized()
      }
      if (response.status === 401 && token && options.auth !== false) {
        if (!options.retried && (await renew(server))) return request<T>(method, path, { ...options, retried: true })
        ctx.onUnauthorized()
      }
      throw new ApiError(response.status, detailOf(parsed))
    }
    return parsed as T
  }

  const api = {
    async login(email: string, password: string): Promise<LoginResult> {
      const form = new URLSearchParams({ username: email, password }).toString()
      const data = await request<{
        access_token?: string
        refresh_token?: string
        requires_2fa?: boolean
        temp_token?: string
        available_methods?: string[]
      }>('POST', '/api/auth/login', { form, auth: false })
      if (data.requires_2fa && data.temp_token) {
        return { kind: 'two-factor', tempToken: data.temp_token, methods: data.available_methods ?? [] }
      }
      if (!data.access_token || !data.refresh_token) throw new ApiError(500, 'login response without a session')
      return { kind: 'token', token: data.access_token, refreshToken: data.refresh_token }
    },

    async verifyTwoFactor(tempToken: string, code: string): Promise<Tokens> {
      const data = await request<{ access_token: string; refresh_token: string }>('POST', '/api/auth/2fa/verify', {
        json: { temp_token: tempToken, code },
        auth: false,
      })
      return { token: data.access_token, refreshToken: data.refresh_token }
    },

    /** End this session on the server. Best effort: the caller signs out locally either way. */
    async logout(): Promise<void> {
      await request<unknown>('POST', '/api/auth/logout', { json: { refresh_token: ctx.refreshToken() }, timeout: 8_000 })
    },

    me: () => request<{ id: string; email: string; primary_currency?: string }>('GET', '/api/users/me'),
    /** Whether the instance's second-factor rule holds this session back (it can then only enrol one, on the website). */
    mfaStatus: () => request<{ blocked: boolean }>('GET', '/api/auth/mfa-status'),
    workspaces: () => request<Workspace[]>('GET', '/api/workspaces'),
    /** The workspace the server uses when the request names none. */
    currentWorkspace: () => request<Workspace>('GET', '/api/workspaces/current'),
    accounts: () => request<Account[]>('GET', '/api/accounts'),
    categories: () => request<Category[]>('GET', '/api/categories'),

    transactions: (params: { from: string; to: string; page?: number; limit?: number }) =>
      request<Page<Transaction>>('GET', '/api/transactions', {
        query: { from: params.from, to: params.to, page: params.page ?? 1, limit: params.limit ?? 30 },
      }),

    createTransaction: (payload: NewTransaction) => request<Transaction>('POST', '/api/transactions', { json: payload }),

    attachments: (transactionId: string) => request<Attachment[]>('GET', `/api/transactions/${transactionId}/attachments`),

    uploadAttachment(transactionId: string, file: Blob, filename: string): Promise<Attachment> {
      const form = new FormData()
      form.append('file', file, filename)
      return request<Attachment>('POST', `/api/transactions/${transactionId}/attachments`, {
        multipart: form,
        timeout: UPLOAD_TIMEOUT_MS,
      })
    },

    /** A receipt as a data: URL, ready for an <img>. It needs the token, so it cannot be a plain src. */
    async attachmentDataUrl(transactionId: string, attachment: Attachment): Promise<string> {
      const server = ctx.server()
      if (!server || !ctx.token()) throw new NetworkError('no session')
      try {
        return await downloadAttachment(server, transactionId, attachment)
      } catch (error) {
        // Same rule as every other call: an expired token is renewed and the download retried once.
        if (error instanceof ApiError && error.status === 401 && (await renew(server))) {
          return downloadAttachment(server, transactionId, attachment)
        }
        throw error
      }
    },
  }

  async function downloadAttachment(server: string, transactionId: string, attachment: Attachment): Promise<string> {
    const token = ctx.token()
    if (!token) throw new NetworkError('no session')
    const url = `${server}/api/transactions/${transactionId}/attachments/${attachment.id}`
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` }
    const workspace = ctx.workspaceId()
    if (workspace) headers['X-Workspace-Id'] = workspace

    if (Capacitor.isNativePlatform()) {
      // The native layer hands binary back as base64; going through fetch().blob() is
      // not reliable there.
      try {
        const response = await CapacitorHttp.get({ url, headers, responseType: 'blob' })
        if (response.status >= 400) throw new ApiError(response.status, '')
        return `data:${attachment.content_type};base64,${response.data as string}`
      } catch (error) {
        if (error instanceof ApiError) throw error
        throw new NetworkError(error instanceof Error ? error.message : 'network error')
      }
    }

    let response: Response
    try {
      response = await fetch(url, { headers })
    } catch (error) {
      throw new NetworkError(error instanceof Error ? error.message : 'network error')
    }
    if (!response.ok) throw new ApiError(response.status, '')
    return `data:${attachment.content_type};base64,${bytesToBase64(new Uint8Array(await response.arrayBuffer()))}`
  }

  return api
}

export type Api = ReturnType<typeof createApi>
