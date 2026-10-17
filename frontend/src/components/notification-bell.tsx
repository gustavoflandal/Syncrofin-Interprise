import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertOctagon, AlertTriangle, Bell, CheckCheck, Info, RefreshCw } from 'lucide-react'
import { notifications as notificationsApi } from '@/lib/api'
import { formatRelativeLocalized } from '@/lib/relative-time'
import { badgeLabel } from '@/lib/notification-utils'
import { cn } from '@/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { AppNotification, NotificationSeverity } from '@/types'

const POLL_MS = 60_000

const SEVERITY_ICON: Record<NotificationSeverity, { Icon: typeof Info; className: string }> = {
  info: { Icon: Info, className: 'text-sky-500' },
  warning: { Icon: AlertTriangle, className: 'text-amber-500' },
  critical: { Icon: AlertOctagon, className: 'text-red-500' },
}

interface NotificationBellProps {
  /** Sidebar (dark) or plain surface. */
  dark?: boolean
  className?: string
}

/**
 * The inbox: a bell with an unread count, and a list you can act on.
 *
 * The count is polled once a minute (cheap, one indexed count). Opening the
 * list refreshes the generators first, so what you see is not an hour old.
 * Clicking a notification marks it read and takes you to the place it is about.
 */
export function NotificationBell({ dark, className }: NotificationBellProps) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: unread = 0 } = useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: POLL_MS,
    staleTime: POLL_MS / 2,
    retry: false,
  })
  const { data: items = [], isFetching } = useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => notificationsApi.list({ limit: 30 }),
    staleTime: 10_000,
    retry: false,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['notifications'] })
  const refresh = useMutation({ mutationFn: notificationsApi.refresh, onSuccess: invalidate })
  const readOne = useMutation({ mutationFn: notificationsApi.markRead, onSettled: invalidate })
  const readAll = useMutation({ mutationFn: notificationsApi.markAllRead, onSuccess: invalidate })

  const open = (n: AppNotification) => {
    if (!n.read_at) readOne.mutate(n.id)
    const route = n.data?.route
    if (typeof route === 'string' && route.startsWith('/')) navigate(route)
  }

  return (
    <Popover onOpenChange={(isOpen) => isOpen && refresh.mutate()}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'relative p-1 rounded-md transition-colors',
            dark
              ? 'text-sidebar-muted hover:text-sidebar-foreground hover:bg-sidebar-accent'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted',
            className,
          )}
          aria-label={t('notifications.aria', { count: unread })}
          title={t('notifications.title')}
        >
          <Bell size={16} />
          {unread > 0 && (
            <span
              data-testid="notification-badge"
              className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold leading-4 text-center"
            >
              {badgeLabel(unread)}
            </span>
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-[22rem] max-w-[calc(100vw-2rem)] p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="text-sm font-semibold text-foreground">{t('notifications.title')}</p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => refresh.mutate()}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted"
              aria-label={t('notifications.refresh')}
              title={t('notifications.refresh')}
            >
              <RefreshCw size={14} className={cn((refresh.isPending || isFetching) && 'animate-spin')} />
            </button>
            <button
              type="button"
              onClick={() => readAll.mutate()}
              disabled={unread === 0}
              className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-40"
              aria-label={t('notifications.markAllRead')}
              title={t('notifications.markAllRead')}
            >
              <CheckCheck size={14} />
            </button>
          </div>
        </div>

        {items.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t('notifications.empty')}</p>
        ) : (
          <ul className="max-h-96 overflow-y-auto divide-y divide-border">
            {items.map((n) => {
              const { Icon, className: iconClass } = SEVERITY_ICON[n.severity] ?? SEVERITY_ICON.info
              return (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => open(n)}
                    className={cn(
                      'flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60',
                      !n.read_at && 'bg-primary/[0.04]',
                    )}
                  >
                    <Icon size={16} className={cn('mt-0.5 shrink-0', iconClass)} />
                    <span className="min-w-0 flex-1">
                      <span className={cn('block text-[13px] text-foreground', !n.read_at && 'font-semibold')}>
                        {n.title}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">{n.body}</span>
                      <span className="mt-1 block text-[10px] text-muted-foreground/70">
                        {formatRelativeLocalized(n.created_at, i18n.resolvedLanguage ?? i18n.language)}
                      </span>
                    </span>
                    {!n.read_at && (
                      <span aria-label={t('notifications.unread')} className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  )
}
