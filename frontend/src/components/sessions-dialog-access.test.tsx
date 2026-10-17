import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { SessionsDialog } from '@/components/sessions-dialog'
import { renderWithProviders, t } from '@/test/utils'

const auth = vi.hoisted(() => ({
  listSessions: vi.fn(),
  revokeSession: vi.fn(),
  revokeOtherSessions: vi.fn(),
  accessHistory: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ auth }))

const devices = [
  { id: 's1', device_label: 'Firefox em Windows', ip: '198.51.100.7', auth_method: 'password', created_at: '2026-03-01T10:00:00Z', last_seen_at: '2026-03-01T12:00:00Z', current: true },
]
const history = {
  items: [
    { id: 'a1', occurred_at: '2026-03-01T12:00:00Z', action: 'login_failed', actor_kind: 'user', detail: 'bad_password', ip: '203.0.113.9', user_agent: 'Firefox' },
    { id: 'a2', occurred_at: '2026-03-01T09:00:00Z', action: 'login', actor_kind: 'user', detail: 'password', ip: '198.51.100.7', user_agent: 'Firefox' },
  ],
  total: 2,
  page: 1,
  limit: 20,
}

beforeEach(() => {
  vi.clearAllMocks()
  auth.listSessions.mockResolvedValue(devices)
  auth.accessHistory.mockResolvedValue(history)
})

describe('SessionsDialog recent access', () => {
  it('lists the recent accesses with what happened, why and from where', async () => {
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByText(t('auth.recentAccess.title'))).toBeInTheDocument()
    expect(
      screen.getByText(`${t('accessLog.actions.login_failed')} · ${t('accessLog.reasons.bad_password')}`),
    ).toBeInTheDocument()
    expect(screen.getByText(/203\.0\.113\.9/)).toBeInTheDocument()
    expect(auth.accessHistory).toHaveBeenCalledWith(20)
  })

  it('says so when nothing has been recorded', async () => {
    auth.accessHistory.mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 })
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByText(t('auth.recentAccess.empty'))).toBeInTheDocument()
  })

  it('keeps the devices when the history cannot be read, and hides the section', async () => {
    auth.accessHistory.mockRejectedValue(new Error('down'))
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByText('Firefox em Windows')).toBeInTheDocument()
    await waitFor(() => expect(auth.accessHistory).toHaveBeenCalled())
    expect(screen.queryByText(t('auth.recentAccess.title'))).not.toBeInTheDocument()
  })
})
