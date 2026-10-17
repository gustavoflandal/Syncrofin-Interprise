import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import type { AxiosError } from 'axios'

import RegisterPage from '@/pages/register'
import { renderWithProviders, t } from '@/test/utils'

const navigate = vi.hoisted(() => vi.fn())
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}))

const authContext = vi.hoisted(() => ({ register: vi.fn() }))
vi.mock('@/contexts/auth-context', () => ({ useAuth: () => authContext }))

const api = vi.hoisted(() => ({
  admin: { registrationStatus: vi.fn(), defaultColors: vi.fn() },
  auth: { oidcConfig: vi.fn() },
}))
vi.mock('@/lib/api', () => ({ admin: api.admin, auth: api.auth }))

vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark' }) }))

function httpError(status?: number): AxiosError {
  return (status === undefined
    ? { isAxiosError: true, response: undefined }
    : { isAxiosError: true, response: { status } }) as AxiosError
}

beforeEach(() => {
  vi.clearAllMocks()
  api.admin.registrationStatus.mockResolvedValue({ enabled: true })
  api.admin.defaultColors.mockResolvedValue({ light: null, dark: null })
  api.auth.oidcConfig.mockResolvedValue({
    enabled: false,
    provider_name: 'OIDC',
    local_auth_enabled: true,
  })
})

async function renderRegister() {
  const rendered = renderWithProviders(<RegisterPage />, { route: '/register' })
  await screen.findByLabelText(t('auth.email'))
  return rendered
}

async function fill(
  user: Awaited<ReturnType<typeof renderRegister>>['user'],
  { password = 'sufficiently-long', confirm = 'sufficiently-long' } = {},
) {
  // Paste rather than type: typing ~50 characters one keystroke at a time made
  // these tests exceed the default timeout on a loaded machine, and what is under
  // test is what the form does with the values, not the keystrokes.
  for (const [label, value] of [
    [t('auth.email'), 'new@example.com'],
    [t('auth.password'), password],
    [t('auth.confirmPassword'), confirm],
  ] as const) {
    await user.click(screen.getByLabelText(label))
    await user.paste(value)
  }
}

describe('RegisterPage', () => {
  it('renders the signup form', async () => {
    await renderRegister()

    expect(screen.getByLabelText(t('auth.email'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('auth.password'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('auth.confirmPassword'))).toBeInTheDocument()
    expect(screen.getByLabelText(t('auth.currency'))).toBeInTheDocument()
  })

  it('registers and lands on the dashboard', async () => {
    authContext.register.mockResolvedValue(undefined)
    const { user } = await renderRegister()

    await fill(user)
    await user.click(screen.getByRole('button', { name: t('auth.register') }))

    // Exactly once: reading calls[0] alone would wave through a double
    // submit, which on this endpoint means a second account attempt.
    await waitFor(() => expect(authContext.register).toHaveBeenCalledTimes(1))
    // Assert the whole payload: sending the confirm field as the password, or
    // dropping the currency, is exactly the kind of slip a looser assertion
    // on the email alone would wave through.
    const [email, password, preferences] = authContext.register.mock.calls[0]
    expect(email).toBe('new@example.com')
    expect(password).toBe('sufficiently-long')
    // The currency is the product default (BRL); the language is the interface's, which the suite pins to English.
    expect(preferences).toEqual({ currency_display: 'BRL', language: 'en' })
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/'))
  })

  it('refuses to submit when the two passwords differ', async () => {
    const { user } = await renderRegister()

    await fill(user, { password: 'first-password', confirm: 'second-password' })
    await user.click(screen.getByRole('button', { name: t('auth.register') }))

    expect(
      await screen.findByText(t('auth.passwordMismatch')),
    ).toBeInTheDocument()
    // Catching it client-side keeps a guaranteed-doomed request off the wire.
    expect(authContext.register).not.toHaveBeenCalled()
  })

  it('refuses a password that is too short', async () => {
    const { user } = await renderRegister()

    await fill(user, { password: 'short', confirm: 'short' })
    await user.click(screen.getByRole('button', { name: t('auth.register') }))

    expect(
      await screen.findByText(t('auth.passwordTooShort', { min: 10 })),
    ).toBeInTheDocument()
    expect(authContext.register).not.toHaveBeenCalled()
  })

  it("says why the server refused the password, in the person's language", async () => {
    authContext.register.mockRejectedValue({
      isAxiosError: true,
      response: { status: 400, data: { detail: { code: 'REGISTER_INVALID_PASSWORD', reason: 'PASSWORD_TOO_COMMON' } } },
    })
    const { user } = await renderRegister()

    await fill(user, { password: 'senha-bem-comum-1', confirm: 'senha-bem-comum-1' })
    await user.click(screen.getByRole('button', { name: t('auth.register') }))

    expect(await screen.findByText(t('passwordPolicy.reasons.PASSWORD_TOO_COMMON'))).toBeInTheDocument()
  })

  it('distinguishes an outage from a rejected signup', async () => {
    authContext.register.mockRejectedValue(httpError())
    const { user } = await renderRegister()

    await fill(user)
    await user.click(screen.getByRole('button', { name: t('auth.register') }))

    expect(await screen.findByText(t('auth.serverError'))).toBeInTheDocument()
  })

  it('names rate limiting', async () => {
    authContext.register.mockRejectedValue(httpError(429))
    const { user } = await renderRegister()

    await fill(user)
    await user.click(screen.getByRole('button', { name: t('auth.register') }))

    expect(await screen.findByText(t('auth.tooManyAttempts'))).toBeInTheDocument()
  })

  it('reports a rejected signup', async () => {
    authContext.register.mockRejectedValue(httpError(400))
    const { user } = await renderRegister()

    await fill(user)
    await user.click(screen.getByRole('button', { name: t('auth.register') }))

    expect(
      await screen.findByText(t('auth.registrationError')),
    ).toBeInTheDocument()
  })

  it('turns visitors away when registration is closed', async () => {
    // Otherwise a self-hosted admin who disabled signups still hands out a
    // working form whose submit always fails.
    api.admin.registrationStatus.mockResolvedValue({ enabled: false })

    renderWithProviders(<RegisterPage />, { route: '/register' })

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith('/login', { replace: true }),
    )
  })

  it('turns visitors away in an OIDC-only deployment', async () => {
    api.auth.oidcConfig.mockResolvedValue({
      enabled: true,
      provider_name: 'Keycloak',
      local_auth_enabled: false,
    })

    renderWithProviders(<RegisterPage />, { route: '/register' })

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith('/login', { replace: true }),
    )
  })

  it('still renders the form when the oidc config call fails', async () => {
    api.auth.oidcConfig.mockRejectedValue(new Error('500'))

    await renderRegister()

    expect(
      screen.getByRole('button', { name: t('auth.register') }),
    ).toBeInTheDocument()
    expect(navigate).not.toHaveBeenCalledWith('/login', { replace: true })
  })

  it('defaults the currency to BRL: this is a Brazilian product', async () => {
    await renderRegister()

    expect(screen.getByLabelText(t('auth.currency'))).toHaveTextContent('BRL')
  })
})
