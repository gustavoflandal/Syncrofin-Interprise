import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import { SessionsDialog } from '@/components/sessions-dialog'
import { renderWithProviders, t } from '@/test/utils'

const auth = vi.hoisted(() => ({
  listSessions: vi.fn(),
  revokeSession: vi.fn(),
  revokeOtherSessions: vi.fn(),
  accessHistory: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ auth }))

const sessions = [
  { id: 's1', device_label: 'Firefox em Windows', ip: '198.51.100.7', auth_method: 'password', created_at: '2026-03-01T10:00:00Z', last_seen_at: '2026-03-01T12:00:00Z', current: true },
  { id: 's2', device_label: 'App SyncroFin em Android', ip: '203.0.113.9', auth_method: 'password', created_at: '2026-03-01T09:00:00Z', last_seen_at: '2026-03-01T11:00:00Z', current: false },
]

beforeEach(() => {
  vi.clearAllMocks()
  auth.listSessions.mockResolvedValue(sessions)
  auth.revokeSession.mockResolvedValue(undefined)
  auth.revokeOtherSessions.mockResolvedValue(1)
  auth.accessHistory.mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 })
})

describe('SessionsDialog', () => {
  it('lists the devices and marks this one', async () => {
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByText('Firefox em Windows')).toBeInTheDocument()
    expect(screen.getByText('App SyncroFin em Android')).toBeInTheDocument()
    expect(screen.getByText(t('auth.sessionThisDevice'))).toBeInTheDocument()
  })

  it('offers "sign out" only for the other devices', async () => {
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)
    await screen.findByText('Firefox em Windows')

    expect(screen.getAllByRole('button', { name: t('auth.sessionEnd') })).toHaveLength(1)
  })

  it('ends one device and takes it off the list', async () => {
    const { user } = renderWithProviders(<SessionsDialog open onClose={() => {}} />)
    const row = (await screen.findByText('App SyncroFin em Android')).closest('li') as HTMLElement

    await user.click(within(row).getByRole('button', { name: t('auth.sessionEnd') }))

    await waitFor(() => expect(auth.revokeSession).toHaveBeenCalledWith('s2'))
    await waitFor(() => expect(screen.queryByText('App SyncroFin em Android')).not.toBeInTheDocument())
    expect(screen.getByText('Firefox em Windows')).toBeInTheDocument()
  })

  it('ends every other device at once', async () => {
    const { user } = renderWithProviders(<SessionsDialog open onClose={() => {}} />)
    await screen.findByText('Firefox em Windows')

    await user.click(screen.getByRole('button', { name: t('auth.sessionsEndOthers') }))

    await waitFor(() => expect(auth.revokeOtherSessions).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('App SyncroFin em Android')).not.toBeInTheDocument())
  })

  it('says so when the devices cannot be loaded', async () => {
    auth.listSessions.mockRejectedValue(new Error('offline'))
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(t('auth.sessionsLoadError'))
  })

  it('does not ask the server while closed', () => {
    renderWithProviders(<SessionsDialog open={false} onClose={() => {}} />)
    expect(auth.listSessions).not.toHaveBeenCalled()
  })
})
