import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import ForgotPasswordPage from '@/pages/forgot-password'
import ResetPasswordPage from '@/pages/reset-password'
import { renderWithProviders } from '@/test/utils'

const api = vi.hoisted(() => ({
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  info: vi.fn(),
}))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    auth: { ...actual.auth, forgotPassword: api.forgotPassword, resetPassword: api.resetPassword },
    info: { get: api.info },
  }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

const navigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigate }
})

const axiosError = (status: number, detail?: unknown) =>
  Object.assign(new Error('request failed'), { isAxiosError: true, response: { status, data: { detail } } })

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset())
  navigate.mockReset()
  api.info.mockResolvedValue({ features: { agents: false, email: true } })
  api.forgotPassword.mockResolvedValue(undefined)
  api.resetPassword.mockResolvedValue(undefined)
})

describe('ForgotPasswordPage', () => {
  it('asks for the address and sends the request', async () => {
    const { user } = renderWithProviders(<ForgotPasswordPage />)

    await user.type(await screen.findByLabelText('Email'), 'ana@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    await waitFor(() => expect(api.forgotPassword).toHaveBeenCalledWith('ana@example.com'))
  })

  it('gives the same confirmation whether or not the account exists', async () => {
    // The server answers 202 either way; the page must not say which it was.
    const { user } = renderWithProviders(<ForgotPasswordPage />)

    await user.type(await screen.findByLabelText('Email'), 'nobody@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByText(/If that address has an account/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
  })

  it('says so, instead of promising a link, when the server cannot send e-mail', async () => {
    api.info.mockResolvedValue({ features: { agents: false, email: false } })
    renderWithProviders(<ForgotPasswordPage />)

    expect(await screen.findByText(/cannot send e-mail/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send reset link' })).not.toBeInTheDocument()
  })

  it('reports rate limiting and an unreachable server distinctly', async () => {
    api.forgotPassword.mockRejectedValueOnce(axiosError(429))
    const { user } = renderWithProviders(<ForgotPasswordPage />)

    await user.type(await screen.findByLabelText('Email'), 'ana@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/too many/i)
  })

  it('always offers a way back to sign in', async () => {
    renderWithProviders(<ForgotPasswordPage />)
    expect(await screen.findByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/login')
  })
})

describe('ResetPasswordPage', () => {
  const at = (query: string) => ({ route: `/reset-password${query}` })

  it('explains an incomplete link instead of showing a form that cannot work', () => {
    renderWithProviders(<ResetPasswordPage />, at(''))

    expect(screen.getByRole('alert')).toHaveTextContent(/incomplete/)
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument()
  })

  it('refuses a short password without calling the server', async () => {
    const { user } = renderWithProviders(<ResetPasswordPage />, at('?token=abc'))

    await user.type(screen.getByLabelText('New password'), 'short')
    await user.type(screen.getByLabelText('Confirm password'), 'short')
    // Native minLength would block the submit in a browser; jsdom submits, and
    // the component's own check has to hold either way.
    screen.getByRole('button', { name: 'Save password' }).closest('form')!.requestSubmit()

    expect(api.resetPassword).not.toHaveBeenCalled()
  })

  it('refuses two different passwords', async () => {
    const { user } = renderWithProviders(<ResetPasswordPage />, at('?token=abc'))

    await user.type(screen.getByLabelText('New password'), 'long-enough-1')
    await user.type(screen.getByLabelText('Confirm password'), 'long-enough-2')
    await user.click(screen.getByRole('button', { name: 'Save password' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(api.resetPassword).not.toHaveBeenCalled()
  })

  it('sends the token with the new password, then goes to sign in', async () => {
    const { user } = renderWithProviders(<ResetPasswordPage />, at('?token=abc.def.ghi'))

    await user.type(screen.getByLabelText('New password'), 'long-enough-1')
    await user.type(screen.getByLabelText('Confirm password'), 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Save password' }))

    await waitFor(() => expect(api.resetPassword).toHaveBeenCalledWith('abc.def.ghi', 'long-enough-1'))
    expect(navigate).toHaveBeenCalledWith('/login', { replace: true })
  })

  it('removes the token from the address bar once it has been read', async () => {
    renderWithProviders(<ResetPasswordPage />, at('?token=secret-token'))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reset-password', { replace: true }))
  })

  it('keeps the invited flag while scrubbing the token', async () => {
    renderWithProviders(<ResetPasswordPage />, at('?token=secret&invited=1'))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reset-password?invited=1', { replace: true }))
    expect(screen.getByText('Welcome to SyncroFin')).toBeInTheDocument()
  })

  it('tells an expired or used link from any other failure', async () => {
    api.resetPassword.mockRejectedValueOnce(axiosError(400, 'RESET_PASSWORD_BAD_TOKEN'))
    const { user } = renderWithProviders(<ResetPasswordPage />, at('?token=old'))

    await user.type(screen.getByLabelText('New password'), 'long-enough-1')
    await user.type(screen.getByLabelText('Confirm password'), 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Save password' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/)
    expect(navigate).not.toHaveBeenCalledWith('/login', expect.anything())
  })
})
