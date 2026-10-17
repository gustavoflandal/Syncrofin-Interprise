import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import DataRequestsPage from '@/pages/admin/data-requests'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({ adminList: vi.fn(), adminResolve: vi.fn() }))
vi.mock('@/lib/api', () => ({ dataRequests: api }))

const pending = {
  id: 'r1', protocol: 'DSR-2026-000010', kind: 'correction', status: 'pending',
  created_at: '2026-09-01T10:00:00Z', due_at: '2026-09-16T10:00:00Z', resolved_at: null,
  detail: 'endereço errado', resolution_note: null, user_id: 'u1', actor_email: 'ana@example.com',
}

beforeEach(() => {
  vi.clearAllMocks()
  api.adminList.mockResolvedValue({ items: [pending] })
})

describe('admin data requests page', () => {
  it('lists who filed each request', async () => {
    renderWithProviders(<DataRequestsPage />)
    expect(await screen.findByText('ana@example.com')).toBeInTheDocument()
    expect(screen.getByText(t('dataRequests.kinds.correction'))).toBeInTheDocument()
  })

  it('marks an overdue pending request', async () => {
    renderWithProviders(<DataRequestsPage />)
    expect(await screen.findByText(new RegExp(t('admin.dataRequests.overdue')))).toBeInTheDocument()
  })

  it('resolves a pending request', async () => {
    api.adminResolve.mockResolvedValue({ ...pending, status: 'resolved_manual' })
    const { user } = renderWithProviders(<DataRequestsPage />)
    await screen.findByText('ana@example.com')

    await user.click(screen.getByRole('button', { name: t('admin.dataRequests.resolveButton') }))

    await waitFor(() => expect(api.adminResolve).toHaveBeenCalledWith('r1', 'resolved_manual', undefined))
  })

  it('says so when nothing matches the filter', async () => {
    api.adminList.mockResolvedValue({ items: [] })
    renderWithProviders(<DataRequestsPage />)
    expect(await screen.findByText(t('admin.dataRequests.empty'))).toBeInTheDocument()
  })
})
