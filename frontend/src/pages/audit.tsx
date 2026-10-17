import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronDown, ChevronRight, Download, ShieldCheck } from 'lucide-react'
import { audit as auditApi } from '@/lib/api'
import { useAuth } from '@/contexts/auth-context'
import { useWorkspace } from '@/contexts/workspace-context'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { AuditEvent, AuditFilters } from '@/types'

const PAGE_SIZE = 50

const SELECT_CLASS =
  'h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'

function display(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function ChangesList({ event }: { event: AuditEvent }) {
  const { t } = useTranslation()
  const entries = Object.entries(event.changes ?? {})
  return (
    <div className="space-y-3 text-xs">
      {entries.length === 0 ? (
        <p className="text-muted-foreground">{event.detail ?? t('audit.noChanges')}</p>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="pr-4 font-medium">{t('audit.field')}</th>
              <th className="pr-4 font-medium">{t('audit.before')}</th>
              <th className="font-medium">{t('audit.after')}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([field, [before, after]]) => (
              <tr key={field} className="align-top">
                <td className="pr-4 font-mono">{field}</td>
                <td className="pr-4 break-all text-muted-foreground">{display(before)}</td>
                <td className="break-all">{display(after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted-foreground">
        {event.ip && (
          <>
            <dt>{t('audit.ip')}</dt>
            <dd className="font-mono">{event.ip}</dd>
          </>
        )}
        {event.request_id && (
          <>
            <dt>{t('audit.request')}</dt>
            <dd className="font-mono">{event.request_id}</dd>
          </>
        )}
        {event.user_agent && (
          <>
            <dt>{t('audit.userAgent')}</dt>
            <dd className="break-all">{event.user_agent}</dd>
          </>
        )}
        {event.entity_id && (
          <>
            <dt>{t('audit.recordId')}</dt>
            <dd className="font-mono break-all">{event.entity_id}</dd>
          </>
        )}
        {event.hash && (
          <>
            <dt>{t('audit.hash')}</dt>
            <dd className="font-mono break-all">
              #{event.seq} {event.hash}
            </dd>
          </>
        )}
      </dl>
    </div>
  )
}

export default function AuditPage() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { can } = useWorkspace()
  const canManage = can('audit.read')
  const [draft, setDraft] = useState<AuditFilters>({})
  const [filters, setFilters] = useState<AuditFilters>({})
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<string | null>(null)

  const facets = useQuery({ queryKey: ['audit-facets'], queryFn: auditApi.facets, enabled: canManage })
  const events = useQuery({
    queryKey: ['audit', filters, page],
    queryFn: () => auditApi.list(filters, page, PAGE_SIZE),
    enabled: canManage,
  })
  const exporting = useMutation({
    mutationFn: () => auditApi.exportCsv(filters),
    onError: () => toast.error(t('audit.exportFailed')),
  })
  const verifying = useMutation({
    mutationFn: auditApi.verify,
    onSuccess: (result) => {
      if (result.ok) toast.success(t('audit.verifyOk', { count: result.checked }))
      else toast.error(t('audit.verifyBroken', { seq: result.broken_at_seq, reason: result.reason }))
    },
    onError: () => toast.error(t('audit.verifyFailed')),
  })

  if (!canManage) {
    return (
      <div className="container max-w-5xl py-8">
        <p className="text-sm text-muted-foreground">{t('audit.ownersOnly')}</p>
      </div>
    )
  }

  const total = events.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const when = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'short', timeStyle: 'medium' })

  function apply() {
    setPage(1)
    setFilters({ ...draft })
  }

  function actorLabel(event: AuditEvent): string {
    if (event.actor_kind === 'system') return t('audit.system')
    if (event.actor_kind === 'api_token') return t('audit.apiToken')
    return event.actor_email ?? t('audit.deletedUser')
  }

  return (
    <div className="container max-w-6xl py-8">
      <PageHeader
        section={t('audit.section')}
        title={t('audit.title')}
        action={
          <div className="flex gap-2">
            {user?.is_superuser && (
              <Button variant="outline" size="sm" onClick={() => verifying.mutate()} disabled={verifying.isPending}>
                <ShieldCheck className="mr-2 h-4 w-4" />
                {t('audit.verify')}
              </Button>
            )}
            <Button size="sm" onClick={() => exporting.mutate()} disabled={exporting.isPending}>
              <Download className="mr-2 h-4 w-4" />
              {t('audit.export')}
            </Button>
          </div>
        }
      />
      <p className="mb-4 max-w-3xl text-sm text-muted-foreground">{t('audit.description')}</p>

      <section className="mb-4 grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1.5">
          <Label htmlFor="audit-from" className="text-[13px]">
            {t('audit.from')}
          </Label>
          <Input
            id="audit-from"
            type="date"
            value={draft.from?.slice(0, 10) ?? ''}
            onChange={(e) => setDraft({ ...draft, from: e.target.value ? `${e.target.value}T00:00:00` : undefined })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="audit-to" className="text-[13px]">
            {t('audit.to')}
          </Label>
          <Input
            id="audit-to"
            type="date"
            value={draft.to?.slice(0, 10) ?? ''}
            onChange={(e) => setDraft({ ...draft, to: e.target.value ? `${e.target.value}T23:59:59` : undefined })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="audit-entity" className="text-[13px]">
            {t('audit.entity')}
          </Label>
          <select
            id="audit-entity"
            className={SELECT_CLASS}
            value={draft.entity_type ?? ''}
            onChange={(e) => setDraft({ ...draft, entity_type: e.target.value || undefined })}
          >
            <option value="">{t('audit.all')}</option>
            {(facets.data?.entity_types ?? []).map((name) => (
              <option key={name} value={name}>
                {t(`audit.entities.${name}`, { defaultValue: name })}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="audit-action" className="text-[13px]">
            {t('audit.action')}
          </Label>
          <select
            id="audit-action"
            className={SELECT_CLASS}
            value={draft.action ?? ''}
            onChange={(e) => setDraft({ ...draft, action: e.target.value || undefined })}
          >
            <option value="">{t('audit.all')}</option>
            {(facets.data?.actions ?? []).map((name) => (
              <option key={name} value={name}>
                {t(`audit.actions.${name}`, { defaultValue: name })}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <Button className="w-full" onClick={apply}>
            {t('audit.filter')}
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
          <p className="p-6 text-sm text-destructive">{t('audit.loadFailed')}</p>
        ) : events.data && events.data.items.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">{t('audit.empty')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>{t('audit.when')}</TableHead>
                <TableHead>{t('audit.who')}</TableHead>
                <TableHead>{t('audit.action')}</TableHead>
                <TableHead>{t('audit.entity')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.data?.items.map((event) => {
                const expanded = open === event.id
                return (
                  <Fragment key={event.id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => setOpen(expanded ? null : event.id)}
                      aria-expanded={expanded}
                    >
                      <TableCell>
                        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">{when.format(new Date(event.occurred_at))}</TableCell>
                      <TableCell>{actorLabel(event)}</TableCell>
                      <TableCell>{t(`audit.actions.${event.action}`, { defaultValue: event.action })}</TableCell>
                      <TableCell>{t(`audit.entities.${event.entity_type}`, { defaultValue: event.entity_type })}</TableCell>
                    </TableRow>
                    {expanded && (
                      <TableRow>
                        <TableCell />
                        <TableCell colSpan={4} className="bg-muted/30 py-3">
                          <ChangesList event={event} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        )}
      </section>

      <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
        <span>{t('audit.total', { count: total })}</span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            {t('audit.previous')}
          </Button>
          <span>{t('audit.pageOf', { page, pages })}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            {t('audit.next')}
          </Button>
        </div>
      </div>
    </div>
  )
}
