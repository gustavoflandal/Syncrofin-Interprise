import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { AuthProvider } from '@/contexts/auth-provider'
import { useAuth } from '@/contexts/auth-context'
import { getAccessToken, setAccessToken } from '@/lib/access-token'
import type { User } from '@/types'
import { createTestQueryClient } from '@/test/utils'

const auth = vi.hoisted(() => ({
  me: vi.fn(),
  login: vi.fn(),
  verify2fa: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ auth }))

// The real module keeps the token in memory; only the network call to trade the refresh cookie
// for an access token is replaced.
const refresh = vi.hoisted(() => vi.fn())
vi.mock('@/lib/access-token', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/access-token')>()),
  refreshAccessToken: refresh,
}))

const USER: User = {
  id: '1',
  email: 'tassio@example.com',
  is_active: true,
  is_superuser: false,
  is_verified: true,
  is_2fa_enabled: false,
  preferences: {},
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  )
}

/** Render the hook and wait for the initial session probe to settle. */
async function renderAuth() {
  const result = renderHook(() => useAuth(), { wrapper })
  await waitFor(() => expect(result.result.current.isLoading).toBe(false))
  return result
}

/** A session the server still knows: the refresh cookie buys an access token. */
function signedInOnTheServer(token = 'fresh-jwt') {
  refresh.mockImplementation(async () => {
    setAccessToken(token)
    return token
  })
  auth.me.mockResolvedValue(USER)
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  setAccessToken(null)
  refresh.mockResolvedValue(null)
  auth.logout.mockResolvedValue(undefined)
})

describe('AuthProvider session restore', () => {
  it('settles as signed out when the server has no session for this browser', async () => {
    const { result } = await renderAuth()

    expect(result.current.token).toBeNull()
    expect(result.current.user).toBeNull()
    expect(auth.me).not.toHaveBeenCalled()
  })

  it('restores the user from the refresh cookie, with no token stored in the page', async () => {
    signedInOnTheServer()

    const { result } = await renderAuth()

    expect(auth.me).toHaveBeenCalled()
    expect(result.current.user).toEqual(USER)
    expect(result.current.token).toBe('fresh-jwt')
    expect(getAccessToken()).toBe('fresh-jwt')
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('removes a token an older version left in localStorage', async () => {
    localStorage.setItem('token', 'old-24h-jwt')

    await renderAuth()

    expect(localStorage.getItem('token')).toBeNull()
  })

  it('stays signed out when the user cannot be loaded with the fresh token', async () => {
    refresh.mockImplementation(async () => {
      setAccessToken('fresh-jwt')
      return 'fresh-jwt'
    })
    auth.me.mockRejectedValue(new Error('401'))

    const { result } = await renderAuth()

    expect(result.current.token).toBeNull()
    expect(result.current.user).toBeNull()
    expect(getAccessToken()).toBeNull()
  })
})

describe('login', () => {
  it('keeps the token in memory and loads the user', async () => {
    auth.login.mockResolvedValue({ access_token: 'new-jwt' })
    auth.me.mockResolvedValue(USER)

    const { result } = await renderAuth()

    await act(async () => {
      const outcome = await result.current.login('tassio@example.com', 'pw')
      expect(outcome).toEqual({ requires_2fa: false })
    })

    expect(getAccessToken()).toBe('new-jwt')
    expect(localStorage.getItem('token')).toBeNull()
    await waitFor(() => expect(result.current.user).toEqual(USER))
  })

  it('does not start a session when a second factor is still required', async () => {
    // The temp token is not a session: it must not authorise anything.
    auth.login.mockResolvedValue({
      requires_2fa: true,
      temp_token: 'temp',
      available_methods: ['totp'],
    })

    const { result } = await renderAuth()

    let outcome!: Awaited<ReturnType<typeof result.current.login>>
    await act(async () => {
      outcome = await result.current.login('tassio@example.com', 'pw')
    })

    expect(outcome).toEqual({
      requires_2fa: true,
      temp_token: 'temp',
      available_methods: ['totp'],
    })
    expect(getAccessToken()).toBeNull()
    expect(result.current.token).toBeNull()
    expect(result.current.user).toBeNull()
  })

  it('propagates a rejected login instead of swallowing it', async () => {
    auth.login.mockRejectedValue(new Error('invalid credentials'))

    const { result } = await renderAuth()

    await expect(
      act(async () => {
        await result.current.login('tassio@example.com', 'wrong')
      }),
    ).rejects.toThrow('invalid credentials')

    expect(getAccessToken()).toBeNull()
  })
})

describe('verify2fa', () => {
  it('exchanges the temp token for a real session', async () => {
    auth.verify2fa.mockResolvedValue({ access_token: 'jwt-after-2fa' })
    auth.me.mockResolvedValue(USER)

    const { result } = await renderAuth()

    await act(async () => {
      await result.current.verify2fa('temp', '123456')
    })

    expect(auth.verify2fa).toHaveBeenCalledWith('temp', '123456')
    expect(getAccessToken()).toBe('jwt-after-2fa')
    await waitFor(() => expect(result.current.user).toEqual(USER))
  })
})

describe('loginWithToken', () => {
  it('adopts a token minted elsewhere, such as the OIDC callback', async () => {
    auth.me.mockResolvedValue(USER)

    const { result } = await renderAuth()

    act(() => {
      result.current.loginWithToken('oidc-jwt')
    })

    expect(getAccessToken()).toBe('oidc-jwt')
    await waitFor(() => expect(result.current.user).toEqual(USER))
  })
})

describe('register', () => {
  it('signs the new account straight in', async () => {
    auth.register.mockResolvedValue(undefined)
    auth.login.mockResolvedValue({ access_token: 'jwt' })
    auth.me.mockResolvedValue(USER)

    const { result } = await renderAuth()

    await act(async () => {
      await result.current.register('new@example.com', 'pw', { language: 'pt-BR' })
    })

    expect(auth.register).toHaveBeenCalledWith('new@example.com', 'pw', {
      language: 'pt-BR',
    })
    expect(auth.login).toHaveBeenCalledWith('new@example.com', 'pw')
    expect(getAccessToken()).toBe('jwt')
  })

  it('does not attempt a login when registration fails', async () => {
    auth.register.mockRejectedValue(new Error('email taken'))

    const { result } = await renderAuth()

    await expect(
      act(async () => {
        await result.current.register('taken@example.com', 'pw')
      }),
    ).rejects.toThrow('email taken')

    expect(auth.login).not.toHaveBeenCalled()
  })
})

describe('logout', () => {
  it('ends the session on the server, and clears the token and the user here', async () => {
    signedInOnTheServer('jwt')

    const { result } = await renderAuth()
    await waitFor(() => expect(result.current.user).toEqual(USER))

    act(() => {
      result.current.logout()
    })

    // Sent with the token it is ending: by the time an interceptor could add it, it is gone.
    expect(auth.logout).toHaveBeenCalledWith('jwt')
    expect(getAccessToken()).toBeNull()
    expect(result.current.token).toBeNull()
    expect(result.current.user).toBeNull()
  })

  it('signs out here even if the server cannot be reached', async () => {
    signedInOnTheServer('jwt')
    auth.logout.mockRejectedValue(new Error('offline'))

    const { result } = await renderAuth()
    await waitFor(() => expect(result.current.user).toEqual(USER))

    act(() => {
      result.current.logout()
    })

    expect(result.current.user).toBeNull()
    expect(getAccessToken()).toBeNull()
  })

  it('empties the query cache, so the next account sees no stale balances', async () => {
    // This is the privacy-relevant half of logout. Signing out on a shared
    // machine has to drop the cached financial data, not just the token.
    signedInOnTheServer('jwt')

    // Not createTestQueryClient: its gcTime of 0 collects data that has no
    // active observer, so the fixture would vanish before logout ran and the
    // test would pass for the wrong reason.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    queryClient.setQueryData(['accounts'], [{ id: 'a1', balance: 4200 }])

    function localWrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          <AuthProvider>{children}</AuthProvider>
        </QueryClientProvider>
      )
    }

    const { result } = renderHook(() => useAuth(), { wrapper: localWrapper })
    await waitFor(() => expect(result.current.user).toEqual(USER))
    expect(queryClient.getQueryData(['accounts'])).toBeDefined()

    act(() => {
      result.current.logout()
    })

    expect(queryClient.getQueryData(['accounts'])).toBeUndefined()
  })
})

