import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Copy, KeyRound, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { apiTokens as apiTokensApi, roles as rolesApi } from '@/lib/api'
import { useDateLocale } from '@/hooks/use-display-locale'
import { useWorkspace } from '@/contexts/workspace-context'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { ApiTokenInfo, PermissionInfo } from '@/types'

const TOKENS_KEY = ['api-tokens'] as const
const DURATIONS = [30, 90, 180, 365]
const GROUPS: PermissionInfo['group'][] = ['data', 'reports']

type ApiError = { response?: { data?: { detail?: string } } }

/** A person-readable reason for a refusal from the tokens API. */
function useMessage() {
  const { t } = useTranslation()
  return (error: ApiError) => {
    const detail = error.response?.data?.detail ?? ''
    if (/cannot do yourself/i.test(detail)) return t('apiTokens.errorBeyondYou')
    if (/at most/i.test(detail)) return t('apiTokens.errorTooMany')
    return t('common.error')
  }
}

/** The secret, once. There is no other way to see it again, which the dialog says plainly. */
function SecretDialog({ secret, onClose }: { secret: string; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('apiTokens.secretTitle')}</DialogTitle>
          <DialogDescription>{t('apiTokens.secretBody')}</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <code
            data-testid="api-token-secret"
            className="min-w-0 flex-1 break-all rounded-lg border bg-muted/40 px-3 py-2 text-xs"
          >
            {secret}
          </code>
          <Button
            variant="outline"
            size="icon"
            title={t('apiTokens.copy')}
            onClick={() => {
              void navigator.clipboard?.writeText(secret)
              toast.success(t('apiTokens.copied'))
            }}
          >
            <Copy className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t('apiTokens.secretHowTo')}</p>
        <DialogFooter>
          <Button onClick={onClose}>{t('apiTokens.savedIt')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CreateDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (secret: string) => void }) {
  const { t } = useTranslation()
  const { can } = useWorkspace()
  const queryClient = useQueryClient()
  const message = useMessage()
  const catalog = useQuery({ queryKey: ['roles', 'catalog'], queryFn: rolesApi.catalog })
  const [name, setName] = useState('')
  const [days, setDays] = useState(90)
  const [chosen, setChosen] = useState<Set<string>>(new Set())

  // What a token can be given: the catalog without administration, and only what this person can do themselves.
  const available = (catalog.data?.permissions ?? []).filter((p) => p.group !== 'admin' && can(p.key))

  const create = useMutation({
    mutationFn: () => apiTokensApi.create({ name, scopes: [...chosen], days }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: TOKENS_KEY })
      onCreated(created.token)
    },
    onError: (error: ApiError) => toast.error(message(error)),
  })

  const toggle = (key: string) =>
    setChosen((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('apiTokens.newTitle')}</DialogTitle>
          <DialogDescription>{t('apiTokens.newBody')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="token-name" className="text-[13px]">
              {t('apiTokens.name')}
            </Label>
            <Input
              id="token-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              placeholder={t('apiTokens.namePlaceholder')}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="token-days" className="text-[13px]">
              {t('apiTokens.duration')}
            </Label>
            <select
              id="token-days"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-10 w-full rounded-lg border border-input bg-transparent px-3 text-sm"
            >
              {DURATIONS.map((d) => (
                <option key={d} value={d}>
                  {t('apiTokens.days', { count: d })}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-muted-foreground">{t('apiTokens.durationHint')}</p>
          </div>
          <div className="space-y-3">
            <p className="text-[13px] font-medium">{t('apiTokens.scopes')}</p>
            <p className="text-xs text-muted-foreground">{t('apiTokens.scopesHint')}</p>
            {GROUPS.map((group) => {
              const items = available.filter((p) => p.group === group)
              if (items.length === 0) return null
              return (
                <fieldset key={group} className="rounded-lg border border-border/60 p-3">
                  <legend className="px-1 text-xs font-semibold text-muted-foreground">{t(`roles.groups.${group}`)}</legend>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {items.map((p) => (
                      <label key={p.key} className="flex items-start gap-2 text-sm">
                        <input type="checkbox" className="mt-1" checked={chosen.has(p.key)} onChange={() => toggle(p.key)} />
                        <span>{t(`permissions.${p.key}`)}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              )
            })}
          </div>
        </div>
        <DialogFooter className="mt-2">
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => create.mutate()} disabled={!name.trim() || chosen.size === 0 || create.isPending}>
            {create.isPending ? t('common.loading') : t('apiTokens.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** The workspace's API tokens: make, rotate, revoke. Shown to whoever holds `tokens.manage`. */
export function ApiTokensCard() {
  const { t } = useTranslation()
  const locale = useDateLocale()
  const queryClient = useQueryClient()
  const message = useMessage()
  const tokens = useQuery({ queryKey: TOKENS_KEY, queryFn: apiTokensApi.list })
  const [creating, setCreating] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<{ id: string; kind: 'rotate' | 'revoke' } | null>(null)

  const done = () => {
    setConfirm(null)
    void queryClient.invalidateQueries({ queryKey: TOKENS_KEY })
  }
  const revoke = useMutation({
    mutationFn: (id: string) => apiTokensApi.revoke(id),
    onSuccess: () => {
      done()
      toast.success(t('apiTokens.revoked'))
    },
    onError: (error: ApiError) => toast.error(message(error)),
  })
  const rotate = useMutation({
    mutationFn: (id: string) => apiTokensApi.rotate(id),
    onSuccess: (created) => {
      done()
      setSecret(created.token)
    },
    onError: (error: ApiError) => toast.error(message(error)),
  })

  const date = (iso: string) => new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(iso))
  const items: ApiTokenInfo[] = tokens.data ?? []

  return (
    <section className="space-y-4 rounded-xl border bg-card p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            {t('apiTokens.title')}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('apiTokens.intro')}</p>
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t('apiTokens.new')}
        </Button>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('apiTokens.none')}</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {items.map((token) => (
            <li key={token.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <span className="truncate">{token.name}</span>
                  <Badge variant={token.state === 'active' ? 'secondary' : 'outline'} className="text-[10px]">
                    {t(`apiTokens.states.${token.state}`)}
                  </Badge>
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  <code>{token.prefix}…</code> · {t('apiTokens.scopeCount', { count: token.scopes.length })} ·{' '}
                  {t('apiTokens.expires', { date: date(token.expires_at) })} ·{' '}
                  {token.last_used_at ? t('apiTokens.usedOn', { date: date(token.last_used_at) }) : t('apiTokens.neverUsed')}
                </p>
              </div>
              {token.state === 'active' &&
                (confirm?.id === token.id ? (
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={rotate.isPending || revoke.isPending}
                    onClick={() => (confirm.kind === 'rotate' ? rotate.mutate(token.id) : revoke.mutate(token.id))}
                  >
                    {confirm.kind === 'rotate' ? t('apiTokens.confirmRotate') : t('apiTokens.confirmRevoke')}
                  </Button>
                ) : (
                  <>
                    <Button
                      variant="ghost"
                      size="icon"
                      title={t('apiTokens.rotate')}
                      onClick={() => setConfirm({ id: token.id, kind: 'rotate' })}
                      className="rounded-lg"
                    >
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title={t('apiTokens.revoke')}
                      onClick={() => setConfirm({ id: token.id, kind: 'revoke' })}
                      className="rounded-lg"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </>
                ))}
            </li>
          ))}
        </ul>
      )}

      {creating && (
        <CreateDialog
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false)
            setSecret(created)
          }}
        />
      )}
      {secret && <SecretDialog secret={secret} onClose={() => setSecret(null)} />}
    </section>
  )
}
