import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { allocationsApi, type CostCenterAllocation, type CostCenterAllocationInput } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { formatCurrency } from '@/lib/format'
import type { CostCenter } from '@/types'

type Mode = 'percentage' | 'amount'
interface Row {
  cost_center_id: string
  value: string
}

const toNumber = (v: string) => {
  const n = Number(v.replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}
const round2 = (n: number) => Math.round(n * 100) / 100

interface Props {
  transactionId: string
  /** Valor da transação (positivo). */
  amount: number
  currency: string
  costCenters: CostCenter[]
  initial: CostCenterAllocation[]
  disabled?: boolean
  onChanged?: () => void
}

/** Rateio de uma transação entre centros de custo (A8). */
export function ApportionmentSection({
  transactionId,
  amount,
  currency,
  costCenters,
  initial,
  disabled = false,
  onChanged,
}: Props) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const locale = i18n.resolvedLanguage ?? 'pt-BR'
  const [enabled, setEnabled] = useState(initial.length > 0)
  const [mode, setMode] = useState<Mode>('percentage')
  const [rows, setRows] = useState<Row[]>(
    initial.map((a) => ({ cost_center_id: a.cost_center_id, value: String(Number(a.percentage ?? 0)) })),
  )

  const target = mode === 'percentage' ? 100 : amount
  const sum = round2(rows.reduce((acc, r) => acc + toNumber(r.value), 0))
  const matches = rows.length > 0 && Math.abs(sum - target) < 0.005
  const usedCenters = new Set(rows.map((r) => r.cost_center_id))
  const hasDuplicate = usedCenters.size !== rows.length
  const canSave = !disabled && matches && !hasDuplicate && rows.every((r) => r.cost_center_id)

  function completeLast(next: Row[], changed: number): Row[] {
    // Percentual: a última linha fecha sozinha em 100%.
    if (mode !== 'percentage' || next.length < 2 || changed === next.length - 1) return next
    const others = next.slice(0, -1).reduce((acc, r) => acc + toNumber(r.value), 0)
    const last = { ...next[next.length - 1], value: String(Math.max(0, round2(100 - others))) }
    return [...next.slice(0, -1), last]
  }

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((prev) => completeLast(prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)), i))
  }

  function addRow() {
    const free = costCenters.find((c) => c.is_active && !usedCenters.has(c.id))
    setRows((prev) => {
      const next = [...prev, { cost_center_id: free?.id ?? '', value: '' }]
      return completeLast(next, -1)
    })
  }

  function changeMode(next: Mode) {
    if (next === mode) return
    setMode(next)
    // Troca de modo recomeça os valores: percentual e valor não se convertem linha a linha sem surpresa.
    setRows((prev) => prev.map((r) => ({ ...r, value: '' })))
  }

  const save = useMutation({
    mutationFn: () => {
      const items: CostCenterAllocationInput[] = rows.map((r) =>
        mode === 'percentage'
          ? { cost_center_id: r.cost_center_id, percentage: toNumber(r.value) }
          : { cost_center_id: r.cost_center_id, amount: toNumber(r.value) },
      )
      return allocationsApi.set(transactionId, items)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      onChanged?.()
      toast.success(t('common.success'))
    },
    onError: (err) => toast.error(extractApiError(err, t('common.error'))),
  })

  const clear = useMutation({
    mutationFn: () => allocationsApi.clear(transactionId),
    onSuccess: () => {
      setRows([])
      setEnabled(false)
      qc.invalidateQueries({ queryKey: ['transactions'] })
      onChanged?.()
    },
    onError: (err) => toast.error(extractApiError(err, t('common.error'))),
  })

  function toggle(on: boolean) {
    if (on) {
      setEnabled(true)
      if (rows.length === 0) setRows([{ cost_center_id: '', value: mode === 'percentage' ? '100' : String(amount) }])
    } else if (initial.length > 0) {
      clear.mutate()
    } else {
      setEnabled(false)
      setRows([])
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border p-3">
      <label className="flex cursor-pointer items-center gap-3">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-border accent-primary"
          checked={enabled}
          disabled={disabled}
          onChange={(e) => toggle(e.target.checked)}
        />
        <span className="text-sm font-medium">{t('apportionment.title')}</span>
      </label>

      {enabled && (
        <>
          <p className="text-xs text-muted-foreground">{t('apportionment.allocations')}</p>
          <div className="flex gap-2 text-xs">
            {(['percentage', 'amount'] as const).map((m) => (
              <button
                key={m}
                type="button"
                disabled={disabled}
                onClick={() => changeMode(m)}
                className={`rounded-md border px-2 py-1 ${mode === m ? 'border-primary bg-primary/10 text-primary' : 'border-border'}`}
              >
                {t(`apportionment.${m}`)}
              </button>
            ))}
          </div>

          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <select
                value={row.cost_center_id}
                disabled={disabled}
                onChange={(e) => updateRow(i, { cost_center_id: e.target.value })}
                className="min-w-0 flex-1 rounded-md border border-input bg-card px-3 py-2 text-sm"
              >
                <option value="">{t('costCenter.none')}</option>
                {costCenters
                  .filter((c) => c.is_active || c.id === row.cost_center_id)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.code ? ` (${c.code})` : ''}
                    </option>
                  ))}
              </select>
              <Input
                inputMode="decimal"
                className="w-28"
                value={row.value}
                disabled={disabled}
                aria-label={t(`apportionment.${mode}`)}
                onChange={(e) => updateRow(i, { value: e.target.value })}
              />
              <span className="w-4 text-xs text-muted-foreground">{mode === 'percentage' ? '%' : ''}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                disabled={disabled}
                onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
                aria-label={t('common.delete')}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}

          <div className="flex items-center justify-between text-sm">
            <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={addRow}>
              <Plus className="mr-1 h-4 w-4" /> {t('apportionment.addCenter')}
            </Button>
            <span className={matches ? 'text-emerald-600' : 'text-destructive'}>
              {mode === 'percentage'
                ? `${sum}% / 100%`
                : `${formatCurrency(sum, currency, locale)} / ${formatCurrency(amount, currency, locale)}`}
            </span>
          </div>
          {!matches && rows.length > 0 && (
            <p className="text-xs text-destructive">{t('apportionment.totalMismatch')}</p>
          )}

          <div className="flex justify-end gap-2">
            {initial.length > 0 && (
              <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={() => clear.mutate()}>
                {t('apportionment.clear')}
              </Button>
            )}
            <Button type="button" size="sm" disabled={!canSave || save.isPending} onClick={() => save.mutate()}>
              {t('common.save')}
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
