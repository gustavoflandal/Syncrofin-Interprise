import { useState, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getAccountName, sortAccountsByDisplayName } from '@/lib/account-utils'
import { useTranslation } from 'react-i18next'
import { useDisplayLocale, useDateLocale } from '@/hooks/use-display-locale'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { transactions as transactionsApi, accounts as accountsApi, categories as categoriesApi, categoryGroups as categoryGroupsApi, nfeApi, payees as payeesApi, type NfePreview } from '@/lib/api'
import { invalidateFinancialQueries } from '@/lib/invalidate-queries'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import type { ImportPreviewTransaction, ImportReviewTransaction, FailedRow } from '@/types'
import { Upload, FileText, X, CheckCircle2, AlertCircle, Settings2, Download, Receipt, ArrowRightLeft, Users, Tag } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/page-header'
import { AssetImportPanel } from '@/components/asset-import-panel'
import { ImportSummaryBar } from '@/components/import-summary-bar'
import { ImportReviewTable } from '@/components/import-review-table'
import { ImportHistory } from '@/components/import-history'
import { useAuth } from '@/contexts/auth-context'
import { useWorkspace } from '@/contexts/workspace-context'

const TYPE_LABELS: Record<string, string> = {
  checking: 'accounts.typeChecking',
  savings: 'accounts.typeSavings',
  credit_card: 'accounts.typeCreditCard',
  investment: 'accounts.typeInvestment',
}

// SyncroFin fields a CSV column can be mapped to, in display order.
const CSV_MAPPING_FIELDS = [
  { key: 'date', label: 'import.mapDate' },
  { key: 'description', label: 'import.mapDescription' },
  { key: 'amount', label: 'import.mapAmount' },
  { key: 'type', label: 'import.mapType' },
  { key: 'category', label: 'import.mapCategory' },
  { key: 'currency', label: 'import.mapCurrency' },
  { key: 'fx_rate', label: 'import.mapFxRate' },
  { key: 'payee', label: 'import.mapPayee' },
  { key: 'external_id', label: 'import.mapExternalId' },
  { key: 'notes', label: 'import.mapNotes' },
] as const

function toReviewTransactions(txns: ImportPreviewTransaction[]): ImportReviewTransaction[] {
  return txns.map((tx, i) => ({
    ...tx,
    _id: tx.external_id ? `${tx.external_id}-${i}` : `idx-${i}`,
    excluded: false,
    selected_category_id: undefined,
  }))
}

