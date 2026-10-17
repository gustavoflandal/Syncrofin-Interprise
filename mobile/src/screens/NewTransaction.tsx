import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ApiError, NetworkError, type Account, type Category } from '@/lib/api'
import { loadLookups, saveLookups } from '@/lib/cache'
import { takeReceiptPhoto } from '@/lib/camera'
import { parseIsoDate, today } from '@/lib/dates'
import { receiptFilename, shrinkPhoto } from '@/lib/image'
import { getLang, locale, t } from '@/lib/i18n'
import { formatMoney, parseAmount } from '@/lib/money'
import { ocrAvailable, readReceipt } from '@/lib/ocr'
import * as queue from '@/lib/queue'
import { hasSuggestion, type ReceiptSuggestion } from '@/lib/receipt-parser'
import { useSession } from '@/lib/session'

type Reading = { state: 'reading' } | { state: 'done'; suggestion: ReceiptSuggestion } | { state: 'none' }

type Outcome = { kind: 'saved' } | { kind: 'saved-no-photo' } | { kind: 'queued' } | { kind: 'error'; message: string }

type DataSource = 'server' | 'cache'

export function NewTransactionScreen({ onSaved }: { onSaved: () => void }) {
  const { api, server, workspaceId } = useSession()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [dataSource, setDataSource] = useState<DataSource>('server')

  const [type, setType] = useState<'debit' | 'credit'>('debit')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [accountId, setAccountId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [date, setDate] = useState(today())
  const [photo, setPhoto] = useState<Blob | null>(null)
  const [reading, setReading] = useState<Reading | null>(null)
  // Which photo the running OCR belongs to: a slow reading must not land on a newer photo.
  const readingFor = useRef<Blob | null>(null)
  const [errors, setErrors] = useState<{ amount?: boolean; description?: boolean; account?: boolean }>({})
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<Outcome | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadFailed(false)
    setDataSource('server')

    function apply(accountList: Account[], categoryList: Category[]) {
      setAccounts(accountList)
      setCategories(categoryList)
      setAccountId((current) => (accountList.some((a) => a.id === current) ? current : (accountList[0]?.id ?? '')))
      setCategoryId('')
    }

    Promise.all([api.accounts(), api.categories()])
      .then(([accountList, categoryList]) => {
        if (cancelled) return
        apply(accountList, categoryList)
        setDataSource('server')
        if (server) void saveLookups(server, workspaceId, accountList, categoryList)
      })
      .catch(async () => {
        if (cancelled) return
        if (!server) { setLoadFailed(true); return }
        const cached = await loadLookups(server, workspaceId)
        if (cancelled) return
        if (cached && cached.accounts.length > 0) {
          apply(cached.accounts, cached.categories)
          setDataSource('cache')
        } else {
          setLoadFailed(true)
        }
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [api, server, workspaceId])

  const photoUrl = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo])
  useEffect(() => () => void (photoUrl && URL.revokeObjectURL(photoUrl)), [photoUrl])

  async function pickPhoto() {
    try {
      const taken = await takeReceiptPhoto()
      if (!taken) return
      setPhoto(taken)
      setReading(null)
      if (ocrAvailable()) {
        readingFor.current = taken
        setReading({ state: 'reading' })
        // The photo as the camera delivered it: the upload is shrunk later, the reading is not.
        const suggestion = await readReceipt(taken)
        if (readingFor.current !== taken) return
        setReading(suggestion && hasSuggestion(suggestion) ? { state: 'done', suggestion } : { state: 'none' })
      }
    } catch {
      setOutcome({ kind: 'error', message: t('genericError') })
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    const parsed = parseAmount(amount)
    const next = { amount: parsed === null, description: !description.trim(), account: !accountId }
    setErrors({ amount: next.amount || undefined, description: next.description || undefined, account: next.account || undefined })
    if (next.amount || next.description || next.account || parsed === null) return

    setBusy(true)
    setOutcome(null)
    const account = accounts.find((a) => a.id === accountId)
    // Generated up front, not only when queuing: sent on every create, online or not. If this
    // request's response never arrives (dropped connection, not a clean "offline"), a later
    // retry — automatic from the queue, or this same request racing the timeout — carries the
    // same id, so the server recognises it as the one already made instead of a second one.
    const clientId = crypto.randomUUID()
    const payload = {
      description: description.trim(),
      amount: parsed,
      date,
      type,
      account_id: accountId,
      category_id: categoryId || null,
      currency: account?.currency,
      client_id: clientId,
    }
    try {
      const created = await api.createTransaction(payload)
      let photoOk = true
      if (photo) {
        try {
          await api.uploadAttachment(created.id, await shrinkPhoto(photo), receiptFilename())
        } catch {
          photoOk = false
        }
      }
      setOutcome({ kind: photoOk ? 'saved' : 'saved-no-photo' })
      resetForm()
      onSaved()
    } catch (error) {
      if (error instanceof NetworkError && server) {
        await queue.enqueue({ clientId, server, workspaceId, payload, photo })
        setOutcome({ kind: 'queued' })
        resetForm()
        return
      }
      const message =
        error instanceof ApiError && error.status === 403
          ? t('readOnly')
          : error instanceof ApiError && error.detail
            ? error.detail
            : t('genericError')
      setOutcome({ kind: 'error', message })
    } finally {
      setBusy(false)
    }
  }

  function resetForm() {
    setAmount('')
    setDescription('')
    setPhoto(null)
    setReading(null)
    readingFor.current = null
  }

  if (loading) return <p className="center muted">{t('loading')}</p>
  if (loadFailed) return <p role="alert" className="error">{t('networkError')}</p>
  if (accounts.length === 0) return <p className="notice">{t('noAccounts')}</p>

  return (
    <form className="screen form" onSubmit={submit} noValidate>
      {dataSource === 'cache' && <p className="notice" role="status">{t('offlineMode')}</p>}

      <div className="segmented" role="group" aria-label={t('tabNew')}>
        <button type="button" className={type === 'debit' ? 'on' : ''} aria-pressed={type === 'debit'} onClick={() => setType('debit')}>
          {t('expense')}
        </button>
        <button type="button" className={type === 'credit' ? 'on' : ''} aria-pressed={type === 'credit'} onClick={() => setType('credit')}>
          {t('income')}
        </button>
      </div>

      <label>
        {t('amount')}
        <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="0,00" aria-invalid={errors.amount} />
        {errors.amount && <span className="error">{t('amountInvalid')}</span>}
      </label>

      <label>
        {t('description')}
        <input value={description} onChange={(e) => setDescription(e.target.value)} aria-invalid={errors.description} />
        {errors.description && <span className="error">{t('descriptionRequired')}</span>}
      </label>

      <label>
        {t('account')}
        <select value={accountId} onChange={(e) => setAccountId(e.target.value)} aria-invalid={errors.account}>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.currency})
            </option>
          ))}
        </select>
      </label>

      <label>
        {t('category')}
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">{t('noCategory')}</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t('date')}
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>

      <div className="receipt">
        <span className="label">{t('receipt')}</span>
        {photoUrl && <img src={photoUrl} alt={t('receipt')} className="preview" />}
        <div className="row">
          <button type="button" className="secondary" onClick={pickPhoto}>
            {photo ? t('retakePhoto') : t('takePhoto')}
          </button>
          {photo && (
            <button
              type="button"
              className="link"
              onClick={() => {
                setPhoto(null)
                setReading(null)
                readingFor.current = null
              }}
            >
              {t('removePhoto')}
            </button>
          )}
        </div>
      </div>

      {reading?.state === 'reading' && <p className="muted">{t('ocrReading')}</p>}
      {reading?.state === 'none' && <p className="notice">{t('ocrNothing')}</p>}
      {reading?.state === 'done' && (
        <ReceiptSuggestions
          suggestion={reading.suggestion}
          currency={accounts.find((a) => a.id === accountId)?.currency ?? 'BRL'}
          onApply={(picked) => {
            if (picked.amount) setAmount(getLang() === 'en' ? picked.amount : picked.amount.replace('.', ','))
            if (picked.date) setDate(picked.date)
            if (picked.merchant) setDescription(picked.merchant)
            setErrors({})
          }}
          onDismiss={() => setReading(null)}
        />
      )}

      {outcome?.kind === 'saved' && <p role="status" className="success">{t('saved')}</p>}
      {outcome?.kind === 'saved-no-photo' && <p role="status" className="notice">{t('savedNoPhoto')}</p>}
      {outcome?.kind === 'queued' && <p role="status" className="notice">{t('savedOffline')}</p>}
      {outcome?.kind === 'error' && <p role="alert" className="error">{outcome.message}</p>}

      <button type="submit" className="primary" disabled={busy}>
        {busy ? t('saving') : t('save')}
      </button>
    </form>
  )
}

