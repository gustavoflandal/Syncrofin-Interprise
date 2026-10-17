import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Download } from 'lucide-react'
import { accessLog as accessLogApi, admin as adminApi } from '@/lib/api'
import { ACCESS_ACTIONS, accessAction, accessReason } from '@/lib/access-log'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { AccessLogFilters, AuditEvent } from '@/types'

const PAGE_SIZE = 50

const SELECT_CLASS =
  'h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'

/** Who got into the instance, or tried to, and from where. Administrator only (the route enforces it). */
export default function AccessLogPage() {
  const { t, i18n } = useTranslation()
  const [draft, setDraft] = useState<AccessLogFilters>({})
  const [filters, setFilters] = useState<AccessLogFilters>({})
  const [page, setPage] = useState(1)

  const retention = useQuery({ queryKey: ['access-log-retention'], queryFn: accessLogApi.retention })
  // The person filter only offers the first 100 accounts (the server caps `limit` at 100).
  const people = useQuery({ queryKey: ['access-log-people'], queryFn: () => adminApi.listUsers({ limit: 100 }) })
  const events = useQuery({
    queryKey: ['access-log', filters, page],
    queryFn: () => accessLogApi.list(filters, page, PAGE_SIZE),
  })
  const exporting = useMutation({
    mutationFn: () => accessLogApi.exportCsv(filters),
    onError: () => toast.error(t('accessLog.exportFailed')),
  })

  const total = events.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const when = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'short', timeStyle: 'medium' })

  function apply() {
    setPage(1)
    setFilters({ ...draft })
  }

  function personLabel(event: AuditEvent): string {
    if (event.actor_email) return event.actor_email
    if (event.actor_kind === 'api_token') return t('accessLog.apiToken')
    return event.actor_user_id ? t('accessLog.deletedUser') : '—'
  }

  return (
    <div className="container max-w-6xl py-8">
      <PageHeader
        section={t('accessLog.section')}
        title={t('accessLog.title')}
        action={
          <Button size="sm" onClick={() => exporting.mutate()} disabled={exporting.isPending}>
            <Download className="mr-2 h-4 w-4" />
            {t('accessLog.export')}
          </Button>
        }
      />
      <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
        {t('accessLog.description', { days: retention.data?.days ?? 183 })}
      </p>

      <section className="mb-4 grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2 lg:grid-cols-6">
        <div className="space-y-1.5">
          <Label htmlFor="access-from" className="text-[13px]">
            {t('accessLog.from')}
          </Label>
          <Input
            id="access-from"
            type="date"
            value={draft.from?.slice(0, 10) ?? ''}
            onChange={(e) => setDraft({ ...draft, from: e.target.value ? `${e.target.value}T00:00:00` : undefined })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-to" className="text-[13px]">
            {t('accessLog.to')}
          </Label>
          <Input
            id="access-to"
            type="date"
            value={draft.to?.slice(0, 10) ?? ''}
            onChange={(e) => setDraft({ ...draft, to: e.target.value ? `${e.target.value}T23:59:59` : undefined })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-person" className="text-[13px]">
            {t('accessLog.person')}
          </Label>
          <select
            id="access-person"
            className={SELECT_CLASS}
            value={draft.actor_user_id ?? ''}
            onChange={(e) => setDraft({ ...draft, actor_user_id: e.target.value || undefined })}
          >
            <option value="">{t('accessLog.all')}</option>
            {(people.data?.items ?? []).map((person) => (
              <option key={person.id} value={person.id}>
                {person.email}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-action" className="text-[13px]">
            {t('accessLog.action')}
          </Label>
          <select
            id="access-action"
            className={SELECT_CLASS}
            value={draft.action ?? ''}
            onChange={(e) => setDraft({ ...draft, action: e.target.value || undefined })}
          >
            <option value="">{t('accessLog.all')}</option>
            {ACCESS_ACTIONS.map((name) => (
              <option key={name} value={name}>
                {accessAction(t, name)}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-ip" className="text-[13px]">
            {t('accessLog.ip')}
          </Label>
          <Input
            id="access-ip"
            value={draft.ip ?? ''}
            onChange={(e) => setDraft({ ...draft, ip: e.target.value.trim() || undefined })}
          />
        </div>
        <div className="flex items-end">
          <Button className="w-full" onClick={apply}>
            {t('accessLog.filter')}
          </Button>
        </div>
      </section>

      <section className="rounded-xl border bg-card">
        {events.isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : events.isError ? (
          <p className="p-6 text-sm text-destructive">{t('accessLog.loadFailed')}</p>
        ) : events.data && events.data.items.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">{t('accessLog.empty')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('accessLog.when')}</TableHead>
                <TableHead>{t('accessLog.who')}</TableHead>
                <TableHead>{t('accessLog.action')}</TableHead>
                <TableHead>{t('accessLog.ip')}</TableHead>
                <TableHead>{t('accessLog.device')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.data?.items.map((event) => {
                const reason = accessReason(t, event.action, event.detail)
                return (
                  <TableRow key={event.id}>
                    <TableCell className="whitespace-nowrap text-sm">{when.format(new Date(event.occurred_at))}</TableCell>
                    <TableCell className="text-sm">{personLabel(event)}</TableCell>
                    <TableCell className="text-sm">
                      {accessAction(t, event.action)}
                      {reason && <span className="text-muted-foreground"> · {reason}</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm">{event.ip ?? '—'}</TableCell>
                    <TableCell className="max-w-[16rem] truncate text-sm text-muted-foreground" title={event.user_agent ?? undefined}>
                      {event.user_agent ?? '—'}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </section>

      {total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-end gap-3 text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            {t('accessLog.previous')}
          </Button>
          <span className="text-muted-foreground">{t('accessLog.pageOf', { page, pages })}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            {t('accessLog.next')}
          </Button>
        </div>
      )}
    </div>
  )
}
