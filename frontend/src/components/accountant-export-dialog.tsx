import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { FileSpreadsheet, ShieldCheck } from 'lucide-react'
import { accountantExport } from '@/lib/api'
import { presetRange, type PeriodPreset } from '@/lib/accountant-period'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const MIN_PASSWORD_LENGTH = 8

const PRESETS: PeriodPreset[] = ['lastMonth', 'thisMonth', 'lastQuarter', 'thisYear', 'lastYear', 'custom']

interface AccountantExportDialogProps {
  open: boolean
  onClose: () => void
}

/**
 * Hands the accountant what they book from: the period's movements and
 * summaries as spreadsheet-ready CSVs. SyncroFin is not the ledger, so this
 * is deliberately a set of plain files rather than a proprietary format.
 * An optional password makes it an AES-256 zip for sending by e-mail.
 */
export function AccountantExportDialog({ open, onClose }: AccountantExportDialogProps) {
  const { t } = useTranslation()
  const [preset, setPreset] = useState<PeriodPreset>('lastMonth')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [password, setPassword] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [downloadingXlsx, setDownloadingXlsx] = useState(false)
  const [error, setError] = useState('')

  const [start, end] = useMemo<[string, string]>(
    () => (preset === 'custom' ? [customStart, customEnd] : presetRange(preset)),
    [preset, customStart, customEnd],
  )

  const handleClose = () => {
    setPassword('')
    setError('')
    onClose()
  }

  const handleXlsx = async () => {
    setError('')
    if (!start || !end) { setError(t('accountantExport.periodRequired')); return }
    if (start > end) { setError(t('accountantExport.periodInverted')); return }
    setDownloadingXlsx(true)
    try {
      await accountantExport.downloadXlsx(start, end)
      toast.success(t('accountantExport.success'))
      handleClose()
    } catch {
      toast.error(t('accountantExport.error'))
    } finally {
      setDownloadingXlsx(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!start || !end) {
      setError(t('accountantExport.periodRequired'))
      return
    }
    if (start > end) {
      setError(t('accountantExport.periodInverted'))
      return
    }
    if (password && password.length < MIN_PASSWORD_LENGTH) {
      setError(t('backup.passwordTooShort', { min: MIN_PASSWORD_LENGTH }))
      return
    }

    setDownloading(true)
    try {
      await accountantExport.download(start, end, password || undefined)
      toast.success(t('accountantExport.success'))
      handleClose()
    } catch {
      toast.error(t('accountantExport.error'))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet size={18} />
            {t('accountantExport.title')}
          </DialogTitle>
          <DialogDescription>{t('accountantExport.description')}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">{t('accountantExport.period')}</legend>
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t('accountantExport.period')}>
              {PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={preset === p}
                  onClick={() => setPreset(p)}
                  className={
                    'rounded-full border px-3 py-1 text-xs transition-colors ' +
                    (preset === p
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:bg-muted')
                  }
                >
                  {t(`accountantExport.preset.${p}`)}
                </button>
              ))}
            </div>
            {preset === 'custom' ? (
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label htmlFor="acc-start">{t('accountantExport.start')}</Label>
                  <Input id="acc-start" type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="acc-end">{t('accountantExport.end')}</Label>
                  <Input id="acc-end" type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground" data-testid="acc-range">
                {start.split('-').reverse().join('/')} → {end.split('-').reverse().join('/')}
              </p>
            )}
          </fieldset>

          <div className="space-y-2">
            <Label htmlFor="acc-password">{t('accountantExport.passwordLabel')}</Label>
            <Input
              id="acc-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              placeholder={t('accountantExport.passwordPlaceholder')}
            />
          </div>
          {password && (
            <p className="flex items-start gap-2 rounded-md bg-muted p-3 text-xs text-muted-foreground">
              <ShieldCheck size={14} className="mt-0.5 shrink-0" />
              {t('accountantExport.encryptionNote')}
            </p>
          )}

          <p className="rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">{t('accountantExport.contents')}</p>

          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter className="flex-col gap-2 sm:flex-row">
            <Button type="button" variant="outline" onClick={handleClose}>
              {t('common.cancel')}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={downloadingXlsx || downloading}
              onClick={handleXlsx}
            >
              {downloadingXlsx ? t('backup.downloading') : t('accountantExport.buttonXlsx')}
            </Button>
            <Button type="submit" disabled={downloading || downloadingXlsx}>
              {downloading ? t('backup.downloading') : t('accountantExport.button')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
