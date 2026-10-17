import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { MfaEnrollmentGate } from '@/components/mfa-enrollment-gate'
import { MfaReminderBanner } from '@/components/mfa-reminder-banner'
import { MfaPolicyCard } from '@/components/admin/mfa-policy-card'
import { toast } from 'sonner'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  auth: { mfaStatus: vi.fn() },
  admin: { mfaPolicy: vi.fn(), updateSetting: vi.fn() },
}))
vi.mock('@/lib/api', () => ({ auth: api.auth, admin: api.admin }))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const logout = vi.hoisted(() => vi.fn())
vi.mock('@/contexts/auth-context', () => ({ useAuth: () => ({ logout }) }))
vi.mock('@/hooks/use-local-auth', () => ({ useLocalAuthEnabled: () => true }))
vi.mock('@/hooks/use-display-locale', () => ({ useDateLocale: () => 'pt-BR', useDisplayLocale: () => 'pt-BR' }))
// The two dialogs are covered by their own tests: here only that the gate opens them.
vi.mock('@/components/two-factor-setup', () => ({
  TwoFactorSetup: ({ open }: { open: boolean }) => (open ? <div>two-factor dialog</div> : null),
}))
vi.mock('@/components/passkey-management-dialog', () => ({
  PasskeyManagementDialog: ({ open }: { open: boolean }) => (open ? <div>passkey dialog</div> : null),
}))

const status = {
  applies: true, enforced: false, blocked: false, reminder: false, session_verified: false,
  enrolled: false, enforced_from: null, from_environment: false,
}
const policy = {
  required: false, scope: 'all', grace_days: 7, enforced_from: null, from_environment: false,
  users_total: 4, users_without_2fa: 3,
}

beforeEach(() => {
  vi.clearAllMocks()
  api.admin.updateSetting.mockResolvedValue({ key: 'x', value: 'y' })
})

describe('MfaEnrollmentGate', () => {
  it('offers the two ways to get a second factor, and sign out, and nothing else', () => {
    renderWithProviders(<MfaEnrollmentGate />)

    expect(screen.getByRole('heading', { name: t('auth.mfaRequiredTitle') })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('auth.mfaSetUpApp') })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('auth.mfaUsePasskey') })).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(3)
  })

  it('opens the authenticator setup', async () => {
    const { user } = renderWithProviders(<MfaEnrollmentGate />)
    await user.click(screen.getByRole('button', { name: t('auth.mfaSetUpApp') }))
    expect(screen.getByText('two-factor dialog')).toBeInTheDocument()
  })

  it('opens the passkey registration', async () => {
    const { user } = renderWithProviders(<MfaEnrollmentGate />)
    await user.click(screen.getByRole('button', { name: t('auth.mfaUsePasskey') }))
    expect(screen.getByText('passkey dialog')).toBeInTheDocument()
  })

  it('signs out', async () => {
    const { user } = renderWithProviders(<MfaEnrollmentGate />)
    await user.click(screen.getByRole('button', { name: t('auth.logout') }))
    expect(logout).toHaveBeenCalled()
  })
})

describe('MfaReminderBanner', () => {
  it('reminds during the grace period, with the date, and offers to set it up', async () => {
    api.auth.mfaStatus.mockResolvedValue({ ...status, reminder: true, enforced_from: '2026-10-01T00:00:00Z' })
    const onSetUp = vi.fn()
    const { user } = renderWithProviders(<MfaReminderBanner onSetUp={onSetUp} />)

    const banner = await screen.findByRole('status')
    expect(banner).toHaveTextContent(/2026/)
    await user.click(screen.getByRole('button', { name: t('auth.mfaSetUpNow') }))
    expect(onSetUp).toHaveBeenCalled()
  })

  it('says nothing when there is nothing to say', async () => {
    api.auth.mfaStatus.mockResolvedValue({ ...status, reminder: false })
    renderWithProviders(<MfaReminderBanner onSetUp={() => {}} />)

    await waitFor(() => expect(api.auth.mfaStatus).toHaveBeenCalled())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('MfaPolicyCard', () => {
  it('shows the rule and how many accounts it would hold back', async () => {
    api.admin.mfaPolicy.mockResolvedValue(policy)
    renderWithProviders(<MfaPolicyCard />)

    expect(await screen.findByRole('switch', { name: t('admin.mfa.require') })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText(t('admin.mfa.withoutApp', { without: 3, total: 4 }))).toBeInTheDocument()
  })

  it('turns the rule on with the chosen scope and grace period, stored before the switch', async () => {
    api.admin.mfaPolicy.mockResolvedValue(policy)
    const { user } = renderWithProviders(<MfaPolicyCard />)

    await user.click(await screen.findByRole('switch', { name: t('admin.mfa.require') }))

    await waitFor(() => expect(api.admin.updateSetting).toHaveBeenCalledTimes(3))
    expect(api.admin.updateSetting.mock.calls).toEqual([
      ['mfa_grace_days', '7'],
      ['mfa_required_scope', 'all'],
      ['mfa_required', 'true'],
    ])
  })

  it('turns it off', async () => {
    api.admin.mfaPolicy.mockResolvedValue({ ...policy, required: true })
    const { user } = renderWithProviders(<MfaPolicyCard />)

    await user.click(await screen.findByRole('switch', { name: t('admin.mfa.require') }))

    await waitFor(() => expect(api.admin.updateSetting).toHaveBeenCalledWith('mfa_required', 'false'))
  })

  it('cannot be turned off from here when the server configuration requires it', async () => {
    api.admin.mfaPolicy.mockResolvedValue({ ...policy, required: true, from_environment: true })
    renderWithProviders(<MfaPolicyCard />)

    const toggle = await screen.findByRole('switch', { name: t('admin.mfa.require') })
    expect(toggle).toBeDisabled()
    expect(screen.getByText(t('admin.mfa.fromEnvironment'))).toBeInTheDocument()
  })

  it('explains, instead of a bare error, that the administrator needs a second factor first', async () => {
    api.admin.mfaPolicy.mockResolvedValue(policy)
    api.admin.updateSetting.mockImplementation(async (key: string) => {
      if (key === 'mfa_required') throw { response: { data: { detail: 'MFA_ADMIN_NOT_ENROLLED' } } }
      return { key, value: 'x' }
    })
    const { user } = renderWithProviders(<MfaPolicyCard />)

    await user.click(await screen.findByRole('switch', { name: t('admin.mfa.require') }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(t('admin.mfa.adminNotEnrolled')))
  })

  it('changes who it covers', async () => {
    api.admin.mfaPolicy.mockResolvedValue(policy)
    const { user } = renderWithProviders(<MfaPolicyCard />)

    await user.selectOptions(await screen.findByLabelText(t('admin.mfa.scope')), 'admins')

    await waitFor(() => expect(api.admin.updateSetting).toHaveBeenCalledWith('mfa_required_scope', 'admins'))
  })
})
