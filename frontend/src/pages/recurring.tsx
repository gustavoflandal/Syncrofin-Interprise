import React, { useMemo, useState } from 'react'
import { getAccountName, sortAccountsByDisplayName } from '@/lib/account-utils'
import { useTranslation } from 'react-i18next'
import { useDisplayLocale, useDateLocale } from '@/hooks/use-display-locale'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { categories as categoriesApi, categoryGroups as categoryGroupsApi, recurring as recurringApi, accounts as accountsApi, currencies as currenciesApi, costCenters as costCentersApi, taxObligations as taxObligationsApi } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { localDateString } from '@/lib/date-utils'
import { invalidateFinancialQueries } from '@/lib/invalidate-queries'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DeleteConfirmationDialog } from '@/components/delete-confirmation-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import type { Category, CategoryGroup, CostCenter, RecurringTransaction, TaxObligationType } from '@/types'
import { Pencil, Trash2, Plus, RefreshCw, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/components/page-header'
import { CategorySelect } from '@/components/category-select'
import { DatePickerInput } from '@/components/ui/date-picker-input'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { useAuth } from '@/contexts/auth-context'
import { useWorkspace } from '@/contexts/workspace-context'
import { formatCurrency } from '@/lib/format'

const TH = 'text-xs font-medium text-muted-foreground py-3'

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
      {children}
    </div>
  )
}

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="px-4 sm:px-5 py-4 border-b border-border flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {action}
    </div>
  )
}

const TAX_TYPES: TaxObligationType[] = [
  'das', 'darf_irpj', 'darf_csll', 'darf_irrf', 'darf_pis_cofins', 'iss', 'inss', 'icms', 'other',
]

// Nomes das categorias de sistema `biz_tax_*` (en, pt-BR, es): a API de
// categorias não expõe o slug, então o pré-preenchimento casa pelo nome.
const TAX_CATEGORY_NAMES: Partial<Record<TaxObligationType, string[]>> = {
  das: ['Simples Nacional'],
  darf_irpj: ['Income Taxes (IRPJ/CSLL)', 'Impostos sobre Lucro (IRPJ/CSLL)', 'Impuestos sobre Ganancia (IRPJ/CSLL)'],
  darf_csll: ['Income Taxes (IRPJ/CSLL)', 'Impostos sobre Lucro (IRPJ/CSLL)', 'Impuestos sobre Ganancia (IRPJ/CSLL)'],
  iss: ['Revenue Taxes (PIS/COFINS/ISS/ICMS)', 'Impostos sobre Receita (PIS/COFINS/ISS/ICMS)'],
}

function taxCategoryFor(type: TaxObligationType, categories: Category[]): string {
  const names = TAX_CATEGORY_NAMES[type]
  if (!names) return ''
  const wanted = names.map((n) => n.toLowerCase())
  return categories.find((c) => wanted.includes(c.name.toLowerCase()))?.id ?? ''
}

type PageTab = 'recurring' | 'tax'

export default function RecurringPage() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<PageTab>('recurring')
  const tabs: { id: PageTab; label: string }[] = [
    { id: 'recurring', label: t('recurring.title') },
    { id: 'tax', label: t('tax.taxObligations') },
  ]

  return (
    <div className="space-y-4">
      <PageHeader section={t('recurring.title')} title={t('recurring.title')} />
      <div className="flex gap-1 border-b">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === tb.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {tb.label}
          </button>
        ))}
      </div>
      <RecurringTab key={tab} taxMode={tab === 'tax'} />
    </div>
  )
}

