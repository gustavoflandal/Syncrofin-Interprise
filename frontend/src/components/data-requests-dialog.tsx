import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import type { AxiosError } from 'axios'
import { Loader2 } from 'lucide-react'
import { useAuth } from '@/contexts/auth-context'
import { dataRequests as api } from '@/lib/api'
import type { DataRequest, WorkspacesBlockErasureBody } from '@/types'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface DataRequestsDialogProps {
  open: boolean
  onClose: () => void
}

const TEXTAREA_CLASS =
  'min-h-[80px] w-full resize-y rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'

/** "profile" has no page of its own — it lives in the account menu, not a route. */
const SELF_SERVICE_ROUTES: Record<string, string> = {
  transactions: '/transactions',
  accounts: '/accounts',
  categories: '/categories',
}

type CorrectionStep = 'ask' | 'links' | 'form' | 'done'
type ErasureStep = 'idle' | 'confirm' | 'blocked' | 'done'

/** The D1 channel: download my data, ask for a correction, or erase my account. */
export function DataRequestsDialog({ open, onClose }: DataRequestsDialogProps) {
  const { t } = useTranslation()
  const { logout } = useAuth()

  const [history, setHistory] = useState<DataRequest[] | null>(null)
  const [downloading, setDownloading] = useState(false)

  const [correctionStep, setCorrectionStep] = useState<CorrectionStep>('ask')
  const [correctionDetail, setCorrectionDetail] = useState('')
  const [correctionLinks, setCorrectionLinks] = useState<Record<string, string> | null>(null)
  const [correctionProtocol, setCorrectionProtocol] = useState('')
  const [correctionBusy, setCorrectionBusy] = useState(false)

  const [erasureStep, setErasureStep] = useState<ErasureStep>('idle')
  const [erasurePassword, setErasurePassword] = useState('')
  const [erasureError, setErasureError] = useState('')
  const [erasureBlock, setErasureBlock] = useState<WorkspacesBlockErasureBody | null>(null)
  const [erasureBusy, setErasureBusy] = useState(false)

  const loadHistory = useCallback(async () => {
    try {
      setHistory((await api.listOwn()).items)
    } catch {
      setHistory(null)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    void loadHistory()
    setCorrectionStep('ask')
    setCorrectionDetail('')
    setErasureStep('idle')
    setErasurePassword('')
    setErasureError('')
    setErasureBlock(null)
  }, [open, loadHistory])

  async function handleDownload() {
    setDownloading(true)
    try {
      await api.download('access')
      toast.success(t('dataRequests.download.success'))
      void loadHistory()
    } catch {
      toast.error(t('dataRequests.download.error'))
    } finally {
      setDownloading(false)
    }
  }

  async function submitCorrectionForm(e: React.FormEvent) {
    e.preventDefault()
    if (!correctionDetail.trim()) return
    setCorrectionBusy(true)
    try {
      const row = await api.createCorrection(false, correctionDetail.trim())
      setCorrectionProtocol(row.protocol)
      setCorrectionStep('done')
      void loadHistory()
    } catch {
      toast.error(t('dataRequests.correction.error'))
    } finally {
      setCorrectionBusy(false)
    }
  }

  async function chooseSelfService(selfService: boolean) {
    if (!selfService) {
      setCorrectionStep('form')
      return
    }
    setCorrectionBusy(true)
    try {
      const row = await api.createCorrection(true)
      setCorrectionLinks(row.self_service_links ?? {})
      setCorrectionStep('links')
      void loadHistory()
    } catch {
      toast.error(t('dataRequests.correction.error'))
    } finally {
      setCorrectionBusy(false)
    }
  }

  async function submitErasure(e: React.FormEvent) {
    e.preventDefault()
    setErasureError('')
    setErasureBusy(true)
    try {
      await api.erasure(erasurePassword)
      setErasureStep('done')
      toast.success(t('dataRequests.erasure.success'))
      setTimeout(() => logout(), 1500)
    } catch (err) {
      const axiosErr = err as AxiosError<WorkspacesBlockErasureBody | { detail?: string }>
      if (axiosErr?.response?.status === 401) {
        setErasureError(t('dataRequests.erasure.wrongPassword'))
      } else if (axiosErr?.response?.status === 409) {
        setErasureBlock(axiosErr.response.data as WorkspacesBlockErasureBody)
        setErasureStep('blocked')
      } else {
        setErasureError(t('dataRequests.erasure.genericError'))
      }
    } finally {
      setErasureBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('dataRequests.title')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          <p className="text-sm text-muted-foreground">{t('dataRequests.description')}</p>

          {/* Access / portability */}
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">{t('dataRequests.download.title')}</h3>
            <p className="text-xs text-muted-foreground">{t('dataRequests.download.description')}</p>
            <Button variant="outline" disabled={downloading} onClick={handleDownload}>
              {downloading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('dataRequests.download.button')}
            </Button>
          </section>

          {/* Correction */}
          <section className="space-y-2 border-t pt-4">
            <h3 className="text-sm font-semibold">{t('dataRequests.correction.title')}</h3>
            {correctionStep === 'ask' && (
              <>
                <p className="text-xs text-muted-foreground">{t('dataRequests.correction.question')}</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={correctionBusy} onClick={() => chooseSelfService(true)}>
                    {t('dataRequests.correction.yes')}
                  </Button>
                  <Button size="sm" variant="outline" disabled={correctionBusy} onClick={() => chooseSelfService(false)}>
                    {t('dataRequests.correction.no')}
                  </Button>
                </div>
              </>
            )}
            {correctionStep === 'links' && (
              <div className="space-y-1.5 rounded-lg border bg-muted/30 p-3">
                <p className="text-xs font-medium">{t('dataRequests.correction.linksTitle')}</p>
                <ul className="space-y-1 text-xs">
                  {Object.keys(correctionLinks ?? {}).map((key) => {
                    const route = SELF_SERVICE_ROUTES[key]
                    return (
                      <li key={key}>
                        {route ? (
                          <Link to={route} className="text-primary hover:underline" onClick={onClose}>
                            {t(`dataRequests.correction.linkLabels.${key}`)}
                          </Link>
                        ) : (
                          t(`dataRequests.correction.linkLabels.${key}`)
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
            {correctionStep === 'form' && (
              <form onSubmit={submitCorrectionForm} className="space-y-2">
                <textarea
                  className={TEXTAREA_CLASS}
                  value={correctionDetail}
                  onChange={(e) => setCorrectionDetail(e.target.value)}
                  placeholder={t('dataRequests.correction.detailPlaceholder')}
                  required
                />
                <Button type="submit" size="sm" disabled={correctionBusy || !correctionDetail.trim()}>
                  {t('dataRequests.correction.submit')}
                </Button>
              </form>
            )}
            {correctionStep === 'done' && (
              <p className="text-xs text-muted-foreground">
                {t('dataRequests.correction.ticketCreated', { protocol: correctionProtocol })}
              </p>
            )}
          </section>

          {/* Erasure */}
          <section className="space-y-2 border-t pt-4">
            <h3 className="text-sm font-semibold text-destructive">{t('dataRequests.erasure.title')}</h3>
            {erasureStep === 'idle' && (
              <>
                <p className="text-xs text-muted-foreground">{t('dataRequests.erasure.warning')}</p>
                <Button variant="destructive" size="sm" onClick={() => setErasureStep('confirm')}>
                  {t('dataRequests.erasure.startButton')}
                </Button>
              </>
            )}
            {erasureStep === 'confirm' && (
              <form onSubmit={submitErasure} className="space-y-2">
                <Label htmlFor="erasure-password" className="text-xs">
                  {t('dataRequests.erasure.passwordLabel')}
                </Label>
                <Input
                  id="erasure-password"
                  type="password"
                  autoComplete="current-password"
                  value={erasurePassword}
                  onChange={(e) => setErasurePassword(e.target.value)}
                  required
                />
                {erasureError && (
                  <p role="alert" className="text-xs text-destructive">
                    {erasureError}
                  </p>
                )}
                <div className="flex gap-2">
                  <Button type="submit" variant="destructive" size="sm" disabled={erasureBusy}>
                    {erasureBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('dataRequests.erasure.confirmButton')}
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setErasureStep('idle')}>
                    {t('common.cancel')}
                  </Button>
                </div>
              </form>
            )}
            {erasureStep === 'blocked' && erasureBlock && (
              <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
                <p className="text-xs">{t('dataRequests.erasure.blockedDescription')}</p>
                <ul className="list-inside list-disc text-xs font-medium">
                  {erasureBlock.workspaces.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
                <p className="text-[11px] text-muted-foreground">
                  {t('dataRequests.erasure.blockedProtocol', { protocol: erasureBlock.protocol })}
                </p>
              </div>
            )}
            {erasureStep === 'done' && (
              <p className="text-xs text-muted-foreground">{t('dataRequests.erasure.success')}</p>
            )}
          </section>

          {/* History */}
          <section className="space-y-2 border-t pt-4">
            <h3 className="text-sm font-semibold">{t('dataRequests.history.title')}</h3>
            {!history ? (
              <p className="text-xs text-muted-foreground">{t('dataRequests.history.loadError')}</p>
            ) : history.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('dataRequests.history.empty')}</p>
            ) : (
              <ul className="divide-y rounded-lg border">
                {history.map((row) => (
                  <li key={row.id} className="px-3 py-2">
                    <p className="text-sm">
                      {t(`dataRequests.kinds.${row.kind}`)} · {t(`dataRequests.statuses.${row.status}`)}
                    </p>
                    <p className="text-xs text-muted-foreground">{row.protocol}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}
