import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { CheckCircle2, Circle, Plus, Send } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useWorkspace } from '@/contexts/workspace-context'
import { useAuth } from '@/contexts/auth-context'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { formatCurrency } from '@/lib/format'
import {
  accounts as accountsApi,
  paymentsApi,
  type PaymentOrder,
  type PaymentOrderCreate,
  type PaymentStatus,
} from '@/lib/api'

const STATUS_FILTERS = ['all', 'draft', 'pending_approval', 'approved', 'sent', 'confirmed', 'failed', 'cancelled'] as const
const PIX_KEY_TYPES = ['cpf', 'cnpj', 'email', 'phone', 'random'] as const

/** i18n key suffix for a status (pending_approval -> pendingApproval). */
function statusKey(status: string): string {
  return status === 'pending_approval' ? 'pendingApproval' : status
}

function statusVariant(status: PaymentStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'confirmed') return 'default'
  if (status === 'failed') return 'destructive'
  if (status === 'draft' || status === 'cancelled') return 'outline'
  return 'secondary'
}

function errorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

function StatusBadge({ status }: { status: PaymentStatus }) {
  const { t } = useTranslation()
  return <Badge variant={statusVariant(status)}>{t(`payments.status.${statusKey(status)}`)}</Badge>
}

function emptyForm() {
  return {
    method: 'pix' as 'pix' | 'ted',
    amount: '',
    description: '',
    beneficiary_name: '',
    beneficiary_tax_id: '',
    pix_key: '',
    pix_key_type: 'email',
    bank_code: '',
    branch: '',
    account_number: '',
    account_type: 'checking',
    source_account_id: '',
  }
}

function CreateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState(emptyForm)
  const set = (patch: Partial<ReturnType<typeof emptyForm>>) => setForm((f) => ({ ...f, ...patch }))

  const { data: accountList = [] } = useQuery({
    queryKey: ['accounts', 'payments-source'],
    queryFn: () => accountsApi.list(),
    enabled: open,
  })

  const create = useMutation({
    mutationFn: (body: PaymentOrderCreate) => paymentsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payments'] })
      toast.success(t('payments.toast.created'))
      setForm(emptyForm())
      onClose()
    },
    onError: (err) => toast.error(errorMessage(err, t('common.error', 'Error'))),
  })

  const submit = () => {
    const body: PaymentOrderCreate = {
      // One key per dialog submission: a double click cannot create two orders.
      idempotency_key: crypto.randomUUID(),
      method: form.method,
      amount: form.amount,
      description: form.description || undefined,
      beneficiary_name: form.beneficiary_name,
      beneficiary_tax_id: form.beneficiary_tax_id || undefined,
      source_account_id: form.source_account_id || undefined,
    }
    if (form.method === 'pix') {
      body.pix_key = form.pix_key
      body.pix_key_type = form.pix_key_type
    } else {
      body.bank_code = form.bank_code
      body.branch = form.branch
      body.account_number = form.account_number
      body.account_type = form.account_type
    }
    create.mutate(body)
  }

  const valid =
    Number(form.amount) > 0 &&
    form.beneficiary_name.trim() !== '' &&
    (form.method === 'pix' ? form.pix_key.trim() !== '' : form.bank_code && form.branch && form.account_number)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('payments.create')}</DialogTitle>
          <DialogDescription>{t('payments.dualApprovalRequired')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>{t('payments.method')}</Label>
              <Select value={form.method} onValueChange={(v) => set({ method: v as 'pix' | 'ted' })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="pix">{t('payments.pix')}</SelectItem>
                  <SelectItem value="ted">{t('payments.ted')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="pay-amount">{t('payments.amount')}</Label>
              <Input
                id="pay-amount"
                type="number"
                min="0.01"
                step="0.01"
                value={form.amount}
                onChange={(e) => set({ amount: e.target.value })}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="pay-ben">{t('payments.beneficiary')}</Label>
            <Input id="pay-ben" value={form.beneficiary_name} onChange={(e) => set({ beneficiary_name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="pay-tax">{t('payments.beneficiaryTaxId')}</Label>
            <Input id="pay-tax" value={form.beneficiary_tax_id} onChange={(e) => set({ beneficiary_tax_id: e.target.value })} />
          </div>
          {form.method === 'pix' ? (
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label>{t('payments.pixKeyType')}</Label>
                <Select value={form.pix_key_type} onValueChange={(v) => set({ pix_key_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PIX_KEY_TYPES.map((k) => (
                      <SelectItem key={k} value={k}>{t(`payments.keyTypes.${k}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="col-span-2 space-y-1">
                <Label htmlFor="pay-key">{t('payments.pixKey')}</Label>
                <Input id="pay-key" value={form.pix_key} onChange={(e) => set({ pix_key: e.target.value })} />
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="pay-bank">{t('payments.bankCode')}</Label>
                <Input id="pay-bank" value={form.bank_code} onChange={(e) => set({ bank_code: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="pay-branch">{t('payments.branch')}</Label>
                <Input id="pay-branch" value={form.branch} onChange={(e) => set({ branch: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="pay-acc">{t('payments.accountNumber')}</Label>
                <Input id="pay-acc" value={form.account_number} onChange={(e) => set({ account_number: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label>{t('payments.accountType')}</Label>
                <Select value={form.account_type} onValueChange={(v) => set({ account_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="checking">{t('payments.checking')}</SelectItem>
                    <SelectItem value="savings">{t('payments.savings')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          <div className="space-y-1">
            <Label>{t('payments.sourceAccount')}</Label>
            <Select
              value={form.source_account_id || 'default'}
              onValueChange={(v) => set({ source_account_id: v === 'default' ? '' : v })}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="default">{t('payments.noSourceAccount')}</SelectItem>
                {accountList.map((a) => (
                  <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="pay-desc">{t('payments.description')}</Label>
            <Input id="pay-desc" value={form.description} onChange={(e) => set({ description: e.target.value })} />
          </div>
          <p className="text-xs text-muted-foreground">{t('payments.createTransaction')}</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={!valid || create.isPending}>{t('payments.create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ApprovalStep({ label, done, userId }: { label: string; done: boolean; userId: string | null }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2 text-sm">
      {done ? <CheckCircle2 size={16} className="text-green-600" /> : <Circle size={16} className="text-muted-foreground" />}
      <span className="font-medium">{label}</span>
      <span className="text-muted-foreground">
        {done ? `${t('payments.approvedBy')} ${userId?.slice(0, 8)}…` : t('payments.pendingApprover')}
      </span>
    </div>
  )
}

function useOrderAction(fn: (id: string) => Promise<PaymentOrder>, toastKey: string, onDone: () => void) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payments'] })
      toast.success(t(`payments.toast.${toastKey}`))
      onDone()
    },
    onError: (err) => toast.error(errorMessage(err, t('common.error', 'Error'))),
  })
}

function DetailDialog({ orderId, onClose }: { orderId: string | null; onClose: () => void }) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const { can } = useWorkspace()
  const { user } = useAuth()
  const [note, setNote] = useState('')

  const { data: order } = useQuery({
    queryKey: ['payments', 'detail', orderId],
    queryFn: () => paymentsApi.get(orderId!),
    enabled: !!orderId,
  })

  const done = () => setNote('')
  const submit = useOrderAction(paymentsApi.submit, 'submitted', done)
  const approve = useOrderAction((id) => paymentsApi.approve(id, note || undefined), 'approved', done)
  const reject = useOrderAction((id) => paymentsApi.reject(id, note || undefined), 'rejected', done)
  const send = useOrderAction(paymentsApi.send, 'sent', done)
  const cancel = useOrderAction(paymentsApi.cancel, 'cancelled', done)
  const check = useOrderAction(paymentsApi.check, 'checked', done)

  const me = user?.id
  const isCreator = !!order && order.created_by_user_id === me
  const involved =
    !!order && [order.created_by_user_id, order.first_approver_id, order.second_approver_id].includes(me ?? '')
  const canApprove =
    !!order &&
    order.status === 'pending_approval' &&
    can('payments.approve') &&
    !isCreator &&
    order.first_approver_id !== me
  const canReject = !!order && order.status === 'pending_approval' && can('payments.approve') && !isCreator
  const canSend = !!order && order.status === 'approved' && can('payments.send') && !involved
  const canCancel = !!order && !['confirmed', 'failed', 'cancelled'].includes(order.status) && can('payments.write')
  const busy = [submit, approve, reject, send, cancel, check].some((m) => m.isPending)

  return (
    <Dialog open={!!orderId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        {order && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {t('payments.details')} <StatusBadge status={order.status} />
              </DialogTitle>
              <DialogDescription>
                {order.method.toUpperCase()} · {formatCurrency(Number(order.amount), order.currency, locale)} · {order.beneficiary_name}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 text-sm">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                {order.method === 'pix' ? (
                  <>
                    <dt className="text-muted-foreground">{t('payments.pixKey')}</dt>
                    <dd>{order.pix_key} ({order.pix_key_type})</dd>
                  </>
                ) : (
                  <>
                    <dt className="text-muted-foreground">{t('payments.bankCode')} / {t('payments.branch')}</dt>
                    <dd>{order.bank_code} / {order.branch}</dd>
                    <dt className="text-muted-foreground">{t('payments.accountNumber')}</dt>
                    <dd>{order.account_number} ({order.account_type})</dd>
                  </>
                )}
                {order.description && (
                  <>
                    <dt className="text-muted-foreground">{t('payments.description')}</dt>
                    <dd>{order.description}</dd>
                  </>
                )}
                <dt className="text-muted-foreground">{t('payments.provider')}</dt>
                <dd>{order.provider}</dd>
                {order.external_id && (
                  <>
                    <dt className="text-muted-foreground">{t('payments.externalId')}</dt>
                    <dd className="truncate">{order.external_id}</dd>
                  </>
                )}
              </dl>

              <div className="space-y-2 rounded-lg border p-3">
                <ApprovalStep label={t('payments.firstApproval')} done={!!order.first_approver_id} userId={order.first_approver_id} />
                <ApprovalStep label={t('payments.secondApproval')} done={!!order.second_approver_id} userId={order.second_approver_id} />
                <div className="flex items-center gap-2 text-sm">
                  {order.sent_by_user_id ? <CheckCircle2 size={16} className="text-green-600" /> : <Circle size={16} className="text-muted-foreground" />}
                  <span className="font-medium">{t('payments.send')}</span>
                  {order.sent_by_user_id && (
                    <span className="text-muted-foreground">{t('payments.sentBy')} {order.sent_by_user_id.slice(0, 8)}…</span>
                  )}
                </div>
                {isCreator && order.status === 'pending_approval' && (
                  <p className="text-xs text-muted-foreground">{t('payments.cannotApproveSelf')}</p>
                )}
                {order.status === 'pending_approval' && order.first_approver_id === me && (
                  <p className="text-xs text-muted-foreground">{t('payments.differentApproverRequired')}</p>
                )}
                {order.status === 'approved' && involved && (
                  <p className="text-xs text-muted-foreground">{t('payments.cannotSend')}</p>
                )}
              </div>

              {order.provider_error && (
                <p className="rounded-md bg-destructive/10 p-2 text-destructive">
                  {t('payments.providerError')}: {order.provider_error}
                </p>
              )}
              {order.receipt_url && (
                <a className="underline" href={order.receipt_url} target="_blank" rel="noreferrer">
                  {t('payments.receipt')}
                </a>
              )}
              {order.provider === 'sandbox' && (
                <p className="text-xs text-muted-foreground">{t('payments.sandboxNotice')}</p>
              )}

              {order.events && order.events.length > 0 && (
                <div>
                  <h3 className="mb-1 font-medium">{t('payments.history')}</h3>
                  <ul className="space-y-1 text-xs text-muted-foreground">
                    {order.events.map((e) => (
                      <li key={e.id}>
                        {e.created_at ? new Date(e.created_at).toLocaleString(locale) : ''} ·{' '}
                        {t(`payments.events.${e.action}`)} · {e.user_id.slice(0, 8)}…{e.note ? ` — ${e.note}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {(canApprove || canReject) && (
                <Input placeholder={t('payments.note')} value={note} onChange={(e) => setNote(e.target.value)} />
              )}
            </div>

            <DialogFooter className="flex-wrap gap-2">
              {order.status === 'draft' && can('payments.write') && (
                <Button disabled={busy} onClick={() => submit.mutate(order.id)}>{t('payments.submit')}</Button>
              )}
              {canApprove && (
                <Button disabled={busy} onClick={() => approve.mutate(order.id)}>{t('payments.approve')}</Button>
              )}
              {canReject && (
                <Button variant="destructive" disabled={busy} onClick={() => reject.mutate(order.id)}>
                  {t('payments.reject')}
                </Button>
              )}
              {canSend && (
                <Button
                  disabled={busy}
                  onClick={() => window.confirm(t('payments.confirmSend')) && send.mutate(order.id)}
                >
                  <Send size={14} /> {t('payments.send')}
                </Button>
              )}
              {order.status === 'sent' && can('payments.write') && (
                <Button variant="outline" disabled={busy} onClick={() => check.mutate(order.id)}>
                  {t('payments.checkStatus')}
                </Button>
              )}
              {canCancel && (
                <Button variant="outline" disabled={busy} onClick={() => cancel.mutate(order.id)}>
                  {t('payments.cancel')}
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default function PaymentsPage() {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const { can } = useWorkspace()
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>('all')
  const [creating, setCreating] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['payments', 'list', status],
    queryFn: () => paymentsApi.list(status === 'all' ? undefined : status),
    enabled: can('payments.read'),
    refetchInterval: 30_000,
  })
  const items = data?.items ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        section={t('payments.orders')}
        title={t('payments.title')}
        action={
          can('payments.write') ? (
            <Button onClick={() => setCreating(true)} className="gap-1.5">
              <Plus size={14} /> {t('payments.create')}
            </Button>
          ) : undefined
        }
      />
      <p className="-mt-4 text-sm text-muted-foreground">{t('payments.subtitle')}</p>

      <div className="flex flex-wrap gap-1.5">
        {STATUS_FILTERS.map((s) => (
          <Button key={s} size="sm" variant={status === s ? 'default' : 'outline'} onClick={() => setStatus(s)}>
            {t(`payments.status.${statusKey(s)}`)}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">{t('common.loading')}</div>
      ) : isError ? (
        <div className="rounded-xl border bg-card p-8 text-center text-sm text-destructive">{t('payments.loadError')}</div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">{t('payments.noOrders')}</div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/30">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">{t('payments.beneficiary')}</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">{t('payments.method')}</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">{t('payments.amount')}</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">{t('common.status', 'Status')}</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">{t('common.date', 'Data')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((o) => (
                <tr
                  key={o.id}
                  className="cursor-pointer border-b transition-colors last:border-0 hover:bg-muted/20"
                  onClick={() => setOpenId(o.id)}
                >
                  <td className="px-4 py-3 font-medium">{o.beneficiary_name}</td>
                  <td className="px-4 py-3">{t(`payments.${o.method}`)}</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums">
                    {formatCurrency(Number(o.amount), o.currency, locale)}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={o.status} /></td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {o.created_at ? new Date(o.created_at).toLocaleDateString(locale) : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CreateDialog open={creating} onClose={() => setCreating(false)} />
      <DetailDialog orderId={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}
