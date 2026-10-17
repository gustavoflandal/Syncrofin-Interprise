import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { BiometricAuth, type AuthenticateOptions } from '@aparajita/capacitor-biometric-auth'
import { ApiError, NetworkError, createApi, type Api, type Tokens, type Workspace } from '@/lib/api'
import { normalizeServerUrl } from '@/lib/server-url'
import { getStored, removeStored, setStored } from '@/lib/storage'
import { startAutoSync, stopAutoSync } from '@/lib/sync'

/** Why a sign-in did not work, in terms the screen can turn into a message. */
export type LoginFailure =
  | 'serverEmpty'
  | 'serverInvalid'
  | 'serverInsecure'
  | 'badCredentials'
  | 'badCode'
  | 'twoFactorExpired'
  | 'localAuthOff'
  | 'mfaRequired'
  | 'network'
  | 'unknown'

export class LoginError extends Error {
  readonly code: LoginFailure

  constructor(code: LoginFailure) {
    super(code)
    this.code = code
  }
}

export type SignInOutcome = { status: 'signed-in' } | { status: 'two-factor'; tempToken: string }

export interface Session {
  /** False until the stored session has been read: nothing should decide "logged out" before that. */
  ready: boolean
  authenticated: boolean
  /**
   * True when there is a restored session (`authenticated`) that has not been confirmed with
   * biometrics yet this app-open. A screen shown while this is true must not reveal any of the
   * person's data — only `unlock()` (or `signOut()`) may clear it.
   */
  locked: boolean
  server: string | null
  workspaces: Workspace[]
  workspaceId: string | null
  /** Set when the server ended the session, so the login screen can say why. */
  sessionExpired: boolean
  api: Api
  signIn: (serverInput: string, email: string, password: string) => Promise<SignInOutcome>
  completeTwoFactor: (tempToken: string, code: string) => Promise<void>
  /** Confirms a restored session with biometrics. Throws `BiometryError` on failure/cancel — `locked` stays true. */
  unlock: (options?: AuthenticateOptions) => Promise<void>
  signOut: () => Promise<void>
  chooseWorkspace: (id: string | null) => Promise<void>
}

const SessionContext = createContext<Session | null>(null)