describe('updateUser', () => {
  it('replaces the cached user without another round trip', async () => {
    signedInOnTheServer('jwt')

    const { result } = await renderAuth()
    await waitFor(() => expect(result.current.user).toEqual(USER))

    const renamed = { ...USER, email: 'renamed@example.com' }
    act(() => {
      result.current.updateUser(renamed)
    })

    expect(result.current.user).toEqual(renamed)
    expect(auth.me).toHaveBeenCalledTimes(1)
  })
})

describe('cross-tab sync', () => {
  const announce = (value: string) =>
    window.dispatchEvent(new StorageEvent('storage', { key: 'syncrofin_session_event', newValue: value }))

  it('signs out when another tab signs out', async () => {
    signedInOnTheServer('jwt')

    const { result } = await renderAuth()
    await waitFor(() => expect(result.current.user).toEqual(USER))

    act(() => announce('signed-out:1'))

    await waitFor(() => expect(result.current.token).toBeNull())
    expect(result.current.user).toBeNull()
    expect(getAccessToken()).toBeNull()
  })

  it('picks the session up when another tab signs in', async () => {
    const { result } = await renderAuth()
    expect(result.current.user).toBeNull()

    signedInOnTheServer('jwt')
    act(() => announce('signed-in:2'))

    await waitFor(() => expect(result.current.user).toEqual(USER))
  })

  it('ignores storage events for unrelated keys', async () => {
    signedInOnTheServer('jwt')

    const { result } = await renderAuth()
    await waitFor(() => expect(result.current.user).toEqual(USER))

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: 'theme', newValue: 'light' }))
    })

    expect(result.current.token).toBe('jwt')
    expect(result.current.user).toEqual(USER)
  })
})

describe('useAuth', () => {
  it('refuses to be used outside the provider', () => {
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used within an AuthProvider',
    )
  })
})
