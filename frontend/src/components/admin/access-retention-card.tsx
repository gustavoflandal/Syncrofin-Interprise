import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { History } from 'lucide-react'
import { accessLog as accessLogApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'

const KEY = ['access-log-retention'] as const

/** How long sign-in and access records are kept before they are anonymized (a system parameter). */
export function AccessRetentionCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: KEY, queryFn: accessLogApi.retention })
  // What the person is typing; until they type, the saved value is shown.
  const [draft, setDraft] = useState<string | null>(null)
  const text = draft ?? String(data?.days ?? '')
  const days = Number(text)
  const limits = { min: data?.minimum ?? 183, max: data?.maximum ?? 3650 }
  const valid = !!data && text.trim() !== '' && Number.isInteger(days) && days >= limits.min && days <= limits.max
  const changed = !!data && days !== data.days
  const shorter = valid && !!data && days < data.days

  const save = useMutation({
    mutationFn: () => accessLogApi.setRetention(days),
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: KEY })
      toast.success(t('admin.accessRetention.saved'))
    },
    onError: () => toast.error(t('common.error')),
  })

  return (
    <div className="mt-6 rounded-xl border border-border/60 bg-card overflow-hidden">
      <div className="px-5 py-4 border-b border-border/40">
        <div className="flex items-center gap-2 mb-0.5">
          <History size={15} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">{t('admin.accessRetention.title')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('admin.accessRetention.description', limits)}</p>
      </div>

      {isLoading || !data ? (
        <div className="p-5">
          <Skeleton className="h-8 w-48" />
        </div>
      ) : (
        <div className="space-y-3 px-5 py-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="access-retention-days" className="text-[13px]">
                {t('admin.accessRetention.days')}
              </Label>
              <Input
                id="access-retention-days"
                type="number"
                min={limits.min}
                max={limits.max}
                value={text}
                disabled={save.isPending}
                onChange={(e) => setDraft(e.target.value)}
                className="h-10 w-32 rounded-lg"
              />
            </div>
            <Button disabled={!valid || !changed || save.isPending} onClick={() => save.mutate()}>
              {t('admin.accessRetention.save')}
            </Button>
          </div>
          <p className={`text-[11px] ${valid ? 'text-muted-foreground' : 'text-destructive'}`}>
            {valid ? t('admin.accessRetention.hint', limits) : t('admin.accessRetention.invalid', limits)}
          </p>
          {shorter && (
            <p role="alert" className="text-xs text-amber-600 dark:text-amber-500">
              {t('admin.accessRetention.shorter')}
            </p>
          )}
          <Link to="/admin/access-log" className="inline-block text-xs font-medium text-primary hover:underline">
            {t('admin.accessRetention.viewLog')}
          </Link>
        </div>
      )}
    </div>
  )
}
