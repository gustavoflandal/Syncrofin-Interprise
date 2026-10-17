import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ChevronDown, Plug, Plus, Trash2 } from 'lucide-react'
import { useWorkspace } from '@/contexts/workspace-context'
import {
  erpApi,
  type ErpConnection,
  type ErpEntityType,
  type ErpSyncRun,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const SYNC_OPTIONS: { entity: ErpEntityType; labelKey: string; push: boolean }[] = [
  { entity: 'category', labelKey: 'erp.pullAccounts', push: false },
  { entity: 'payee', labelKey: 'erp.pullPayees', push: false },
  { entity: 'transaction', labelKey: 'erp.pushTransactions', push: true },
  { entity: 'invoice', labelKey: 'erp.pushInvoices', push: true },
]

const SELECT_CLASS =
  'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring'

function StatusBadge({ status }: { status: string | null }) {
  const { t } = useTranslation()
  if (!status) {
    return (
      <Badge variant="secondary" className="text-xs">
        {t('erp.neverSynced')}
      </Badge>
    )
  }
  const label =
    status === 'running'
      ? t('erp.syncRunning')
      : status === 'success'
        ? t('erp.syncSuccess')
        : t('erp.syncError')
  const variant = status === 'success' ? 'default' : status === 'error' ? 'destructive' : 'secondary'
  return (
    <Badge variant={variant} className="text-xs">
      {label}
    </Badge>
  )
}

function HistoryTable({ connectionId, running }: { connectionId: string; running: boolean }) {
  const { t } = useTranslation()
  const { data: runs = [] } = useQuery({
    queryKey: ['erp-history', connectionId],
    queryFn: () => erpApi.history(connectionId),
    // Sync runs in a worker: poll while one is in flight so the table updates itself.
    refetchInterval: running ? 3000 : false,
  })

  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground py-2">{t('erp.noHistory')}</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-1 pr-3 font-medium">{t('erp.started')}</th>
            <th className="py-1 pr-3 font-medium">{t('erp.entity')}</th>
            <th className="py-1 pr-3 font-medium">{t('erp.direction')}</th>
            <th className="py-1 pr-3 font-medium">{t('erp.status')}</th>
            <th className="py-1 pr-3 font-medium text-right">{t('erp.created')}</th>
            <th className="py-1 pr-3 font-medium text-right">{t('erp.updated')}</th>
            <th className="py-1 font-medium text-right">{t('erp.errors')}</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r: ErpSyncRun) => (
            <tr key={r.id} className="border-t align-top">
              <td className="py-1 pr-3 whitespace-nowrap">
                {new Date(r.started_at).toLocaleString()}
              </td>
              <td className="py-1 pr-3">{r.entity_type ? t(`erp.${r.entity_type}`) : '—'}</td>
              <td className="py-1 pr-3">{r.direction ? t(`erp.${r.direction}`) : '—'}</td>
              <td className="py-1 pr-3">
                <StatusBadge status={r.status} />
              </td>
              <td className="py-1 pr-3 text-right">{r.created_count}</td>
              <td className="py-1 pr-3 text-right">{r.updated_count}</td>
              <td className="py-1 text-right" title={r.errors.join('\n')}>
                {r.error_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ConnectionCard({
  conn,
  canManage,
  onDelete,
}: {
  conn: ErpConnection
  canManage: boolean
  onDelete: (c: ErpConnection) => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [entity, setEntity] = useState<ErpEntityType>('category')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const option = SYNC_OPTIONS.find(o => o.entity === entity)!

  const testMutation = useMutation({
    mutationFn: () => erpApi.test(conn.id),
    onSuccess: r =>
      r.ok
        ? toast.success(t('erp.testSuccess'))
        : toast.error(r.message ? `${t('erp.testFailed')}: ${r.message}` : t('erp.testFailed')),
    onError: () => toast.error(t('erp.testFailed')),
  })

  const syncMutation = useMutation({
    mutationFn: () =>
      erpApi.sync(conn.id, {
        entity_type: entity,
        ...(option.push && dateFrom ? { date_from: dateFrom } : {}),
        ...(option.push && dateTo ? { date_to: dateTo } : {}),
      }),
    onSuccess: () => {
      toast.success(t('erp.syncQueued'))
      qc.invalidateQueries({ queryKey: ['erp-connections'] })
      qc.invalidateQueries({ queryKey: ['erp-history', conn.id] })
    },
    onError: () => toast.error(t('common.error')),
  })

  const toggleMutation = useMutation({
    mutationFn: () => erpApi.update(conn.id, { is_active: !conn.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['erp-connections'] }),
    onError: () => toast.error(t('common.error')),
  })

  const providerLabel = t(`erp.${conn.provider}`, conn.provider)
  const comingSoon = conn.provider === 'contaazul'

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Plug className="h-4 w-4 text-muted-foreground shrink-0" />
        <span className="font-semibold">{providerLabel}</span>
        <Badge variant={conn.is_active ? 'default' : 'secondary'} className="text-xs">
          {conn.is_active ? t('erp.active') : t('erp.inactive')}
        </Badge>
        <StatusBadge status={conn.last_sync_status} />
        <span className="text-xs text-muted-foreground flex-1 min-w-[8rem]">
          {t('erp.lastSync')}:{' '}
          {conn.last_sync_at ? new Date(conn.last_sync_at).toLocaleString() : t('erp.neverSynced')}
        </span>
        {canManage && (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
            >
              {t('erp.testConnection')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => toggleMutation.mutate()}
              disabled={toggleMutation.isPending}
            >
              {conn.is_active ? t('erp.inactive') : t('erp.active')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              onClick={() => onDelete(conn)}
              aria-label={t('common.delete')}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </>
        )}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setOpen(v => !v)}
          aria-label={t('erp.syncHistory')}
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        </Button>
      </div>

      {comingSoon && (
        <p className="text-xs text-muted-foreground">{t('erp.contaazulComingSoon')}</p>
      )}
      {conn.last_sync_status === 'error' && conn.last_sync_error && (
        <p className="text-xs text-destructive break-words">{conn.last_sync_error}</p>
      )}

      {canManage && !comingSoon && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1 min-w-[12rem]">
            <Label className="text-xs">{t('erp.sync')}</Label>
            <select
              className={SELECT_CLASS}
              value={entity}
              onChange={e => setEntity(e.target.value as ErpEntityType)}
            >
              {SYNC_OPTIONS.map(o => (
                <option key={o.entity} value={o.entity}>
                  {t(o.labelKey)}
                </option>
              ))}
            </select>
          </div>
          {option.push && (
            <>
              <div className="space-y-1">
                <Label className="text-xs">{t('erp.dateFrom')}</Label>
                <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('erp.dateTo')}</Label>
                <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
              </div>
            </>
          )}
          <Button
            size="sm"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending || !conn.is_active || conn.last_sync_status === 'running'}
          >
            {t('erp.runSync')}
          </Button>
        </div>
      )}

      {open && (
        <div className="pt-1">
          <p className="text-xs font-semibold mb-1">{t('erp.syncHistory')}</p>
          <HistoryTable connectionId={conn.id} running={conn.last_sync_status === 'running'} />
        </div>
      )}
    </div>
  )
}