function toLoginError(error: unknown, during: 'password' | 'code'): LoginError {
  if (error instanceof LoginError) return error
  if (error instanceof NetworkError) return new LoginError('network')
  if (error instanceof ApiError) {
    if (error.detail === 'LOCAL_AUTH_DISABLED') return new LoginError('localAuthOff')
    if (during === 'password' && (error.status === 400 || error.status === 401)) return new LoginError('badCredentials')
    if (during === 'code') return new LoginError(error.status === 401 ? 'twoFactorExpired' : 'badCode')
  }
  return new LoginError('unknown')
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [server, setServer] = useState<string | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [locked, setLocked] = useState(false)

  // The API client reads these at call time, so it never holds a stale token.
  const live = useRef<{ server: string | null; token: string | null; refresh: string | null; workspaceId: string | null }>({
    server,
    token,
    refresh: null,
    workspaceId,
  })
  live.current = { ...live.current, server, token, workspaceId }

  const clear = useCallback(async (expired: boolean) => {
    setToken(null)
    setWorkspaces([])
    setWorkspaceId(null)
    setSessionExpired(expired)
    setLocked(false) // nothing left to gate: authenticated is false once token is
    live.current = { ...live.current, token: null, refresh: null, workspaceId: null }
    await Promise.all([removeStored('token'), removeStored('refresh'), removeStored('workspace')])
  }, [])

  const api = useMemo(
    () =>
      createApi({
        server: () => live.current.server,
        token: () => live.current.token,
        refreshToken: () => live.current.refresh,
        onTokens: (tokens) => {
          // The access token lasts minutes and the refresh token rotates on every use: both are
          // kept as they arrive, or the next renewal would present a token already spent.
          live.current = { ...live.current, token: tokens.token, refresh: tokens.refreshToken }
          setToken(tokens.token)
          void Promise.all([setStored('token', tokens.token), setStored('refresh', tokens.refreshToken)])
        },
        workspaceId: () => live.current.workspaceId,
        onUnauthorized: () => void clear(true),
      }),
    [clear],
  )

  const loadWorkspaces = useCallback(
    async (preferred: string | null) => {
      try {
        const list = (await api.workspaces()).filter((w) => !w.is_archived)
        setWorkspaces(list)
        let chosen = list.find((w) => w.id === preferred)?.id ?? null
        if (!chosen) {
          // Nothing chosen yet: show (and use) the workspace the server would pick anyway,
          // so the selector never says "Workspace" while data from another one is on screen.
          const current = await api.currentWorkspace().catch(() => null)
          chosen = list.find((w) => w.id === current?.id)?.id ?? null
        }
        setWorkspaceId(chosen)
        live.current = { ...live.current, workspaceId: chosen }
      } catch {
        // Not fatal: without the list the server's default workspace is used.
        setWorkspaces([])
      }
    },
    [api],
  )

  // Restore the session from secure storage.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const [storedServer, storedToken, storedRefresh, storedWorkspace] = await Promise.all([
        getStored('server'),
        getStored('token'),
        getStored('refresh'),
        getStored('workspace'),
      ])
      if (cancelled) return
      setServer(storedServer)
      live.current = { server: storedServer, token: storedToken, refresh: storedRefresh, workspaceId: storedWorkspace }
      setToken(storedToken)
      // Not awaited: a person who is already signed in should see the app right away, offline or
      // not — `authenticated` only needs the stored token. Waiting here for a network call meant
      // the app stayed on the loading splash for as long as that call took, which, offline, could
      // be a very long time (see the timeout note in `api.ts`'s `request()`). `loadWorkspaces`
      // still runs, and updates the workspace list in the background once (if) it succeeds.
      if (storedToken && storedServer) {
        void loadWorkspaces(storedWorkspace)
        // A restored session shows nothing until biometrics confirm it, on a device that offers
        // them: a phone that is already unlocked should not hand over financial data by itself.
        // `checkBiometry` is a local, offline device call — nothing here needs the network.
        try {
          const check = await BiometricAuth.checkBiometry()
          if (!cancelled && check.isAvailable) setLocked(true)
        } catch {
          // No biometry on this device: nothing to gate behind, same as before this existed.
        }
      }
      if (!cancelled) setReady(true)
    })()
    return () => {
      cancelled = true
    }
  }, [loadWorkspaces])

  // Drains the offline queue (mobile/src/lib/queue.ts) automatically: right away, on reconnect,
  // and with a backing-off retry while something is still stuck — see lib/sync.ts. Only while
  // signed in; a queue with nobody signed in has nothing to authenticate the upload with. Items
  // belong to a specific server + workspace (checked at drain time), so switching workspaces
  // just means a different subset gets sent.
  useEffect(() => {
    if (!token) return
    startAutoSync(() => ({ api, server: live.current.server, workspaceId: live.current.workspaceId }))
    return () => stopAutoSync()
  }, [token, api])

  const finish = useCallback(
    async (serverUrl: string, tokens: Tokens) => {
      live.current = { ...live.current, server: serverUrl, token: tokens.token, refresh: tokens.refreshToken }
      setServer(serverUrl)
      setToken(tokens.token)
      setSessionExpired(false)
      // A server that requires a second factor holds back a session that has none, and the app cannot enrol one:
      // say so now, instead of leaving the person on screens that only fail.
      const mfa = await api.mfaStatus().catch(() => null)
      if (mfa?.blocked) {
        await clear(false)
        throw new LoginError('mfaRequired')
      }
      await Promise.all([
        setStored('server', serverUrl),
        setStored('token', tokens.token),
        setStored('refresh', tokens.refreshToken),
      ])
      await loadWorkspaces(await getStored('workspace'))
    },
    [api, clear, loadWorkspaces],
  )

  const signIn = useCallback<Session['signIn']>(
    async (serverInput, email, password) => {
      const normalized = normalizeServerUrl(serverInput)
      if (!normalized.ok) {
        throw new LoginError(normalized.error === 'empty' ? 'serverEmpty' : normalized.error === 'insecure' ? 'serverInsecure' : 'serverInvalid')
      }
      // Point the client at the address being tried before the first request.
      live.current = { ...live.current, server: normalized.url, token: null, refresh: null }
      setServer(normalized.url) // keeps the render-time sync of `live` from putting the old address back
      try {
        const result = await api.login(email.trim(), password)
        if (result.kind === 'two-factor') return { status: 'two-factor', tempToken: result.tempToken }
        await finish(normalized.url, { token: result.token, refreshToken: result.refreshToken })
        return { status: 'signed-in' }
      } catch (error) {
        throw toLoginError(error, 'password')
      }
    },
    [api, finish],
  )

  const completeTwoFactor = useCallback<Session['completeTwoFactor']>(
    async (tempToken, code) => {
      const serverUrl = live.current.server
      if (!serverUrl) throw new LoginError('unknown')
      try {
        await finish(serverUrl, await api.verifyTwoFactor(tempToken, code.trim()))
      } catch (error) {
        throw toLoginError(error, 'code')
      }
    },
    [api, finish],
  )

  const unlock = useCallback<Session['unlock']>(async (options) => {
    // Throws `BiometryError` on failure/cancel: the caller decides what to show for that.
    // Purely local — this works exactly the same offline as online.
    await BiometricAuth.authenticate(options)
    setLocked(false)
  }, [])

  const signOut = useCallback(async () => {
    // Ask the server to end the session first, so a lost or stolen phone is not left with a live
    // refresh token; but never let a dead connection keep the person signed in here.
    await api.logout().catch(() => {})
    await clear(false)
  }, [api, clear])

  const chooseWorkspace = useCallback(async (id: string | null) => {
    setWorkspaceId(id)
    live.current = { ...live.current, workspaceId: id }
    if (id) await setStored('workspace', id)
    else await removeStored('workspace')
  }, [])

  const value: Session = {
    ready,
    authenticated: !!token,
    locked,
    server,
    workspaces,
    workspaceId,
    sessionExpired,
    api,
    signIn,
    completeTwoFactor,
    unlock,
    signOut,
    chooseWorkspace,
  }
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession outside SessionProvider')
  return value
}
