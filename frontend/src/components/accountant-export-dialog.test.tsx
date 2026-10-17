import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { AccountantExportDialog } from '@/components/accountant-export-dialog'
import { presetRange } from '@/lib/accountant-period'
import { renderWithProviders } from '@/test/utils'

const download = vi.fn()
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, accountantExport: { download: (...args: unknown[]) => download(...args) } }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

describe('presetRange', () => {
  // Wednesday 2026-05-20 — mid-month, mid-quarter, so no boundary is a coincidence.
  const today = new Date(2026, 4, 20)

  it('covers the previous calendar month, whatever its length', () => {
    expect(presetRange('lastMonth', today)).toEqual(['2026-04-01', '2026-04-30'])
    expect(presetRange('lastMonth', new Date(2026, 2, 10))).toEqual(['2026-02-01', '2026-02-28'])
  })

  it('runs the current month up to today', () => {
    expect(presetRange('thisMonth', today)).toEqual(['2026-05-01', '2026-05-20'])
  })

  it('finds the previous quarter, including across a year boundary', () => {
    expect(presetRange('lastQuarter', today)).toEqual(['2026-01-01', '2026-03-31'])
    expect(presetRange('lastQuarter', new Date(2026, 1, 5))).toEqual(['2025-10-01', '2025-12-31'])
  })

  it('handles the year presets', () => {
    expect(presetRange('thisYear', today)).toEqual(['2026-01-01', '2026-05-20'])
    expect(presetRange('lastYear', today)).toEqual(['2025-01-01', '2025-12-31'])
  })

  it('does not drift a day in timezones behind UTC (local calendar parts, not toISOString)', () => {
    // 22:30 on the last day of the month: toISOString() would already be "tomorrow" in UTC-3.
    expect(presetRange('thisMonth', new Date(2026, 4, 31, 22, 30))[1]).toBe('2026-05-31')
  })
})

describe('AccountantExportDialog', () => {
  beforeEach(() => {
    download.mockReset()
    download.mockResolvedValue(undefined)
  })

  it('renders nothing while closed', () => {
    renderWithProviders(<AccountantExportDialog open={false} onClose={vi.fn()} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('exports the chosen preset period without a password', async () => {
    const onClose = vi.fn()
    const { user } = renderWithProviders(<AccountantExportDialog open onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Download ZIP' }))

    await waitFor(() => expect(download).toHaveBeenCalledTimes(1))
    const [start, end, password] = download.mock.calls[0]
    expect(start).toMatch(/^\d{4}-\d{2}-01$/)
    expect(end >= start).toBe(true)
    expect(password).toBeUndefined()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('refuses a custom period with no dates', async () => {
    const { user } = renderWithProviders(<AccountantExportDialog open onClose={vi.fn()} />)

    await user.click(screen.getByRole('radio', { name: 'Custom' }))
    await user.click(screen.getByRole('button', { name: 'Download ZIP' }))

    expect(await screen.findByText('Choose the period.')).toBeInTheDocument()
    expect(download).not.toHaveBeenCalled()
  })

  it('refuses a start date after the end date', async () => {
    const { user } = renderWithProviders(<AccountantExportDialog open onClose={vi.fn()} />)

    await user.click(screen.getByRole('radio', { name: 'Custom' }))
    await user.type(screen.getByLabelText('From'), '2026-03-10')
    await user.type(screen.getByLabelText('To'), '2026-03-01')
    await user.click(screen.getByRole('button', { name: 'Download ZIP' }))

    expect(await screen.findByText('The start date cannot be after the end date.')).toBeInTheDocument()
    expect(download).not.toHaveBeenCalled()
  })

  it('refuses a password shorter than the backend accepts', async () => {
    const { user } = renderWithProviders(<AccountantExportDialog open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Password (optional)'), 'short')
    await user.click(screen.getByRole('button', { name: 'Download ZIP' }))

    expect(download).not.toHaveBeenCalled()
    expect(screen.getByText(/at least 8/i)).toBeInTheDocument()
  })

  it('passes a valid password through', async () => {
    const { user } = renderWithProviders(<AccountantExportDialog open onClose={vi.fn()} />)

    await user.type(screen.getByLabelText('Password (optional)'), 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Download ZIP' }))

    await waitFor(() => expect(download).toHaveBeenCalled())
    expect(download.mock.calls[0][2]).toBe('long-enough-1')
  })
})
