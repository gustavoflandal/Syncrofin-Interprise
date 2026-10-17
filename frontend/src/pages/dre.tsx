import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Download } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { costCenters, dreApi } from '@/lib/api'
import type { DreReport, DreSection } from '@/lib/api'
import { formatCurrency } from '@/lib/format'
import { useWorkspace } from '@/contexts/workspace-context'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'

type PeriodMode = 'monthly' | 'quarterly' | 'annual'
type AccountingMode = 'competence' | 'cash'

function SectionAccordion({
  section,
  fmt,
  prevSection,
  showBudget,
}: {
  section: DreSection
  fmt: (v: number) => string
  prevSection?: DreSection
  showBudget?: boolean
}) {
  const [open, setOpen] = useState(true)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const n = (v: string | undefined | null) => Number(v ?? 0)

  const extraCols = (showBudget ? 1 : 0) + (prevSection ? 1 : 0)

  const varianceBadge = (actual: number, budgeted: number | undefined | null) => {
    if (budgeted == null) return null
    const diff = actual - budgeted
    const pct = budgeted !== 0 ? Math.abs(diff / budgeted) * 100 : 0
    const positive = diff >= 0
    return (
      <span className={`text-xs ml-1 ${positive ? 'text-green-600' : 'text-destructive'}`}>
        {positive ? '+' : ''}
        {diff.toFixed(0)} ({pct.toFixed(0)}%)
      </span>
    )
  }

  return (
    <tbody>
      <tr
        className="bg-muted/30 cursor-pointer select-none"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-6 py-2 font-semibold">
          <span className="inline-flex items-center gap-1">
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            {section.label}
          </span>
        </td>
        <td className="px-6 py-2 text-right tabular-nums font-semibold">
          {fmt(n(section.subtotal))}
        </td>
        {showBudget && (
          <td className="px-6 py-2 text-right tabular-nums font-semibold text-muted-foreground">
            {section.budgeted != null ? fmt(n(section.budgeted)) : '—'}
            {varianceBadge(n(section.subtotal), section.budgeted ? n(section.budgeted) : null)}
          </td>
        )}
        {prevSection && (
          <td className="px-6 py-2 text-right tabular-nums text-muted-foreground">
            {fmt(n(prevSection.subtotal))}
          </td>
        )}
      </tr>

      {open &&
        section.groups.map((grp) => {
          const grpOpen = openGroups[grp.group_name] ?? true
          const prevGrp = prevSection?.groups.find((g) => g.group_name === grp.group_name)
          return (
            <tr
              key={`grp-${grp.group_name}`}
              className="cursor-pointer hover:bg-muted/20"
              onClick={() => setOpenGroups((o) => ({ ...o, [grp.group_name]: !grpOpen }))}
            >
              <td colSpan={2 + extraCols} className="p-0">
                <table className="w-full text-sm">
                  <tbody>
                    <tr>
                      <td className="px-8 py-1.5">
                        <span className="inline-flex items-center gap-1">
                          {grpOpen ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronRight className="h-3 w-3" />
                          )}
                          {grp.group_name}
                        </span>
                      </td>
                      <td className="px-6 py-1.5 text-right tabular-nums">
                        {fmt(n(grp.subtotal))}
                      </td>
                      {showBudget && (
                        <td className="px-6 py-1.5 text-right tabular-nums text-muted-foreground">
                          {grp.budgeted != null ? fmt(n(grp.budgeted)) : '—'}
                        </td>
                      )}
                      {prevGrp && (
                        <td className="px-6 py-1.5 text-right tabular-nums text-muted-foreground">
                          {fmt(n(prevGrp.subtotal))}
                        </td>
                      )}
                    </tr>
                    {grpOpen &&
                      grp.lines.map((line) => {
                        const prevLine = prevGrp?.lines.find((l) => l.label === line.label)
                        return (
                          <tr key={`line-${line.label}`} className="border-b last:border-0">
                            <td className="px-12 py-1 text-muted-foreground">{line.label}</td>
                            <td className="px-6 py-1 text-right tabular-nums">
                              {fmt(n(line.amount))}
                            </td>
                            {showBudget && (
                              <td className="px-6 py-1 text-right tabular-nums text-muted-foreground">
                                {line.budgeted != null ? (
                                  <>
                                    {fmt(n(line.budgeted))}
                                    {varianceBadge(n(line.amount), n(line.budgeted))}
                                  </>
                                ) : (
                                  '—'
                                )}
                              </td>
                            )}
                            {prevLine && (
                              <td className="px-6 py-1 text-right tabular-nums text-muted-foreground">
                                {fmt(n(prevLine.amount))}
                              </td>
                            )}
                          </tr>
                        )
                      })}
                  </tbody>
                </table>
              </td>
            </tr>
          )
        })}
    </tbody>
  )
}

