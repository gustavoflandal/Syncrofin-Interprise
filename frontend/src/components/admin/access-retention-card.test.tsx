import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { AccessRetentionCard } from '@/components/admin/access-retention-card'
import { renderWithProviders, t } from '@/test/utils'

const accessLog = vi.hoisted(() => ({ retention: vi.fn(), setRetention: vi.fn() }))
vi.mock('@/lib/api', () => ({ accessLog }))

const LIMITS = { minimum: 183, maximum: 3650 }

beforeEach(() => {
  vi.clearAllMocks()
  accessLog.retention.mockResolvedValue({ days: 183, ...LIMITS })
  accessLog.setRetention.mockImplementation(async (days: number) => ({ days, ...LIMITS }))
})

describe('AccessRetentionCard', () => {
  it('shows the period in force', async () => {
    renderWithProviders(<AccessRetentionCard />)
    expect(await screen.findByLabelText(t('admin.accessRetention.days'))).toHaveValue(183)
  })

  it('saves a longer period', async () => {
    const { user } = renderWithProviders(<AccessRetentionCard />)
    const field = await screen.findByLabelText(t('admin.accessRetention.days'))

    await user.clear(field)
    await user.type(field, '400')
    await user.click(screen.getByRole('button', { name: t('admin.accessRetention.save') }))

    await waitFor(() => expect(accessLog.setRetention).toHaveBeenCalledWith(400))
  })

  it('refuses a period outside the limits before asking the server', async () => {
    const { user } = renderWithProviders(<AccessRetentionCard />)
    const field = await screen.findByLabelText(t('admin.accessRetention.days'))

    await user.clear(field)
    await user.type(field, '100')

    expect(
      screen.getByText(t('admin.accessRetention.invalid', { min: LIMITS.minimum, max: LIMITS.maximum })),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('admin.accessRetention.save') })).toBeDisabled()
  })

  it('warns that a shorter period anonymizes older records', async () => {
    accessLog.retention.mockResolvedValue({ days: 400, ...LIMITS })
    const { user } = renderWithProviders(<AccessRetentionCard />)
    const field = await screen.findByLabelText(t('admin.accessRetention.days'))

    await user.clear(field)
    await user.type(field, '200')

    expect(screen.getByRole('alert')).toHaveTextContent(t('admin.accessRetention.shorter'))
    expect(screen.getByRole('button', { name: t('admin.accessRetention.save') })).toBeEnabled()
  })

  it('does not warn when the new period is longer than the saved one', async () => {
    const { user } = renderWithProviders(<AccessRetentionCard />)
    const field = await screen.findByLabelText(t('admin.accessRetention.days'))

    await user.clear(field)
    await user.type(field, '400')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('leads to the access log', async () => {
    renderWithProviders(<AccessRetentionCard />)
    const link = await screen.findByRole('link', { name: t('admin.accessRetention.viewLog') })
    expect(link).toHaveAttribute('href', '/admin/access-log')
  })
})