export default function ErpConnectionsPage() {
  const { t } = useTranslation()
  const { current, can } = useWorkspace()
  const workspaceId = current?.id
  const qc = useQueryClient()
  const canManage = can('erp.manage')

  const [showAdd, setShowAdd] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ErpConnection | null>(null)
  const [provider, setProvider] = useState('omie')
  const [appKey, setAppKey] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [defaultCategory, setDefaultCategory] = useState('')
  const [defaultAccount, setDefaultAccount] = useState('')

  const { data: providers = [] } = useQuery({
    queryKey: ['erp-providers', workspaceId],
    queryFn: erpApi.providers,
    enabled: !!workspaceId,
  })

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['erp-connections', workspaceId],
    queryFn: erpApi.list,
    enabled: !!workspaceId,
    // Keep the status badge fresh while a background sync is running.
    refetchInterval: query =>
      query.state.data?.some(c => c.last_sync_status === 'running') ? 3000 : false,
  })

  function resetForm() {
    setProvider('omie')
    setAppKey('')
    setAppSecret('')
    setDefaultCategory('')
    setDefaultAccount('')
  }

  const createMutation = useMutation({
    mutationFn: () =>
      erpApi.create({
        provider,
        credentials: provider === 'omie' ? { app_key: appKey, app_secret: appSecret } : {},
        sync_config: {
          ...(defaultCategory ? { default_category_code: defaultCategory } : {}),
          ...(defaultAccount ? { default_account_id: defaultAccount } : {}),
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['erp-connections'] })
      setShowAdd(false)
      resetForm()
      toast.success(t('erp.saved'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: (c: ErpConnection) => erpApi.remove(c.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['erp-connections'] })
      setDeleteTarget(null)
      toast.success(t('erp.deleted'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const canSubmit =
    !createMutation.isPending && (provider !== 'omie' || (appKey.trim() && appSecret.trim()))

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t('erp.title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('erp.description')}</p>
        </div>
        {canManage && (
          <Button onClick={() => setShowAdd(true)}>
            <Plus className="h-4 w-4 mr-1" />
            {t('erp.addConnection')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : connections.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('erp.noConnections')}</p>
      ) : (
        <div className="space-y-3">
          {connections.map(c => (
            <ConnectionCard key={c.id} conn={c} canManage={canManage} onDelete={setDeleteTarget} />
          ))}
        </div>
      )}

      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('erp.addConnection')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>{t('erp.provider')}</Label>
              <select
                className={SELECT_CLASS}
                value={provider}
                onChange={e => setProvider(e.target.value)}
              >
                {providers.map(p => (
                  <option key={p.key} value={p.key}>
                    {t(`erp.${p.key}`, p.key)}
                    {p.available ? '' : ` (${t('erp.contaazulComingSoon')})`}
                  </option>
                ))}
              </select>
            </div>
            {provider === 'omie' ? (
              <div className="space-y-3">
                <p className="text-xs font-semibold">{t('erp.credentials')}</p>
                <div className="space-y-1">
                  <Label>{t('erp.appKey')}</Label>
                  <Input
                    value={appKey}
                    onChange={e => setAppKey(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="space-y-1">
                  <Label>{t('erp.appSecret')}</Label>
                  <Input
                    type="password"
                    value={appSecret}
                    onChange={e => setAppSecret(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="space-y-1">
                  <Label>{t('erp.defaultCategory')}</Label>
                  <Input
                    value={defaultCategory}
                    onChange={e => setDefaultCategory(e.target.value)}
                    placeholder="1.01.01"
                  />
                </div>
                <div className="space-y-1">
                  <Label>{t('erp.defaultAccount')}</Label>
                  <Input
                    inputMode="numeric"
                    value={defaultAccount}
                    onChange={e => setDefaultAccount(e.target.value.replace(/\D/g, ''))}
                  />
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t('erp.contaazulComingSoon')}</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => createMutation.mutate()} disabled={!canSubmit}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={v => !v && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('common.delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('erp.deleteConfirm')}</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
              disabled={deleteMutation.isPending}
            >
              {t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
