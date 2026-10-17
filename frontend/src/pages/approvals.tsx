import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/contexts/workspace-context'
import { useAuth } from '@/contexts/auth-context'
import { approvalsApi } from '@/lib/api'
import type { Transaction } from '@/types'
import { formatCurrency } from '@/lib/format'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { CheckCircle, XCircle, Banknote } from 'lucide-react'

function ApprovalRow({
  tx,
  onApprove,
  onReject,
  onSettle,
  isPending,
  currentUserId,
  segregationEnabled,
}: {
  tx: Transaction
  onApprove: (note: string) => void
  onReject: (note: string) => void
  onSettle: (note: string) => void
  isPending: boolean
  currentUserId: string | undefined
  segregationEnabled: boolean
}) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const [note, setNote] = useState('')

  const isCreator = currentUserId === tx.user_id
  const isApproved = tx.approval_status === 'approved'
  const isSettled = !!tx.settled_by_user_id

  return (
    <tr className="border-b last:border-0 hover:bg-muted/20 transition-colors">
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {new Date(tx.date).toLocaleDateString(locale)}
      </td>
      <td className="px-4 py-3 text-sm font-medium max-w-xs truncate">
        <div className="flex items-center gap-2">
          {tx.description}
          {isCreator && segregationEnabled && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {t('segregation.creator')}
            </Badge>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-right font-mono tabular-nums">
        {formatCurrency(tx.amount, tx.currency, locale)}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {isApproved && (
          <Badge variant="secondary" className="text-[10px]">
            {t('approvals.statusApproved')}
          </Badge>
        )}
        {isSettled && tx.settled_at && (
          <Badge variant="outline" className="text-[10px] ml-1">
            {t('segregation.settledBy')}
          </Badge>
        )}
      </td>
      <td className="px-4 py-3">
        <Input
          className="h-7 text-xs min-w-[140px]"
          placeholder={t('approvals.note')}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-1.5 justify-end">
          {tx.approval_status === 'pending' && (
            <>
              <Button
                size="sm"
                className="h-7 text-xs gap-1"
                onClick={() => onApprove(note)}
                disabled={isPending}
              >
                <CheckCircle size={12} />
                {t('approvals.approve')}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                className="h-7 text-xs gap-1"
                onClick={() => onReject(note)}
                disabled={isPending}
              >
                <XCircle size={12} />
                {t('approvals.reject')}
              </Button>
            </>
          )}
          {isApproved && !isSettled && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs gap-1"
              onClick={() => onSettle(note)}
              disabled={isPending}
            >
              <Banknote size={12} />
              {t('segregation.settle')}
            </Button>
          )}
        </div>
      </td>
    </tr>
  )
}

export default function ApprovalsPage() {
  const { t } = useTranslation()
  const { current } = useWorkspace()
  const { user } = useAuth()
  const workspaceId = current?.id
  const qc = useQueryClient()
  const segregationEnabled = !!current?.segregation_enabled

  const { data: pending = [], isLoading } = useQuery({
    queryKey: ['approvals-pending', workspaceId],
    queryFn: () => approvalsApi.listPending(workspaceId!),
    enabled: !!workspaceId,
    refetchInterval: 30_000,
  })

  const approveMutation = useMutation({
    mutationFn: ({ txId, note }: { txId: string; note: string }) =>
      approvalsApi.approve(workspaceId!, txId, note || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approvals-pending'] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      toast.success(t('approvals.approvedSuccess', 'Transação aprovada'))
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : t('common.error', 'Ocorreu um erro')
      toast.error(msg)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ txId, note }: { txId: string; note: string }) =>
      approvalsApi.reject(workspaceId!, txId, note || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approvals-pending'] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      toast.success(t('approvals.rejectedSuccess', 'Transação rejeitada'))
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : t('common.error', 'Ocorreu um erro')
      toast.error(msg)
    },
  })

  const settleMutation = useMutation({
    mutationFn: ({ txId, note }: { txId: string; note: string }) =>
      approvalsApi.settle(workspaceId!, txId, note || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approvals-pending'] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      toast.success(t('segregation.settledSuccess', 'Transação liquidada'))
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : t('common.error', 'Ocorreu um erro')
      toast.error(msg)
    },
  })

  const isBusy = approveMutation.isPending || rejectMutation.isPending || settleMutation.isPending

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t('approvals.title')}</h1>
        {pending.length > 0 && (
          <span className="inline-flex items-center justify-center min-w-[22px] h-[22px] rounded-full bg-destructive text-white text-xs font-bold px-1.5">
            {pending.length}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          {t('common.loading')}
        </div>
      ) : pending.length === 0 ? (
        <div className="rounded-xl border bg-card p-8 text-center text-muted-foreground text-sm">
          {t('approvals.noPending')}
        </div>
      ) : (
        <div className="rounded-xl border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/30">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">
                  {t('common.date', 'Data')}
                </th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">
                  {t('common.description', 'Descrição')}
                </th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">
                  {t('common.amount', 'Valor')}
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  {t('common.status', 'Status')}
                </th>
                <th className="px-4 py-3 font-medium text-muted-foreground">
                  {t('approvals.note')}
                </th>
                <th className="px-4 py-3 w-56" aria-label={t('common.actions', 'Ações')} />
              </tr>
            </thead>
            <tbody>
              {(pending as Transaction[]).map((tx) => (
                <ApprovalRow
                  key={tx.id}
                  tx={tx}
                  onApprove={(note) => approveMutation.mutate({ txId: tx.id, note })}
                  onReject={(note) => rejectMutation.mutate({ txId: tx.id, note })}
                  onSettle={(note) => settleMutation.mutate({ txId: tx.id, note })}
                  isPending={isBusy}
                  currentUserId={user?.id}
                  segregationEnabled={segregationEnabled}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
