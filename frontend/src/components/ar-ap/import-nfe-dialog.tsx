import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, CheckCircle, AlertCircle, SkipForward, X } from 'lucide-react'
import { arAp, type NfeImportRow, type NfeImportResult } from '@/lib/api'

interface Props {
  open: boolean
  onClose: () => void
}

const STATUS_ICON = {
  imported: <CheckCircle className="h-4 w-4 text-green-600" />,
  duplicate: <SkipForward className="h-4 w-4 text-amber-500" />,
  error: <AlertCircle className="h-4 w-4 text-destructive" />,
}

export function ImportNfeDialog({ open, onClose }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [result, setResult] = useState<NfeImportResult | null>(null)

  const mutation = useMutation({
    mutationFn: (fs: File[]) => arAp.importNfe(fs),
    onSuccess: (data) => {
      setResult(data)
      if (data.imported > 0) {
        qc.invalidateQueries({ queryKey: ['ar-ap-overview'] })
        qc.invalidateQueries({ queryKey: ['ar-ap-titles'] })
      }
    },
  })

  const handleFiles = (picked: FileList | null) => {
    if (!picked) return
    setFiles(Array.from(picked).filter((f) => f.name.endsWith('.xml')))
    setResult(null)
  }

  const handleClose = () => {
    setFiles([])
    setResult(null)
    mutation.reset()
    onClose()
  }

  const statusLabel = (row: NfeImportRow) => {
    if (row.status === 'imported') return t('arAp.importNfeRowImported')
    if (row.status === 'duplicate') return t('arAp.importNfeRowDuplicate')
    return t('arAp.importNfeRowError')
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background rounded-xl border shadow-lg w-full max-w-lg mx-4 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b shrink-0">
          <h2 className="text-lg font-semibold">{t('arAp.importNfeTitle')}</h2>
          <button onClick={handleClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4 overflow-y-auto">
          {!result ? (
            <>
              <p className="text-sm text-muted-foreground">{t('arAp.importNfeDesc')}</p>

              {/* Drop zone */}
              <div
                className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary transition-colors"
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  handleFiles(e.dataTransfer.files)
                }}
              >
                <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm font-medium">{t('arAp.importNfeSelectFiles')}</p>
                {files.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {t('arAp.importNfeSelectedCount', { count: files.length })}
                  </p>
                )}
              </div>

              <input
                ref={fileRef}
                type="file"
                accept=".xml"
                multiple
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />

              {/* File list preview */}
              {files.length > 0 && (
                <ul className="space-y-1 max-h-40 overflow-y-auto">
                  {files.map((f) => (
                    <li key={f.name} className="flex items-center gap-2 text-sm">
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="truncate">{f.name}</span>
                    </li>
                  ))}
                </ul>
              )}

              {mutation.isError && (
                <p className="text-sm text-destructive">
                  {(mutation.error as Error)?.message ?? t('common.error')}
                </p>
              )}
            </>
          ) : (
            <>
              {/* Summary chips */}
              <div className="flex flex-wrap gap-2">
                {result.imported > 0 && (
                  <span className="text-xs px-2 py-1 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                    {t('arAp.importNfeResultImported', { count: result.imported })}
                  </span>
                )}
                {result.duplicates > 0 && (
                  <span className="text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                    {t('arAp.importNfeResultDuplicate', { count: result.duplicates })}
                  </span>
                )}
                {result.errors > 0 && (
                  <span className="text-xs px-2 py-1 rounded-full bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                    {t('arAp.importNfeResultError', { count: result.errors })}
                  </span>
                )}
              </div>

              {/* Row detail */}
              <ul className="space-y-2 max-h-64 overflow-y-auto">
                {result.rows.map((row, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="mt-0.5 shrink-0">{STATUS_ICON[row.status]}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{row.filename}</p>
                      <p className="text-muted-foreground text-xs truncate">
                        {row.supplier_name ?? statusLabel(row)}
                        {row.total != null && ` — R$ ${Number(row.total).toFixed(2)}`}
                        {row.error && ` — ${row.error}`}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-6 border-t shrink-0">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm rounded-lg border hover:bg-muted transition-colors"
          >
            {result ? t('common.close') : t('common.cancel')}
          </button>
          {!result && (
            <button
              disabled={files.length === 0 || mutation.isPending}
              onClick={() => mutation.mutate(files)}
              className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {mutation.isPending ? t('arAp.importNfeImporting') : t('arAp.importNfeImport')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