function RecurringTab({ taxMode }: { taxMode: boolean }) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const { mask } = usePrivacyMode()
  const { user } = useAuth()
  const { canWrite } = useWorkspace()
  const userCurrency = user?.preferences?.currency_display ?? 'BRL'
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<RecurringTransaction | null>(null)
  const [deletingRecurring, setDeletingRecurring] = useState<RecurringTransaction | null>(null)

  const { data: recurringList } = useQuery({
    queryKey: ['recurring'],
    queryFn: recurringApi.list,
  })

  const { data: taxSummary } = useQuery({
    queryKey: ['tax-obligations', 'summary'],
    queryFn: taxObligationsApi.summary,
    enabled: taxMode,
  })

  const { data: categoriesList } = useQuery({
    queryKey: ['categories'],
    queryFn: categoriesApi.list,
  })

  const { data: allCategoriesList } = useQuery({
    queryKey: ['categories', 'management'],
    queryFn: categoriesApi.listIncludingHidden,
    enabled: Boolean(editing?.category_id),
  })

  const { data: categoryGroupsList } = useQuery({
    queryKey: ['categoryGroups'],
    queryFn: categoryGroupsApi.list,
  })

  const { data: accountsList } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: costCentersList } = useQuery({
    queryKey: ['cost-centers'],
    queryFn: () => costCentersApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<RecurringTransaction>) => recurringApi.create(data),
    onSuccess: () => {
      invalidateFinancialQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
      setDialogOpen(false)
      toast.success(t('recurring.created'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, ...data }: Partial<RecurringTransaction> & { id: string }) =>
      recurringApi.update(id, data),
    onSuccess: () => {
      invalidateFinancialQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
      setDialogOpen(false)
      setEditing(null)
      toast.success(t('recurring.updated'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => recurringApi.delete(id),
    onSuccess: () => {
      invalidateFinancialQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
      setDeletingRecurring(null)
      toast.success(t('recurring.deleted'))
    },
    onError: (err: unknown) => {
      toast.error(extractApiError(err, t('common.error')))
    },
  })

  const generateMutation = useMutation({
    mutationFn: () => recurringApi.generate(),
    onSuccess: (data) => {
      invalidateFinancialQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['recurring'] })
      toast.success(t('recurring.generated', { count: data.generated }))
    },
    onError: () => toast.error(t('common.error')),
  })

  const visibleList = (recurringList ?? []).filter((rt) =>
    taxMode ? rt.tax_obligation_type != null : rt.tax_obligation_type == null,
  )

  const frequencyLabel = (f: string) => {
    const map: Record<string, string> = {
      monthly: t('recurring.monthly'),
      quarterly: t('recurring.quarterly'),
      semiannual: t('recurring.semiannual'),
      weekly: t('recurring.weekly'),
      biweekly: t('recurring.biweekly'),
      yearly: t('recurring.yearly'),
    }
    return map[f] ?? f
  }

  return (
    <>
      <SectionCard>
        <SectionHeader
          title={taxMode ? t('tax.taxObligations') : t('recurring.title')}
          action={
            canWrite ? (
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 h-8"
                  onClick={() => generateMutation.mutate()}
                  disabled={generateMutation.isPending}
                >
                  <RefreshCw size={12} />
                  <span className="hidden sm:inline">{t('recurring.generatePending')}</span>
                </Button>
                <Button size="sm" className="gap-1.5 h-8" onClick={() => { setEditing(null); setDialogOpen(true) }}>
                  <Plus size={13} /> <span className="hidden sm:inline">{taxMode ? t('tax.newTaxObligation') : t('recurring.add')}</span>
                </Button>
              </div>
            ) : undefined
          }
        />
        {taxMode && taxSummary && (
          <div className="px-4 sm:px-5 py-3 border-b border-border flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-xs font-medium text-muted-foreground">{t('tax.monthlySummary')}</span>
            <span className="text-lg font-bold tabular-nums text-orange-600">
              {mask(formatCurrency(Number(taxSummary.total), userCurrency, locale))}
            </span>
          </div>
        )}
        {visibleList.length > 0 ? (
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                {taxMode && <th className={`${TH} pl-4 sm:pl-5 text-left w-44`}>{t('tax.taxObligationType')}</th>}
                <th className={`${TH} ${taxMode ? '' : 'pl-4 sm:pl-5'} text-left`}>{t('recurring.description')}</th>
                <th className={`${TH} text-left w-36`}>{t('recurring.amount')}</th>
                <th className={`${TH} text-left w-28 hidden md:table-cell`}>{t('recurring.frequency')}</th>
                <th className={`${TH} text-left w-32 hidden md:table-cell`}>{t('recurring.nextOccurrence')}</th>
                <th className={`${TH} text-left w-24 hidden sm:table-cell`}>{t('recurring.status')}</th>
                {canWrite && <th className={`${TH} pr-4 sm:pr-5 text-right w-24`}>{t('recurring.actions')}</th>}
              </tr>
            </thead>
            <tbody>
              {visibleList.map((rt) => (
                <tr key={rt.id} className="border-b border-border last:border-0 hover:bg-muted transition-colors">
                  {taxMode && (
                    <td className="py-3 pl-4 sm:pl-5">
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full border bg-orange-50 text-orange-700 border-orange-100">
                        {rt.tax_obligation_type ? t(`tax.taxObligationTypes.${rt.tax_obligation_type}`) : ''}
                      </span>
                    </td>
                  )}
                  <td className={`py-3 ${taxMode ? '' : 'pl-4 sm:pl-5'} text-sm font-medium text-foreground`}>{rt.description}</td>
                  <td className={`py-3 text-xs sm:text-sm font-bold tabular-nums ${rt.type === 'credit' ? 'text-emerald-600' : 'text-rose-500'}`}>
                    {mask(`${rt.type === 'credit' ? '+' : '−'}${formatCurrency(rt.amount, rt.currency, locale)}`)}
                    {rt.currency !== userCurrency && rt.amount_primary != null && (
                      <div className="flex items-center gap-1 text-[11px] font-normal text-muted-foreground">
                        <span>{mask(formatCurrency(rt.amount_primary, userCurrency, locale))}</span>
                        <span title={t('recurring.fxEstimate', { rate: rt.fx_rate_used?.toFixed(4) ?? '–' })}>
                          <Info size={11} className="inline opacity-60" />
                        </span>
                      </div>
                    )}
                  </td>
                  <td className="py-3 hidden md:table-cell">
                    <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded-full font-medium">
                      {frequencyLabel(rt.frequency)}
                    </span>
                  </td>
                  <td className="py-3 text-xs text-muted-foreground tabular-nums hidden md:table-cell">
                    {new Date(rt.next_occurrence + 'T00:00:00').toLocaleDateString(dateLocale)}
                  </td>
                  <td className="py-3 hidden sm:table-cell">
                    <span className={cn(
                      'text-[11px] font-semibold px-2 py-0.5 rounded-full border',
                      rt.is_active
                        ? 'bg-emerald-50 text-emerald-600 border-emerald-100'
                        : 'bg-muted text-muted-foreground border-border'
                    )}>
                      {rt.is_active ? t('recurring.active') : t('recurring.inactive')}
                    </span>
                  </td>
                  {canWrite && (
                    <td className="py-3 pr-4 sm:pr-5">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          className="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/5 transition-colors"
                          onClick={() => { setEditing(rt); setDialogOpen(true) }}
                          aria-label={t('common.edit')}
                          title={t('common.edit')}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          className="p-1.5 rounded-md text-muted-foreground hover:text-rose-500 hover:bg-rose-50 transition-colors"
                          onClick={() => setDeletingRecurring(rt)}
                          disabled={deleteMutation.isPending}
                          aria-label={t('common.delete')}
                          title={t('common.delete')}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-10">
            {taxMode ? t('tax.noTaxObligations') : t('recurring.empty')}
          </p>
        )}
      </SectionCard>

      <Dialog open={dialogOpen} onOpenChange={() => { setDialogOpen(false); setEditing(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {taxMode
                ? (editing ? t('tax.editTaxObligation') : t('tax.newTaxObligation'))
                : (editing ? t('recurring.edit') : t('recurring.add'))}
            </DialogTitle>
          </DialogHeader>
          <RecurringForm
            key={editing?.id ?? 'new'}
            recurring={editing}
            taxMode={taxMode}
            categories={categoriesList ?? []}
            categoryGroups={categoryGroupsList ?? []}
            currentCategory={allCategoriesList?.find(
              (category) => category.id === editing?.category_id
            )}
            accounts={accountsList ?? []}
            costCenters={costCentersList ?? []}
            onSave={(data) => {
              if (editing) {
                updateMutation.mutate({ id: editing.id, ...data })
              } else {
                createMutation.mutate(data)
              }
            }}
            onCancel={() => { setDialogOpen(false); setEditing(null) }}
            loading={createMutation.isPending || updateMutation.isPending}
          />
        </DialogContent>
      </Dialog>

      <DeleteConfirmationDialog
        open={!!deletingRecurring}
        title={t('recurring.confirmDeleteTitle')}
        description={t('recurring.confirmDeleteDescription', { description: deletingRecurring?.description })}
        isPending={deleteMutation.isPending}
        onClose={() => setDeletingRecurring(null)}
        onConfirm={() => deletingRecurring && deleteMutation.mutate(deletingRecurring.id)}
      />
    </>
  )
}

function RecurringForm({
  recurring,
  taxMode,
  categories,
  categoryGroups,
  currentCategory,
  accounts,
  costCenters,
  onSave,
  onCancel,
  loading,
}: {
  recurring: RecurringTransaction | null
  taxMode: boolean
  categories: Category[]
  categoryGroups: CategoryGroup[]
  currentCategory?: Category
  accounts: { id: string; name: string; display_name?: string | null }[]
  costCenters: CostCenter[]
  onSave: (data: Partial<RecurringTransaction>) => void
  onCancel: () => void
  loading: boolean
}) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const userCurrency = user?.preferences?.currency_display ?? 'BRL'
  const sortedAccounts = useMemo(() => sortAccountsByDisplayName(accounts), [accounts])
  const { data: supportedCurrencies } = useQuery({
    queryKey: ['currencies'],
    queryFn: currenciesApi.list,
    staleTime: Infinity,
  })
  const [description, setDescription] = useState(recurring?.description ?? '')
  const [amount, setAmount] = useState(recurring?.amount?.toString() ?? '')
  const [currency, setCurrency] = useState(recurring?.currency ?? userCurrency)
  const [type, setType] = useState<'debit' | 'credit'>(recurring?.type ?? 'debit')
  const [frequency, setFrequency] = useState(recurring?.frequency ?? 'monthly')
  const [weekendAdjustment, setWeekendAdjustment] = useState<RecurringTransaction['weekend_adjustment']>(
    recurring?.weekend_adjustment ?? 'none'
  )
  const [dayOfMonth, setDayOfMonth] = useState(recurring?.day_of_month?.toString() ?? '')
  const [startDate, setStartDate] = useState(recurring?.start_date ?? localDateString())
  const [endDate, setEndDate] = useState(recurring?.end_date ?? '')
  const [categoryId, setCategoryId] = useState(recurring?.category_id ?? '')
  const [costCenterId, setCostCenterId] = useState(recurring?.cost_center_id ?? '')
  const [accountId, setAccountId] = useState(recurring?.account_id ?? sortedAccounts[0]?.id ?? '')
  const [isActive, setIsActive] = useState(recurring?.is_active ?? true)
  const [autoGenerate, setAutoGenerate] = useState(recurring?.auto_generate ?? true)
  const [taxType, setTaxType] = useState<TaxObligationType>(recurring?.tax_obligation_type ?? 'das')
  const [taxRefCode, setTaxRefCode] = useState(recurring?.tax_reference_code ?? '')
  const [competenceOffset, setCompetenceOffset] = useState(
    (recurring?.competence_offset_months ?? 1).toString(),
  )

  const changeTaxType = (next: TaxObligationType) => {
    setTaxType(next)
    // Pré-preenche a categoria só quando o usuário ainda não escolheu uma.
    if (!recurring && !categoryId) setCategoryId(taxCategoryFor(next, categories))
    if (!recurring && !description) setDescription(t(`tax.taxObligationTypes.${next}`))
  }

  const selectClass = 'w-full border border-border rounded-lg px-3 py-2 text-sm bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary'

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSave({
          description,
          amount: parseFloat(amount),
          currency,
          type,
          frequency,
          weekend_adjustment: weekendAdjustment,
          day_of_month: dayOfMonth ? parseInt(dayOfMonth) : null,
          start_date: startDate,
          end_date: endDate || null,
          category_id: categoryId || null,
          cost_center_id: costCenterId || null,
          account_id: accountId || null,
          is_active: isActive,
          auto_generate: autoGenerate,
          ...(taxMode
            ? {
                type: 'debit',
                tax_obligation_type: taxType,
                tax_reference_code: taxType.startsWith('darf') ? taxRefCode || null : null,
                competence_offset_months: parseInt(competenceOffset) || 0,
              }
            : {}),
        } as Partial<RecurringTransaction>)
      }}
      className="space-y-4"
    >
      {taxMode && (
        <div className="space-y-2">
          <Label>{t('tax.taxObligationType')}</Label>
          <select
            className={selectClass}
            value={taxType}
            onChange={(e) => changeTaxType(e.target.value as TaxObligationType)}
          >
            {TAX_TYPES.map((k) => (
              <option key={k} value={k}>{t(`tax.taxObligationTypes.${k}`)}</option>
            ))}
          </select>
        </div>
      )}
      <div className="space-y-2">
        <Label>{t('recurring.description')}</Label>
        <Input value={description} onChange={(e) => setDescription(e.target.value)} required />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-2">
          <Label>{t('recurring.amount')}</Label>
          <Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </div>
        <div className="space-y-2">
          <Label>{t('recurring.currency')}</Label>
          <select className={selectClass} value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {(supportedCurrencies ?? [{ code: userCurrency, symbol: userCurrency, name: userCurrency, flag: '' }]).map((c) => (
              <option key={c.code} value={c.code}>{c.flag} {c.name}</option>
            ))}
          </select>
        </div>
        {!taxMode && <div className="space-y-2">
          <Label>{t('recurring.type')}</Label>
          <select className={selectClass} value={type} onChange={(e) => setType(e.target.value as 'debit' | 'credit')}>
            <option value="debit">{t('recurring.expense')}</option>
            <option value="credit">{t('recurring.income')}</option>
          </select>
        </div>}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>{t('recurring.frequency')}</Label>
          <select className={selectClass} value={frequency} onChange={(e) => setFrequency(e.target.value as RecurringTransaction['frequency'])}>
            <option value="monthly">{t('recurring.monthly')}</option>
            <option value="quarterly">{t('recurring.quarterly')}</option>
            <option value="semiannual">{t('recurring.semiannual')}</option>
            <option value="weekly">{t('recurring.weekly')}</option>
            <option value="biweekly">{t('recurring.biweekly')}</option>
            <option value="yearly">{t('recurring.yearly')}</option>
          </select>
        </div>
        {(frequency === 'monthly' || frequency === 'quarterly' || frequency === 'semiannual') && (
          <div className="space-y-2">
            <Label>{t('recurring.dayOfMonth')}</Label>
            <Input type="number" min="1" max="31" value={dayOfMonth} onChange={(e) => setDayOfMonth(e.target.value)} />
          </div>
        )}
      </div>
      {taxMode && (
        <div className="grid grid-cols-2 gap-4">
          {taxType.startsWith('darf') && (
            <div className="space-y-2">
              <Label>{t('tax.taxReferenceCode')}</Label>
              <Input value={taxRefCode} onChange={(e) => setTaxRefCode(e.target.value)} />
            </div>
          )}
          <div className="space-y-2">
            <Label>{t('tax.competenceOffset')}</Label>
            <Input type="number" min="0" max="12" value={competenceOffset} onChange={(e) => setCompetenceOffset(e.target.value)} />
          </div>
        </div>
      )}
      <div className="space-y-2">
        <Label>{t('recurring.weekendAdjustment')}</Label>
        <select
          className={selectClass}
          value={weekendAdjustment}
          onChange={(e) => setWeekendAdjustment(e.target.value as RecurringTransaction['weekend_adjustment'])}
        >
          <option value="none">{t('recurring.weekendAdjustmentNone')}</option>
          <option value="previous_friday">{t('recurring.weekendAdjustmentPreviousFriday')}</option>
          <option value="next_monday">{t('recurring.weekendAdjustmentNextMonday')}</option>
        </select>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>{t('recurring.startDate')}</Label>
          <DatePickerInput value={startDate} onChange={setStartDate} className="w-full justify-start" />
        </div>
        <div className="space-y-2">
          <Label>{t('recurring.endDate')}</Label>
          <DatePickerInput value={endDate} onChange={setEndDate} placeholder={t('recurring.endDate')} className="w-full justify-start" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>{t('recurring.category')}</Label>
          <CategorySelect
            value={categoryId}
            onChange={setCategoryId}
            categories={categories}
            groups={categoryGroups}
            currentCategory={currentCategory}
            allowNone={true}
            className={selectClass}
          />
        </div>
        <div className="space-y-2">
          <Label>{t('recurring.account')}</Label>
          <select
            className={selectClass}
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            required
          >
            {!accountId && <option value="" disabled>{t('recurring.noAccount')}</option>}
            {sortedAccounts.map((acc) => (
              <option key={acc.id} value={acc.id}>{getAccountName(acc)}</option>
            ))}
          </select>
        </div>
      </div>
      {costCenters.length > 0 && (
        <div className="space-y-2">
          <Label>{t('recurring.costCenter')}</Label>
          <select
            className={selectClass}
            value={costCenterId}
            onChange={(e) => setCostCenterId(e.target.value)}
          >
            <option value="">{t('recurring.noCostCenter')}</option>
            {costCenters.map((cc) => (
              <option key={cc.id} value={cc.id}>{cc.code ? `${cc.code} — ${cc.name}` : cc.name}</option>
            ))}
          </select>
        </div>
      )}
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={autoGenerate}
          onChange={(e) => setAutoGenerate(e.target.checked)}
          className="h-4 w-4 mt-0.5 rounded border-border"
        />
        <span className="text-sm text-foreground">
          {t('recurring.autoGenerate')}
          <span className="block text-xs text-muted-foreground">{t('recurring.autoGenerateHelp')}</span>
        </span>
      </label>
      {recurring && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          <span className="text-sm text-foreground">{t('recurring.active')}</span>
        </label>
      )}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>{t('common.cancel')}</Button>
        <Button type="submit" disabled={loading}>
          {loading ? t('common.loading') : t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  )
}
