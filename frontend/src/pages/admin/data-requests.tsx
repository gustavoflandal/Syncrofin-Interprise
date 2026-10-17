import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { dataRequests as api } from '@/lib/api'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { AdminDataRequest, DataRequestStatus } from '@/types'

const STATUSES: DataRequestStatus[] = ['pending', 'resolved_auto', 'resolved_manual', 'rejected']

const SELECT_CLASS =
  'h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-56'

function ResolveRow({ row, onDone }: { row: AdminDataRequest; onDone: () => void }) {
  const { t } = useTranslation()
  const [note, setNote] = useState('')

  const resolve = useMutation({
    mutationFn: (status: 'resolved_manual' | 'rejected') => api.adminResolve(row.id, status, note.trim() || undefined),
    onSuccess: () => {
      toast.success(t('admin.dataRequests.resolved'))
      onDone()
    },
    onError: () => toast.error(t('common.error')),
  })

  return (
    <div className="space-y-1.5">
      <textarea
        className="min-h-13.5 w-full resize-y rounded-lg border border-input bg-transparent px-2 py-1.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={t('admin.dataRequests.resolutionNotePlaceholder')}
      />
      <div className="flex gap-1.5">
        <Button size="sm" disabled={resolve.isPending} onClick={() => resolve.mutate('resolved_manual')}>
          {t('admin.dataRequests.resolveButton')}
        </Button>
        <Button size="sm" variant="outline" disabled={resolve.isPending} onClick={() => resolve.mutate('rejected')}>
          {t('admin.dataRequests.rejectButton')}
        </Button>
      </div>
    </div>
  )
}

/** The administrator's queue: who asked for what, and — for a correction ticket — resolve it. */
export default function DataRequestsPage() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('')
  // Captured once, on mount: "overdue" only needs to be roughly right, not to tick live.
  const [now] = useState(() => Date.now())

  const requests = useQuery({
    queryKey: ['admin-data-requests', status],
    queryFn: () => api.adminList(status || undefined),
  })

  const when = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'short', timeStyle: 'short' })

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ['admin-data-requests'] })
  }

  return (
    <div className="container max-w-6xl py-8">
      <PageHeader section={t('admin.dataRequests.section')} title={t('admin.dataRequests.title')} />
      <p className="mb-4 max-w-3xl text-sm text-muted-foreground">{t('admin.dataRequests.description')}</p>

      <div className="mb-4 max-w-xs">
        <select
          className={SELECT_CLASS}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label={t('admin.dataRequests.filterStatus')}
        >
          <option value="">{t('accessLog.all')}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`dataRequests.statuses.${s}`)}
            </option>
          ))}
        </select>
      </div>

      <section className="rounded-xl border bg-card">
        {requests.isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : requests.isError ? (
          <p className="p-6 text-sm text-destructive">{t('admin.dataRequests.loadError')}</p>
        ) : requests.data && requests.data.items.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">{t('admin.dataRequests.empty')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('admin.dataRequests.requester')}</TableHead>
                <TableHead>{t('accessLog.action')}</TableHead>
                <TableHead>{t('admin.dataRequests.status')}</TableHead>
                <TableHead>{t('admin.dataRequests.due')}</TableHead>
                <TableHead>{t('admin.dataRequests.resolution')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.data?.items.map((row) => {
                const overdue = row.status === 'pending' && new Date(row.due_at).getTime() < now
                return (
                  <TableRow key={row.id}>
                    <TableCell className="text-sm">{row.actor_email ?? t('accessLog.deletedUser')}</TableCell>
                    <TableCell className="text-sm">
                      {t(`dataRequests.kinds.${row.kind}`)}
                      {row.detail && <p className="max-w-[16rem] truncate text-xs text-muted-foreground">{row.detail}</p>}
                    </TableCell>
                    <TableCell className="text-sm">{t(`dataRequests.statuses.${row.status}`)}</TableCell>
                    <TableCell className={`whitespace-nowrap text-sm ${overdue ? 'font-semibold text-destructive' : ''}`}>
                      {when.format(new Date(row.due_at))}
                      {overdue && <span className="ml-1 text-xs">({t('admin.dataRequests.overdue')})</span>}
                    </TableCell>
                    <TableCell className="min-w-56">
                      {row.status === 'pending' ? (
                        <ResolveRow row={row} onDone={refresh} />
                      ) : (
                        <span className="text-xs text-muted-foreground">{row.resolution_note ?? '—'}</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  )
}
