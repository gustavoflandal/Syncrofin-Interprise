import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/contexts/workspace-context'
import {
  webhooksApi,
  type WebhookEndpoint,
  type WebhookDelivery,
  type WebhookEndpointCreate,
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
import { Webhook, ChevronDown, Plus, Trash2, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'

const ALL_EVENTS = [
  'transaction.created',
  'transaction.updated',
  'transaction.deleted',
  'invoice.paid',
  'sync.completed',
  'sync.failed',
  'period.closed',
  'period.reopened',
] as const

type EventKey = (typeof ALL_EVENTS)[number]

function eventLabel(event: string, t: (k: string, fb: string) => string): string {
  const map: Record<string, string> = {
    'transaction.created': t('webhooks.eventTransactionCreated', 'Transaction created'),
    'transaction.updated': t('webhooks.eventTransactionUpdated', 'Transaction updated'),
    'transaction.deleted': t('webhooks.eventTransactionDeleted', 'Transaction deleted'),
    'invoice.paid': t('webhooks.eventInvoicePaid', 'Invoice paid'),
    'sync.completed': t('webhooks.eventSyncCompleted', 'Sync completed'),
    'sync.failed': t('webhooks.eventSyncFailed', 'Sync failed'),
    'period.closed': t('webhooks.eventPeriodClosed', 'Period closed'),
    'period.reopened': t('webhooks.eventPeriodReopened', 'Period reopened'),
  }
  return map[event] ?? event
}

function DeliveriesList({ wsId, epId }: { wsId: string; epId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data: deliveries = [] } = useQuery({
    queryKey: ['webhook-deliveries', wsId, epId],
    queryFn: () => webhooksApi.listDeliveries(wsId, epId),
  })

  const redeliverMutation = useMutation({
    mutationFn: (deliveryId: string) => webhooksApi.redeliver(wsId, epId, deliveryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhook-deliveries', wsId, epId] })
      toast.success(t('webhooks.redeliver', 'Redeliver') + ' OK')
    },
    onError: () => toast.error(t('common.error', 'Error')),
  })

  if (deliveries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-2">
        {t('webhooks.noDeliveries', 'No deliveries recorded')}
      </p>
    )
  }

  return (
    <div className="space-y-1 mt-2">
      {deliveries.map((d: WebhookDelivery) => (
        <div key={d.id} className="flex items-center gap-2 text-xs border rounded px-2 py-1">
          <Badge
            variant={d.delivered_at ? 'default' : 'destructive'}
            className="text-[10px] px-1"
          >
            {d.http_status ?? '—'}
          </Badge>
          <span className="font-mono flex-1 truncate">{d.event_type}</span>
          <span className="text-muted-foreground">
            {t('webhooks.attemptCount', 'Attempts: {{count}}', { count: d.attempt_count })}
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="h-5 px-1"
            onClick={() => redeliverMutation.mutate(d.id)}
            disabled={redeliverMutation.isPending}
          >
            <RotateCcw className="h-3 w-3" />
          </Button>
        </div>
      ))}
    </div>
  )
}

function EndpointRow({
  ep,
  wsId,
  canManage,
  onDelete,
}: {
  ep: WebhookEndpoint
  wsId: string
  canManage: boolean
  onDelete: (ep: WebhookEndpoint) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()

  const toggleMutation = useMutation({
    mutationFn: () => webhooksApi.update(wsId, ep.id, { is_active: !ep.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['webhook-endpoints', wsId] }),
    onError: () => toast.error(t('common.error', 'Error')),
  })

  return (
    <div className="border rounded-lg p-3">
      <div className="flex items-center gap-2">
        <Webhook className="h-4 w-4 text-muted-foreground shrink-0" />
        <span className="font-mono text-sm flex-1 truncate">{ep.url}</span>
        <Badge variant={ep.is_active ? 'default' : 'secondary'} className="text-xs">
          {ep.is_active ? t('webhooks.isActive', 'Active') : t('webhooks.inactive', 'Inactive')}
        </Badge>
        {canManage && (
          <>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs"
              onClick={() => toggleMutation.mutate()}
              disabled={toggleMutation.isPending}
            >
              {ep.is_active
                ? t('webhooks.inactive', 'Inactive')
                : t('webhooks.isActive', 'Active')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-destructive hover:text-destructive"
              onClick={() => onDelete(ep)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-1"
          onClick={() => setOpen(v => !v)}
        >
          <ChevronDown
            className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </Button>
      </div>

      {open && (
        <div className="mt-2 pl-6">
          <p className="text-xs text-muted-foreground mb-1">
            {ep.events.length === 0
              ? t('webhooks.allEvents', 'All events')
              : ep.events.map(e => eventLabel(e, t)).join(', ')}
          </p>
          <p className="text-xs font-semibold mt-2 mb-1">
            {t('webhooks.deliveries', 'Deliveries')}
          </p>
          <DeliveriesList wsId={wsId} epId={ep.id} />
        </div>
      )}
    </div>
  )
}

export default function WebhooksPage() {
  const { t } = useTranslation()
  const { current, can } = useWorkspace()
  const workspaceId = current?.id
  const qc = useQueryClient()
  const canManage = can('webhooks.manage')

  const [showAdd, setShowAdd] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WebhookEndpoint | null>(null)
  const [form, setForm] = useState<WebhookEndpointCreate>({ url: '', secret: '', events: [] })

  const { data: endpoints = [], isLoading } = useQuery({
    queryKey: ['webhook-endpoints', workspaceId],
    queryFn: () => webhooksApi.list(workspaceId!),
    enabled: !!workspaceId,
  })

  const createMutation = useMutation({
    mutationFn: (data: WebhookEndpointCreate) =>
      webhooksApi.create(workspaceId!, {
        ...data,
        secret: data.secret || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhook-endpoints', workspaceId] })
      setShowAdd(false)
      setForm({ url: '', secret: '', events: [] })
      toast.success(t('common.saved', 'Saved'))
    },
    onError: () => toast.error(t('common.error', 'Error')),
  })

  const deleteMutation = useMutation({
    mutationFn: (ep: WebhookEndpoint) => webhooksApi.delete(workspaceId!, ep.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhook-endpoints', workspaceId] })
      setDeleteTarget(null)
      toast.success(t('common.deleted', 'Deleted'))
    },
    onError: () => toast.error(t('common.error', 'Error')),
  })

  function toggleEvent(event: EventKey) {
    setForm(f => ({
      ...f,
      events: f.events.includes(event)
        ? f.events.filter(e => e !== event)
        : [...f.events, event],
    }))
  }

  return (
    <div className="max-w-2xl mx-auto py-8 px-4 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('webhooks.title', 'Webhooks')}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t(
              'webhooks.description',
              'Receive real-time notifications when events occur in this workspace.',
            )}
          </p>
        </div>
        {canManage && (
          <Button onClick={() => setShowAdd(true)}>
            <Plus className="h-4 w-4 mr-1" />
            {t('webhooks.addEndpoint', 'Add endpoint')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading', 'Loading...')}</p>
      ) : endpoints.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('webhooks.noEndpoints', 'No webhooks configured')}</p>
      ) : (
        <div className="space-y-2">
          {endpoints.map(ep => (
            <EndpointRow
              key={ep.id}
              ep={ep}
              wsId={workspaceId!}
              canManage={canManage}
              onDelete={setDeleteTarget}
            />
          ))}
        </div>
      )}

      {/* Add endpoint dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('webhooks.addEndpoint', 'Add endpoint')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>{t('webhooks.url', 'Endpoint URL')}</Label>
              <Input
                value={form.url}
                onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/hook"
                type="url"
              />
            </div>
            <div className="space-y-1">
              <Label>{t('webhooks.secret', 'HMAC secret (optional)')}</Label>
              <Input
                value={form.secret}
                onChange={e => setForm(f => ({ ...f, secret: e.target.value }))}
                placeholder={t('webhooks.secretPlaceholder', 'Leave blank to skip signing')}
                type="password"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label>
                {t('webhooks.events', 'Events')}
                <span className="ml-2 text-xs text-muted-foreground">
                  ({form.events.length === 0
                    ? t('webhooks.allEvents', 'All events')
                    : `${form.events.length} selected`})
                </span>
              </Label>
              <div className="grid grid-cols-2 gap-1">
                {ALL_EVENTS.map(ev => (
                  <label
                    key={ev}
                    className="flex items-center gap-2 text-sm cursor-pointer select-none"
                  >
                    <input
                      type="checkbox"
                      checked={form.events.includes(ev)}
                      onChange={() => toggleEvent(ev)}
                      className="accent-primary"
                    />
                    {eventLabel(ev, t)}
                  </label>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button
              onClick={() => createMutation.mutate(form)}
              disabled={!form.url || createMutation.isPending}
            >
              {t('common.save', 'Save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={v => !v && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('webhooks.deleteEndpoint', 'Remove endpoint')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t('webhooks.confirmDelete', 'Remove the webhook for {{url}}?', {
              url: deleteTarget?.url ?? '',
            })}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
              disabled={deleteMutation.isPending}
            >
              {t('common.delete', 'Delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
