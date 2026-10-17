import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

import AuditPage from '@/pages/audit'
import { renderWithProviders } from '@/test/utils'

const api = vi.hoisted(() => ({
  audit: { list: vi.fn(), facets: vi.fn(), exportCsv: vi.fn(), verify: vi.fn() },
}))
const state = vi.hoisted(() => ({ canManage: true, superuser: false }))

vi.mock('@/lib/api', () => ({ audit: api.audit }))
vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { is_superuser: state.superuser } }),
}))
vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ can: (permission: string) => state.canManage && permission === 'audit.read' }),
}))

const event = {
  id: 'e1', seq: 7, occurred_at: '2026-03-01T12:00:00Z', actor_user_id: 'u1', actor_email: 'ana@example.com',
  actor_kind: 'user', workspace_id: 'w1', action: 'update', entity_type: 'transactions', entity_id: 'tx-1',
  changes: { amount: ['10.00', '12.50'], totp_secret: [null, '***'] },
  ip: '198.51.100.7', user_agent: 'Firefox', request_id: 'req-1', detail: null, hash: 'a'.repeat(64),
}

beforeEach(() => {
  vi.clearAllMocks()
  state.canManage = true
  state.superuser = false
  api.audit.facets.mockResolvedValue({ entity_types: ['transactions'], actions: ['update'] })
  api.audit.list.mockResolvedValue({ items: [event], total: 1, page: 1, limit: 50 })
})

describe('audit page', () => {
  it('lists who changed what', async () => {
    renderWithProviders(<AuditPage />)
    expect(await screen.findByText('ana@example.com')).toBeInTheDocument()
  })

  it('shows the before and after of a change, with secrets masked, when a row is opened', async () => {
    renderWithProviders(<AuditPage />)
    fireEvent.click(await screen.findByText('ana@example.com'))
    expect(await screen.findByText('12.50')).toBeInTheDocument()
    expect(screen.getByText('10.00')).toBeInTheDocument()
    expect(screen.getByText('***')).toBeInTheDocument()
    expect(screen.getByText('198.51.100.7')).toBeInTheDocument()
  })

  it('asks the server for the filtered page', async () => {
    renderWithProviders(<AuditPage />)
    await screen.findByText('ana@example.com')
    fireEvent.change(await screen.findByLabelText(/entity|registro|record/i), { target: { value: 'transactions' } })
    fireEvent.click(screen.getByRole('button', { name: /filtrar|filter/i }))
    await waitFor(() =>
      expect(api.audit.list).toHaveBeenLastCalledWith(expect.objectContaining({ entity_type: 'transactions' }), 1, 50),
    )
  })

  it('only offers the integrity check to an administrator', async () => {
    renderWithProviders(<AuditPage />)
    await screen.findByText('ana@example.com')
    expect(screen.queryByRole('button', { name: /verificar|verify/i })).toBeNull()
  })

  it('offers the integrity check to an administrator', async () => {
    state.superuser = true
    renderWithProviders(<AuditPage />)
    expect(await screen.findByRole('button', { name: /verificar|verify/i })).toBeInTheDocument()
  })

  it('does not even ask the server when the person is not an owner or manager', async () => {
    state.canManage = false
    renderWithProviders(<AuditPage />)
    await waitFor(() => expect(screen.getByText(/proprietários|owners/i)).toBeInTheDocument())
    expect(api.audit.list).not.toHaveBeenCalled()
  })
})
