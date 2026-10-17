import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

import AccessLogPage from '@/pages/admin/access-log'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  accessLog: { list: vi.fn(), exportCsv: vi.fn(), retention: vi.fn() },
  admin: { listUsers: vi.fn() },
}))
vi.mock('@/lib/api', () => ({ accessLog: api.accessLog, admin: api.admin }))

const failed = {
  id: 'e1', seq: 7, occurred_at: '2026-03-01T12:00:00Z', actor_user_id: 'u1', actor_email: 'ana@example.com',
  actor_kind: 'user', workspace_id: null, action: 'login_failed', entity_type: 'user', entity_id: 'u1',
  changes: null, ip: '198.51.100.7', user_agent: 'Mozilla/5.0 Firefox', request_id: 'req-1', detail: 'bad_password',
  hash: 'a'.repeat(64),
}
const unknown = { ...failed, id: 'e2', actor_user_id: null, actor_email: null, detail: 'unknown_user', ip: '203.0.113.9' }

beforeEach(() => {
  vi.clearAllMocks()
  api.accessLog.retention.mockResolvedValue({ days: 365, minimum: 183, maximum: 3650 })
  api.accessLog.list.mockResolvedValue({ items: [failed, unknown], total: 2, page: 1, limit: 50 })
  api.admin.listUsers.mockResolvedValue({ items: [{ id: 'u2', email: 'bruno@example.com' }], total: 1 })
})

describe('access log page', () => {
  it('lists who tried what, from where, and why it failed', async () => {
    renderWithProviders(<AccessLogPage />)

    expect(await screen.findByText('ana@example.com')).toBeInTheDocument()
    expect(screen.getAllByText(new RegExp(t('accessLog.actions.login_failed')))).not.toHaveLength(0)
    expect(screen.getByText(/wrong password/)).toBeInTheDocument()
    expect(screen.getByText('203.0.113.9')).toBeInTheDocument()
  })

  it('tells how long the records are kept', async () => {
    renderWithProviders(<AccessLogPage />)
    expect(await screen.findByText(/Kept for 365 days/)).toBeInTheDocument()
  })

  it('asks the server for the filtered page', async () => {
    renderWithProviders(<AccessLogPage />)
    await screen.findByText('ana@example.com')

    fireEvent.change(screen.getByLabelText(t('accessLog.action')), { target: { value: 'login_failed' } })
    fireEvent.change(screen.getByLabelText(t('accessLog.ip')), { target: { value: '203.0.113.9' } })
    fireEvent.click(screen.getByRole('button', { name: t('accessLog.filter') }))

    await waitFor(() =>
      expect(api.accessLog.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ action: 'login_failed', ip: '203.0.113.9' }),
        1,
        50,
      ),
    )
  })

  it('exports what is filtered', async () => {
    api.accessLog.exportCsv.mockResolvedValue(undefined)
    renderWithProviders(<AccessLogPage />)
    await screen.findByText('ana@example.com')

    fireEvent.click(screen.getByRole('button', { name: t('accessLog.export') }))

    await waitFor(() => expect(api.accessLog.exportCsv).toHaveBeenCalledWith({}))
  })

  it('says so when there is nothing to show', async () => {
    api.accessLog.list.mockResolvedValue({ items: [], total: 0, page: 1, limit: 50 })
    renderWithProviders(<AccessLogPage />)
    expect(await screen.findByText(t('accessLog.empty'))).toBeInTheDocument()
  })
})
