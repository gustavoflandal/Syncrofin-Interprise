import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from '@/components/protected-route'
import { renderWithProviders } from '@/test/utils'

const useAuth = vi.hoisted(() => vi.fn())
vi.mock('@/contexts/auth-context', () => ({ useAuth }))

// Where the session stands with the second-factor rule is the server's answer, not this test's business.
const useMfaStatus = vi.hoisted(() => vi.fn())
vi.mock('@/hooks/use-mfa-status', () => ({ useMfaStatus, MFA_STATUS_KEY: ['mfa-status'] }))
vi.mock('@/components/mfa-enrollment-gate', () => ({ MfaEnrollmentGate: () => <div>enrolment gate</div> }))

function renderGuard() {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<div>login screen</div>} />
      <Route
        path="/private"
        element={
          <ProtectedRoute>
            <div>private page</div>
          </ProtectedRoute>
        }
      />
    </Routes>,
    { route: '/private' },
  )
}

beforeEach(() => {
  useMfaStatus.mockReturnValue({ isPending: false, data: { blocked: false } })
})

describe('ProtectedRoute', () => {
  it('renders the page for an authenticated user', () => {
    useAuth.mockReturnValue({ token: 'jwt', user: null, isLoading: false })

    renderGuard()

    expect(screen.getByText('private page')).toBeInTheDocument()
  })

  it('sends an anonymous visitor to the login screen', () => {
    useAuth.mockReturnValue({ token: null, user: null, isLoading: false })

    renderGuard()

    expect(screen.getByText('login screen')).toBeInTheDocument()
    expect(screen.queryByText('private page')).not.toBeInTheDocument()
  })

  it('shows a loading indicator instead of redirecting while the session resolves', () => {
    // Redirecting during the initial `auth.me()` call would bounce every
    // returning user to /login on a hard refresh.
    useAuth.mockReturnValue({ token: 'jwt', user: null, isLoading: true })

    const { container } = renderGuard()

    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText('private page')).not.toBeInTheDocument()
    expect(screen.queryByText('login screen')).not.toBeInTheDocument()
  })

  it('does not leak the page for a moment while loading without a token', () => {
    useAuth.mockReturnValue({ token: null, user: null, isLoading: true })

    renderGuard()

    expect(screen.queryByText('private page')).not.toBeInTheDocument()
  })
})

describe('ProtectedRoute and the second-factor rule', () => {
  it('shows the enrolment screen, not the page, to a session that owes a second factor', () => {
    useAuth.mockReturnValue({ token: 'jwt', user: null, isLoading: false })
    useMfaStatus.mockReturnValue({ isPending: false, data: { blocked: true } })

    renderGuard()

    expect(screen.getByText('enrolment gate')).toBeInTheDocument()
    expect(screen.queryByText('private page')).not.toBeInTheDocument()
  })

  it('waits for the answer before showing the page (a page of 403s is worse than a spinner)', () => {
    useAuth.mockReturnValue({ token: 'jwt', user: null, isLoading: false })
    useMfaStatus.mockReturnValue({ isPending: true, data: undefined })

    const { container } = renderGuard()

    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    expect(screen.queryByText('private page')).not.toBeInTheDocument()
  })

  it('lets the page through when the status cannot be read: the server still enforces the rule', () => {
    useAuth.mockReturnValue({ token: 'jwt', user: null, isLoading: false })
    useMfaStatus.mockReturnValue({ isPending: false, data: undefined, isError: true })

    renderGuard()

    expect(screen.getByText('private page')).toBeInTheDocument()
  })

  it('does not ask about the rule for someone who is not signed in', () => {
    useAuth.mockReturnValue({ token: null, user: null, isLoading: false })

    renderGuard()

    expect(useMfaStatus).toHaveBeenCalledWith(false)
  })
})
