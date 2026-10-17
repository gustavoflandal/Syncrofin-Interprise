import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Globe, Plus, Send, Trash2, Pencil } from 'lucide-react'
import { webhooks as webhooksApi, type WebhookRead, type WebhookCreate, type WebhookUpdate } from '@/lib/api'
import { useWorkspace } from '@/contexts/workspace-context'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const WEBHOOKS_KEY = ['webhooks'] as const
const EVENT_TYPES_KEY = ['webhook-event-types'] as const

type FormState = {
  url: string
  secret: string
  eventTypes: string[]
  active: boolean
}

const EMPTY_FORM: FormState = { url: '', secret: '', eventTypes: [], active: true }

function fromRead(wh: WebhookRead): FormState {
  return {
    url: wh.url,
    secret: '',
    eventTypes: wh.event_types ?? [],
    active: wh.active,
  }
}

export function WebhooksCard() {
  const { t } = useTranslation()
  const { canManage } = useWorkspace()
  const qc = useQueryClient()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<WebhookRead | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)

  const { data: eventTypes = [] } = useQuery({
    queryKey: EVENT_TYPES_KEY,
    queryFn: webhooksApi.eventTypes,
    staleTime: Infinity,
  })

  const { data: list = [], isLoading } = useQuery({
    queryKey: WEBHOOKS_KEY,
    queryFn: webhooksApi.list,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: WEBHOOKS_KEY })

  const createMut = useMutation({
    mutationFn: (p: WebhookCreate) => webhooksApi.create(p),
    onSuccess: () => { invalidate(); closeDialog(); toast.success(t('webhooks.created')) },
    onError: () => toast.error(t('common.error')),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, p }: { id: string; p: WebhookUpdate }) => webhooksApi.update(id, p),
    onSuccess: () => { invalidate(); closeDialog(); toast.success(t('webhooks.updated')) },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => webhooksApi.remove(id),
    onSuccess: () => { invalidate(); toast.success(t('webhooks.deleted')) },
    onError: () => toast.error(t('common.error')),
  })

  const testMut = useMutation({
    mutationFn: (id: string) => webhooksApi.test(id),
    onSuccess: () => toast.success(t('webhooks.testScheduled')),
    onError: () => toast.error(t('common.error')),
  })

  function openCreate() {
    setEditing(null)
    setForm(EMPTY_FORM)
    setDialogOpen(true)
  }

  function openEdit(wh: WebhookRead) {
    setEditing(wh)
    setForm(fromRead(wh))
    setDialogOpen(true)
  }

  function closeDialog() {
    setDialogOpen(false)
    setEditing(null)
    setForm(EMPTY_FORM)
  }

  function toggleEventType(et: string) {
    setForm((f) => ({
      ...f,
      eventTypes: f.eventTypes.includes(et)
        ? f.eventTypes.filter((x) => x !== et)
        : [...f.eventTypes, et],
    }))
  }

  function handleSubmit() {
    if (!form.url.trim()) return
    if (editing) {
      const p: WebhookUpdate = {
        url: form.url.trim(),
        event_types: form.eventTypes.length ? form.eventTypes : null,
        active: form.active,
      }
      if (form.secret) p.secret = form.secret
      updateMut.mutate({ id: editing.id, p })
    } else {
      const p: WebhookCreate = {
        url: form.url.trim(),
        event_types: form.eventTypes.length ? form.eventTypes : null,
      }
      if (form.secret) p.secret = form.secret
      createMut.mutate(p)
    }
  }

  const busy = createMut.isPending || updateMut.isPending

  return (
    <section className="space-y-4 rounded-xl border bg-card p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">{t('webhooks.title')}</h2>
          <Badge variant="outline" className="text-[11px]">{list.length}</Badge>
        </div>
        {canManage && (
          <Button size="sm" variant="outline" className="rounded-lg" onClick={openCreate}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {t('webhooks.add')}
          </Button>
        )}
      </div>

      <p className="text-[13px] text-muted-foreground">{t('webhooks.description')}</p>

      {isLoading && (
        <div className="text-[13px] text-muted-foreground animate-pulse">{t('common.loading')}</div>
      )}

      {!isLoading && list.length === 0 && (
        <p className="text-[13px] text-muted-foreground">{t('webhooks.empty')}</p>
      )}

      <ul className="space-y-2">
        {list.map((wh) => (
          <li key={wh.id} className="flex items-center gap-3 rounded-lg border bg-muted/20 px-4 py-3">
            <div className="min-w-0 flex-1 space-y-0.5">
              <p className="text-[13px] font-medium break-all">{wh.url}</p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {wh.active
                  ? <Badge variant="outline" className="text-[10px] text-emerald-600 border-emerald-300">{t('webhooks.active')}</Badge>
                  : <Badge variant="outline" className="text-[10px] text-muted-foreground">{t('webhooks.inactive')}</Badge>
                }
                {wh.has_secret && (
                  <Badge variant="outline" className="text-[10px]">{t('webhooks.hasSecret')}</Badge>
                )}
                {wh.last_status_code != null && (
                  <Badge
                    variant="outline"
                    className={`text-[10px] ${wh.last_status_code >= 200 && wh.last_status_code < 300 ? 'text-emerald-600 border-emerald-300' : 'text-destructive border-destructive/40'}`}
                  >
                    {wh.last_status_code}
                  </Badge>
                )}
              </div>
              {wh.event_types && wh.event_types.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {wh.event_types.map((et) => (
                    <span key={et} className="text-[10px] font-mono bg-muted rounded px-1.5 py-0.5">{et}</span>
                  ))}
                </div>
              )}
            </div>
            {canManage && (
              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost" size="icon"
                  className="h-8 w-8 text-muted-foreground"
                  disabled={testMut.isPending}
                  title={t('webhooks.testButton')}
                  onClick={() => testMut.mutate(wh.id)}
                >
                  <Send className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost" size="icon"
                  className="h-8 w-8 text-muted-foreground"
                  onClick={() => openEdit(wh)}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost" size="icon"
                  className="h-8 w-8 text-destructive hover:bg-destructive/10"
                  disabled={deleteMut.isPending}
                  onClick={() => deleteMut.mutate(wh.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {/* Create / Edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={(v) => !v && closeDialog()}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? t('webhooks.editTitle') : t('webhooks.createTitle')}</DialogTitle>
            <DialogDescription>{t('webhooks.formDesc')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="wh-url" className="text-[13px]">{t('webhooks.urlLabel')}</Label>
              <Input
                id="wh-url"
                placeholder="https://example.com/hook"
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="wh-secret" className="text-[13px]">
                {t('webhooks.secretLabel')}
                {editing?.has_secret && (
                  <span className="ml-1 text-[11px] text-muted-foreground">({t('webhooks.secretKeep')})</span>
                )}
              </Label>
              <Input
                id="wh-secret"
                type="password"
                placeholder={editing?.has_secret ? '••••••••' : t('webhooks.secretPlaceholder')}
                value={form.secret}
                onChange={(e) => setForm((f) => ({ ...f, secret: e.target.value }))}
              />
            </div>

            {eventTypes.length > 0 && (
              <div className="space-y-2">
                <Label className="text-[13px]">{t('webhooks.eventTypesLabel')}</Label>
                <p className="text-[11px] text-muted-foreground">{t('webhooks.eventTypesHint')}</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {eventTypes.map((et) => (
                    <label key={et} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded"
                        checked={form.eventTypes.includes(et)}
                        onChange={() => toggleEventType(et)}
                      />
                      <span className="text-[12px] font-mono">{et}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {editing && (
              <div className="flex items-center gap-3">
                <Switch
                  id="wh-active"
                  checked={form.active}
                  onCheckedChange={(v) => setForm((f) => ({ ...f, active: v }))}
                />
                <Label htmlFor="wh-active" className="text-[13px]">{t('webhooks.activeLabel')}</Label>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeDialog}>{t('common.cancel')}</Button>
            <Button onClick={handleSubmit} disabled={busy || !form.url.trim()}>
              {busy ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
