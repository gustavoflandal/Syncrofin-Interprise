import { useCallback, useEffect, useState } from 'react'
import { ApiError, type Attachment, type Transaction } from '@/lib/api'
import { takeReceiptPhoto } from '@/lib/camera'
import { parseIsoDate } from '@/lib/dates'
import { receiptFilename, shrinkPhoto } from '@/lib/image'
import { locale, t } from '@/lib/i18n'
import { formatMoney } from '@/lib/money'
import { useSession } from '@/lib/session'

interface Props {
  transaction: Transaction
  onClose: () => void
  /** A receipt was added: the list's paperclip count is out of date. */
  onChanged: () => void
}

interface Receipt {
  attachment: Attachment
  /** Null while it loads or if it failed. */
  src: string | null
}

export function TransactionDetail({ transaction, onClose, onChanged }: Props) {
  const { api } = useSession()
  const [receipts, setReceipts] = useState<Receipt[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [zoom, setZoom] = useState<string | null>(null)

  const loadReceipts = useCallback(async () => {
    try {
      const list = await api.attachments(transaction.id)
      setReceipts(list.map((attachment) => ({ attachment, src: null })))
      for (const attachment of list) {
        api
          .attachmentDataUrl(transaction.id, attachment)
          .then((src) => setReceipts((current) => current?.map((r) => (r.attachment.id === attachment.id ? { ...r, src } : r)) ?? null))
          .catch(() => undefined) // a broken thumbnail stays a grey box
      }
    } catch {
      setReceipts([])
    }
  }, [api, transaction.id])

  useEffect(() => {
    void loadReceipts()
  }, [loadReceipts])

  async function addReceipt() {
    setMessage(null)
    let photo: Blob | null
    try {
      photo = await takeReceiptPhoto()
    } catch {
      setMessage({ kind: 'error', text: t('genericError') })
      return
    }
    if (!photo) return
    setBusy(true)
    try {
      await api.uploadAttachment(transaction.id, await shrinkPhoto(photo), receiptFilename())
      setMessage({ kind: 'ok', text: t('receiptSent') })
      await loadReceipts()
      onChanged()
    } catch (error) {
      setMessage({ kind: 'error', text: error instanceof ApiError && error.status === 403 ? t('readOnly') : t('receiptFailed') })
    } finally {
      setBusy(false)
    }
  }

  const expense = transaction.type === 'debit'
  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={t('detail')}>
      <div className="sheet-body">
        <header className="sheet-head">
          <h2>{transaction.description}</h2>
          <button type="button" className="link" onClick={onClose}>
            {t('close')}
          </button>
        </header>

        <p className={expense ? 'big out' : 'big in'}>
          {expense ? '−' : '+'}
          {formatMoney(Math.abs(Number(transaction.amount)), transaction.currency, locale())}
        </p>

        <dl className="facts">
          <dt>{t('date')}</dt>
          <dd>{new Intl.DateTimeFormat(locale(), { dateStyle: 'long' }).format(parseIsoDate(transaction.date))}</dd>
          {transaction.category && (
            <>
              <dt>{t('category')}</dt>
              <dd>{transaction.category.name}</dd>
            </>
          )}
          <dt>{t('detail')}</dt>
          <dd>{transaction.status === 'pending' ? t('pending') : t('posted')}</dd>
          {transaction.notes && (
            <>
              <dt>{t('notes')}</dt>
              <dd>{transaction.notes}</dd>
            </>
          )}
        </dl>

        <h3>{t('receipt')}</h3>
        {receipts === null && <p className="muted">{t('loading')}</p>}
        {receipts?.length === 0 && <p className="muted">{t('noReceipts')}</p>}
        <div className="thumbs">
          {receipts?.map(({ attachment, src }) =>
            src && attachment.content_type.startsWith('image/') ? (
              <button key={attachment.id} type="button" className="thumb" onClick={() => setZoom(src)}>
                <img src={src} alt={attachment.filename} />
              </button>
            ) : (
              <span key={attachment.id} className="thumb file">
                {attachment.filename}
              </span>
            ),
          )}
        </div>

        {message && (
          <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'error' : 'success'}>
            {message.text}
          </p>
        )}
        <button type="button" className="secondary" onClick={addReceipt} disabled={busy}>
          {busy ? t('uploading') : t('addReceipt')}
        </button>
      </div>

      {zoom && (
        <button type="button" className="zoom" onClick={() => setZoom(null)} aria-label={t('close')}>
          <img src={zoom} alt={t('receipt')} />
        </button>
      )}
    </div>
  )
}
