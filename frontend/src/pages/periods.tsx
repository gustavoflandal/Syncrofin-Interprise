import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/contexts/workspace-context'
import { periodClosesApi, type PeriodClose } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Lock, LockOpen } from 'lucide-react'
import { toast } from 'sonner'

function formatPeriod(year: number, month: number, locale: string) {
  return new Date(year, month - 1, 1).toLocaleDateString(locale, {
    month: 'long',
    year: 'numeric',
  })
}

export default function PeriodsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'pt-BR'
  const { current, can } = useWorkspace()
  const workspaceId = current?.id
  const qc = useQueryClient()
  const canManage = can('periods.manage')

  const [closeModal, setCloseModal] = useState<{ year: number; month: number } | null>(null)
  const [reopenModal, setReopenModal] = useState<PeriodClose | null>(null)
  const [reason, setReason] = useState('')

  const { data: closes = [], isLoading } = useQuery({
    queryKey: ['period-closes', workspaceId],
    queryFn: () => periodClosesApi.list(workspaceId!),
    enabled: !!workspaceId,
  })

  const closeMutation = useMutation({
    mutationFn: ({ year, month }: { year: number; month: number }) =>
      periodClosesApi.close(workspaceId!, { year, month, reason: reason || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['period-closes'] })
      setCloseModal(null)
      setReason('')
      toast.success(t('periods.closedSuccess', 'Período fechado com sucesso'))
    },
    onError: () => toast.error(t('common.error', 'Ocorreu um erro')),
  })

  const reopenMutation = useMutation({
    mutationFn: (pc: PeriodClose) =>
      periodClosesApi.reopen(workspaceId!, pc.year, pc.month, reason || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['period-closes'] })
      setReopenModal(null)
      setReason('')
      toast.success(t('periods.reopenedSuccess', 'Período reaberto com sucesso'))
    },
    onError: () => toast.error(t('common.error', 'Ocorreu um erro')),
  })

  // Last 24 months
  const now = new Date()
  const periods = Array.from({ length: 24 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    return { year: d.getFullYear(), month: d.getMonth() + 1 }
  })

  const closedMap = new Map(
    closes
      .filter((c) => c.reopened_at === null)
      .map((c) => [`${c.year}-${c.month}`, c]),
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t('periods.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t('periods.subtitle', 'Gerencie o fechamento de períodos contábeis do workspace.')}
        </p>
      </div>

      <div className="rounded-xl border bg-card overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            {t('common.loading')}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/30">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">
                  {t('common.period', 'Período')}
                </th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">
                  {t('common.status', 'Status')}
                </th>
                {canManage && <th className="px-4 py-3 w-32" aria-label={t('common.actions', 'Ações')} />}
              </tr>
            </thead>
            <tbody>
              {periods.map(({ year, month }) => {
                const key = `${year}-${month}`
                const closed = closedMap.get(key)
                return (
                  <tr key={key} className="border-b last:border-0 hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 font-medium capitalize">
                      {formatPeriod(year, month, locale)}
                    </td>
                    <td className="px-4 py-3">
                      {closed ? (
                        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-destructive bg-destructive/10 rounded-full px-2.5 py-1">
                          <Lock size={11} />
                          {t('periods.closed', 'Fechado')}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 rounded-full px-2.5 py-1">
                          <LockOpen size={11} />
                          {t('periods.open', 'Aberto')}
                        </span>
                      )}
                    </td>
                    {canManage && (
                      <td className="px-4 py-3 text-right">
                        {closed ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-7"
                            onClick={() => {
                              setReopenModal(closed)
                              setReason('')
                            }}
                          >
                            {t('periods.reopen')}
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-xs h-7 text-destructive hover:text-destructive"
                            onClick={() => {
                              setCloseModal({ year, month })
                              setReason('')
                            }}
                          >
                            {t('periods.close')}
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Close modal */}
      <Dialog open={!!closeModal} onOpenChange={(open) => !open && setCloseModal(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {closeModal &&
                t('periods.confirmClose', {
                  month: closeModal.month,
                  year: closeModal.year,
                  defaultValue: `Fechar ${closeModal.month}/${closeModal.year}?`,
                })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label>{t('periods.reason')}</Label>
            <Input
              placeholder={t('periods.reasonPlaceholder', 'Motivo (opcional)')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCloseModal(null)}>
              {t('common.cancel', 'Cancelar')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => closeModal && closeMutation.mutate(closeModal)}
              disabled={closeMutation.isPending}
            >
              {t('periods.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reopen modal */}
      <Dialog open={!!reopenModal} onOpenChange={(open) => !open && setReopenModal(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {reopenModal &&
                t('periods.confirmReopen', {
                  month: reopenModal.month,
                  year: reopenModal.year,
                  defaultValue: `Reabrir ${reopenModal.month}/${reopenModal.year}?`,
                })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label>{t('periods.reason')}</Label>
            <Input
              placeholder={t('periods.reasonPlaceholder', 'Motivo (opcional)')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReopenModal(null)}>
              {t('common.cancel', 'Cancelar')}
            </Button>
            <Button
              onClick={() => reopenModal && reopenMutation.mutate(reopenModal)}
              disabled={reopenMutation.isPending}
            >
              {t('periods.reopen')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
