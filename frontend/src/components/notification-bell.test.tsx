import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { NotificationBell } from '@/components/notification-bell'
import { badgeLabel } from '@/lib/notification-utils'
import { renderWithProviders } from '@/test/utils'
import type { AppNotification } from '@/types'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  unreadCount: vi.fn(),
  refresh: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
}))
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, notifications: api }
})

const navigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigate }
})

const note = (over: Partial<AppNotification> = {}): AppNotification => ({
  id: 'n1',
  kind: 'budget_over',
  severity: 'critical',
  title: 'Orçamento estourado: Alimentação',
  body: 'Você gastou R$ 130,00 de R$ 100,00.',
  data: { route: '/budgets' },
  created_at: new Date().toISOString(),
  read_at: null,
  ...over,
})

describe('badgeLabel', () => {
  it('caps the count so the badge never outgrows the bell', () => {
    expect(badgeLabel(3)).toBe('3')
    expect(badgeLabel(9)).toBe('9')
    expect(badgeLabel(10)).toBe('9+')
    expect(badgeLabel(250)).toBe('9+')
  })
})

describe('NotificationBell', () => {
  beforeEach(() => {
    Object.values(api).forEach((m) => m.mockReset())
    navigate.mockReset()
    api.unreadCount.mockResolvedValue(0)
    api.list.mockResolvedValue([])
    api.refresh.mockResolvedValue(0)
    api.markRead.mockResolvedValue(undefined)
    api.markAllRead.mockResolvedValue(undefined)
  })

  it('shows no badge when everything is read', async () => {
    renderWithProviders(<NotificationBell />)
    await waitFor(() => expect(api.unreadCount).toHaveBeenCalled())
    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument()
  })

  it('shows the unread count and announces it to screen readers', async () => {
    api.unreadCount.mockResolvedValue(12)
    renderWithProviders(<NotificationBell />)

    expect(await screen.findByTestId('notification-badge')).toHaveTextContent('9+')
    expect(screen.getByRole('button', { name: 'Notifications, 12 unread' })).toBeInTheDocument()
  })

  it('refreshes on open, lists notifications, and says so when there are none', async () => {
    const { user } = renderWithProviders(<NotificationBell />)

    await user.click(screen.getByRole('button', { name: /Notifications/ }))

    expect(await screen.findByText('Nothing needs your attention.')).toBeInTheDocument()
    expect(api.refresh).toHaveBeenCalled()
  })

  it('marks a notification read and goes where it points', async () => {
    api.unreadCount.mockResolvedValue(1)
    api.list.mockResolvedValue([note()])
    const { user } = renderWithProviders(<NotificationBell />)

    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await user.click(await screen.findByText('Orçamento estourado: Alimentação'))

    await waitFor(() => expect(api.markRead.mock.calls[0][0]).toBe('n1'))
    expect(navigate).toHaveBeenCalledWith('/budgets')
  })

  it('does not re-mark a read notification, and ignores routes that are not in-app paths', async () => {
    api.list.mockResolvedValue([
      note({ read_at: new Date().toISOString(), data: { route: 'https://evil.example/' } }),
    ])
    const { user } = renderWithProviders(<NotificationBell />)

    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await user.click(await screen.findByText('Orçamento estourado: Alimentação'))

    expect(api.markRead).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('marks everything read', async () => {
    api.unreadCount.mockResolvedValue(2)
    api.list.mockResolvedValue([note(), note({ id: 'n2' })])
    const { user } = renderWithProviders(<NotificationBell />)

    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await user.click(await screen.findByRole('button', { name: 'Mark all as read' }))

    await waitFor(() => expect(api.markAllRead).toHaveBeenCalled())
  })
})
