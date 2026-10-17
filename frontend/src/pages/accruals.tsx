import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Play, X } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useWorkspace } from '@/contexts/workspace-context'
import {
  accounts as accountsApi,
  accrualsApi,
  categories as categoriesApi,
  costCenters as costCentersApi,
  type AccrualEntryStatus,
  type AccrualSchedule,
  type AccrualType,
} from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { formatCurrency } from '@/lib/format'

const STATUS_STYLE: Record<AccrualEntryStatus, string> = {
  pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  posted: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  skipped: 'bg-muted text-muted-foreground',
}

function monthLabel(iso: string, locale: string) {
  const [y, m] = iso.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString(locale, { month: 'short', year: 'numeric' })
}

const EMPTY_FORM = {
  type: 'accrual' as AccrualType,
  description: '',
  total: '',
  start: '',
  end: '',
  accountId: '',
  categoryId: '',
  costCenterId: '',
}

export default function AccrualsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'pt-BR'
  const qc = useQueryClient()
  const { can } = useWorkspace()
  const canWrite = can('transactions.write')

  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: schedules = [], isLoading } = useQuery({ queryKey: ['accruals'], queryFn: accrualsApi.list })
  const { data: detail } = useQuery({
    queryKey: ['accruals', selectedId],
    queryFn: () => accrualsApi.get(selectedId!),
    enabled: !!selectedId,
  })
  const { data: accountsList = [] } = useQuery({ queryKey: ['accounts'], queryFn: () => accountsApi.list() })
  const { data: categoriesList = [] } = useQuery({ queryKey: ['categories'], queryFn: () => categoriesApi.list() })
  const { data: ccList = [] } = useQuery({ queryKey: ['cost-centers'], queryFn: () => costCentersApi.list() })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['accruals'] })
    qc.invalidateQueries({ queryKey: ['transactions'] })
  }

  const create = useMutation({
    mutationFn: () =>
      accrualsApi.create({
        type: form.type,
        description: form.description,
        total_amount: Number(form.total.replace(',', '.')),
        start_date: form.start,
        end_date: form.end,
        account_id: form.accountId,
        category_id: form.categoryId || null,
        cost_center_id: form.costCenterId || null,
      }),
    onSuccess: (created) => {
      invalidate()
      setCreateOpen(false)
      setForm(EMPTY_FORM)
      setSelectedId(created.id)
    },
    onError: (err) => toast.error(extractApiError(err, t('common.error'))),
  })

  const cancel = useMutation({
    mutationFn: (id: string) => accrualsApi.cancel(id),
    onSuccess: invalidate,
    onError: (err) => toast.error(extractApiError(err, t('common.error'))),
  })

  const postNow = useMutation({
    mutationFn: () => accrualsApi.post(),
    onSuccess: (r) => {
      invalidate()
      toast.success(t('accruals.postResult', { posted: r.posted, skipped: r.skipped }))
    },
    onError: (err) => toast.error(extractApiError(err, t('common.error'))),
  })

  const formValid =
    form.description.trim() &&
    Number(form.total.replace(',', '.')) > 0 &&
    form.start &&
    form.end &&
    form.start < form.end &&
    form.accountId

  const selected: AccrualSchedule | undefined = detail

  return (
    <div className="space-y-6">
      <PageHeader
        section={t('accruals.description')}
        title={t('accruals.title')}
        action={
          canWrite && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => postNow.mutate()} disabled={postNow.isPending}>
                <Play className="mr-1 h-4 w-4" /> {t('accruals.postNow')}
              </Button>
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="mr-1 h-4 w-4" /> {t('accruals.create')}
              </Button>
            </div>
          )
        }
      />

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">{t('accruals.schedules')}</h2>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : schedules.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('accruals.empty')}</p>
        ) : (
          <ul className="space-y-2">
            {schedules.map((s) => {
              const done = s.posted_count
              const pct = s.period_count ? Math.round((done / s.period_count) * 100) : 0
              return (
                <li
                  key={s.id}
                  className={`cursor-pointer rounded-lg border p-3 ${selectedId === s.id ? 'border-primary' : 'border-border'} ${s.is_active ? '' : 'opacity-60'}`}
                  onClick={() => setSelectedId(s.id)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{s.description}</p>
                      <p className="text-xs text-muted-foreground">
                        {t(`accruals.${s.type}`)} · {monthLabel(s.start_date, locale)} → {monthLabel(s.end_date, locale)} ·{' '}
                        {t('accruals.periods')}: {s.period_count}
                      </p>
                    </div>
                    <div className="text-right text-sm">
                      <p className="font-medium">{formatCurrency(Number(s.total_amount), s.currency, locale)}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatCurrency(Number(s.amount_per_period), s.currency, locale)} / {t('accruals.perPeriod')}
                      </p>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-3">
                    <div
                      className="h-2 flex-1 overflow-hidden rounded-full bg-muted"
                      role="progressbar"
                      aria-label={t('accruals.progress')}
                      aria-valuemin={0}
                      aria-valuemax={s.period_count}
                      aria-valuenow={done}
                    >
                      <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {done}/{s.period_count}
                    </span>
                    {canWrite && s.is_active && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={(e) => {
                          e.stopPropagation()
                          cancel.mutate(s.id)
                        }}
                      >
                        <X className="mr-1 h-3 w-3" /> {t('accruals.cancel')}
                      </Button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {selected && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium">{selected.description}</h2>
          <ol className="space-y-1">
            {(selected.entries ?? []).map((e) => (
              <li key={e.id} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
                <span>{monthLabel(e.period_date, locale)}</span>
                <span className="flex items-center gap-3">
                  {formatCurrency(Number(e.amount), selected.currency, locale)}
                  <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[e.status]}`}>
                    {t(`accruals.${e.status}`)}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('accruals.create')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>{t('accruals.type')}</Label>
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value as AccrualType })}
                className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm"
              >
                <option value="accrual">{t('accruals.accrual')}</option>
                <option value="deferral">{t('accruals.deferral')}</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label>{t('accruals.descriptionField')}</Label>
              <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>{t('accruals.totalAmount')}</Label>
              <Input
                inputMode="decimal"
                value={form.total}
                onChange={(e) => setForm({ ...form, total: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>{t('accruals.startDate')}</Label>
                <Input type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label>{t('accruals.endDate')}</Label>
                <Input type="date" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} />
              </div>
            </div>
            <div className="space-y-1">
              <Label>{t('accruals.account')}</Label>
              <select
                value={form.accountId}
                onChange={(e) => setForm({ ...form, accountId: e.target.value })}
                className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm"
              >
                <option value="">—</option>
                {accountsList.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">{t('accruals.accountHint')}</p>
            </div>
            <div className="space-y-1">
              <Label>{t('accruals.category')}</Label>
              <select
                value={form.categoryId}
                onChange={(e) => setForm({ ...form, categoryId: e.target.value })}
                className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm"
              >
                <option value="">—</option>
                {categoriesList.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            {ccList.length > 0 && (
              <div className="space-y-1">
                <Label>{t('costCenter.filter')}</Label>
                <select
                  value={form.costCenterId}
                  onChange={(e) => setForm({ ...form, costCenterId: e.target.value })}
                  className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm"
                >
                  <option value="">{t('costCenter.none')}</option>
                  {ccList.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button disabled={!formValid || create.isPending} onClick={() => create.mutate()}>
              {t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
