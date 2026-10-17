import { useTranslation } from 'react-i18next'
import { ShieldAlert } from 'lucide-react'
import { useMfaStatus } from '@/hooks/use-mfa-status'
import { useDateLocale } from '@/hooks/use-display-locale'
import { Button } from '@/components/ui/button'

/** During the grace period: the rule is announced, not yet in force, and this session has no second factor. */
export function MfaReminderBanner({ onSetUp }: { onSetUp: () => void }) {
  const { t } = useTranslation()
  const locale = useDateLocale()
  const { data } = useMfaStatus(true)

  if (!data?.reminder) return null

  const when = data.enforced_from
    ? new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(new Date(data.enforced_from))
    : null

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-800 dark:text-amber-200"
    >
      <ShieldAlert size={16} className="shrink-0" />
      <p className="flex-1 min-w-[16rem]">
        {when ? t('auth.mfaReminderOn', { date: when }) : t('auth.mfaReminder')}
      </p>
      <Button size="sm" variant="outline" onClick={onSetUp}>
        {t('auth.mfaSetUpNow')}
      </Button>
    </div>
  )
}