function TransactionImportPanel() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { canWrite } = useWorkspace()
  const userCurrency = user?.preferences?.currency_display ?? 'BRL'
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previewData, setPreviewData] = useState<{ transactions: ImportPreviewTransaction[]; detected_format: string; csv_columns?: string[]; parse_error?: string | null; failed_rows?: FailedRow[] } | null>(null)
  const [reviewTransactions, setReviewTransactions] = useState<ImportReviewTransaction[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [fileName, setFileName] = useState<string | null>(null)
  const [currentFile, setCurrentFile] = useState<File | null>(null)
  const [csvHeaders, setCsvHeaders] = useState<string[]>([])
  const [isFailedRowsOpen, setIsFailedRowsOpen] = useState(false)

  const [searchQuery, setSearchQuery] = useState('')
  const [filterCategoryIds, setFilterCategoryIds] = useState<string[]>([])
  const [filterUncategorized, setFilterUncategorized] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'all' | 'included' | 'excluded'>('all')
  const [currentPage, setCurrentPage] = useState(1)

  const [csvDateFormat, setCsvDateFormat] = useState('')
  const [csvFlipAmount, setCsvFlipAmount] = useState(false)
  const [csvDetectDuplicates, setCsvDetectDuplicates] = useState(true)
  const [csvSplitColumns, setCsvSplitColumns] = useState(false)
  const [csvInflowColumn, setCsvInflowColumn] = useState('')
  const [csvOutflowColumn, setCsvOutflowColumn] = useState('')
  const [csvColumnMapping, setCsvColumnMapping] = useState<Record<string, string>>({})

  const { data: accountsList } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: categoriesList = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: categoriesApi.list,
  })

  const { data: categoryGroupsList = [] } = useQuery({
    queryKey: ['category-groups'],
    queryFn: categoryGroupsApi.list,
  })

  const previewMutation = useMutation({
    mutationFn: ({ file, options }: { file: File; options?: { date_format?: string; flip_amount?: boolean; inflow_column?: string; outflow_column?: string; column_mapping?: Record<string, string> } }) =>
      transactionsApi.previewImport(file, options),
    onSuccess: (data) => {
      setPreviewData(data)
      setCsvHeaders(data.csv_columns ?? [])
      setReviewTransactions(toReviewTransactions(data.transactions))
      setSearchQuery('')
      setFilterCategoryIds([])
      setFilterUncategorized(false)
      setStatusFilter('all')
      setCurrentPage(1)
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || t('import.processError'))
    },
  })

  const importMutation = useMutation({
    mutationFn: () => {
      const txns = reviewTransactions.map(rt => ({
        description: rt.description,
        amount: rt.amount,
        date: rt.date,
        type: rt.type,
        external_id: rt.external_id ?? undefined,
        currency: rt.currency ?? undefined,
        fx_rate: rt.fx_rate ?? undefined,
        payee_raw: rt.payee_raw ?? undefined,
        notes: rt.notes ?? undefined,
        category_name: rt.category_name ?? undefined,
        excluded: rt.excluded,
        category_id: rt.selected_category_id !== undefined
          ? (rt.selected_category_id ?? undefined)
          : undefined,
        force_uncategorized: rt.selected_category_id === null,
      }))
      return transactionsApi.import(
        selectedAccount,
        txns,
        fileName ?? '',
        previewData!.detected_format,
        isCsvFile ? { detect_duplicates: csvDetectDuplicates } : undefined,
      )
    },
    onSuccess: (data) => {
      invalidateFinancialQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['import-logs'] })
      queryClient.invalidateQueries({ queryKey: ['payees'] })
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      const hasSkippedOrExcluded = (data.skipped ?? 0) > 0 || (data.excluded ?? 0) > 0
      const msg = hasSkippedOrExcluded
        ? t('import.importedWithExcluded', { imported: data.imported, skipped: data.skipped ?? 0, excluded: data.excluded ?? 0 })
        : `${data.imported} ${t('import.transactionsImported')}`
      toast.success(msg)
      setPreviewData(null)
      setReviewTransactions([])
      setSelectedAccount('')
      setFileName(null)
      setCurrentFile(null)
      resetCsvOptions()
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || t('import.importError'))
    },
  })

  function resetCsvOptions() {
    setCsvDateFormat('')
    setCsvFlipAmount(false)
    setCsvDetectDuplicates(true)
    setCsvSplitColumns(false)
    setCsvInflowColumn('')
    setCsvOutflowColumn('')
    setCsvColumnMapping({})
    setCsvHeaders([])
  }

  function processFile(file: File) {
    setFileName(file.name)
    setCurrentFile(file)
    resetCsvOptions()
    // CSV headers come back from the preview response (csv_columns), which
    // parses the file server-side and handles any delimiter/quoting.
    previewMutation.mutate({ file })
  }

  // Re-run the preview with the current CSV options. Accepts overrides so a
  // change handler can pass its new value synchronously instead of waiting
  // for the corresponding state update to flush.
  const rePreview = useCallback((overrides?: {
    date_format?: string
    flip_amount?: boolean
    split?: boolean
    inflow?: string
    outflow?: string
    mapping?: Record<string, string>
  }) => {
    if (!currentFile) return
    const dateFormat = overrides?.date_format ?? csvDateFormat
    const flip = overrides?.flip_amount ?? csvFlipAmount
    const split = overrides?.split ?? csvSplitColumns
    const inflow = overrides?.inflow ?? csvInflowColumn
    const outflow = overrides?.outflow ?? csvOutflowColumn
    const mapping = overrides?.mapping ?? csvColumnMapping

    const options: { date_format?: string; flip_amount?: boolean; inflow_column?: string; outflow_column?: string; column_mapping?: Record<string, string> } = {}
    if (dateFormat) options.date_format = dateFormat
    if (flip) options.flip_amount = true
    if (split && inflow && outflow) {
      options.inflow_column = inflow
      options.outflow_column = outflow
    }
    const cleanMapping = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v))
    if (Object.keys(cleanMapping).length > 0) options.column_mapping = cleanMapping
    previewMutation.mutate({ file: currentFile, options })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentFile, csvDateFormat, csvFlipAmount, csvSplitColumns, csvInflowColumn, csvOutflowColumn, csvColumnMapping])

  const handleMappingChange = useCallback((field: string, column: string) => {
    setCsvColumnMapping(prev => {
      const next = { ...prev, [field]: column }
      rePreview({ mapping: next })
      return next
    })
  }, [rePreview])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) processFile(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) processFile(file)
  }

  const handleReset = () => {
    setPreviewData(null)
    setReviewTransactions([])
    setFileName(null)
    setCurrentFile(null)
    setSelectedAccount('')
    resetCsvOptions()
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleToggleExcluded = useCallback((id: string) => {
    setReviewTransactions(prev => prev.map(t =>
      t._id === id ? { ...t, excluded: !t.excluded } : t
    ))
  }, [])

  const handleChangeCategory = useCallback((id: string, categoryId: string | null) => {
    setReviewTransactions(prev => prev.map(t =>
      t._id === id ? { ...t, selected_category_id: categoryId } : t
    ))
  }, [])

  const isCsvFile = fileName?.toLowerCase().endsWith('.csv') ?? false
  // QIF dates are ambiguous for days 1-12 (DD/MM vs MM/DD), so the file
  // options panel is shown for QIF too, limited to the date-format selector.
  const isQifFile = fileName?.toLowerCase().endsWith('.qif') ?? false

  const incomeCount = previewData?.transactions.filter(t => t.type === 'credit').length ?? 0
  const expenseCount = previewData?.transactions.filter(t => t.type === 'debit').length ?? 0

  const includedCount = reviewTransactions.filter(t => !t.excluded).length

  return (
    <div className="space-y-6">
      {/* Upload zone */}
      {canWrite && <div
        className={`bg-card rounded-xl border-2 border-dashed transition-all cursor-pointer ${
          dragOver ? 'border-primary bg-primary/5' : 'border-border hover:border-border'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !previewMutation.isPending && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".ofx,.qfx,.csv,.qif,.xml,.camt"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
          {previewMutation.isPending ? (
            <>
              <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-4 animate-pulse">
                <FileText size={22} className="text-primary" />
              </div>
              <p className="text-sm font-semibold text-foreground">{t('import.processing')}</p>
              <p className="text-xs text-muted-foreground mt-1">{fileName}</p>
            </>
          ) : fileName && previewData ? (
            <>
              <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center mb-4">
                <CheckCircle2 size={22} className="text-emerald-500" />
              </div>
              <p className="text-sm font-semibold text-foreground">{fileName}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {t('import.previewInfo', { count: previewData.transactions.length, format: previewData.detected_format.toUpperCase() })}
              </p>
              <button
                className="mt-3 text-xs text-muted-foreground hover:text-rose-500 transition-colors flex items-center gap-1"
                onClick={(e) => { e.stopPropagation(); handleReset() }}
              >
                <X size={12} /> {t('import.removeFile')}
              </button>
            </>
          ) : (
            <>
              <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
                <Upload size={22} className="text-muted-foreground" />
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">
                {t('import.dragOrClick')}
              </p>
              <p className="text-xs text-muted-foreground">{t('import.acceptedFormats')}</p>
              <button
                className="mt-2 text-xs text-primary hover:text-primary/80 transition-colors flex items-center gap-1"
                onClick={(e) => {
                  e.stopPropagation()
                  const csv = 'date,description,amount,currency,fx_rate\n2026-01-15,Grocery Store,-120.50,USD,\n2026-01-20,Salary Payment,5000.00,EUR,1.08\n'
                  const blob = new Blob([csv], { type: 'text/csv' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = 'template.csv'
                  a.click()
                  URL.revokeObjectURL(url)
                }}
              >
                <Download size={12} />
                {t('import.downloadTemplate')}
              </button>
            </>
          )}
        </div>
      </div>}

      {/* Review section */}
      {previewData && (
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b border-border">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-foreground">{t('import.preview')}</p>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1 text-emerald-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                  {t('import.incomeCount', { count: incomeCount })}
                </span>
                <span className="flex items-center gap-1 text-rose-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 inline-block" />
                  {t('import.expenseCount', { count: expenseCount })}
                </span>
              </div>
            </div>
          </div>

          {/* Account picker */}
          <div className="px-4 sm:px-5 py-4 border-b border-border bg-muted/50">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
              <Label className="text-sm text-muted-foreground whitespace-nowrap shrink-0">
                {t('import.importTo')}
              </Label>
              <select
                className="flex-1 border border-border rounded-md px-3 py-2 text-sm bg-card focus:outline-none focus-visible:ring-ring/30 focus-visible:ring-[2px]"
                value={selectedAccount}
                onChange={(e) => setSelectedAccount(e.target.value)}
              >
                <option value="">{t('import.selectAccount')}</option>
                {sortAccountsByDisplayName(accountsList ?? []).map((acc) => (
                  <option key={acc.id} value={acc.id}>{getAccountName(acc)} ({t(TYPE_LABELS[acc.type] || acc.type)})</option>
                ))}
              </select>
              {!selectedAccount && (
                <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 border border-amber-100 px-2.5 py-1.5 rounded-lg shrink-0">
                  <AlertCircle size={12} />
                  {t('import.selectAccountWarning')}
                </div>
              )}
            </div>
          </div>

          {/* CSV/QIF Options */}
          {(isCsvFile || isQifFile) && previewData && (
            <div className="px-5 py-4 border-b border-border bg-muted/30">
              <div className="flex items-center gap-2 mb-3">
                <Settings2 size={14} className="text-muted-foreground" />
                <p className="text-xs font-medium text-muted-foreground">
                  {isCsvFile ? t('import.csvOptions') : t('import.importOptions')}
                </p>
              </div>

              {previewData.parse_error && (
                <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg mb-3">
                  <AlertCircle size={14} className="shrink-0 mt-0.5" />
                  <span>{t('import.mappingNeeded')}</span>
                </div>
              )}

              {previewData.failed_rows && previewData.failed_rows.length > 0 && (
                <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg mb-3">
                  <AlertCircle size={14} className="shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <span>
                      {t('import.failedRowsWarning', { count: previewData.failed_rows.length })}
                    </span>
                    <button
                      type="button"
                      className="ml-2 font-semibold underline hover:text-amber-800 focus:outline-none"
                      onClick={() => setIsFailedRowsOpen(true)}
                    >
                      {t('import.viewDetails')}
                    </button>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <Label className="text-xs text-muted-foreground mb-1 block">{t('import.dateFormat')}</Label>
                  <select
                    className="w-full border border-border rounded-lg px-3 py-1.5 text-sm bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                    value={csvDateFormat}
                    onChange={(e) => { setCsvDateFormat(e.target.value); rePreview({ date_format: e.target.value }) }}
                  >
                    <option value="">{t('import.dateFormatAuto')}</option>
                    <option value="DD/MM/YYYY">DD/MM/YYYY</option>
                    <option value="MM/DD/YYYY">MM/DD/YYYY</option>
                    <option value="YYYY-MM-DD">YYYY-MM-DD</option>
                  </select>
                </div>
                {isCsvFile && <div className="flex items-center gap-2 pt-4">
                  <input
                    type="checkbox"
                    id="flip-amount"
                    checked={csvFlipAmount}
                    onChange={(e) => { setCsvFlipAmount(e.target.checked); rePreview({ flip_amount: e.target.checked }) }}
                    className="rounded border-border text-primary focus:ring-primary"
                  />
                  <Label htmlFor="flip-amount" className="text-sm text-muted-foreground cursor-pointer">
                    {t('import.flipAmounts')}
                  </Label>
                </div>}
                {isCsvFile && <div className="flex items-center gap-2 pt-4">
                  <input
                    type="checkbox"
                    id="split-columns"
                    checked={csvSplitColumns}
                    onChange={(e) => { setCsvSplitColumns(e.target.checked); rePreview({ split: e.target.checked }) }}
                    className="rounded border-border text-primary focus:ring-primary"
                  />
                  <Label htmlFor="split-columns" className="text-sm text-muted-foreground cursor-pointer">
                    {t('import.splitColumns')}
                  </Label>
                </div>}
                {isCsvFile && <div className="flex items-center gap-2 pt-4">
                  <input
                    type="checkbox"
                    id="detect-duplicates"
                    checked={csvDetectDuplicates}
                    onChange={(e) => setCsvDetectDuplicates(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary"
                  />
                  <Label htmlFor="detect-duplicates" className="text-sm text-muted-foreground cursor-pointer">
                    {t('import.detectDuplicates')}
                  </Label>
                </div>}
              </div>

              {csvSplitColumns && csvHeaders.length > 0 && (
                <div className="grid grid-cols-2 gap-4 my-3">
                  <div>
                    <Label className="text-xs text-muted-foreground mb-1 block">{t('import.inflowColumn')}</Label>
                    <select
                      className="w-full border border-border rounded-md px-3 py-1.5 text-sm bg-card focus:outline-none focus-visible:ring-ring/30 focus-visible:ring-[2px]"
                      value={csvInflowColumn}
                      onChange={(e) => { setCsvInflowColumn(e.target.value); rePreview({ inflow: e.target.value }) }}
                    >
                      <option value="">{t('import.selectColumn')}</option>
                      {csvHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground mb-1 block">{t('import.outflowColumn')}</Label>
                    <select
                      className="w-full border border-border rounded-md px-3 py-1.5 text-sm bg-card focus:outline-none focus-visible:ring-ring/30 focus-visible:ring-[2px]"
                      value={csvOutflowColumn}
                      onChange={(e) => { setCsvOutflowColumn(e.target.value); rePreview({ outflow: e.target.value }) }}
                    >
                      <option value="">{t('import.selectColumn')}</option>
                      {csvHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </div>
                </div>
              )}

              {/* Column mapping — map CSV headers to SyncroFin fields */}
              {csvHeaders.length > 0 && (
                <div className="mt-4 pt-4 border-t border-border">
                  <p className="text-xs font-medium text-muted-foreground">{t('import.columnMapping')}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 mb-3">{t('import.columnMappingHint')}</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {CSV_MAPPING_FIELDS
                      .filter((f) => !(csvSplitColumns && f.key === 'amount'))
                      .map((f) => (
                        <div key={f.key}>
                          <Label className="text-xs text-muted-foreground mb-1 block">{t(f.label)}</Label>
                          <select
                            className="w-full border border-border rounded-md px-3 py-1.5 text-sm bg-card focus:outline-none focus-visible:ring-ring/30 focus-visible:ring-[2px]"
                            value={csvColumnMapping[f.key] ?? ''}
                            onChange={(e) => handleMappingChange(f.key, e.target.value)}
                          >
                            <option value="">{t('import.columnAutoDetect')}</option>
                            {csvHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                          </select>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Summary bar */}
          <ImportSummaryBar
            transactions={reviewTransactions}
            userCurrency={userCurrency}
            locale={locale}
          />

          {/* Review table */}
          <ImportReviewTable
            transactions={reviewTransactions}
            categories={categoriesList}
            groups={categoryGroupsList}
            userCurrency={userCurrency}
            locale={locale}
            dateLocale={dateLocale}
            searchQuery={searchQuery}
            filterCategoryIds={filterCategoryIds}
            filterUncategorized={filterUncategorized}
            statusFilter={statusFilter}
            currentPage={currentPage}
            onToggleExcluded={handleToggleExcluded}
            onChangeCategory={handleChangeCategory}
            onSearchChange={setSearchQuery}
            onCategoryIdsChange={setFilterCategoryIds}
            onUncategorizedChange={setFilterUncategorized}
            onStatusFilterChange={setStatusFilter}
            onPageChange={setCurrentPage}
          />

          {/* Footer actions */}
          <div className="px-4 sm:px-5 py-4 border-t border-border flex items-center justify-between">
            <button
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={handleReset}
            >
              {t('common.cancel')}
            </button>
            <Button
              onClick={() => importMutation.mutate()}
              disabled={!selectedAccount || importMutation.isPending || includedCount === 0}
              className="gap-2"
            >
              <Upload size={14} />
              {importMutation.isPending
                ? t('common.loading')
                : t('import.importButton', { count: includedCount })}
            </Button>
          </div>
        </div>
      )}

      <ImportHistory entity="transactions" />

      {/* Unparsed CSV rows dialog */}
      <Dialog open={isFailedRowsOpen} onOpenChange={setIsFailedRowsOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">{t('import.failedRowsTitle')}</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground mt-1">
              {t('import.failedRowsDesc')}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 border border-border rounded-lg overflow-hidden bg-card text-foreground mt-4 max-h-[50vh] overflow-y-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-muted text-muted-foreground border-b border-border sticky top-0">
                  <th className="px-3 py-2 font-semibold w-16">{t('import.lineNumber')}</th>
                  <th className="px-3 py-2 font-semibold">{t('import.description')}</th>
                  <th className="px-3 py-2 font-semibold">{t('import.rawValue')}</th>
                  <th className="px-3 py-2 font-semibold">{t('import.errorReason')}</th>
                </tr>
              </thead>
              <tbody>
                {previewData?.failed_rows?.map((row, idx) => (
                  <tr key={idx} className="border-b border-border last:border-0 hover:bg-muted/50">
                    <td className="px-3 py-2 text-muted-foreground">{row.line_number}</td>
                    <td className="px-3 py-2 truncate max-w-[200px]" title={row.description}>{row.description || '-'}</td>
                    <td className="px-3 py-2 font-mono break-all max-w-[150px]">{row.raw_value}</td>
                    <td className="px-3 py-2 text-amber-600 font-medium">{t(`import.errors.${row.error_reason}`)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <DialogFooter className="mt-4 pt-4 border-t border-border flex justify-end">
            <Button onClick={() => setIsFailedRowsOpen(false)} size="sm">
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** Both importers live behind one menu entry: someone with a file to upload
    should not have to know first whether it holds transactions or orders. */
// ─── NF-e import panel ───────────────────────────────────────────────────────

function NfeImportPanel() {
  const { t } = useTranslation()
  const { current: workspace } = useWorkspace()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<NfePreview | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [dueDate, setDueDate] = useState('')
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  async function handleFile(f: File) {
    if (!workspace) return
    setFile(f)
    setPreview(null)
    setLoading(true)
    try {
      const data = await nfeApi.preview(workspace.id, f)
      setPreview(data)
      if (!dueDate) setDueDate(data.issue_date)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t('import.nfe.parseError', 'Erro ao ler XML'))
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm() {
    if (!file || !preview || !workspace || !dueDate) return
    setLoading(true)
    try {
      const result = await nfeApi.import(workspace.id, file, dueDate)
      if (result.already_existed) {
        toast.info(t('import.nfe.alreadyImported', 'NF-e já importada anteriormente'))
      } else {
        toast.success(t('import.nfe.success', 'Título a pagar criado'))
        queryClient.invalidateQueries({ queryKey: ['invoices'] })
      }
      setPreview(null)
      setFile(null)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? t('common.error', 'Erro'))
    } finally {
      setLoading(false)
    }
  }

  function formatBRL(v: string) {
    try {
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(parseFloat(v))
    } catch {
      return `R$ ${v}`
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <p className="text-sm text-muted-foreground">
        {t('import.nfe.description', 'Importe o XML de NF-e de fornecedores para criar automaticamente um título a pagar.')}
      </p>

      {/* Drop zone */}
      <div
        className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary/60 transition-colors"
        onClick={() => fileInputRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => {
          e.preventDefault()
          const f = e.dataTransfer.files[0]
          if (f) handleFile(f)
        }}
      >
        <Receipt className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
        <p className="text-sm font-medium">{t('import.nfe.dropZone', 'Arraste o XML da NF-e ou clique para selecionar')}</p>
        <p className="text-xs text-muted-foreground mt-1">.xml (nfeProc ou NFe)</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xml"
          className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
        />
      </div>

      {loading && (
        <p className="text-sm text-muted-foreground animate-pulse">{t('common.loading', 'Carregando...')}</p>
      )}

      {preview && (
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">{t('import.nfe.preview', 'Prévia')}</h3>
            {preview.already_imported && (
              <Badge variant="outline" className="text-amber-600 border-amber-400">
                {t('import.nfe.alreadyImported', 'Já importada')}
              </Badge>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">{t('import.nfe.emitente', 'Emitente')}</dt>
            <dd className="font-medium">{preview.emitente_nome}</dd>
            <dt className="text-muted-foreground">CNPJ</dt>
            <dd>{preview.emitente_cnpj}</dd>
            <dt className="text-muted-foreground">{t('import.nfe.numero', 'Número')}</dt>
            <dd>{preview.numero} / {preview.serie}</dd>
            <dt className="text-muted-foreground">{t('common.date', 'Data')}</dt>
            <dd>{preview.issue_date}</dd>
            <dt className="text-muted-foreground">{t('import.nfe.valorTotal', 'Total')}</dt>
            <dd className="font-semibold">{formatBRL(preview.valor_total)}</dd>
            <dt className="text-muted-foreground">{t('import.nfe.impostos', 'Impostos')}</dt>
            <dd>{formatBRL(preview.valor_impostos)}</dd>
          </dl>

          {preview.items.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground">
                {t('import.nfe.items', 'Itens')} ({preview.items.length})
              </summary>
              <ul className="mt-2 space-y-0.5 pl-2">
                {preview.items.map((it, i) => (
                  <li key={i} className="flex justify-between">
                    <span className="truncate max-w-[60%]">{it.description}</span>
                    <span>{formatBRL(it.total)}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className="space-y-1">
            <Label className="text-xs">{t('import.nfe.dueDate', 'Vencimento')}</Label>
            <input
              type="date"
              value={dueDate}
              onChange={e => setDueDate(e.target.value)}
              className="rounded border px-2 py-1.5 text-sm bg-background w-40"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <Button
              onClick={handleConfirm}
              disabled={loading || !dueDate}
              size="sm"
            >
              {t('import.nfe.confirm', 'Criar título a pagar')}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setPreview(null); setFile(null) }}
            >
              {t('common.cancel', 'Cancelar')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Migration wizard panel (F5) ─────────────────────────────────────────────

interface ImportResult {
  created: number
  skipped: number
  failed: number
  errors: string[]
}

function CsvUploadStep({
  title,
  description,
  templateCols,
  onUpload,
}: {
  title: string
  description: string
  templateCols: string
  onUpload: (file: File) => Promise<ImportResult>
}) {
  const { t } = useTranslation()
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await onUpload(file)
      setResult(res)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function downloadTemplate() {
    const blob = new Blob([templateCols + '\n'], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="rounded-xl border bg-card p-5 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[13px] font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
        </div>
        <Button variant="ghost" size="sm" className="text-xs shrink-0" onClick={downloadTemplate}>
          <Download className="h-3.5 w-3.5 mr-1.5" />
          {t('import.migration.downloadTemplate', 'Baixar modelo')}
        </Button>
      </div>

      <div
        className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-primary/50 transition-colors"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
      >
        <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = '' }} />
        {loading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading', 'Carregando…')}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            {t('import.migration.dropCsv', 'Arraste um CSV ou clique para selecionar')}
          </p>
        )}
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {result && (
        <div className="rounded-lg bg-muted/50 p-3 space-y-1 text-xs">
          <div className="flex gap-4">
            <span className="text-green-600 font-medium">+{result.created} {t('import.migration.created', 'criados')}</span>
            <span className="text-muted-foreground">{result.skipped} {t('import.migration.skipped', 'ignorados')}</span>
            {result.failed > 0 && <span className="text-destructive">{result.failed} {t('import.migration.failed', 'falhas')}</span>}
          </div>
          {result.errors.length > 0 && (
            <ul className="list-disc list-inside text-destructive space-y-0.5">
              {result.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function MigrationWizardPanel() {
  const { t } = useTranslation()

  const steps = [
    {
      icon: <Tag className="h-5 w-5" />,
      title: t('import.migration.stepCategories', 'Categorias'),
      description: t('import.migration.stepCategoriesDesc', 'Importe categorias de outro sistema. Colunas: name (obrigatório), icon, color.'),
      templateCols: 'name,icon,color,treat_as_transfer,is_ignored',
      onUpload: (f: File) => categoriesApi.importCsv(f),
    },
    {
      icon: <Users className="h-5 w-5" />,
      title: t('import.migration.stepPayees', 'Beneficiários / Fornecedores'),
      description: t('import.migration.stepPayeesDesc', 'Importe clientes e fornecedores. Colunas: name (obrigatório), type (person|company), email, phone, address, notes.'),
      templateCols: 'name,type,email,phone,address,notes',
      onUpload: (f: File) => payeesApi.importCsv(f),
    },
    {
      icon: <ArrowRightLeft className="h-5 w-5" />,
      title: t('import.migration.stepTransactions', 'Transações históricas'),
      description: t('import.migration.stepTransactionsDesc', 'Use a aba "Extrato bancário" para importar transações históricas em CSV, OFX, QIF ou CAMT.053.'),
      templateCols: '',
      onUpload: async () => ({ created: 0, skipped: 0, failed: 0, errors: [] }),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="rounded-xl border bg-card p-5">
        <h3 className="text-sm font-semibold mb-1">{t('import.migration.title', 'Assistente de migração')}</h3>
        <p className="text-xs text-muted-foreground">
          {t('import.migration.description', 'Importe dados de outro sistema financeiro passo a passo. Linhas com nomes que já existem são ignoradas automaticamente (sem duplicatas).')}
        </p>
      </div>

      <div className="grid gap-3">
        {steps.map((step, i) => (
          step.templateCols ? (
            <CsvUploadStep
              key={i}
              title={`${i + 1}. ${step.title}`}
              description={step.description}
              templateCols={step.templateCols}
              onUpload={step.onUpload}
            />
          ) : (
            <div key={i} className="rounded-xl border bg-card p-5 flex items-start gap-3">
              <div className="mt-0.5 text-muted-foreground">{step.icon}</div>
              <div>
                <p className="text-[13px] font-semibold">{`${i + 1}. ${step.title}`}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{step.description}</p>
              </div>
            </div>
          )
        ))}
      </div>
    </div>
  )
}

// ─── Import page ─────────────────────────────────────────────────────────────

type ImportTab = 'transactions' | 'investments' | 'nfe' | 'migration'

export default function ImportPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab')
  const tab: ImportTab =
    rawTab === 'investments' ? 'investments' :
    rawTab === 'nfe' ? 'nfe' :
    rawTab === 'migration' ? 'migration' :
    'transactions'

  function selectTab(next: ImportTab) {
    const params = new URLSearchParams(searchParams)
    if (next === 'transactions') params.delete('tab')
    else params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const TAB_LABELS: Record<ImportTab, string> = {
    transactions: t('import.tabTransactions', 'Extrato bancário'),
    investments: t('import.tabInvestments', 'Investimentos'),
    nfe: t('import.tabNfe', 'NF-e XML'),
    migration: t('import.tabMigration', 'Migração'),
  }

  return (
    <div className="space-y-6">
      <PageHeader
        section={t('import.title')}
        title={
          tab === 'investments' ? t('assetImport.title') :
          tab === 'nfe' ? t('import.nfe.title', 'Importar NF-e') :
          tab === 'migration' ? t('import.migration.title', 'Assistente de migração') :
          t('import.subtitle')
        }
      />

      <div className="inline-flex items-center rounded-lg border border-border bg-muted/40 p-0.5">
        {(['transactions', 'investments', 'nfe', 'migration'] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => selectTab(value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {TAB_LABELS[value]}
          </button>
        ))}
      </div>

      {tab === 'investments' ? <AssetImportPanel /> :
       tab === 'nfe' ? <NfeImportPanel /> :
       tab === 'migration' ? <MigrationWizardPanel /> :
       <TransactionImportPanel />}
    </div>
  )
}