export default function DrePage() {
  const { t } = useTranslation()
  const { current } = useWorkspace()
  const currency = current?.default_currency ?? 'BRL'
  const locale = useDisplayLocale()
  const { mask } = usePrivacyMode()
  const now = new Date()

  const [mode, setMode] = useState<PeriodMode>('monthly')
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [quarter, setQuarter] = useState(Math.ceil((now.getMonth() + 1) / 3))
  const [ccId, setCcId] = useState<string>('')
  const [accountingMode, setAccountingMode] = useState<AccountingMode>('competence')
  const [showBudget, setShowBudget] = useState(false)

  const fmt = (v: number) => mask(formatCurrency(v, currency, locale))
  const n = (v: string | undefined | null) => Number(v ?? 0)

  const { data: ccList } = useQuery({
    queryKey: ['cost-centers'],
    queryFn: () => costCenters.list({ includeInactive: false }),
  })

  const cc = ccId || null

  const { data: dreMonthly, isLoading: loadingMonthly } = useQuery({
    queryKey: ['dre', year, month, cc, accountingMode, showBudget],
    queryFn: () => dreApi.getDre(year, month, cc, accountingMode, showBudget),
    enabled: mode === 'monthly',
  })

  const { data: dreQuarterly, isLoading: loadingQuarterly } = useQuery({
    queryKey: ['dre-quarterly', year, quarter, cc, accountingMode, showBudget],
    queryFn: () => dreApi.getDreQuarterly(year, quarter, cc, accountingMode, showBudget),
    enabled: mode === 'quarterly',
  })

  const { data: dreAnnual, isLoading: loadingAnnual } = useQuery({
    queryKey: ['dre-annual', year, cc, accountingMode, showBudget],
    queryFn: () => dreApi.getDreAnnual(year, cc, accountingMode, showBudget),
    enabled: mode === 'annual',
  })

  const { data: dfc, isLoading: loadingDfc } = useQuery({
    queryKey: ['dfc', year, month, cc],
    queryFn: () => dreApi.getDfc(year, month, cc),
    enabled: mode === 'monthly',
  })

  // DFC range for quarterly/annual (monthly buckets)
  const dfcRangeStart = mode === 'quarterly' ? (quarter - 1) * 3 + 1 : 1
  const dfcRangeEnd = mode === 'quarterly' ? (quarter - 1) * 3 + 3 : 12
  const { data: dfcRange, isLoading: loadingDfcRange } = useQuery({
    queryKey: ['dfc-range', year, dfcRangeStart, dfcRangeEnd, cc],
    queryFn: () => dreApi.getDfcRange(year, dfcRangeStart, dfcRangeEnd, cc),
    enabled: mode === 'quarterly' || mode === 'annual',
  })

  const isLoading =
    (mode === 'monthly' && loadingMonthly) ||
    (mode === 'quarterly' && loadingQuarterly) ||
    (mode === 'annual' && loadingAnnual)

  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i)
  const months = Array.from({ length: 12 }, (_, i) => i + 1)

  const activeDre: { sections: DreSection[]; result: string; prev?: DreReport } | null =
    mode === 'monthly' && dreMonthly
      ? { sections: dreMonthly.sections, result: dreMonthly.result, prev: dreMonthly.prev_month }
      : mode === 'quarterly' && dreQuarterly
        ? { sections: dreQuarterly.sections, result: dreQuarterly.result }
        : mode === 'annual' && dreAnnual
          ? { sections: dreAnnual.sections, result: dreAnnual.result }
          : null

  const dfcChartData = dfc?.periods.map((p) => ({
    date: p.date,
    inflows: n(p.inflows),
    outflows: n(p.outflows),
  }))

  // DFC range chart: aggregate weekly periods per month bucket
  const dfcRangeChartData = dfcRange?.map((r) => ({
    date: `${String(r.month).padStart(2, '0')}/${r.year}`,
    inflows: r.periods.reduce((s, p) => s + n(p.inflows), 0),
    outflows: r.periods.reduce((s, p) => s + n(p.outflows), 0),
  }))

  const periodLabel =
    mode === 'monthly'
      ? `${String(month).padStart(2, '0')}/${year}`
      : mode === 'quarterly'
        ? `Q${quarter}/${year}`
        : String(year)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PageHeader section="analyze" title={t('dre.title')} />
        <div className="flex flex-wrap items-center gap-2">
          {/* Period mode selector */}
          <div className="flex rounded border overflow-hidden text-sm">
            {(['monthly', 'quarterly', 'annual'] as PeriodMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1 ${mode === m ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
              >
                {t(`dre.period${m.charAt(0).toUpperCase()}${m.slice(1)}`)}
              </button>
            ))}
          </div>

          {/* Period params */}
          {mode === 'monthly' && (
            <>
              <select
                value={month}
                onChange={(e) => setMonth(Number(e.target.value))}
                className="rounded border px-2 py-1 text-sm"
              >
                {months.map((m) => (
                  <option key={m} value={m}>
                    {String(m).padStart(2, '0')}
                  </option>
                ))}
              </select>
              <select
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                className="rounded border px-2 py-1 text-sm"
              >
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </>
          )}
          {mode === 'quarterly' && (
            <>
              <select
                value={quarter}
                onChange={(e) => setQuarter(Number(e.target.value))}
                className="rounded border px-2 py-1 text-sm"
              >
                {[1, 2, 3, 4].map((q) => (
                  <option key={q} value={q}>
                    Q{q}
                  </option>
                ))}
              </select>
              <select
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                className="rounded border px-2 py-1 text-sm"
              >
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </>
          )}
          {mode === 'annual' && (
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="rounded border px-2 py-1 text-sm"
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          )}

          {/* Accounting mode toggle */}
          <div className="flex rounded border overflow-hidden text-sm">
            {(['competence', 'cash'] as AccountingMode[]).map((am) => (
              <button
                key={am}
                onClick={() => setAccountingMode(am)}
                className={`px-3 py-1 ${accountingMode === am ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
              >
                {t(`dre.accounting${am.charAt(0).toUpperCase()}${am.slice(1)}`)}
              </button>
            ))}
          </div>

          {/* Budget overlay toggle */}
          <button
            onClick={() => setShowBudget((v) => !v)}
            className={`rounded border px-3 py-1 text-sm ${showBudget ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
          >
            {t('dre.showBudget')}
          </button>

          {/* CC filter */}
          {ccList && ccList.length > 0 && (
            <select
              value={ccId}
              onChange={(e) => setCcId(e.target.value)}
              className="rounded border px-2 py-1 text-sm"
              aria-label={t('dre.filterCc')}
            >
              <option value="">{t('dre.filterCcAll')}</option>
              {ccList.map((cc) => (
                <option key={cc.id} value={cc.id}>
                  {cc.name}
                </option>
              ))}
            </select>
          )}

          {mode === 'monthly' && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => dreApi.exportDre(year, month, accountingMode, showBudget)}
              >
                <Download className="h-4 w-4 mr-1" />
                {t('dre.export')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => dreApi.exportDfc(year, month)}
              >
                <Download className="h-4 w-4 mr-1" />
                {t('dre.exportDfc')}
              </Button>
            </>
          )}
        </div>
      </div>

      {/* DRE table */}
      {isLoading ? (
        <Skeleton className="h-48" />
      ) : activeDre ? (
        <div className="rounded-xl border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-6 py-3 text-left font-medium text-muted-foreground"></th>
                <th className="px-6 py-3 text-right font-medium">{periodLabel}</th>
                {showBudget && (
                  <th className="px-6 py-3 text-right font-medium text-muted-foreground">
                    {t('dre.budgeted')}
                  </th>
                )}
                {activeDre.prev && (
                  <th className="px-6 py-3 text-right font-medium text-muted-foreground">
                    {t('dre.prevMonth')}
                  </th>
                )}
              </tr>
            </thead>
            {activeDre.sections.map((sec) => (
              <SectionAccordion
                key={sec.key}
                section={sec}
                fmt={fmt}
                prevSection={activeDre.prev?.sections.find((s) => s.key === sec.key)}
                showBudget={showBudget}
              />
            ))}
            <tbody>
              <tr className="border-t-2">
                <td className="px-6 py-3 font-bold">{t('dre.result')}</td>
                <td
                  className={`px-6 py-3 text-right tabular-nums font-bold ${n(activeDre.result) < 0 ? 'text-destructive' : ''}`}
                >
                  {fmt(n(activeDre.result))}
                </td>
                {showBudget && mode === 'monthly' && dreMonthly?.budget_result != null && (
                  <td className="px-6 py-3 text-right tabular-nums text-muted-foreground font-bold">
                    {fmt(n(dreMonthly.budget_result))}
                  </td>
                )}
                {showBudget && mode !== 'monthly' && <td />}
                {activeDre.prev && (
                  <td
                    className={`px-6 py-3 text-right tabular-nums text-muted-foreground ${n(activeDre.prev.result) < 0 ? 'text-destructive' : ''}`}
                  >
                    {fmt(n(activeDre.prev.result))}
                  </td>
                )}
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-muted-foreground">{t('dre.noData')}</p>
      )}

      {/* Quarterly: detail by month */}
      {mode === 'quarterly' && dreQuarterly && (
        <details className="rounded-xl border bg-card p-4">
          <summary className="cursor-pointer font-medium">{t('dre.monthsDetail')}</summary>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {dreQuarterly.months.map((m) => (
              <div key={m.month} className="rounded border p-3 text-sm">
                <div className="font-semibold mb-2">
                  {String(m.month).padStart(2, '0')}/{m.year}
                </div>
                {m.sections.map((s) => (
                  <div key={s.key} className="flex justify-between">
                    <span className="text-muted-foreground">{s.label}</span>
                    <span>{fmt(n(s.subtotal))}</span>
                  </div>
                ))}
                <div className="flex justify-between font-semibold border-t mt-1 pt-1">
                  <span>{t('dre.result')}</span>
                  <span className={n(m.result) < 0 ? 'text-destructive' : ''}>
                    {fmt(n(m.result))}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Annual: seasonality table */}
      {mode === 'annual' && dreAnnual && (
        <div className="rounded-xl border bg-card overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left font-medium text-muted-foreground sticky left-0 bg-card">
                  {t('dre.title')}
                </th>
                {dreAnnual.monthly.map((m) => (
                  <th key={m.month} className="px-3 py-2 text-right font-medium">
                    {String(m.month).padStart(2, '0')}
                  </th>
                ))}
                <th className="px-3 py-2 text-right font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              {dreAnnual.sections.map((sec) => (
                <tr key={sec.key} className="bg-muted/30">
                  <td className="px-4 py-1.5 font-semibold sticky left-0 bg-muted/30">
                    {sec.label}
                  </td>
                  {dreAnnual.monthly.map((m) => {
                    const ms = m.sections.find((s) => s.key === sec.key)
                    return (
                      <td key={m.month} className="px-3 py-1.5 text-right tabular-nums">
                        {fmt(ms ? n(ms.subtotal) : 0)}
                      </td>
                    )
                  })}
                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                    {fmt(n(sec.subtotal))}
                  </td>
                </tr>
              ))}
              <tr className="border-t-2 font-bold">
                <td className="px-4 py-2 sticky left-0 bg-card">{t('dre.result')}</td>
                {dreAnnual.monthly.map((m) => (
                  <td
                    key={m.month}
                    className={`px-3 py-2 text-right tabular-nums ${n(m.result) < 0 ? 'text-destructive' : ''}`}
                  >
                    {fmt(n(m.result))}
                  </td>
                ))}
                <td
                  className={`px-3 py-2 text-right tabular-nums ${n(dreAnnual.result) < 0 ? 'text-destructive' : ''}`}
                >
                  {fmt(n(dreAnnual.result))}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* DFC chart (monthly: weekly view; quarterly/annual: monthly buckets) */}
      {mode === 'monthly' && (
        <div>
          <h3 className="font-semibold mb-3">{t('dre.dfc')}</h3>
          {loadingDfc ? (
            <Skeleton className="h-48" />
          ) : dfcChartData && dfcChartData.length > 0 ? (
            <div className="rounded-xl border bg-card p-4">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={dfcChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number | undefined) => [
                      value != null ? fmt(value) : '',
                      '',
                    ]}
                  />
                  <Bar dataKey="inflows" name={t('dre.inflows')} fill="#22c55e" />
                  <Bar dataKey="outflows" name={t('dre.outflows')} fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-muted-foreground">{t('dre.noData')}</p>
          )}
        </div>
      )}

      {(mode === 'quarterly' || mode === 'annual') && (
        <div>
          <h3 className="font-semibold mb-3">{t('dre.dfc')}</h3>
          {loadingDfcRange ? (
            <Skeleton className="h-48" />
          ) : dfcRangeChartData && dfcRangeChartData.length > 0 ? (
            <div className="rounded-xl border bg-card p-4">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={dfcRangeChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number | undefined) => [
                      value != null ? fmt(value) : '',
                      '',
                    ]}
                  />
                  <Bar dataKey="inflows" name={t('dre.inflows')} fill="#22c55e" />
                  <Bar dataKey="outflows" name={t('dre.outflows')} fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-muted-foreground">{t('dre.noData')}</p>
          )}
        </div>
      )}
    </div>
  )
}
