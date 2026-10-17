import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Loader2, Monitor, Smartphone } from 'lucide-react'
import { auth } from '@/lib/api'
import { accessAction, accessReason } from '@/lib/access-log'
import type { AccessHistoryItem, DeviceSession } from '@/types'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface SessionsDialogProps {
  open: boolean
  onClose: () => void
}

function isPhone(label: string | null): boolean {
  return !!label && /android|ios|app syncrofin/i.test(label)
}

/** The devices signed in to this account, with a way to end any of them. */
export function SessionsDialog({ open, onClose }: SessionsDialogProps) {
  const { t, i18n } = useTranslation()
  const [sessions, setSessions] = useState<DeviceSession[]>([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [endingOthers, setEndingOthers] = useState(false)
  // null: not loaded, or it could not be read (then the section is simply not shown).
  const [recent, setRecent] = useState<AccessHistoryItem[] | null>(null)

  const load = useCallback(async () => {
    setRecent(null)
    setLoading(true)
    setFailed(false)
    try {
      setSessions(await auth.listSessions())
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
    // The recent accesses are a bonus: if they cannot be read, the devices above still work.
    try {
      setRecent((await auth.accessHistory(20)).items)
    } catch {
      setRecent(null)
    }
  }, [])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  async function endOne(id: string) {
    setBusyId(id)
    try {
      await auth.revokeSession(id)
      setSessions((current) => current.filter((s) => s.id !== id))
      toast.success(t('auth.sessionEnded'))
    } catch {
      toast.error(t('auth.sessionEndError'))
    } finally {
      setBusyId(null)
    }
  }

  async function endOthers() {
    setEndingOthers(true)
    try {
      await auth.revokeOtherSessions()
      setSessions((current) => current.filter((s) => s.current))
      toast.success(t('auth.sessionsOthersEnded'))
    } catch {
      toast.error(t('auth.sessionEndError'))
    } finally {
      setEndingOthers(false)
    }
  }

  const when = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'short', timeStyle: 'short' })
  const others = sessions.filter((s) => !s.current)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('auth.sessionsTitle')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">{t('auth.sessionsDescription')}</p>

          {loading ? (
            <div className="flex justify-center py-6" role="status">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : failed ? (
            <p role="alert" className="text-sm text-destructive">
              {t('auth.sessionsLoadError')}
            </p>
          ) : (
            <ul className="divide-y rounded-lg border">
              {sessions.map((session) => {
                const Icon = isPhone(session.device_label) ? Smartphone : Monitor
                return (
                  <li key={session.id} className="flex items-center gap-3 px-3 py-2.5">
                    <Icon size={18} className="shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {session.device_label ?? t('auth.sessionUnknownDevice')}
                        {session.current && (
                          <span className="ml-2 rounded bg-primary/10 px-1.5 py-0.5 text-[10.5px] font-semibold text-primary">
                            {t('auth.sessionThisDevice')}
                          </span>
                        )}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {session.ip ? `${session.ip} · ` : ''}
                        {t('auth.sessionLastActive', { when: when.format(new Date(session.last_seen_at)) })}
                      </p>
                    </div>
                    {!session.current && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busyId === session.id}
                        onClick={() => endOne(session.id)}
                      >
                        {t('auth.sessionEnd')}
                      </Button>
                    )}
                  </li>
                )
              })}
            </ul>
          )}

          {others.length > 0 && (
            <Button variant="outline" className="w-full" disabled={endingOthers} onClick={endOthers}>
              {t('auth.sessionsEndOthers')}
            </Button>
          )}
        </div>
        {recent && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">{t('auth.recentAccess.title')}</h3>
            {recent.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('auth.recentAccess.empty')}</p>
            ) : (
              <ul className="divide-y rounded-lg border">
                {recent.map((item) => {
                  const reason = accessReason(t, item.action, item.detail)
                  return (
                    <li key={item.id} className="px-3 py-2">
                      <p className="text-sm">{[accessAction(t, item.action), reason].filter(Boolean).join(' · ')}</p>
                      <p className="text-xs text-muted-foreground">
                        {when.format(new Date(item.occurred_at))}
                        {item.ip ? ` · ${item.ip}` : ''}
                      </p>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
