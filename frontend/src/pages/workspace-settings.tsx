import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/hooks/use-display-locale'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { auth as authApi, currencies as currenciesApi, fiscal as fiscalApi, fiscalEmissionsApi, billingApi, reconciliationAuto, dataRetention, roles as rolesApi, workspaces as workspacesApi, approvalRulesApi, categoryGroups as categoryGroupsApi, type ApprovalRule, type FiscalProviderConfig, type BillingProviderConfig, type PurgeResult } from '@/lib/api'
import { useAuth } from '@/contexts/auth-context'
import { useWorkspace } from '@/contexts/workspace-context'
import { useLocalAuthEnabled } from '@/hooks/use-local-auth'
import { useFeatureFlags } from '@/hooks/use-feature-flags'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { IconPicker } from '@/components/icon-picker'
import { CategoryIcon } from '@/components/category-icon'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { AlertTriangle, Archive, Bot, Clock, Database, FileText, Image, Plus, Save, Shield, ShieldCheck, Trash2, Users, Wand2, CreditCard } from 'lucide-react'
import { WORKSPACE_KIND_LABEL_KEY } from '@/lib/workspace-kinds'
import { roleHint, roleLabel } from '@/lib/roles'
import { RolesCard, ROLES_KEY } from '@/components/roles-card'
import { ApiTokensCard } from '@/components/api-tokens-card'
import { WebhooksCard } from '@/components/webhooks-card'
import { SUPPORTED_LANGS } from '@/lib/i18n'
import { countryFlag } from '@/lib/country-flag'
import { countryName } from '@/lib/country-name'
import type { Workspace, WorkspaceKind, WorkspaceMember, WorkspaceRole } from '@/types'

