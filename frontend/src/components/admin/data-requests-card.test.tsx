import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

import { DataRequestsCard } from '@/components/admin/data-requests-card'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({ adminList: vi.fn() }))
vi.mock('@/lib/api', () => ({ dataRequests: api }))

beforeEach(() => {
  vi.clearAllMocks()
  api.adminList.mockResolvedValue({ items: [{}, {}] })
})

describe('DataRequestsCard', () => {
  it('shows how many requests are pending', async () => {
    renderWithProviders(<DataRequestsCard />)
    expect(await screen.findByText('2')).toBeInTheDocument()
    expect(api.adminList).toHaveBeenCalledWith('pending')
  })

  it('links to the queue', async () => {
    renderWithProviders(<DataRequestsCard />)
    expect(await screen.findByRole('link', { name: t('admin.dataRequests.card.viewAll') })).toHaveAttribute(
      'href',
      '/admin/data-requests',
    )
  })
})
