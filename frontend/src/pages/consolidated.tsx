import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { consolidatedApi, workspaces as workspacesApi, type WorkspaceDreSummary, type DreReport } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Building2, ChevronDown, Info } from 'lucide-react'
import { toast } from 'sonner'

const currentYear = new Date().getFullYear()
const currentMonth = new Date().getMonth() + 1

function formatCurrency(amount: string | number, currency: string) {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount
  if (currency === 'MIX') return n.toFixed(2)
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(n)
  } catch {
    return `${currency} ${n.toFixed(2)}`
  }
}

function DreSectionAccordion({
  dre,
  currency,
  label,
}: {
  dre: DreReport
  currency: string
  label: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <div className="border rounded-lg">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        onClick={() => setOpen(v => !v)}
      >
        <span className="font-semibold text-sm flex items-center gap-2">
          <Building2 className="h-4 w-4 text-muted-foreground" />
          {label}
        </span>
        <span className="flex items-center gap-3">
          <Badge
            variant={parseFloat(String(dre.result)) >= 0 ? 'default' : 'destructive'}
            className="text-xs"
          >
            {formatCurrency(dre.result, currency)}
          </Badge>
          <ChevronDown
            className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </span>
      </button>

      {open && (
        <div className="border-t px-4 py-3 space-y-2">
          {dre.sections.map(sec => (
            <div key={sec.key}>
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-1">
                {sec.label}
              </p>
              {sec.groups.map(grp => (
                <div key={grp.group_name} className="mb-1">
                  <p className="text-xs font-medium">{grp.group_name}</p>
                  {grp.lines.map(line => (
                    <div key={line.label} className="flex justify-between text-xs pl-3 py-0.5">
                      <span className="text-muted-foreground">{line.label}</span>
                      <span>{formatCurrency(line.amount, currency)}</span>
                    </div>
                  ))}
                  <div className="flex justify-between text-xs font-semibold pl-3 pt-0.5 border-t mt-0.5">
                    <span>{t('common.subtotal', 'Subtotal')}</span>
                    <span>{formatCurrency(grp.subtotal, currency)}</span>
                  </div>
                </div>
              ))}
            </div>
          ))}
          <div className="flex justify-between text-sm font-bold border-t pt-2">
            <span>{t('dre.result', 'Result')}</span>
            <span>{formatCurrency(dre.result, currency)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ConsolidatedPage() {
  const { t } = useTranslation()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [year, setYear] = useState(currentYear)
  const [month, setMonth] = useState(currentMonth)
  const [mode, setMode] = useState<'competence' | 'cash'>('competence')
  const [enabled, setEnabled] = useState(false)

  const { data: allWorkspaces = [] } = useQuery({
    queryKey: ['workspaces-list'],
    queryFn: workspacesApi.list,
  })

  const businessWorkspaces = allWorkspaces.filter(
    (ws: { kind: string }) => ws.kind === 'business' || ws.kind === 'enterprise',
  )

  const { data, isFetching, error } = useQuery({
    queryKey: ['consolidated-dre', [...selectedIds].sort(), year, month, mode],
    queryFn: () =>
      consolidatedApi.dre({
        workspace_ids: [...selectedIds],
        year,
        month,
        accounting_mode: mode,
      }),
    enabled: enabled && selectedIds.size >= 2,
    retry: false,
  })

  useEffect(() => {
    if (error) toast.error(String(error))
  }, [error])

  function toggleWs(id: string) {
    setSelectedIds(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
    setEnabled(false)
  }

  const months = Array.from({ length: 12 }, (_, i) => i + 1)

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('consolidated.title', 'Multi-Company Consolidation')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t('consolidated.description', 'View the aggregated DRE across multiple business workspaces.')}
        </p>
      </div>

      {/* Workspace selector */}
      {businessWorkspaces.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t('consolidated.noBusinessWorkspaces', 'No business workspaces available')}
        </p>
      ) : (
        <div className="space-y-2">
          <p className="text-sm font-medium">{t('consolidated.selectWorkspaces', 'Select workspaces')}</p>
          <div className="flex flex-wrap gap-2">
            {businessWorkspaces.map((ws: { id: string; name: string }) => (
              <button
                key={ws.id}
                type="button"
                onClick={() => toggleWs(ws.id)}
                className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                  selectedIds.has(ws.id)
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-background border-border hover:bg-muted'
                }`}
              >
                {ws.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Period + mode */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <label className="text-xs font-medium">{t('common.year', 'Year')}</label>
          <input
            type="number"
            value={year}
            min={2000}
            max={2100}
            onChange={e => { setYear(Number(e.target.value)); setEnabled(false) }}
            className="w-20 rounded border px-2 py-1.5 text-sm bg-background"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium">{t('common.month', 'Month')}</label>
          <select
            value={month}
            onChange={e => { setMonth(Number(e.target.value)); setEnabled(false) }}
            className="rounded border px-2 py-1.5 text-sm bg-background"
          >
            {months.map(m => (
              <option key={m} value={m}>
                {new Date(year, m - 1, 1).toLocaleDateString(undefined, { month: 'long' })}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium">{t('dre.accountingMode', 'Mode')}</label>
          <select
            value={mode}
            onChange={e => { setMode(e.target.value as 'competence' | 'cash'); setEnabled(false) }}
            className="rounded border px-2 py-1.5 text-sm bg-background"
          >
            <option value="competence">{t('dre.modeCompetence', 'Competence')}</option>
            <option value="cash">{t('dre.modeCash', 'Cash')}</option>
          </select>
        </div>
        <Button
          onClick={() => setEnabled(true)}
          disabled={selectedIds.size < 2 || isFetching}
        >
          {isFetching ? t('common.loading', 'Loading...') : t('consolidated.generate', 'Generate consolidated')}
        </Button>
      </div>

      {selectedIds.size < 2 && selectedIds.size > 0 && (
        <p className="text-sm text-amber-600 dark:text-amber-400 flex items-center gap-1">
          <Info className="h-4 w-4" />
          {t('consolidated.minTwo', 'Select at least 2 workspaces to consolidate.')}
        </p>
      )}

      {/* Note about intercompany */}
      <p className="text-xs text-muted-foreground flex items-center gap-1">
        <Info className="h-3 w-3" />
        {t('consolidated.intercompanyNote', 'Inter-company transfers are eliminated automatically.')}
      </p>

      {/* Results */}
      {data && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">{t('consolidated.perWorkspace', 'Per company')}</h2>
          {data.workspace_reports.map((ws: WorkspaceDreSummary) => (
            <DreSectionAccordion
              key={ws.workspace_id}
              dre={ws.dre}
              currency={ws.currency}
              label={ws.workspace_name}
            />
          ))}

          <h2 className="text-lg font-semibold mt-4">{t('consolidated.consolidated', 'Consolidated')}</h2>
          <DreSectionAccordion
            dre={data.consolidated}
            currency={data.consolidated.currency}
            label={t('consolidated.consolidated', 'Consolidated')}
          />
        </div>
      )}
    </div>
  )
}