function formatDate(iso: string, locale: string): string {
  try {
    return new Date(iso).toLocaleDateString(locale, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return iso.slice(0, 10)
  }
}

const DEFAULT_WORKSPACE_COLOR = '#6366F1'
const DEFAULT_WORKSPACE_ICON = 'briefcase'

export default function WorkspaceSettingsPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const localeForFormat = useDateLocale()
  const { current, canManage, can, workspaces: allWorkspaces, refresh, switchWorkspace } = useWorkspace()
  // The roles a member can be given here: the built-in three, and the workspace's own.
  const rolesQuery = useQuery({ queryKey: ROLES_KEY, queryFn: rolesApi.list })
  const assignableRoles = (rolesQuery.data ?? []).map((r) => r.key)
  if (assignableRoles.length === 0) assignableRoles.push('owner', 'editor', 'viewer')
  const { user: currentUser, updateUser } = useAuth()
  const queryClient = useQueryClient()

  const [editName, setEditName] = useState('')
  const [editCurrency, setEditCurrency] = useState('')
  const [editLocale, setEditLocale] = useState('')
  const [editJurisdiction, setEditJurisdiction] = useState('')
  const [editIcon, setEditIcon] = useState(DEFAULT_WORKSPACE_ICON)
  const [editColor, setEditColor] = useState(DEFAULT_WORKSPACE_COLOR)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitePassword, setInvitePassword] = useState('')
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>('editor')
  const [removeTarget, setRemoveTarget] = useState<WorkspaceMember | null>(null)
  const [archiveOpen, setArchiveOpen] = useState(false)

  const formKey = JSON.stringify([current?.id, current?.name, current?.default_currency, current?.locale, current?.tax_jurisdiction, current?.icon, current?.color])
  const [previousFormKey, setPreviousFormKey] = useState<string | null>(null)
  if (formKey !== previousFormKey) {
    setPreviousFormKey(formKey)
    if (current) {
      setEditName(current.name)
      setEditCurrency(current.default_currency)
      setEditLocale(current.locale ?? '')
      setEditJurisdiction(current.tax_jurisdiction ?? '')
      setEditIcon(current.icon ?? DEFAULT_WORKSPACE_ICON)
      setEditColor(current.color ?? DEFAULT_WORKSPACE_COLOR)
    }
  }

  // Which jurisdictions ship a pack. An empty choice is valid, not missing:
  // with none set, documents are stored as free text with no mask.
  const { data: jurisdictions } = useQuery({
    queryKey: ['fiscal-jurisdictions'],
    queryFn: fiscalApi.jurisdictions,
    staleTime: Infinity,
  })

  const membersQuery = useQuery({
    queryKey: ['workspace-members', current?.id],
    queryFn: () => (current ? workspacesApi.listMembers(current.id) : Promise.resolve([])),
    enabled: !!current,
  })

  const { data: supportedCurrencies } = useQuery({
    queryKey: ['currencies'],
    queryFn: currenciesApi.list,
    staleTime: Infinity,
  })

  const localAuthEnabled = useLocalAuthEnabled()
  const { emailEnabled } = useFeatureFlags()

  // The server lists codes; the user reads names. Sorted by the name actually
  // shown, in the reader's own collation.
  const sortedJurisdictions = useMemo(
    () =>
      [...(jurisdictions ?? [])].sort((a, b) =>
        countryName(a, i18n.language).localeCompare(countryName(b, i18n.language), i18n.language),
      ),
    [jurisdictions, i18n.language],
  )

  const statsQuery = useQuery({
    queryKey: ['workspace-stats', current?.id],
    queryFn: () => (current ? workspacesApi.stats(current.id) : Promise.resolve({ members: 0, accounts: 0, transactions: 0 })),
    enabled: !!current,
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.update(current.id, {
        name: editName,
        default_currency: editCurrency,
        locale: editLocale || (null as unknown as string),
        tax_jurisdiction: editJurisdiction || null,
        icon: editIcon,
        color: editColor,
      })
    },
    onSuccess: () => {
      toast.success(t('workspace.saveSuccess'))
      void refresh()
      // Changing the workspace currency also updates the acting user's
      // display currency server-side; refresh the cached user so the
      // whole app re-renders in the new currency, then drop currency-
      // dependent queries.
      void authApi.me().then(updateUser).catch(() => {})
      void queryClient.invalidateQueries()
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : t('workspace.saveError'))
      toast.error(detail)
    },
  })

  // Reconciliation automation: how sure the engine must be before it accepts a
  // suggestion on its own. Saved on change (one control, one decision), and
  // separate from the form above so it never rides along with an unrelated edit.
  const autoApplyMutation = useMutation({
    mutationFn: (score: number | null) => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.update(current.id, { reconciliation_auto_apply_score: score })
    },
    onSuccess: () => {
      toast.success(t('workspace.autoApply.saved'))
      void refresh()
    },
    onError: () => toast.error(t('workspace.saveError')),
  })
  const autoApplyRunMutation = useMutation({
    mutationFn: reconciliationAuto.run,
    onSuccess: ({ applied }) => {
      toast.success(t('workspace.autoApply.ran', { count: applied }))
      void queryClient.invalidateQueries({ queryKey: ['reconciliation'] })
    },
    onError: () => toast.error(t('workspace.autoApply.runError')),
  })

  const archiveMutation = useMutation({
    mutationFn: () => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.archive(current.id)
    },
    onSuccess: async () => {
      toast.success(t('workspace.archiveSuccess', 'Workspace arquivado'))
      setArchiveOpen(false)
      await refresh()
      // Switch into another accessible workspace, then redirect home.
      const remaining = allWorkspaces.filter((w) => w.id !== current?.id)
      if (remaining.length > 0) {
        await switchWorkspace(remaining[0].id)
      }
      navigate('/')
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : 'Failed')
      toast.error(detail)
    },
  })

  const inviteMutation = useMutation({
    mutationFn: () => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.invite(current.id, {
        email: inviteEmail.trim(),
        role: inviteRole,
        password: localAuthEnabled ? (invitePassword || undefined) : undefined,
      })
    },
    onSuccess: (member) => {
      // Say what actually happened: an invitation that was e-mailed, or one
      // the owner still has to pass on.
      if (member.invitation_email_sent) toast.success(t('workspace.inviteSentByEmail', { email: member.email }))
      else if (!invitePassword) toast.warning(t('workspace.inviteNotEmailed', { email: member.email }))
      else toast.success(t('workspace.addSuccess'))
      setInviteOpen(false)
      setInviteEmail('')
      setInvitePassword('')
      setInviteRole('editor')
      queryClient.invalidateQueries({ queryKey: ['workspace-members', current?.id] })
      queryClient.invalidateQueries({ queryKey: ['workspace-stats', current?.id] })
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : 'Failed')
      toast.error(detail)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (member: WorkspaceMember) => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.removeMember(current.id, member.user_id)
    },
    onSuccess: () => {
      toast.success(t('workspace.removeSuccess'))
      setRemoveTarget(null)
      queryClient.invalidateQueries({ queryKey: ['workspace-members', current?.id] })
      queryClient.invalidateQueries({ queryKey: ['workspace-stats', current?.id] })
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : 'Failed')
      toast.error(detail)
    },
  })

  const roleChangeMutation = useMutation({
    mutationFn: ({ member, role }: { member: WorkspaceMember; role: WorkspaceRole }) => {
      if (!current) throw new Error('No workspace')
      return workspacesApi.changeRole(current.id, member.user_id, role)
    },
    onSuccess: () => {
      toast.success(t('workspace.roleUpdated'))
      queryClient.invalidateQueries({ queryKey: ['workspace-members', current?.id] })
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : 'Failed')
      toast.error(detail)
    },
  })

  if (!current) {
    return (
      <div className="container max-w-5xl py-8 space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  const members = membersQuery.data ?? []
  const stats = statsQuery.data ?? { members: 1, accounts: 0, transactions: 0 }
  const isManaged = !!current.managed_by_user_id
  const isManagerSelf = isManaged && current.managed_by_user_id === currentUser?.id
  const kindLabelKey = WORKSPACE_KIND_LABEL_KEY[current.kind as WorkspaceKind]

  return (
    <div className="container max-w-5xl py-8 space-y-6">
      {/* Header card — identity + role + stats strip */}
      <section className="rounded-xl border bg-card overflow-hidden">
        <div className="p-6 flex items-center gap-5 border-b">
          <CategoryIcon
            icon={current.icon ?? DEFAULT_WORKSPACE_ICON}
            color={current.color ?? DEFAULT_WORKSPACE_COLOR}
            size="lg"
            className="shrink-0"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-semibold truncate">{current.name}</h1>
              {/* Fixed at creation, so it reads as identity, not a control. */}
              {kindLabelKey && (
                <Badge variant="outline" className="text-[11px]">
                  {t(kindLabelKey)}
                </Badge>
              )}
              {current.role && (
                <Badge variant="secondary" className="text-[11px]">
                  {roleLabel(current.role, rolesQuery.data, t)}
                </Badge>
              )}
              {isManaged && (
                <Badge variant="outline" className="text-[11px]">
                  {isManagerSelf
                    ? t('workspace.youManageThis')
                    : t('workspace.externallyManaged')}
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {t('workspace.settingsDescription')}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-border">
          <StatTile label={t('workspace.members')} value={String(stats.members)} />
          <StatTile label={t('workspace.statAccounts', 'Contas')} value={String(stats.accounts)} />
          <StatTile label={t('workspace.statTransactions', 'Transações')} value={String(stats.transactions)} />
          <StatTile label={t('workspace.statCreatedAt', 'Criado em')} value={formatDate(current.created_at, localeForFormat)} />
        </div>
      </section>

      {can('audit.read') && (
        <section className="flex items-center justify-between gap-4 rounded-xl border bg-card p-4">
          <div>
            <h2 className="text-base font-semibold">{t('audit.title')}</h2>
            <p className="text-sm text-muted-foreground">{t('audit.openFromSettingsHint')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/workspace/audit')}>
            {t('audit.openFromSettings')}
          </Button>
        </section>
      )}

      {can('periods.manage') && (
        <section className="flex items-center justify-between gap-4 rounded-xl border bg-card p-4">
          <div>
            <h2 className="text-base font-semibold">{t('periods.title')}</h2>
            <p className="text-sm text-muted-foreground">
              {t('periods.settingsHint', 'Feche e reabra meses contábeis para bloquear lançamentos retroativos.')}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/workspace/periods')}>
            {t('periods.manage', 'Gerenciar períodos')}
          </Button>
        </section>
      )}

      {can('approvals.approve') && (
        <section className="flex items-center justify-between gap-4 rounded-xl border bg-card p-4">
          <div>
            <h2 className="text-base font-semibold">{t('approvals.title')}</h2>
            <p className="text-sm text-muted-foreground">
              {t('approvals.settingsHint', 'Aprove ou rejeite transações que aguardam análise por alçada.')}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/workspace/approvals')}>
            {t('approvals.manage', 'Fila de aprovações')}
          </Button>
        </section>
      )}

      {can('webhooks.manage') && (
        <section className="flex items-center justify-between gap-4 rounded-xl border bg-card p-4">
          <div>
            <h2 className="text-base font-semibold">{t('webhooks.title', 'Webhooks')}</h2>
            <p className="text-sm text-muted-foreground">
              {t('webhooks.description', 'Receive real-time notifications when events occur in this workspace.')}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/workspace/webhooks')}>
            {t('webhooks.title', 'Webhooks')}
          </Button>
        </section>
      )}

      {(can('erp.manage') || can('erp.read')) && (
        <section className="flex items-center justify-between gap-4 rounded-xl border bg-card p-4">
          <div>
            <h2 className="text-base font-semibold">{t('erp.title')}</h2>
            <p className="text-sm text-muted-foreground">{t('erp.description')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/workspace/erp')}>
            {t('erp.title')}
          </Button>
        </section>
      )}

      {/* Details card — 4-column form */}
      <section className="space-y-4 rounded-xl border bg-card p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{t('workspace.details')}</h2>
          {canManage && (
            <Button
              onClick={() => updateMutation.mutate()}
              disabled={updateMutation.isPending}
              className="rounded-lg"
              size="sm"
            >
              <Save className="mr-2 h-4 w-4" />
              {updateMutation.isPending ? t('common.loading') : t('common.save')}
            </Button>
          )}
        </div>
        <div className="space-y-4">
          {/* Identity row — icon button + color swatch align with the
              input (not the label) so the label sits over the name
              field only. */}
          <div className="flex items-end gap-2">
            {canManage ? (
              <>
                <div className="space-y-1.5">
                  <Label className="text-[13px]">
                    {t('workspace.icon', 'Ícone')}
                  </Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <button
                        type="button"
                        className="h-10 w-10 rounded-lg border border-input flex items-center justify-center hover:bg-muted/40 transition-colors shrink-0"
                        title={t('workspace.icon', 'Ícone')}
                      >
                        <CategoryIcon icon={editIcon} color={editColor} size="sm" />
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className="w-80 p-3" align="start">
                      <IconPicker value={editIcon} color={editColor} onChange={setEditIcon} />
                    </PopoverContent>
                  </Popover>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ws-color" className="text-[13px]">
                    {t('groups.color', 'Cor')}
                  </Label>
                  <input
                    id="ws-color"
                    type="color"
                    value={editColor}
                    onChange={(e) => setEditColor(e.target.value)}
                    className="h-10 w-10 p-1 rounded-lg cursor-pointer border border-input bg-card shrink-0"
                    title={t('groups.color', 'Cor')}
                  />
                </div>
              </>
            ) : (
              <div className="h-10 w-10 rounded-lg flex items-center justify-center shrink-0">
                <CategoryIcon icon={editIcon} color={editColor} size="sm" />
              </div>
            )}
            <div className="space-y-1.5 flex-1">
              <Label htmlFor="ws-name" className="text-[13px]">
                {t('workspace.name')}
              </Label>
              <Input
                id="ws-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                disabled={!canManage}
                maxLength={100}
                className="h-10 rounded-lg w-full"
              />
            </div>
          </div>

          {/* Logo upload — brand reports (G2) */}
          {canManage && (
            <div className="flex items-center gap-4 py-2">
              <div className="flex items-center gap-3">
                {current?.logo_storage_key ? (
                  <img
                    src={`/api/workspaces/${current.id}/logo?t=${Date.now()}`}
                    alt={t('workspace.logo')}
                    className="h-10 w-auto max-w-[120px] rounded border border-border object-contain"
                  />
                ) : (
                  <div className="h-10 w-10 rounded border border-dashed border-border flex items-center justify-center">
                    <Image className="h-4 w-4 text-muted-foreground" />
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <Label className="text-[13px]">{t('workspace.logo')}</Label>
                <p className="text-[11px] text-muted-foreground">{t('workspace.logoHint')}</p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-lg"
                  onClick={() => {
                    const input = document.createElement('input')
                    input.type = 'file'
                    input.accept = 'image/png,image/jpeg,image/webp'
                    input.onchange = async () => {
                      const file = input.files?.[0]
                      if (!file) return
                      if (file.size > 2 * 1024 * 1024) {
                        toast.error(t('workspace.logoMaxSize'))
                        return
                      }
                      try {
                        await workspacesApi.uploadLogo(current!.id, file)
                        toast.success(t('workspace.logoUploaded'))
                        void refresh()
                      } catch {
                        toast.error(t('workspace.logoError'))
                      }
                    }
                    input.click()
                  }}
                >
                  {t('workspace.uploadLogo')}
                </Button>
                {current?.logo_storage_key && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="rounded-lg text-destructive hover:text-destructive"
                    onClick={async () => {
                      try {
                        await workspacesApi.deleteLogo(current.id)
                        toast.success(t('workspace.logoRemoved'))
                        void refresh()
                      } catch {
                        toast.error(t('workspace.logoError'))
                      }
                    }}
                  >
                    <Trash2 className="mr-1 h-3.5 w-3.5" />
                    {t('workspace.removeLogo')}
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Region row — currency, language, and where the workspace files */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="ws-currency" className="text-[13px]">
                {t('workspace.defaultCurrency')}
              </Label>
              <Select
                value={editCurrency}
                onValueChange={setEditCurrency}
                disabled={!canManage}
              >
                <SelectTrigger id="ws-currency" className="h-10 rounded-lg w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(supportedCurrencies ?? [{ code: editCurrency, symbol: editCurrency, name: editCurrency, flag: '' }]).map((c) => (
                    <SelectItem key={c.code} value={c.code}>
                      <span className="mr-2">{c.flag}</span>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ws-locale" className="text-[13px]">
                {t('workspace.locale')}
              </Label>
              <Select
                value={editLocale || '__none__'}
                onValueChange={(v) => setEditLocale(v === '__none__' ? '' : v)}
                disabled={!canManage}
              >
                <SelectTrigger id="ws-locale" className="h-10 rounded-lg w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {SUPPORTED_LANGS.map(({ code, label }) => (
                    <SelectItem key={code} value={code}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ws-jurisdiction" className="text-[13px]">
                {t('workspace.taxJurisdiction', 'Tax jurisdiction')}
              </Label>
              <Select
                value={editJurisdiction || '__none__'}
                onValueChange={(v) => setEditJurisdiction(v === '__none__' ? '' : v)}
                disabled={!canManage}
              >
                <SelectTrigger id="ws-jurisdiction" className="h-10 rounded-lg w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {sortedJurisdictions.map((code) => (
                    <SelectItem key={code} value={code}>
                      <span className="mr-2">{countryFlag(code)}</span>
                      {countryName(code, i18n.language)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                {t(
                  'workspace.taxJurisdictionHint',
                  'Decides which fiscal documents this workspace is offered. Separate from the interface language.',
                )}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Reconciliation automation — only where matching exists (invoices module) */}
      {canManage && current?.enabled_modules.includes('invoices') && (
        <section className="space-y-4 rounded-xl border bg-card p-6" data-testid="auto-apply-section">
          <div className="flex items-center gap-2">
            <Wand2 size={16} className="text-primary" />
            <h2 className="text-sm font-semibold">{t('workspace.autoApply.title')}</h2>
          </div>
          <p className="text-[13px] text-muted-foreground leading-relaxed">
            {t('workspace.autoApply.description')}
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ws-auto-apply" className="text-[13px]">
                {t('workspace.autoApply.threshold')}
              </Label>
              <Select
                value={current.reconciliation_auto_apply_score == null ? 'off' : String(current.reconciliation_auto_apply_score)}
                onValueChange={(v) => autoApplyMutation.mutate(v === 'off' ? null : Number(v))}
                disabled={autoApplyMutation.isPending}
              >
                <SelectTrigger id="ws-auto-apply" className="h-10 rounded-lg w-56">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="off">{t('workspace.autoApply.off')}</SelectItem>
                  <SelectItem value="0.99">{t('workspace.autoApply.veryStrict')}</SelectItem>
                  <SelectItem value="0.95">{t('workspace.autoApply.strict')}</SelectItem>
                  <SelectItem value="0.9">{t('workspace.autoApply.balanced')}</SelectItem>
                  <SelectItem value="0.8">{t('workspace.autoApply.permissive')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={current.reconciliation_auto_apply_score == null || autoApplyRunMutation.isPending}
              onClick={() => autoApplyRunMutation.mutate()}
            >
              {t('workspace.autoApply.runNow')}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {t('workspace.autoApply.safeguards')}
          </p>
        </section>
      )}

      {/* Fechamento & Aprovações */}
      {canManage && <PeriodApprovalSection workspaceId={current?.id ?? ''} current={current} />}

      {/* MFA por workspace (C5) */}
      {canManage && current && (
        <section className="space-y-4 rounded-xl border bg-card p-6">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">{t('common.security', 'Segurança')}</h2>
          </div>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <Label className="text-[13px] font-medium">{t('workspace.mfaRequired')}</Label>
              <p className="text-xs text-muted-foreground max-w-prose">{t('workspace.mfaRequiredDescription')}</p>
            </div>
            <Switch
              checked={!!current.mfa_required}
              onCheckedChange={(checked) =>
                workspacesApi.update(current.id, { mfa_required: checked }).then(() =>
                  queryClient.invalidateQueries({ queryKey: ['workspaces'] })
                )
              }
            />
          </div>
        </section>
      )}

      {/* Segregação de funções (C3) */}
      {canManage && current && (
        <section className="space-y-4 rounded-xl border bg-card p-6">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">{t('segregation.title')}</h2>
          </div>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <Label className="text-[13px] font-medium">{t('segregation.enabled')}</Label>
              <p className="text-xs text-muted-foreground max-w-prose">{t('segregation.description')}</p>
            </div>
            <Switch
              checked={!!current.segregation_enabled}
              onCheckedChange={(checked) =>
                workspacesApi.update(current.id, { segregation_enabled: checked }).then(() =>
                  queryClient.invalidateQueries({ queryKey: ['workspaces'] })
                )
              }
            />
          </div>
        </section>
      )}

      {/* Política de IA por workspace (D6) */}
      {canManage && current && (
        <section className="space-y-4 rounded-xl border bg-card p-6">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">{t('workspace.aiPolicy')}</h2>
          </div>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <Label className="text-[13px] font-medium">{t('workspace.agentsEnabled')}</Label>
              <p className="text-xs text-muted-foreground max-w-prose">{t('workspace.agentsEnabledDescription')}</p>
            </div>
            <Switch
              checked={current.agents_enabled !== false}
              onCheckedChange={(checked) =>
                workspacesApi.update(current.id, { agents_enabled: checked }).then(() =>
                  queryClient.invalidateQueries({ queryKey: ['workspaces'] })
                )
              }
            />
          </div>
          {current.agents_enabled !== false && (
            <div className="space-y-3 border-t pt-3">
              <p className="text-xs font-medium text-muted-foreground">{t('workspace.aiDataPolicy')}</p>
              {(
                [
                  ['allow_identity', t('workspace.aiPolicyIdentity')],
                  ['allow_balances', t('workspace.aiPolicyBalances')],
                  ['allow_transactions', t('workspace.aiPolicyTransactions')],
                  ['allow_payees', t('workspace.aiPolicyPayees')],
                  ['allow_invoices', t('workspace.aiPolicyInvoices')],
                ] as const
              ).map(([key, label]) => {
                const policy = current.agent_data_policy ?? {}
                const allowed = policy[key] !== false
                return (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-[13px]">{label}</span>
                    <Switch
                      checked={allowed}
                      onCheckedChange={(checked) => {
                        const next = { ...(current.agent_data_policy ?? {}), [key]: checked }
                        workspacesApi.update(current.id, { agent_data_policy: next }).then(() =>
                          queryClient.invalidateQueries({ queryKey: ['workspaces'] })
                        )
                      }}
                    />
                  </div>
                )
              })}
            </div>
          )}
        </section>
      )}

      {/* Members card */}
      <section className="space-y-4 rounded-xl border bg-card p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">{t('workspace.members')}</h2>
            <Badge variant="outline" className="text-[11px]">
              {members.length}
            </Badge>
          </div>
          {canManage && (
            <Button onClick={() => setInviteOpen(true)} size="sm" className="rounded-lg">
              <Plus className="mr-2 h-4 w-4" />
              {t('workspace.addMember')}
            </Button>
          )}
        </div>

        {membersQuery.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : members.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t('workspace.noMembers')} {canManage && t('workspace.noMembersHint')}
          </p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {members.map((m) => {
              const isMe = m.user_id === currentUser?.id
              return (
                <li
                  key={m.id}
                  className="py-3 px-4 flex items-center gap-3 hover:bg-muted/30 transition-colors"
                >
                  <Avatar className="h-9 w-9">
                    <AvatarFallback className="bg-primary/15 text-primary text-xs font-semibold">
                      {(m.display_name || m.email).slice(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {m.display_name || m.email}
                      {isMe && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({t('workspace.you')})
                        </span>
                      )}
                    </p>
                    {m.display_name && (
                      <p className="text-xs text-muted-foreground truncate">{m.email}</p>
                    )}
                  </div>
                  {canManage && !isMe ? (
                    <select
                      value={m.role}
                      onChange={(e) =>
                        roleChangeMutation.mutate({
                          member: m,
                          role: e.target.value as WorkspaceRole,
                        })
                      }
                      className="h-9 w-32 rounded-lg border border-input bg-card px-2 text-sm"
                    >
                      {[...assignableRoles, ...(assignableRoles.includes(m.role) ? [] : [m.role])].map((r) => (
                        <option key={r} value={r}>
                          {roleLabel(r, rolesQuery.data, t)}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Badge variant="secondary" className="text-[11px]">
                      {roleLabel(m.role, rolesQuery.data, t)}
                    </Badge>
                  )}
                  {canManage && !isMe && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setRemoveTarget(m)}
                      title={t('workspace.remove')}
                      className="rounded-lg"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {can('roles.manage') && rolesQuery.data && <RolesCard roles={rolesQuery.data} />}

      {can('tokens.manage') && <ApiTokensCard />}

      {canManage && <WebhooksCard />}

      {can('fiscal.admin') && current && <FiscalConfigSection workspaceId={current.id} />}

      {can('billing.manage') && current && <BillingConfigSection workspaceId={current.id} />}

      {/* Retenção de dados (D2) */}
      {canManage && current && <DataRetentionSection />}

      {/* Danger zone — owners only */}
      {canManage && (
        <section className="space-y-4 rounded-xl border bg-card p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">
                {t('workspace.dangerZone', 'Zona de perigo')}
              </h2>
            </div>
          </div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">
                {t('workspace.archiveAction', 'Arquivar workspace')}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {t(
                  'workspace.archiveHint',
                  'O workspace fica oculto da lista e do switcher. Os dados continuam preservados.',
                )}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="rounded-lg text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setArchiveOpen(true)}
            >
              <Archive className="mr-2 h-4 w-4" />
              {t('workspace.archive', 'Arquivar')}
            </Button>
          </div>
        </section>
      )}

      {/* Invite dialog */}
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('workspace.addMemberTitle')}</DialogTitle>
            <DialogDescription>
              {t(
                localAuthEnabled
                  ? 'workspace.addMemberDescription'
                  : 'workspace.addMemberDescriptionExistingOnly',
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="invite-email" className="text-[13px]">
                {t('admin.users.email', 'Email')}
              </Label>
              <Input
                id="invite-email"
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                autoFocus
                className="h-10 rounded-lg"
                placeholder="user@example.com"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="invite-role" className="text-[13px]">
                {t('workspace.role')}
              </Label>
              <select
                id="invite-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}
                className="w-full h-10 rounded-lg border border-input bg-card px-3 text-sm"
              >
                {assignableRoles.map((r) => (
                  <option key={r} value={r}>
                    {roleLabel(r, rolesQuery.data, t)}
                    {roleHint(r, rolesQuery.data, t) ? ` — ${roleHint(r, rolesQuery.data, t)}` : ''}
                  </option>
                ))}
              </select>
            </div>
            {localAuthEnabled && (
              <div className="space-y-1.5">
                <Label htmlFor="invite-password" className="text-[13px]">
                  {t('workspace.passwordForNewUsers')}
                </Label>
                <Input
                  id="invite-password"
                  type="password"
                  value={invitePassword}
                  onChange={(e) => setInvitePassword(e.target.value)}
                  className="h-10 rounded-lg"
                  placeholder=""
                />
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  {emailEnabled ? t('workspace.passwordHintEmail') : t('workspace.passwordHint')}
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setInviteOpen(false)}
              className="rounded-lg"
            >
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => inviteMutation.mutate()}
              disabled={inviteMutation.isPending || !inviteEmail.trim()}
              className="rounded-lg"
            >
              {inviteMutation.isPending ? t('common.loading') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Remove member dialog */}
      <Dialog
        open={!!removeTarget}
        onOpenChange={(open) => !open && setRemoveTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('workspace.removeConfirmTitle')}</DialogTitle>
            <DialogDescription>
              {t('workspace.removeConfirmDescription', { email: removeTarget?.email })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRemoveTarget(null)}
              className="rounded-lg"
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => removeTarget && removeMutation.mutate(removeTarget)}
              disabled={removeMutation.isPending}
              className="rounded-lg"
            >
              {removeMutation.isPending ? t('common.loading') : t('workspace.remove')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Archive workspace dialog */}
      <Dialog open={archiveOpen} onOpenChange={setArchiveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('workspace.archiveConfirmTitle', 'Arquivar workspace?')}
            </DialogTitle>
            <DialogDescription>
              {t(
                'workspace.archiveConfirmDescription',
                'O workspace "{{name}}" será removido da sua lista. Os dados ficam preservados e um admin pode restaurar mais tarde.',
                { name: current.name },
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setArchiveOpen(false)}
              className="rounded-lg"
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => archiveMutation.mutate()}
              disabled={archiveMutation.isPending}
              className="rounded-lg"
            >
              <Archive className="mr-2 h-4 w-4" />
              {archiveMutation.isPending ? t('common.loading') : t('workspace.archive', 'Arquivar')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function DataRetentionSection() {
  const { t } = useTranslation()
  const localeForFormat = useDateLocale()
  const queryClient = useQueryClient()
  const [purgeOpen, setPurgeOpen] = useState(false)

  const policyQuery = useQuery({
    queryKey: ['data-retention'],
    queryFn: dataRetention.get,
  })

  const policy = policyQuery.data
  const [txDays, setTxDays] = useState(2555)
  const [attDays, setAttDays] = useState(1825)
  const [auditDays, setAuditDays] = useState(3650)
  const [anonymize, setAnonymize] = useState(true)

  // Sync form when data loads
  const formKey = JSON.stringify([policy?.transaction_retention_days, policy?.attachment_retention_days, policy?.audit_retention_days, policy?.anonymize_on_expiry])
  const [prevFormKey, setPrevFormKey] = useState<string | null>(null)
  if (formKey !== prevFormKey && policy) {
    setPrevFormKey(formKey)
    setTxDays(policy.transaction_retention_days)
    setAttDays(policy.attachment_retention_days)
    setAuditDays(policy.audit_retention_days)
    setAnonymize(policy.anonymize_on_expiry)
  }

  const updateMutation = useMutation({
    mutationFn: () =>
      dataRetention.update({
        transaction_retention_days: txDays,
        attachment_retention_days: attDays,
        audit_retention_days: auditDays,
        anonymize_on_expiry: anonymize,
      }),
    onSuccess: () => {
      toast.success(t('common.saved', 'Salvo'))
      queryClient.invalidateQueries({ queryKey: ['data-retention'] })
    },
    onError: () => toast.error(t('common.error', 'Ocorreu um erro')),
  })

  const purgeMutation = useMutation({
    mutationFn: dataRetention.purge,
    onSuccess: (result: PurgeResult) => {
      toast.success(
        t('dataRetention.purgeResult', {
          transactions: result.transactions_anonymized,
          attachments: result.attachments_deleted,
          audit: result.audit_anonymized,
        }),
      )
      setPurgeOpen(false)
      queryClient.invalidateQueries({ queryKey: ['data-retention'] })
    },
    onError: () => toast.error(t('common.error', 'Ocorreu um erro')),
  })

  return (
    <>
      <section className="space-y-4 rounded-xl border bg-card p-6">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">{t('dataRetention.title')}</h2>
        </div>
        <p className="text-sm text-muted-foreground">{t('dataRetention.description')}</p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="ret-tx" className="text-[13px]">
              {t('dataRetention.transactionDays')}
            </Label>
            <Input
              id="ret-tx"
              type="number"
              min={365}
              value={txDays}
              onChange={(e) => setTxDays(Math.max(365, Number(e.target.value)))}
              className="h-9 text-sm"
            />
            <p className="text-[11px] text-muted-foreground">{t('dataRetention.minDays', { min: 365 })}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ret-att" className="text-[13px]">
              {t('dataRetention.attachmentDays')}
            </Label>
            <Input
              id="ret-att"
              type="number"
              min={365}
              value={attDays}
              onChange={(e) => setAttDays(Math.max(365, Number(e.target.value)))}
              className="h-9 text-sm"
            />
            <p className="text-[11px] text-muted-foreground">{t('dataRetention.minDays', { min: 365 })}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ret-audit" className="text-[13px]">
              {t('dataRetention.auditDays')}
            </Label>
            <Input
              id="ret-audit"
              type="number"
              min={365}
              value={auditDays}
              onChange={(e) => setAuditDays(Math.max(365, Number(e.target.value)))}
              className="h-9 text-sm"
            />
            <p className="text-[11px] text-muted-foreground">{t('dataRetention.minDays', { min: 365 })}</p>
          </div>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <Label className="text-[13px] font-medium">{t('dataRetention.anonymize')}</Label>
            <p className="text-xs text-muted-foreground max-w-prose">{t('dataRetention.anonymizeDesc')}</p>
          </div>
          <Switch checked={anonymize} onCheckedChange={setAnonymize} />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            <span>
              {t('dataRetention.lastPurge')}:{' '}
              {policy?.last_purge_at
                ? formatDate(policy.last_purge_at, localeForFormat)
                : t('dataRetention.never')}
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPurgeOpen(true)}
            >
              {t('dataRetention.purgeNow')}
            </Button>
            <Button
              size="sm"
              onClick={() => updateMutation.mutate()}
              disabled={updateMutation.isPending}
            >
              <Save className="mr-2 h-3.5 w-3.5" />
              {updateMutation.isPending ? t('common.loading') : t('common.save')}
            </Button>
          </div>
        </div>
      </section>

      {/* Purge confirmation dialog */}
      <Dialog open={purgeOpen} onOpenChange={setPurgeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('dataRetention.purgeNow')}</DialogTitle>
            <DialogDescription>{t('dataRetention.purgeConfirm')}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPurgeOpen(false)} className="rounded-lg">
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => purgeMutation.mutate()}
              disabled={purgeMutation.isPending}
              className="rounded-lg"
            >
              {purgeMutation.isPending ? t('common.loading') : t('dataRetention.purgeNow')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-6 py-4">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold mt-1">{value}</p>
    </div>
  )
}

function PeriodApprovalSection({
  workspaceId,
  current,
}: {
  workspaceId: string
  current: Workspace | null
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  // Period close settings
  const [periodCloseBy, setPeriodCloseBy] = useState(current?.period_close_by ?? 'date')
  const [syncMode, setSyncMode] = useState(current?.period_close_sync_mode ?? 'reject')
  const periodSettingsMutation = useMutation({
    mutationFn: () =>
      workspacesApi.update(workspaceId, {
        period_close_by: periodCloseBy,
        period_close_sync_mode: syncMode,
      }),
    onSuccess: () => toast.success(t('common.saved', 'Salvo')),
    onError: () => toast.error(t('common.error', 'Ocorreu um erro')),
  })

  // Approval rules
  const { data: rules = [] } = useQuery({
    queryKey: ['approval-rules', workspaceId],
    queryFn: () => approvalRulesApi.list(workspaceId),
    enabled: !!workspaceId,
  })
  const { data: categoryGroupsList = [] } = useQuery({
    queryKey: ['category-groups'],
    queryFn: () => categoryGroupsApi.list(),
  })
  const [newThreshold, setNewThreshold] = useState('')
  const [newGroupId, setNewGroupId] = useState('')
  const createRuleMutation = useMutation({
    mutationFn: () =>
      approvalRulesApi.create(workspaceId, {
        amount_threshold: newThreshold,
        currency: current?.default_currency ?? 'BRL',
        ...(newGroupId ? { category_group_id: newGroupId } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-rules'] })
      setNewThreshold('')
      setNewGroupId('')
    },
    onError: () => toast.error(t('common.error', 'Ocorreu um erro')),
  })
  const deleteRuleMutation = useMutation({
    mutationFn: (ruleId: string) => approvalRulesApi.delete(workspaceId, ruleId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-rules'] }),
    onError: () => toast.error(t('common.error', 'Ocorreu um erro')),
  })

  return (
    <section className="space-y-6 rounded-xl border bg-card p-6">
      <h2 className="text-base font-semibold">
        {t('workspace.closureApprovals', 'Fechamento & Aprovações')}
      </h2>

      {/* Period close settings */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          {t('periods.title')}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-[13px]">
              {t('workspace.periodCloseBy', 'Campo de data para fechamento')}
            </Label>
            <Select value={periodCloseBy} onValueChange={setPeriodCloseBy}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="date">
                  {t('workspace.periodCloseByDate', 'Data do lançamento')}
                </SelectItem>
                <SelectItem value="effective_date">
                  {t('workspace.periodCloseByEffective', 'Data efetiva')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-[13px]">
              {t('workspace.periodSyncMode', 'Sync bancário em período fechado')}
            </Label>
            <Select value={syncMode} onValueChange={setSyncMode}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="reject">
                  {t('workspace.syncModeReject', 'Rejeitar')}
                </SelectItem>
                <SelectItem value="pending_review">
                  {t('workspace.syncModePendingReview', 'Revisão pendente')}
                </SelectItem>
                <SelectItem value="allow">
                  {t('workspace.syncModeAllow', 'Permitir')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <Button
          size="sm"
          onClick={() => periodSettingsMutation.mutate()}
          disabled={periodSettingsMutation.isPending}
        >
          <Save className="mr-2 h-3.5 w-3.5" />
          {t('common.save')}
        </Button>
      </div>

      {/* Approval rules */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          {t('approvals.rules')}
        </h3>
        {rules.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t('approvals.noRules', 'Nenhuma regra de alçada configurada.')}
          </p>
        ) : (
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 border-b">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    {t('approvals.ruleGroup')}
                  </th>
                  <th className="text-right px-4 py-2 font-medium text-muted-foreground">
                    {t('approvals.threshold')}
                  </th>
                  <th className="px-4 py-2 w-12" aria-label={t('common.actions', 'Ações')} />
                </tr>
              </thead>
              <tbody>
                {(rules as ApprovalRule[]).map((rule) => {
                  const groupName = rule.category_group_id
                    ? (categoryGroupsList as { id: string; name: string }[]).find(g => g.id === rule.category_group_id)?.name ?? rule.category_group_id
                    : t('approvals.ruleGlobal')
                  return (
                    <tr key={rule.id} className="border-b last:border-0 hover:bg-muted/20">
                      <td className="px-4 py-2">{groupName}</td>
                      <td className="px-4 py-2 text-right font-mono tabular-nums">
                        {rule.amount_threshold} {rule.currency}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <button
                          className="text-muted-foreground hover:text-destructive transition-colors"
                          onClick={() => deleteRuleMutation.mutate(rule.id)}
                          disabled={deleteRuleMutation.isPending}
                          title={t('approvals.deleteRule')}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Add rule form */}
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-[12px]">{t('approvals.ruleGroup')}</Label>
            <select
              className="border border-border rounded-md px-3 py-2 text-sm bg-card h-9 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
              value={newGroupId}
              onChange={(e) => setNewGroupId(e.target.value)}
            >
              <option value="">{t('approvals.ruleGlobal')}</option>
              {(categoryGroupsList as { id: string; name: string }[]).map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label className="text-[12px]">{t('approvals.threshold')}</Label>
            <Input
              type="number"
              min="0.01"
              step="0.01"
              className="h-9 w-36"
              placeholder="0.00"
              value={newThreshold}
              onChange={(e) => setNewThreshold(e.target.value)}
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => createRuleMutation.mutate()}
            disabled={!newThreshold || createRuleMutation.isPending}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {t('approvals.addRule')}
          </Button>
        </div>
      </div>
    </section>
  )
}

function BillingConfigSection({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const configQuery = useQuery<BillingProviderConfig | null>({
    queryKey: ['billing-config', workspaceId],
    queryFn: () => billingApi.getConfig(workspaceId).catch(() => null),
  })

  const cfg = configQuery.data

  const [provider, setProvider] = useState('asaas')
  const [environment, setEnvironment] = useState('sandbox')
  const [apiKey, setApiKey] = useState('')

  const [synced, setSynced] = useState(false)
  if (cfg && !synced) {
    setProvider(cfg.provider)
    setEnvironment(cfg.environment)
    setSynced(true)
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      billingApi.saveConfig(workspaceId, { provider, api_key: apiKey, environment }),
    onSuccess: () => {
      toast.success(t('billing.saved'))
      qc.invalidateQueries({ queryKey: ['billing-config', workspaceId] })
      setApiKey('')
      setSynced(false)
    },
  })

  return (
    <section className="space-y-4 rounded-xl border bg-card p-6">
      <div className="flex items-center gap-2">
        <CreditCard className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-base font-semibold">{t('billing.settingsTitle')}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{t('billing.settingsDescription')}</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-[13px]">{t('billing.provider')}</Label>
          <Select value={provider} onValueChange={setProvider}>
            <SelectTrigger className="h-9 text-sm">
              <SelectValue placeholder={t('billing.provider')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="asaas">{t('billing.providerAsaas')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-[13px]">{t('billing.environment')}</Label>
          <Select value={environment} onValueChange={setEnvironment}>
            <SelectTrigger className="h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sandbox">{t('billing.envSandbox')}</SelectItem>
              <SelectItem value="production">{t('billing.envProduction')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label className="text-[13px]">{t('billing.apiKey')}</Label>
          <Input
            className="h-9 text-sm font-mono"
            type="password"
            placeholder={cfg?.has_api_key ? t('billing.apiKeyConfigured') : t('billing.apiKeyPlaceholder')}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>
        {cfg?.webhook_token && (
          <div className="space-y-1.5 sm:col-span-2">
            <Label className="text-[13px]">{t('billing.webhookToken')}</Label>
            <Input
              className="h-9 text-sm font-mono"
              readOnly
              value={cfg.webhook_token}
            />
            <p className="text-xs text-muted-foreground">{t('billing.webhookTokenHelp')}</p>
          </div>
        )}
      </div>
      <div className="flex justify-end">
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={!provider || !apiKey || saveMutation.isPending}
        >
          <Save className="mr-2 h-4 w-4" />
          {saveMutation.isPending ? t('common.loading') : t('billing.save')}
        </Button>
      </div>
    </section>
  )
}

function FiscalConfigSection({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const configQuery = useQuery<FiscalProviderConfig | null>({
    queryKey: ['fiscal-config', workspaceId],
    queryFn: () =>
      fiscalEmissionsApi.getConfig(workspaceId).catch(() => null),
  })

  const cfg = configQuery.data

  const [provider, setProvider] = useState('')
  const [environment, setEnvironment] = useState('homologation')
  const [apiKey, setApiKey] = useState('')
  const [cnpj, setCnpj] = useState('')
  const [serie, setSerie] = useState('1')

  // Sync form state when data loads
  const [synced, setSynced] = useState(false)
  if (cfg && !synced) {
    setProvider(cfg.provider)
    setEnvironment(cfg.environment)
    setCnpj(cfg.cnpj_emitente ?? '')
    setSerie(cfg.serie_padrao)
    setSynced(true)
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      fiscalEmissionsApi.saveConfig(workspaceId, {
        provider,
        api_key: apiKey,
        environment,
        cnpj_emitente: cnpj || undefined,
        serie_padrao: serie || '1',
      }),
    onSuccess: () => {
      toast.success(t('fiscalEmission.saved'))
      qc.invalidateQueries({ queryKey: ['fiscal-config', workspaceId] })
      setApiKey('')
      setSynced(false)
    },
  })

  return (
    <section className="space-y-4 rounded-xl border bg-card p-6">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-base font-semibold">{t('fiscalEmission.settingsTitle')}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{t('fiscalEmission.settingsDescription')}</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-[13px]">{t('fiscalEmission.provider')}</Label>
          <Select value={provider} onValueChange={setProvider}>
            <SelectTrigger className="h-9 text-sm">
              <SelectValue placeholder={t('fiscalEmission.provider')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="focus_nfe">{t('fiscalEmission.providerFocusNfe')}</SelectItem>
              <SelectItem value="enotas">{t('fiscalEmission.providerEnotas')}</SelectItem>
              <SelectItem value="plugnotas">{t('fiscalEmission.providerPlugnotas')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-[13px]">{t('fiscalEmission.environment')}</Label>
          <Select value={environment} onValueChange={setEnvironment}>
            <SelectTrigger className="h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="homologation">{t('fiscalEmission.envHomologation')}</SelectItem>
              <SelectItem value="production">{t('fiscalEmission.envProduction')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label className="text-[13px]">{t('fiscalEmission.apiKey')}</Label>
          <Input
            className="h-9 text-sm font-mono"
            type="password"
            placeholder={cfg?.has_api_key ? t('fiscalEmission.apiKeyConfigured') : t('fiscalEmission.apiKeyPlaceholder')}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-[13px]">{t('fiscalEmission.cnpjEmitente')}</Label>
          <Input
            className="h-9 text-sm font-mono"
            placeholder={t('fiscalEmission.cnpjEmitentePlaceholder')}
            maxLength={14}
            value={cnpj}
            onChange={(e) => setCnpj(e.target.value.replace(/\D/g, ''))}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-[13px]">{t('fiscalEmission.seriePadrao')}</Label>
          <Input
            className="h-9 text-sm"
            maxLength={3}
            value={serie}
            onChange={(e) => setSerie(e.target.value)}
          />
        </div>
      </div>
      <div className="flex justify-end">
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={!provider || saveMutation.isPending}
        >
          <Save className="mr-2 h-4 w-4" />
          {saveMutation.isPending ? t('common.loading') : t('fiscalEmission.save')}
        </Button>
      </div>
    </section>
  )
}
