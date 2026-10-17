import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ShieldCheck } from 'lucide-react'
import { admin as adminApi } from '@/lib/api'
import { useDateLocale } from '@/hooks/use-display-locale'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'

const POLICY_KEY = ['admin', 'mfa-policy'] as const
const MAX_GRACE_DAYS = 90

type ApiError = { response?: { data?: { detail?: string } } }

/** The instance's second-factor rule: on/off, who it covers, and how long people have to comply. */
export function MfaPolicyCard() {
  const { t } = useTranslation()
  const locale = useDateLocale()
  const queryClient = useQueryClient()
  const { data: policy, isLoading } = useQuery({ queryKey: POLICY_KEY, queryFn: adminApi.mfaPolicy })
  // What the person is typing; until they type, the saved value is shown.
  const [draft, setDraft] = useState<string | null>(null)
  const grace = draft ?? String(policy?.grace_days ?? 7)

  const save = useMutation({
    mutationFn: async (changes: { required?: boolean; scope?: string; graceDays?: number }) => {
      // The grace period and the scope are stored first: turning the rule on reads them.
      if (changes.graceDays !== undefined) await adminApi.updateSetting('mfa_grace_days', String(changes.graceDays))
      if (changes.scope !== undefined) await adminApi.updateSetting('mfa_required_scope', changes.scope)
      if (changes.required !== undefined) await adminApi.updateSetting('mfa_required', String(changes.required))
    },
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: POLICY_KEY })
      toast.success(t('admin.settings.updated'))
    },
    onError: (error: ApiError) => {
      const detail = error.response?.data?.detail
      toast.error(detail === 'MFA_ADMIN_NOT_ENROLLED' ? t('admin.mfa.adminNotEnrolled') : t('common.error'))
    },
  })

  const formatDate = (iso: string) => new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(new Date(iso))

  return (
    <div className="mt-6 rounded-xl border border-border/60 bg-card overflow-hidden">
      <div className="px-5 py-4 border-b border-border/40">
        <div className="flex items-center gap-2 mb-0.5">
          <ShieldCheck size={15} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">{t('admin.mfa.title')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('admin.mfa.description')}</p>
      </div>

      {isLoading || !policy ? (
        <div className="p-5">
          <Skeleton className="h-8 w-48" />
        </div>
      ) : (
        <div className="space-y-4 px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm text-foreground">{t('admin.mfa.require')}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {policy.from_environment
                  ? t('admin.mfa.fromEnvironment')
                  : policy.required && policy.enforced_from && new Date(policy.enforced_from) > new Date()
                    ? t('admin.mfa.startsOn', { date: formatDate(policy.enforced_from) })
                    : policy.required
                      ? t('admin.mfa.inForce')
                      : t('admin.mfa.off')}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={policy.required}
              aria-label={t('admin.mfa.require')}
              disabled={save.isPending || policy.from_environment}
              onClick={() =>
                save.mutate(
                  policy.required
                    ? { required: false }
                    : { required: true, graceDays: Number(grace) || 0, scope: policy.scope },
                )
              }
              className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 ${policy.required ? 'bg-primary' : 'bg-muted-foreground/20'}`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${policy.required ? 'translate-x-6' : 'translate-x-1'}`}
              />
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="mfa-scope" className="text-[13px]">
                {t('admin.mfa.scope')}
              </Label>
              <select
                id="mfa-scope"
                value={policy.scope}
                disabled={save.isPending || policy.from_environment}
                onChange={(e) => save.mutate({ scope: e.target.value })}
                className="h-10 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="all">{t('admin.mfa.scopeAll')}</option>
                <option value="admins">{t('admin.mfa.scopeAdmins')}</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mfa-grace" className="text-[13px]">
                {t('admin.mfa.grace')}
              </Label>
              <Input
                id="mfa-grace"
                type="number"
                min={0}
                max={MAX_GRACE_DAYS}
                value={grace}
                disabled={save.isPending || policy.from_environment}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => {
                  const days = Math.min(MAX_GRACE_DAYS, Math.max(0, Number(grace) || 0))
                  setDraft(String(days))
                  if (days !== policy.grace_days) save.mutate({ graceDays: days })
                }}
                className="h-10 rounded-lg"
              />
              <p className="text-[11px] text-muted-foreground">{t('admin.mfa.graceHint')}</p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            {t('admin.mfa.withoutApp', { without: policy.users_without_2fa, total: policy.users_total })}
          </p>
        </div>
      )}
    </div>
  )
}