/**
 * What the OCR read, offered field by field. Nothing is filled in until the person taps: a
 * thermal receipt is often misread, and a wrong amount that was saved quietly is worse than none.
 */
function ReceiptSuggestions({
  suggestion,
  currency,
  onApply,
  onDismiss,
}: {
  suggestion: ReceiptSuggestion
  currency: string
  onApply: (picked: ReceiptSuggestion) => void
  onDismiss: () => void
}) {
  const rows: { key: keyof ReceiptSuggestion; label: string; shown: string }[] = []
  if (suggestion.amount) rows.push({ key: 'amount', label: t('amount'), shown: formatMoney(suggestion.amount, currency, locale()) })
  if (suggestion.date) {
    rows.push({ key: 'date', label: t('date'), shown: new Intl.DateTimeFormat(locale(), { dateStyle: 'medium' }).format(parseIsoDate(suggestion.date)) })
  }
  if (suggestion.merchant) rows.push({ key: 'merchant', label: t('description'), shown: suggestion.merchant })

  return (
    <section className="suggest" aria-label={t('ocrTitle')}>
      <h3>{t('ocrTitle')}</h3>
      <p className="muted">{t('ocrHint')}</p>
      <ul>
        {rows.map((row) => (
          <li key={row.key}>
            <span>
              <span className="muted">{row.label}</span>
              <strong>{row.shown}</strong>
            </span>
            <button type="button" className="secondary small" onClick={() => onApply({ [row.key]: suggestion[row.key] })}>
              {t('ocrUse')}
            </button>
          </li>
        ))}
      </ul>
      <div className="row">
        <button type="button" className="primary small" onClick={() => onApply(suggestion)}>
          {t('ocrUseAll')}
        </button>
        <button type="button" className="link" onClick={onDismiss}>
          {t('ocrDismiss')}
        </button>
      </div>
    </section>
  )
}
