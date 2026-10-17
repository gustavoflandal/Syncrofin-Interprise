import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { DataRequestsDialog } from '@/components/data-requests-dialog'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  download: vi.fn(),
  createCorrection: vi.fn(),
  erasure: vi.fn(),
  listOwn: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ dataRequests: api }))

const useAuth = vi.hoisted(() => vi.fn())
vi.mock('@/contexts/auth-context', () => ({ useAuth }))

const requests = [
  { id: 'r1', protocol: 'DSR-2026-000001', kind: 'access', status: 'resolved_auto', created_at: '2026-09-20T10:00:00Z', due_at: '2026-10-05T10:00:00Z', resolved_at: '2026-09-20T10:00:01Z', detail: null, resolution_note: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  useAuth.mockReturnValue({ logout: vi.fn() })
  api.listOwn.mockResolvedValue({ items: requests })
  api.download.mockResolvedValue(undefined)
})

describe('DataRequestsDialog', () => {
  it('lists past requests', async () => {
    renderWithProviders(<DataRequestsDialog open onClose={() => {}} />)
    expect(await screen.findByText('DSR-2026-000001')).toBeInTheDocument()
  })

  it('downloads the access/portability package', async () => {
    const { user } = renderWithProviders(<DataRequestsDialog open onClose={() => {}} />)
    await user.click(await screen.findByRole('button', { name: t('dataRequests.download.button') }))
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('access'))
  })

  it('creates a self-service correction and shows the links', async () => {
    api.createCorrection.mockResolvedValue({
      id: 'r2', protocol: 'DSR-2026-000002', kind: 'correction', status: 'resolved_auto',
      created_at: '', due_at: '', resolved_at: '', detail: null, resolution_note: null,
      self_service_links: { transactions: '/transactions' },
    })
    const { user } = renderWithProviders(<DataRequestsDialog open onClose={() => {}} />)
    await screen.findByText(t('dataRequests.correction.question'))

    await user.click(screen.getByRole('button', { name: t('dataRequests.correction.yes') }))

    expect(await screen.findByText(t('dataRequests.correction.linkLabels.transactions'))).toBeInTheDocument()
    expect(api.createCorrection).toHaveBeenCalledWith(true)
  })

  it('opens a correction ticket with the free-text detail', async () => {
    api.createCorrection.mockResolvedValue({
      id: 'r3', protocol: 'DSR-2026-000003', kind: 'correction', status: 'pending',
      created_at: '', due_at: '', resolved_at: null, detail: 'meu nome está errado', resolution_note: null,
    })
    const { user } = renderWithProviders(<DataRequestsDialog open onClose={() => {}} />)
    await screen.findByText(t('dataRequests.correction.question'))

    await user.click(screen.getByRole('button', { name: t('dataRequests.correction.no') }))
    await user.type(screen.getByPlaceholderText(t('dataRequests.correction.detailPlaceholder')), 'meu nome está errado')
    await user.click(screen.getByRole('button', { name: t('dataRequests.correction.submit') }))

    expect(await screen.findByText('DSR-2026-000003', { exact: false })).toBeInTheDocument()
    expect(api.createCorrection).toHaveBeenCalledWith(false, 'meu nome está errado')
  })

  it('shows the blocking workspaces on a 409 and does not sign out', async () => {
    const logout = vi.fn()
    useAuth.mockReturnValue({ logout })
    api.erasure.mockRejectedValue({
      response: { status: 409, data: { code: 'WORKSPACES_BLOCK_ERASURE', workspaces: ['Casa'], protocol: 'DSR-2026-000004' } },
    })
    const { user } = renderWithProviders(<DataRequestsDialog open onClose={() => {}} />)
    await screen.findByText(t('dataRequests.correction.question'))

    await user.click(screen.getByRole('button', { name: t('dataRequests.erasure.startButton') }))
    await user.type(screen.getByLabelText(t('dataRequests.erasure.passwordLabel')), 'senha-atual')
    await user.click(screen.getByRole('button', { name: t('dataRequests.erasure.confirmButton') }))

    expect(await screen.findByText('Casa')).toBeInTheDocument()
    expect(logout).not.toHaveBeenCalled()
  })

  it('rejects a wrong password without signing out', async () => {
    const logout = vi.fn()
    useAuth.mockReturnValue({ logout })
    api.erasure.mockRejectedValue({ response: { status: 401 } })
    const { user } = renderWithProviders(<DataRequestsDialog open onClose={() => {}} />)
    await screen.findByText(t('dataRequests.correction.question'))

    await user.click(screen.getByRole('button', { name: t('dataRequests.erasure.startButton') }))
    await user.type(screen.getByLabelText(t('dataRequests.erasure.passwordLabel')), 'wrong')
    await user.click(screen.getByRole('button', { name: t('dataRequests.erasure.confirmButton') }))

    expect(await screen.findByRole('alert')).toHaveTextContent(t('dataRequests.erasure.wrongPassword'))
    expect(logout).not.toHaveBeenCalled()
  })

  it('signs out after a successful erasure', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const logout = vi.fn()
    useAuth.mockReturnValue({ logout })
    api.erasure.mockResolvedValue({ id: 'r5', protocol: 'DSR-2026-000005', kind: 'erasure', status: 'resolved_auto', created_at: '', due_at: '', resolved_at: '', detail: null, resolution_note: null })
    const { user } = renderWithProviders(<DataRequestsDialog open onClose={() => {}} />)
    await screen.findByText(t('dataRequests.correction.question'))

    await user.click(screen.getByRole('button', { name: t('dataRequests.erasure.startButton') }))
    await user.type(screen.getByLabelText(t('dataRequests.erasure.passwordLabel')), 'senha-atual')
    await user.click(screen.getByRole('button', { name: t('dataRequests.erasure.confirmButton') }))

    expect(await screen.findByText(t('dataRequests.erasure.success'))).toBeInTheDocument()
    await vi.advanceTimersByTimeAsync(1500)
    expect(logout).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('does not ask the server while closed', () => {
    renderWithProviders(<DataRequestsDialog open={false} onClose={() => {}} />)
    expect(api.listOwn).not.toHaveBeenCalled()
  })
})
