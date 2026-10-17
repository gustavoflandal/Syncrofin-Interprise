import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Banknote } from 'lucide-react'
import { arAp as arApApi, invoices as invoicesApi } from '@/lib/api'
import type { TitleRead } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { formatCurrency } from '@/lib/format'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'

const STATE_FILTERS = ['all', 'open', 'overdue', 'paid', 'draft'] as const

function StateBadge({ state }: { state: string }) {
  const { t } = useTranslation()
  const colors: Record<string, string> = {
    open: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    overdue: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    paid: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    partial: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    draft: 'bg-muted text-muted-foreground',
    void: 'bg-muted text-muted-foreground',
    uncollectible: 'bg-muted text-muted-foreground',
  }
  const label = t(`arAp.state${state.charAt(0).toUpperCase() + state.slice(1)}`, state)
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[state] ?? 'bg-muted text-muted-foreground'}`}>
      {label}
    </span>
  )
}

interface QuickSettleDialogProps {
  title: TitleRead | null
  currency: string
  onClose: () => void
}

function QuickSettleDialog({ title, currency, onClose }: QuickSettleDialogProps) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const qc = useQueryClient()
  const [txId, setTxId] = useState('')
  const [amount, setAmount] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mut = useMutation({
    mutationFn: () => invoicesApi.allocate(title!.id, txId.trim(), amount.trim() || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ar-ap-titles'] })
      qc.invalidateQueries({ queryKey: ['ar-ap-overview'] })
      onClose()
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? t('common.error'))
    },
  })

  return (
    <Dialog open={!!title} onOpenChange={() => onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('arAp.quickSettleTitle')}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">{t('arAp.quickSettleDesc')}</p>
        {title && (
          <p className="text-sm font-medium">
            {title.payee_name ?? `#${title.number}`} —{' '}
            {formatCurrency(Number(title.balance), currency, locale)}
          </p>
        )}
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium">{t('arAp.quickSettleTransaction')}</label>
            <Input
              value={txId}
              onChange={(e) => setTxId(e.target.value)}
              placeholder="UUID"
              className="mt-1 font-mono text-xs"
            />
          </div>
          <div>
            <label className="text-sm font-medium">{t('arAp.quickSettleAmount')}</label>
            <Input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={formatCurrency(Number(title?.balance ?? 0), currency, locale)}
              className="mt-1"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={() => { setError(null); mut.mutate() }}
            disabled={!txId.trim() || mut.isPending}
          >
            {t('arAp.quickSettleConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface TitlesListProps {
  direction: 'receivable' | 'payable'
  currency: string
}

export function TitlesList({ direction, currency }: TitlesListProps) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const { mask } = usePrivacyMode()
  const [stateFilter, setStateFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [settling, setSettling] = useState<TitleRead | null>(null)
  const PAGE_SIZE = 25

  const { data, isLoading } = useQuery({
    queryKey: ['ar-ap-titles', direction, stateFilter, page],
    queryFn: () => arApApi.titles(direction, stateFilter === 'all' ? undefined : stateFilter, page, PAGE_SIZE),
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const fmt = (v: string | number) => mask(formatCurrency(Number(v), currency, locale))

  return (
    <div className="space-y-4">
      {/* State filter tabs */}
      <div className="flex gap-1 flex-wrap">
        {STATE_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => { setStateFilter(s); setPage(1) }}
            className={`px-3 py-1 rounded-full text-sm transition-colors ${
              stateFilter === s
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            {t(`arAp.filter${s.charAt(0).toUpperCase() + s.slice(1)}`)}
          </button>
        ))}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <p className="text-muted-foreground text-sm py-8 text-center">{t('arAp.noTitles')}</p>
      ) : (
        <>
          <div className="rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">{t('arAp.titleNumber')}</th>
                  <th className="px-4 py-2 text-left font-medium">{t('arAp.titlePayee')}</th>
                  <th className="px-4 py-2 text-left font-medium">{t('arAp.titleDueDate')}</th>
                  <th className="px-4 py-2 text-right font-medium">{t('arAp.titleBalance')}</th>
                  <th className="px-4 py-2 text-left font-medium">{t('arAp.titleState')}</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {data.items.map((inv) => (
                  <tr key={inv.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {inv.series ? `${inv.series}-${inv.number}` : (inv.external_number ?? `#${inv.number ?? '—'}`)}
                    </td>
                    <td className="px-4 py-3 max-w-[180px] truncate">
                      {inv.payee_name ?? <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {inv.due_date}
                      {inv.days_overdue > 0 && (
                        <span className="ml-2 text-xs text-destructive">
                          {t('arAp.daysOverdue', { count: inv.days_overdue })}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-medium tabular-nums">{fmt(inv.balance)}</td>
                    <td className="px-4 py-3"><StateBadge state={inv.state} /></td>
                    <td className="px-4 py-3 text-right">
                      {(inv.state === 'open' || inv.state === 'overdue' || inv.state === 'partial') && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          onClick={() => setSettling(inv)}
                          title={t('arAp.quickSettleTitle')}
                        >
                          <Banknote className="h-4 w-4" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{data.total} títulos</span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPage((p) => p - 1)}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span>{page} / {totalPages}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      <QuickSettleDialog
        title={settling}
        currency={currency}
        onClose={() => setSettling(null)}
      />
    </div>
  )
}
