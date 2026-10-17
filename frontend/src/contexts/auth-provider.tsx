import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { auth } from '@/lib/api'
import {
  announceSessionEvent,
  getAccessToken,
  onSessionEvent,
  refreshAccessToken,
  setAccessToken,
} from '@/lib/access-token'
import type { User } from '@/types'

import { AuthContext, type LoginResult } from '@/contexts/auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // A signed-in marker for the routes (`token` is truthy or null). The token that authorises
  // requests is in `lib/access-token.ts` and is renewed there without touching React state,
  // so a silent refresh does not re-render the app or reload the workspace.
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const queryClient = useQueryClient()

  const restore = useCallback(async (): Promise<boolean> => {
    const fresh = await refreshAccessToken()
    if (!fresh) return false
    try {
      const me = await auth.me()
      setToken(fresh)
      setUser(me)
      return true
    } catch {
      setAccessToken(null)
      return false
    }
  }, [])

  // Reload, or a new tab: the refresh cookie is what says who is signed in.
  useEffect(() => {
    let cancelled = false
    // A token left in localStorage by a version that stored it there is now just a liability.
    try {
      localStorage.removeItem('token')
    } catch {
      // storage blocked
    }
    // restore() sets state only after the server has answered, never synchronously in this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void restore().finally(() => {
      if (!cancelled) setIsLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [restore])

  // Another tab signed out (end this one too) or in (pick the session up).
  useEffect(
    () =>
      onSessionEvent((event) => {
        if (event === 'signed-out') {
          setAccessToken(null)
          setToken(null)
          setUser(null)
          queryClient.clear()
        } else {
          void restore()
        }
      }),
    [restore, queryClient],
  )

  const startSession = useCallback(async (accessToken: string) => {
    setAccessToken(accessToken)
    setToken(accessToken)
    announceSessionEvent('signed-in')
    setUser(await auth.me())
  }, [])

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const data = await auth.login(email, password)

      if (data.requires_2fa) {
        return { requires_2fa: true, temp_token: data.temp_token, available_methods: data.available_methods }
      }

      await startSession(data.access_token)
      return { requires_2fa: false }
    },
    [startSession],
  )

  const verify2fa = useCallback(
    async (tempToken: string, code: string) => {
      const data = await auth.verify2fa(tempToken, code)
      await startSession(data.access_token)
    },
    [startSession],
  )

  const loginWithToken = useCallback((accessToken: string) => {
    setAccessToken(accessToken)
    setToken(accessToken)
    announceSessionEvent('signed-in')
    auth.me().then(setUser).catch(() => {})
  }, [])

  const updateUser = useCallback((updatedUser: User) => {
    setUser(updatedUser)
  }, [])

  const register = useCallback(
    async (email: string, password: string, preferences?: Record<string, string>) => {
      await auth.register(email, password, preferences)
      await login(email, password)
    },
    [login],
  )

  const logout = useCallback(() => {
    // Tell the server first (it needs the token to know which session to end), and do not wait:
    // the person is signed out here whether or not the request gets through.
    void Promise.resolve(auth.logout(getAccessToken())).catch(() => {})
    setAccessToken(null)
    setToken(null)
    setUser(null)
    queryClient.clear()
    announceSessionEvent('signed-out')
  }, [queryClient])

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, verify2fa, loginWithToken, register, updateUser, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
