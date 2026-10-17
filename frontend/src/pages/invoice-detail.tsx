import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Ban, Check, CheckCircle2, CircleSlash, Copy, CreditCard, Download, FileText, Link2,
  MoreHorizontal, Pencil, RefreshCw, RotateCcw, Send, Share2, Trash2, Unlink,
} from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PageHeader } from '@/components/page-header'
import { InvoiceSuggestions } from '@/components/invoice-suggestions'
import {
  IconAction,
  SectionCard,
  SectionHeader,
  Segmented,
  StateBadge,
} from '@/components/invoice-ui'
import { InvoiceDocumentView } from '@/components/invoice-document'
import { InvoiceDocumentBrowser } from '@/components/invoice-documents'
import { InvoiceLineEditor } from '@/components/invoice-line-editor'
import type { Invoice, InvoiceDirection, InvoiceLineInput, WithholdingTaxType } from '@/types'
import { cn } from '@/lib/utils'
import { formatCurrency } from '@/lib/format'
import { useDisplayLocale, useDateLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { useAuth } from '@/contexts/auth-context'
import { useWorkspace } from '@/contexts/workspace-context'
import {
  invoices as invoicesApi,
  payees as payeesApi,
  transactions as transactionsApi,
  fiscalEmissionsApi,
  billingApi,
  type FiscalEmission,
  type BillingCharge,
  type CreateBillingChargeRequest,
} from '@/lib/api'
import {
  allocationOrigin,
  availableActions,
  customFieldDefs,
  displayNumber,
  invoiceErrorKey,
  linesTotal,
} from '@/lib/invoice-utils'

/**
 * One invoice: what is owed, the money bound to it, and the document.
 *
 * The tab split is the point. "Details" is the operator's view — the
 * ledger side, where money gets linked. "Document" is what the client
 * receives, rendered from the same structure the PDF is. Mixing the two
 * on one screen is what made the first version feel like neither.
 */
type Tab = 'details' | 'document'

export default function InvoiceDetailPage() {
  const { t } = useTranslation()
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const { mask } = usePrivacyMode()
  const { user } = useAuth()
  const { canWrite, can, current: currentWorkspace } = useWorkspace()
  const fallbackCurrency = user?.preferences?.currency_display ?? 'BRL'

  const [linkOpen, setLinkOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [emitOpen, setEmitOpen] = useState(false)
  const [cancelEmissionOpen, setCancelEmissionOpen] = useState(false)
  const [cancelJustificativa, setCancelJustificativa] = useState('')
  const [chargeOpen, setChargeOpen] = useState(false)
  const [chargeMethod, setChargeMethod] = useState<'boleto' | 'pix'>('pix')
  const [chargePayerName, setChargePayerName] = useState('')
  const [chargePayerCpfCnpj, setChargePayerCpfCnpj] = useState('')
  const [chargePayerEmail, setChargePayerEmail] = useState('')
  const [chargeAddress, setChargeAddress] = useState('')
  const [chargeAddressNumber, setChargeAddressNumber] = useState('')
  const [chargeCity, setChargeCity] = useState('')
  const [chargeState, setChargeState] = useState('')
  const [chargeZip, setChargeZip] = useState('')
  const [tab, setTab] = useState<Tab>('details')
  const [copied, setCopied] = useState(false)
  const [whOpen, setWhOpen] = useState(false)
  const [whType, setWhType] = useState<WithholdingTaxType>('irrf')
  const [whRate, setWhRate] = useState('')
  const [whBase, setWhBase] = useState('')
  const [whAmount, setWhAmount] = useState('')

  const { data: invoice, isLoading } = useQuery({
    queryKey: ['invoice', id],
    queryFn: () => invoicesApi.get(id),
    enabled: Boolean(id),
  })
  const { data: settings } = useQuery({
    queryKey: ['invoice-settings'],
    queryFn: invoicesApi.settings,
  })
  // Only when the tab is open: it resolves the snapshot and builds the
  // whole page server-side, and the ledger view has no use for any of it.
  // Fetched here rather than only inside the Documents section: the
  // header has to know whether a real document exists before it offers
  // to download one. Same query key as the section, so this is one
  // request shared through the cache, not two.
  const { data: attachments = [] } = useQuery({
    queryKey: ['invoice-attachments', id],
    queryFn: () => invoicesApi.attachments.list(id!),
    enabled: Boolean(id),
  })
  const hasFiledDocument = attachments.some((a) => a.is_primary)

  const { data: documentPayload } = useQuery({
    queryKey: ['invoice-document', id],
    queryFn: () => invoicesApi.document(id),
    enabled: Boolean(id) && tab === 'document',
  })

  const wsId = currentWorkspace?.id ?? ''

  const { data: emissions = [] } = useQuery<FiscalEmission[]>({
    queryKey: ['fiscal-emissions', id],
    queryFn: () => fiscalEmissionsApi.listEmissions(wsId, id),
    enabled: Boolean(id) && Boolean(wsId) && can('fiscal.emit'),
  })
  const activeEmission = emissions[0] ?? null

  const { data: billingCharges = [] } = useQuery<BillingCharge[]>({
    queryKey: ['billing-charges', id],
    queryFn: () => billingApi.listCharges(wsId, id),
    enabled: Boolean(id) && Boolean(wsId) && can('billing.read'),
  })
  const activeCharge = billingCharges[0] ?? null

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['invoice', id] })
    void queryClient.invalidateQueries({ queryKey: ['invoice-document', id] })
    void queryClient.invalidateQueries({ queryKey: ['invoices'] })
    void queryClient.invalidateQueries({ queryKey: ['invoice-summary'] })
    void queryClient.invalidateQueries({ queryKey: ['invoice-facets'] })
  }

  const onError = (error: unknown) => {
    const key = invoiceErrorKey(error)
    toast.error(key ? t(key, t('invoices.errors.generic')) : t('invoices.errors.generic'))
  }

  const emitMutation = useMutation({
    mutationFn: () => fiscalEmissionsApi.emit(wsId, id),
    onSuccess: () => {
      toast.success(t('fiscalEmission.emitTitle'))
      void queryClient.invalidateQueries({ queryKey: ['fiscal-emissions', id] })
      setEmitOpen(false)
    },
    onError,
  })

  const refreshEmissionMutation = useMutation({
    mutationFn: (emissionId: string) => fiscalEmissionsApi.refresh(wsId, emissionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['fiscal-emissions', id] })
    },
    onError,
  })

  const cancelEmissionMutation = useMutation({
    mutationFn: (emissionId: string) =>
      fiscalEmissionsApi.cancel(wsId, emissionId, cancelJustificativa || undefined),
    onSuccess: () => {
      toast.success(t('fiscalEmission.cancel'))
      void queryClient.invalidateQueries({ queryKey: ['fiscal-emissions', id] })
      setCancelEmissionOpen(false)
    },
    onError,
  })

  const createChargeMutation = useMutation({
    mutationFn: (req: CreateBillingChargeRequest) =>
      billingApi.createCharge(wsId, id, req),
    onSuccess: () => {
      toast.success(t('billing.createCharge'))
      void queryClient.invalidateQueries({ queryKey: ['billing-charges', id] })
      setChargeOpen(false)
    },
    onError,
  })

  const refreshChargeMutation = useMutation({
    mutationFn: (chargeId: string) => billingApi.refreshCharge(wsId, chargeId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['billing-charges', id] })
    },
    onError,
  })

  const cancelChargeMutation = useMutation({
    mutationFn: (chargeId: string) => billingApi.cancelCharge(wsId, chargeId),
    onSuccess: () => {
      toast.success(t('billing.cancel'))
      void queryClient.invalidateQueries({ queryKey: ['billing-charges', id] })
    },
    onError,
  })

  const decision = (run: () => Promise<unknown>, successKey: string) => ({
    mutationFn: run,
    onSuccess: () => {
      toast.success(t(successKey))
      refresh()
    },
    onError,
  })

  const issueMutation = useMutation(decision(() => invoicesApi.issue(id), 'invoices.issued'))
  const voidMutation = useMutation(decision(() => invoicesApi.void(id), 'invoices.voided'))
  const writeOffMutation = useMutation(
    decision(() => invoicesApi.writeOff(id), 'invoices.writtenOff'),
  )
  const reopenMutation = useMutation(decision(() => invoicesApi.reopen(id), 'invoices.reopened'))
  const deleteMutation = useMutation({
    mutationFn: () => invoicesApi.remove(id),
    onSuccess: () => {
      toast.success(t('invoices.deleted'))
      refresh()
      navigate('/invoices')
    },
    onError,
  })
  const addWithholdingMutation = useMutation({
    mutationFn: () =>
      invoicesApi.addWithholding(id, {
        tax_type: whType,
        rate: whRate || null,
        base_amount: whBase,
        withheld_amount: whAmount,
      }),
    onSuccess: () => {
      toast.success(t('tax.addWithholding'))
      setWhOpen(false)
      setWhRate('')
      setWhBase('')
      setWhAmount('')
      refresh()
    },
    onError,
  })
  const deleteWithholdingMutation = useMutation({
    mutationFn: (whId: string) => invoicesApi.deleteWithholding(id, whId),
    onSuccess: refresh,
    onError,
  })
  const unlinkMutation = useMutation({
    mutationFn: (allocationId: string) => invoicesApi.unallocate(id, allocationId),
    onSuccess: () => {
      toast.success(t('invoices.unlinked'))
      refresh()
    },
    onError,
  })

  // Fetched as a blob rather than opened as a link: the PDF route needs
  // the auth and workspace headers the axios interceptor adds, which a
  // plain anchor would not carry.
  const downloadMutation = useMutation({
    mutationFn: async () => {
      const blob = await invoicesApi.pdf(id)
      const url = URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = url
      anchor.download = `${invoice?.number ?? 'invoice'}.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
    },
    onError,
  })

  const shareMutation = useMutation({
    mutationFn: () => invoicesApi.share(id),
    onSuccess: async (link) => {
      const url = `${window.location.origin}${link.path}`
      try {
        await navigator.clipboard.writeText(url)
        setCopied(true)
        setTimeout(() => setCopied(false), 2500)
        toast.success(t('invoices.shareCopied'))
      } catch {
        // A blocked clipboard is not a failed share — the link exists.
        toast.success(url)
      }
      refresh()
    },
    onError,
  })

  const unshareMutation = useMutation({
    mutationFn: () => invoicesApi.unshare(id),
    onSuccess: () => {
      toast.success(t('invoices.shareRevoked'))
      refresh()
    },
    onError,
  })

  if (isLoading || !invoice) {
    return (
      <div>
        <Skeleton className="h-4 w-28 mb-6" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    )
  }

  const actions = availableActions(invoice)
  const currency = invoice.currency || fallbackCurrency
  const money = (value: string | number | null | undefined) =>
    mask(formatCurrency(Number(value ?? 0), currency, locale))
  const showDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(dateLocale)
  const number = displayNumber(invoice, settings?.number_prefix)
  const customFields = customFieldDefs(settings?.template)
    .map((def) => ({ ...def, value: invoice.custom_fields?.[def.key] }))
    .filter((field): field is typeof field & { value: string } => Boolean(field.value))
  const shareUrl = invoice.share_token
    ? `${window.location.origin}/i/${invoice.share_token}`
    : null

  return (
    <div>
      <button
        onClick={() => navigate('/invoices')}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors mb-3"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        {t('invoices.backToList')}
      </button>

      <PageHeader
        section={
          invoice.payee?.name ??
          t(invoice.direction === 'payable' ? 'invoices.noSupplier' : 'invoices.noClient')
        }
        title={number ?? t('invoices.draftTitle')}
        action={
          canWrite ? (
            <div className="flex flex-wrap items-center gap-2">
              {actions.canEdit && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditOpen(true)}
                  data-testid="invoice-edit"
                >
                  <Pencil className="h-4 w-4 mr-1.5" />
                  {t('common.edit')}
                </Button>
              )}
              {actions.canIssue && (
                <Button size="sm" onClick={() => issueMutation.mutate()} data-testid="invoice-issue">
                  <Send className="h-4 w-4 mr-1.5" />
                  {t('invoices.action.issue')}
                </Button>
              )}
              {actions.canAllocate && (
                <Button size="sm" onClick={() => setLinkOpen(true)} data-testid="invoice-link-payment">
                  <Link2 className="h-4 w-4 mr-1.5" />
                  {t('invoices.action.markPaid')}
                </Button>
              )}
              {invoice.status !== 'draft' && (
                <>
                  {/* Downloading an imported invoice with nothing filed
                      would hand over a page we drew for a document
                      somebody else issued — the same invention the
                      Document tab refuses to make. Nothing to download
                      until the real file arrives. */}
                  {(invoice.origin !== 'imported' || hasFiledDocument) && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => downloadMutation.mutate()}
                      disabled={downloadMutation.isPending}
                      data-testid="invoice-download-pdf"
                    >
                      <Download className="h-4 w-4 mr-1.5" />
                      {t('invoices.action.downloadPdf')}
                    </Button>
                  )}
                  {/* Sharing is for sending your invoice to your client.
                      A bill you received belongs to your supplier and has
                      nobody to be sent to. */}
                  {invoice.direction === 'receivable' && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      invoice.share_token ? unshareMutation.mutate() : shareMutation.mutate()
                    }
                    data-testid={invoice.share_token ? 'invoice-unshare' : 'invoice-share'}
                  >
                    {copied ? (
                      <Check className="h-4 w-4 mr-1.5" />
                    ) : (
                      <Share2 className="h-4 w-4 mr-1.5" />
                    )}
                    {invoice.share_token
                      ? t('invoices.action.revokeLink')
                      : t('invoices.action.share')}
                  </Button>
                  )}
                </>
              )}
              {/* The rare and irreversible decisions live behind an
                  overflow menu, with words. Two bare icons side by side
                  were indistinguishable, and giving "void" the same
                  weight as "mark as paid" is how someone voids by
                  reflex. */}
              {(actions.canWriteOff ||
                actions.canReopen ||
                actions.canVoid ||
                actions.canDelete) && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      aria-label={t('invoices.moreActions')}
                      data-testid="invoice-more-actions"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border/80 bg-card text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    className="w-[220px] p-1 bg-card border border-border rounded-xl shadow-md"
                  >
                    {actions.canWriteOff && (
                      <DropdownMenuItem
                        onClick={() => writeOffMutation.mutate()}
                        data-testid="invoice-writeoff"
                        className="gap-2 text-sm"
                      >
                        <Ban className="h-4 w-4 text-muted-foreground" />
                        {t('invoices.action.writeOff')}
                      </DropdownMenuItem>
                    )}
                    {actions.canReopen && (
                      <DropdownMenuItem
                        onClick={() => reopenMutation.mutate()}
                        data-testid="invoice-reopen"
                        className="gap-2 text-sm"
                      >
                        <RotateCcw className="h-4 w-4 text-muted-foreground" />
                        {t('invoices.action.reopen')}
                      </DropdownMenuItem>
                    )}
                    {actions.canVoid && (
                      <DropdownMenuItem
                        onClick={() => voidMutation.mutate()}
                        data-testid="invoice-void"
                        className="gap-2 text-sm text-destructive focus:text-destructive"
                      >
                        <CircleSlash className="h-4 w-4" />
                        {t('invoices.action.void')}
                      </DropdownMenuItem>
                    )}
                    {actions.canDelete && (
                      <DropdownMenuItem
                        onClick={() => deleteMutation.mutate()}
                        data-testid="invoice-delete"
                        className="gap-2 text-sm text-destructive focus:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                        {t('common.delete')}
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-5">
        <Segmented<Tab>
          value={tab}
          onChange={setTab}
          testIdPrefix="invoice-tab"
          options={[
            { value: 'details', label: t('invoices.tab.details') },
            { value: 'document', label: t('invoices.tab.document') },
          ]}
        />
        <StateBadge state={invoice.state} />
        {invoice.days_overdue > 0 && (
          <span className="text-xs font-medium text-rose-500">
            {t('invoices.daysLate', { count: invoice.days_overdue })}
          </span>
        )}
      </div>

      {tab === 'document' ? (
        <div className="space-y-4">
          {shareUrl && (
            <SectionCard>
              <div
                className="flex flex-wrap items-center gap-2 px-4 sm:px-5 py-3 text-xs"
                data-testid="invoice-share-banner"
              >
                <Share2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground">{t('invoices.shareActive')}</span>
                <code className="truncate font-mono text-[11px] text-foreground">{shareUrl}</code>
                <div className="ml-auto">
                  <IconAction
                    onClick={() => {
                      void navigator.clipboard.writeText(shareUrl)
                      toast.success(t('invoices.shareCopied'))
                    }}
                    label={t('invoices.shareCopy')}
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </IconAction>
                </div>
              </div>
            </SectionCard>
          )}
          {documentPayload ? (
            // Every page this invoice has, in one browser: the files down
            // the left, the selected one read on the right. Our own
            // render is one entry among them — and not offered at all on
            // an import, where drawing it would invent a document
            // somebody else issued.
            <InvoiceDocumentBrowser
              invoiceId={invoice.id}
              origin={invoice.origin}
              canWrite={canWrite}
              ourPageLabel={number}
              ourPageDate={invoice.issue_date}
              ourPage={<InvoiceDocumentView document={documentPayload} />}
              onChanged={refresh}
            />
          ) : (
            <Skeleton className="h-[520px] w-full rounded-xl" />
          )}
        </div>
      ) : (
        <div className="space-y-5">
          <SectionCard>
            <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-border">
              {[
                { label: t('invoices.column.total'), value: money(invoice.total) },
                {
                  label:
                    invoice.direction === 'payable'
                      ? t('invoices.field.paidOut')
                      : t('invoices.field.paid'),
                  value: money(invoice.amount_paid),
                },
                {
                  label: t('invoices.column.balance'),
                  value: money(invoice.balance),
                  tone:
                    Number(invoice.balance) > 0
                      ? 'text-foreground'
                      : 'text-emerald-600',
                  testId: 'invoice-balance',
                },
                { label: t('invoices.column.due'), value: showDate(invoice.due_date) },
              ].map((figure) => (
                <div key={figure.label} className="px-4 sm:px-5 py-4" data-testid={figure.testId}>
                  <p className="text-xs font-medium text-muted-foreground mb-0.5">{figure.label}</p>
                  <p
                    className={cn(
                      'text-lg font-bold tabular-nums',
                      figure.tone ?? 'text-foreground',
                    )}
                  >
                    {figure.value}
                  </p>
                </div>
              ))}
            </div>
          </SectionCard>

          {(invoice.lines.length > 0 || invoice.notes || customFields.length > 0) && (
            <SectionCard>
              <SectionHeader title={t('invoices.detailsTitle')} />
              <div className="px-4 sm:px-5 py-4 space-y-4">
                {/* Competence only earns a row when it disagrees with the
                    issue date; otherwise it is noise on every invoice. */}
                {invoice.competence_date && invoice.competence_date !== invoice.issue_date && (
                  <p className="text-xs text-muted-foreground" data-testid="invoice-competence">
                    {t('invoices.competenceDiverges', {
                      competence: showDate(invoice.competence_date),
                      issue: showDate(invoice.issue_date),
                    })}
                  </p>
                )}

                {/* Driven by the workspace's definitions, so the label
                    the sender chose is what shows — never the raw key —
                    and a field removed from settings stops appearing. */}
                {customFields.length > 0 && (
                  <div className="flex flex-wrap gap-x-8 gap-y-2">
                    {customFields.map((field) => (
                      <div key={field.key}>
                        <p className="text-xs font-medium text-muted-foreground mb-0.5">
                          {field.label}
                        </p>
                        <p className="text-sm">{field.value}</p>
                      </div>
                    ))}
                  </div>
                )}

                {invoice.lines.length > 0 && (
                  <table className="w-full">
                    <tbody>
                      {invoice.lines.map((line) => (
                        <tr key={line.id} className="border-b border-border last:border-0">
                          <td className="py-2.5 text-sm text-foreground">{line.description}</td>
                          <td className="py-2.5 text-right text-xs text-muted-foreground tabular-nums">
                            {Number(line.quantity)} × {money(line.unit_price)}
                          </td>
                          <td className="py-2.5 text-right text-sm font-medium tabular-nums w-32">
                            {money(line.total)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                {invoice.notes && (
                  <p className="text-sm text-muted-foreground">{invoice.notes}</p>
                )}
              </div>
            </SectionCard>
          )}

          {invoice.direction === 'receivable' && (
            <SectionCard>
              <SectionHeader
                title={t('tax.withholdings')}
                action={
                  canWrite && invoice.status !== 'void' ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setWhBase(String(invoice.total))
                        setWhOpen(true)
                      }}
                    >
                      + {t('tax.addWithholding')}
                    </Button>
                  ) : undefined
                }
              />
              {invoice.withholdings.length > 0 && (
                <div className="px-4 sm:px-5 py-4">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="py-2 text-left font-medium">{t('tax.taxObligationType')}</th>
                        <th className="py-2 text-right font-medium">{t('tax.withholdingRate')}</th>
                        <th className="py-2 text-right font-medium">{t('tax.withholdingBase')}</th>
                        <th className="py-2 text-right font-medium">{t('tax.withheldAmount')}</th>
                        {canWrite && <th className="py-2 w-10"><span className="sr-only">{t('tax.removeWithholding')}</span></th>}
                      </tr>
                    </thead>
                    <tbody>
                      {invoice.withholdings.map((wh) => (
                        <tr key={wh.id} className="border-b border-border last:border-0">
                          <td className="py-2.5">{t(`tax.withholdingTypes.${wh.tax_type}`)}</td>
                          <td className="py-2.5 text-right tabular-nums">{wh.rate ? `${Number(wh.rate)}%` : '—'}</td>
                          <td className="py-2.5 text-right tabular-nums">{money(wh.base_amount)}</td>
                          <td className="py-2.5 text-right tabular-nums text-destructive">
                            −{money(wh.withheld_amount)}
                          </td>
                          {canWrite && (
                            <td className="py-2.5 text-right">
                              <button
                                className="p-1 rounded-md text-muted-foreground hover:text-destructive transition-colors"
                                onClick={() => deleteWithholdingMutation.mutate(wh.id)}
                                disabled={deleteWithholdingMutation.isPending}
                                aria-label={t('tax.removeWithholding')}
                                title={t('tax.removeWithholding')}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="mt-3 flex flex-wrap justify-end gap-x-6 gap-y-1 text-sm font-medium">
                    <span>{t('tax.grossTotal')}: {money(invoice.total)}</span>
                    <span className="text-destructive">
                      {t('tax.totalWithheld')}: −{money(invoice.total_withheld)}
                    </span>
                    <span className="text-primary">
                      {t('tax.netReceivable')}: {money(invoice.net_receivable)}
                    </span>
                  </div>
                </div>
              )}
            </SectionCard>
          )}

          {/* Above the payments, because it is a question about them and
              because an answer here changes the list below. Renders
              nothing when nothing is waiting. */}
          <InvoiceSuggestions invoiceId={invoice.id} canWrite={canWrite} />

          <SectionCard>
            <SectionHeader
              title={t('invoices.payments')}
              action={
                actions.canAllocate && canWrite ? (
                  <Button size="sm" variant="outline" onClick={() => setLinkOpen(true)}>
                    <Link2 className="h-3.5 w-3.5 mr-1.5" />
                    {t('invoices.action.link')}
                  </Button>
                ) : undefined
              }
            />
            {invoice.allocations.length === 0 ? (
              <p
                className="px-4 sm:px-5 py-8 text-center text-sm text-muted-foreground"
                data-testid="invoice-no-payments"
              >
                {t('invoices.noPayments')}
              </p>
            ) : (
              <table className="w-full">
                <tbody>
                  {invoice.allocations.map((allocation) => (
                    <tr
                      key={allocation.id}
                      data-testid="invoice-allocation"
                      className="border-b border-border last:border-0"
                    >
                      <td className="py-3 pl-4 sm:pl-5">
                        <div className="text-sm font-medium text-foreground truncate">
                          {allocation.transaction?.description ?? t('invoices.linkedPayment')}
                        </div>
                        <div className="text-xs text-muted-foreground tabular-nums mt-0.5">
                          {allocation.transaction?.date
                            ? showDate(allocation.transaction.date)
                            : ''}
                          {' · '}
                          {(() => {
                            const origin = allocationOrigin(allocation.method)
                            if (!origin.automatic) return t('invoices.linkedManually')
                            // The strategy id is shown as the title rather
                            // than the label: it is a machine name today
                            // and becomes a readable one when the policy
                            // is fetchable, without this line changing.
                            return (
                              <span title={origin.strategyId ?? undefined}>
                                {t('invoices.linkedAutomatically')}
                              </span>
                            )
                          })()}
                        </div>
                      </td>
                      <td className="py-3 text-right text-sm font-bold tabular-nums text-emerald-600">
                        {money(allocation.amount)}
                      </td>
                      <td className="py-3 pr-4 sm:pr-5 text-right w-16">
                        {canWrite && (
                          <IconAction
                            onClick={() => unlinkMutation.mutate(allocation.id)}
                            label={t('invoices.action.unlink')}
                            destructive
                          >
                            <Unlink className="h-4 w-4" />
                          </IconAction>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </SectionCard>
        </div>
      )}

      {can('fiscal.emit') && (
        <SectionCard>
          <SectionHeader title={t('fiscalEmission.settingsTitle')} action={<FileText className="h-4 w-4 text-muted-foreground" />} />
          {activeEmission ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className={cn(
                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                  activeEmission.status === 'issued' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
                  activeEmission.status === 'processing' && 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
                  activeEmission.status === 'error' && 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
                  activeEmission.status === 'cancelled' && 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400',
                  activeEmission.status === 'pending' && 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
                )}>
                  {t(`fiscalEmission.status${activeEmission.status.charAt(0).toUpperCase() + activeEmission.status.slice(1)}` as const, activeEmission.status)}
                </span>
                {activeEmission.nfe_number && (
                  <span className="text-sm text-muted-foreground">
                    {t('fiscalEmission.nfeNumber')}: {activeEmission.nfe_number}/{activeEmission.nfe_serie}
                  </span>
                )}
              </div>
              {activeEmission.chave_acesso && (
                <p className="text-xs font-mono break-all text-muted-foreground">
                  {activeEmission.chave_acesso}
                </p>
              )}
              {activeEmission.error_message && (
                <p className="text-xs text-destructive">{activeEmission.error_message}</p>
              )}
              <div className="flex flex-wrap gap-2">
                {activeEmission.xml_url && (
                  <Button size="sm" variant="outline" asChild>
                    <a href={activeEmission.xml_url} target="_blank" rel="noreferrer">
                      {t('fiscalEmission.xmlUrl')}
                    </a>
                  </Button>
                )}
                {activeEmission.pdf_url && (
                  <Button size="sm" variant="outline" asChild>
                    <a href={activeEmission.pdf_url} target="_blank" rel="noreferrer">
                      {t('fiscalEmission.pdfUrl')}
                    </a>
                  </Button>
                )}
                {!['issued', 'cancelled'].includes(activeEmission.status) && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => refreshEmissionMutation.mutate(activeEmission.id)}
                    disabled={refreshEmissionMutation.isPending}
                  >
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                    {t('fiscalEmission.refresh')}
                  </Button>
                )}
                {activeEmission.status === 'issued' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => setCancelEmissionOpen(true)}
                  >
                    <Ban className="mr-1.5 h-3.5 w-3.5" />
                    {t('fiscalEmission.cancel')}
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm text-muted-foreground">{t('fiscalEmission.noEmission')}</p>
              {invoice.status === 'open' && (
                <Button size="sm" variant="outline" onClick={() => setEmitOpen(true)}>
                  <FileText className="mr-1.5 h-4 w-4" />
                  {t('fiscalEmission.emitButton')}
                </Button>
              )}
            </div>
          )}
        </SectionCard>
      )}

      {can('billing.read') && (
        <SectionCard>
          <SectionHeader title={t('billing.chargesTitle')} action={<CreditCard className="h-4 w-4 text-muted-foreground" />} />
          {activeCharge ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className={cn(
                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                  activeCharge.status === 'received' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
                  activeCharge.status === 'confirmed' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
                  activeCharge.status === 'awaiting_payment' && 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
                  activeCharge.status === 'pending' && 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
                  activeCharge.status === 'overdue' && 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
                  activeCharge.status === 'cancelled' && 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400',
                  activeCharge.status === 'error' && 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
                )}>
                  {(() => {
                    const key = `billing.status${activeCharge.status.split('_').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join('')}`
                    return t(key as string, { defaultValue: activeCharge.status })
                  })()}
                </span>
                <span className="text-sm text-muted-foreground capitalize">{activeCharge.method}</span>
                {activeCharge.paid_at && (
                  <span className="text-sm text-muted-foreground">
                    {t('billing.paidAt')}: {activeCharge.paid_at.slice(0, 10)}
                  </span>
                )}
              </div>
              {activeCharge.error_message && (
                <p className="text-xs text-destructive">{activeCharge.error_message}</p>
              )}
              {activeCharge.pix_copy_paste && (
                <div className="rounded bg-muted p-2">
                  <p className="text-xs font-mono break-all select-all">{activeCharge.pix_copy_paste}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {activeCharge.boleto_url && (
                  <Button size="sm" variant="outline" asChild>
                    <a href={activeCharge.boleto_url} target="_blank" rel="noreferrer">
                      {t('billing.boletoUrl')}
                    </a>
                  </Button>
                )}
                {!['received', 'confirmed', 'cancelled', 'error'].includes(activeCharge.status) && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => refreshChargeMutation.mutate(activeCharge.id)}
                    disabled={refreshChargeMutation.isPending}
                  >
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                    {t('billing.refresh')}
                  </Button>
                )}
                {can('billing.manage') && !['received', 'confirmed', 'cancelled'].includes(activeCharge.status) && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => cancelChargeMutation.mutate(activeCharge.id)}
                    disabled={cancelChargeMutation.isPending}
                  >
                    <Ban className="mr-1.5 h-3.5 w-3.5" />
                    {t('billing.cancel')}
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm text-muted-foreground">{t('billing.noCharge')}</p>
              {can('billing.manage') && invoice.status === 'open' && (
                <Button size="sm" variant="outline" onClick={() => setChargeOpen(true)}>
                  <CreditCard className="mr-1.5 h-4 w-4" />
                  {t('billing.createCharge')}
                </Button>
              )}
            </div>
          )}
        </SectionCard>
      )}

      <EditDraftDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        invoice={invoice}
        showTax={(settings?.tax_fields ?? 'hidden') !== 'hidden'}
        currency={currency}
        onSaved={refresh}
      />

      <Dialog open={whOpen} onOpenChange={setWhOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('tax.addWithholding')}</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              addWithholdingMutation.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>{t('tax.taxObligationType')}</Label>
              <select
                className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                value={whType}
                onChange={(e) => setWhType(e.target.value as WithholdingTaxType)}
              >
                {(['irrf', 'iss', 'pis', 'cofins', 'csll', 'inss', 'other'] as const).map((k) => (
                  <option key={k} value={k}>{t(`tax.withholdingTypes.${k}`)}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>{t('tax.withholdingRate')}</Label>
                <Input type="number" step="0.01" value={whRate} onChange={(e) => setWhRate(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>{t('tax.withholdingBase')}</Label>
                <Input type="number" step="0.01" value={whBase} onChange={(e) => setWhBase(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>{t('tax.withheldAmount')}</Label>
                <Input type="number" step="0.01" value={whAmount} onChange={(e) => setWhAmount(e.target.value)} required />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setWhOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={addWithholdingMutation.isPending}>
                {t('common.save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Emit NF-e confirm dialog */}
      <Dialog open={emitOpen} onOpenChange={setEmitOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('fiscalEmission.emitTitle')}</DialogTitle>
            <DialogDescription>{t('fiscalEmission.emitDescription')}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmitOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => emitMutation.mutate()} disabled={emitMutation.isPending}>
              {emitMutation.isPending ? t('fiscalEmission.emitting') : t('fiscalEmission.emitConfirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cancel NF-e dialog */}
      <Dialog open={cancelEmissionOpen} onOpenChange={setCancelEmissionOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('fiscalEmission.cancelTitle')}</DialogTitle>
            <DialogDescription>{t('fiscalEmission.cancelDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-2">
            <Label>{t('fiscalEmission.cancelJustificativa')}</Label>
            <Input
              placeholder={t('fiscalEmission.cancelJustificativaPlaceholder')}
              value={cancelJustificativa}
              onChange={(e) => setCancelJustificativa(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelEmissionOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => activeEmission && cancelEmissionMutation.mutate(activeEmission.id)}
              disabled={cancelEmissionMutation.isPending}
            >
              {t('fiscalEmission.cancelConfirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create billing charge dialog */}
      <Dialog open={chargeOpen} onOpenChange={setChargeOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('billing.createCharge')}</DialogTitle>
            <DialogDescription>{t('billing.settingsDescription')}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 space-y-1">
              <Label className="text-[13px]">{t('billing.method')}</Label>
              <Select value={chargeMethod} onValueChange={(v) => setChargeMethod(v as 'boleto' | 'pix')}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="pix">{t('billing.methodPix')}</SelectItem>
                  <SelectItem value="boleto">{t('billing.methodBoleto')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[13px]">{t('billing.payerName')}</Label>
              <Input className="h-9 text-sm" value={chargePayerName} onChange={(e) => setChargePayerName(e.target.value)} />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[13px]">{t('billing.payerCpfCnpj')}</Label>
              <Input className="h-9 text-sm font-mono" value={chargePayerCpfCnpj} onChange={(e) => setChargePayerCpfCnpj(e.target.value.replace(/\D/g, ''))} maxLength={14} />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[13px]">{t('billing.payerEmail')}</Label>
              <Input className="h-9 text-sm" type="email" value={chargePayerEmail} onChange={(e) => setChargePayerEmail(e.target.value)} />
            </div>
            {chargeMethod === 'boleto' && (<>
              <div className="col-span-2 space-y-1">
                <Label className="text-[13px]">{t('billing.payerAddress')}</Label>
                <Input className="h-9 text-sm" value={chargeAddress} onChange={(e) => setChargeAddress(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-[13px]">{t('billing.payerAddressNumber')}</Label>
                <Input className="h-9 text-sm" value={chargeAddressNumber} onChange={(e) => setChargeAddressNumber(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-[13px]">{t('billing.payerZip')}</Label>
                <Input className="h-9 text-sm font-mono" value={chargeZip} onChange={(e) => setChargeZip(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-[13px]">{t('billing.payerCity')}</Label>
                <Input className="h-9 text-sm" value={chargeCity} onChange={(e) => setChargeCity(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-[13px]">{t('billing.payerState')}</Label>
                <Input className="h-9 text-sm" maxLength={2} value={chargeState} onChange={(e) => setChargeState(e.target.value.toUpperCase())} />
              </div>
            </>)}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setChargeOpen(false)}>{t('common.cancel')}</Button>
            <Button
              onClick={() => createChargeMutation.mutate({
                method: chargeMethod,
                amount: String(invoice.total),
                due_date: invoice.due_date ?? new Date().toISOString().slice(0, 10),
                payer_name: chargePayerName,
                payer_cpf_cnpj: chargePayerCpfCnpj,
                payer_email: chargePayerEmail || undefined,
                payer_address: chargeAddress,
                payer_address_number: chargeAddressNumber,
                payer_city: chargeCity,
                payer_state: chargeState,
                payer_zip: chargeZip,
              })}
              disabled={!chargePayerName || !chargePayerCpfCnpj || createChargeMutation.isPending}
            >
              {createChargeMutation.isPending ? t('billing.emitting') : t('billing.createCharge')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <LinkPaymentDialog
        open={linkOpen}
        onOpenChange={setLinkOpen}
        invoiceId={id}
        direction={invoice.direction}
        balance={invoice.balance}
        currency={currency}
        onLinked={refresh}
      />
    </div>
  )
}

function LinkPaymentDialog({
  open,
  onOpenChange,
  invoiceId,
  direction,
  balance,
  currency,
  onLinked,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  invoiceId: string
  direction: InvoiceDirection
  balance: string
  currency: string
  onLinked: () => void
}) {
  const { t } = useTranslation()
  const [selected, setSelected] = useState<string>('')
  const [amount, setAmount] = useState('')

  // Money moving the way this invoice is settled: a receivable by money
  // coming in, a payable by money going out. Asking for credits either
  // way — which this did — means the payment that actually settled a
  // supplier's bill is never in the list, and the bill stays open
  // forever with no way to close it.
  const settlingType = direction === 'payable' ? 'debit' : 'credit'
  const { data } = useQuery({
    queryKey: ['transactions', 'for-invoice', settlingType],
    queryFn: () => transactionsApi.list({ type: settlingType, limit: 50 }),
    enabled: open,
  })

  // Same currency only — the server refuses a cross-currency allocation
  // rather than inventing a rate, so offering one here would only be
  // offering an error.
  const candidates = useMemo(
    () => (data?.items ?? []).filter((tx) => (tx.currency ?? currency) === currency),
    [data, currency],
  )

  const mutation = useMutation({
    mutationFn: () => invoicesApi.allocate(invoiceId, selected, amount || undefined),
    onSuccess: () => {
      toast.success(t('invoices.linked'))
      onOpenChange(false)
      setSelected('')
      setAmount('')
      onLinked()
    },
    onError: (error) => {
      const key = invoiceErrorKey(error)
      toast.error(key ? t(key, t('invoices.errors.generic')) : t('invoices.errors.generic'))
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('invoices.action.markPaid')}</DialogTitle>
          <DialogDescription>{t('invoices.linkDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 max-h-72 overflow-y-auto">
          {candidates.length === 0 && (
            <p className="text-sm text-muted-foreground">{t('invoices.noCandidates')}</p>
          )}
          {candidates.map((tx) => (
            <button
              key={tx.id}
              onClick={() => setSelected(tx.id)}
              data-testid="invoice-candidate"
              className={cn(
                'w-full flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors',
                selected === tx.id ? 'border-primary bg-primary/5' : 'hover:bg-muted/40',
              )}
            >
              <div className="min-w-0">
                <div className="text-sm truncate">{tx.description}</div>
                <div className="text-xs text-muted-foreground tabular-nums">{tx.date}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-sm tabular-nums">
                  {formatCurrency(Number(tx.amount), tx.currency ?? currency, 'en')}
                </span>
                {selected === tx.id && <CheckCircle2 className="h-4 w-4 text-primary" />}
              </div>
            </button>
          ))}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="allocation-amount">{t('invoices.field.amountToApply')}</Label>
          <Input
            id="allocation-amount"
            data-testid="invoice-allocation-amount"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={balance}
          />
          {/* Leaving it blank is the common case — one payment closing one
              invoice should not require typing the number twice. */}
          <p className="text-[11px] text-muted-foreground">{t('invoices.field.amountHint')}</p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!selected || mutation.isPending}
            data-testid="invoice-allocation-submit"
          >
            {t('invoices.action.link')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Editing a draft.
 *
 * Only a draft: once issued, the financial substance is frozen and the
 * server refuses the change, because a document that changes after the
 * client received it is not an edit, it is a second document. The button
 * that opens this disappears at the same moment.
 *
 * Notes stay editable after issuance through the detail view, since they
 * are the seller's own record and never left the building.
 */
function EditDraftDialog({
  open,
  onOpenChange,
  invoice,
  showTax,
  currency,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  invoice: Invoice
  showTax: boolean
  currency: string
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const { data: clients = [] } = useQuery({
    queryKey: ['payees', 'for-invoice'],
    queryFn: () => payeesApi.list({}),
    enabled: open,
  })

  // Seeded from the invoice each time the dialog opens, keyed so a
  // reopen after a save starts from what was saved.
  const [payeeId, setPayeeId] = useState(invoice.payee_id ?? '')
  const [total, setTotal] = useState(invoice.total)
  const [dueDate, setDueDate] = useState(invoice.due_date)
  const [notes, setNotes] = useState(invoice.notes ?? '')
  const [lines, setLines] = useState<InvoiceLineInput[]>(() =>
    invoice.lines.map((line) => ({
      description: line.description,
      quantity: String(Number(line.quantity)),
      unit_price: line.unit_price,
      tax_rate: line.tax_rate,
    })),
  )

  const mutation = useMutation({
    mutationFn: () =>
      invoicesApi.update(invoice.id, {
        payee_id: payeeId || null,
        due_date: dueDate,
        notes: notes || null,
        // Lines are the source of truth once they exist: the server
        // recomputes the total from them and ignores what was typed.
        //
        // An empty list is sent when the draft had lines and no longer
        // does, because omitting the key means "leave them alone" — so
        // deleting every row used to save successfully and change
        // nothing, and the rows came back on the next read.
        ...(lines.length
          ? { lines }
          : invoice.lines.length
            ? { lines: [], total }
            : { total }),
      }),
    onSuccess: () => {
      toast.success(t('invoices.updated'))
      onOpenChange(false)
      onSaved()
    },
    onError: (error) => {
      const key = invoiceErrorKey(error)
      toast.error(key ? t(key, t('invoices.errors.generic')) : t('invoices.errors.generic'))
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Same rule as the create dialog: the line-item table needs the
          room, and without it the row overflows and the remove button
          falls off the right edge. */}
      <DialogContent
        className={cn(
          'flex flex-col max-h-[calc(100dvh-2rem)]',
          lines.length ? 'sm:max-w-3xl' : 'sm:max-w-lg',
        )}
      >
        <DialogHeader>
          <DialogTitle>{t('invoices.editDraft')}</DialogTitle>
          <DialogDescription>{t('invoices.editDraftDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{t('invoices.field.client')}</Label>
            <Select value={payeeId} onValueChange={setPayeeId}>
              <SelectTrigger data-testid="edit-client-select">
                <SelectValue placeholder={t('invoices.field.clientPlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                {clients.map((client) => (
                  <SelectItem key={client.id} value={client.id}>
                    {client.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="edit-total">{t('invoices.field.total')}</Label>
              <Input
                id="edit-total"
                data-testid="edit-total-input"
                inputMode="decimal"
                value={lines.length ? linesTotal(lines).toFixed(2) : total}
                onChange={(e) => setTotal(e.target.value)}
                disabled={lines.length > 0}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-due">{t('invoices.field.dueDate')}</Label>
              <Input
                id="edit-due"
                data-testid="edit-due-input"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>
          </div>

          <InvoiceLineEditor
            lines={lines}
            onChange={setLines}
            currency={currency}
            showTax={showTax}
          />

          <div className="space-y-1.5">
            <Label htmlFor="edit-notes">{t('invoices.field.notes')}</Label>
            <Input
              id="edit-notes"
              data-testid="edit-notes-input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            data-testid="edit-submit"
          >
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
