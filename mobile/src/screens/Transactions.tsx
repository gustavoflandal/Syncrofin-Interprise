import { useCallback, useEffect, useState } from 'react'
import { type Transaction } from '@/lib/api'
import { monthRange, parseIsoDate, shiftMonth } from '@/lib/dates'
import { locale, t } from '@/lib/i18n'
import { formatMoney } from '@/lib/money'
import { useSession } from '@/lib/session'
import { PendingQueue } from '@/screens/PendingQueue'
import { TransactionDetail } from '@/screens/TransactionDetail'

const PAGE_SIZE = 30

export function TransactionsScreen({ refreshKey }: { refreshKey: number }) {
  const { api, workspaceId } = useSession()
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth())
  const [items, setItems] = useState<Transaction[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [reload, setReload] = useState(0)
  const [selected, setSelected] = useState<Transaction | null>(null)

  // Page 1 again whenever the month, the workspace, or a save elsewhere changes what is listed.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setFailed(false)
    const { from, to } = monthRange(year, month)
    api
      .transactions({ from, to, page: 1, limit: PAGE_SIZE })
      .then((result) => {
        if (cancelled) return
        setItems(result.items)
        setTotal(result.total)
        setPage(1)
      })
      .catch(() => !cancelled && setFailed(true))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [api, year, month, workspaceId, refreshKey, reload])

  const loadMore = useCallback(async () => {
    const { from, to } = monthRange(year, month)
    const next = page + 1
    try {
      const result = await api.transactions({ from, to, page: next, limit: PAGE_SIZE })
      setItems((current) => [...current, ...result.items.filter((i) => !current.some((c) => c.id === i.id))])
      setPage(next)
    } catch {
      setFailed(true)
    }
  }, [api, year, month, page])

  function go(delta: number) {
    const moved = shiftMonth(year, month, delta)
    setYear(moved.year)
    setMonth(moved.month)
  }

  const rawMonth = new Intl.DateTimeFormat(locale(), { month: 'long', year: 'numeric' }).format(new Date(year, month, 1))
  // Only the first letter: CSS capitalize would also turn "de" into "De".
  const monthLabel = rawMonth.charAt(0).toLocaleUpperCase(locale()) + rawMonth.slice(1)

  return (
    <section className="screen">
      <PendingQueue onSynced={() => setReload((n) => n + 1)} />

      <div className="month">
        <button type="button" onClick={() => go(-1)} aria-label={t('prevMonth')}>
          ‹
        </button>
        <h2>{monthLabel}</h2>
        <button type="button" onClick={() => go(1)} aria-label={t('nextMonth')}>
          ›
        </button>
      </div>

      {loading && <p className="center muted">{t('loading')}</p>}
      {failed && (
        <p role="status" className="notice">
          {t('offlineList')}{' '}
          <button type="button" className="link" onClick={() => setReload((n) => n + 1)}>
            {t('tryAgain')}
          </button>
        </p>
      )}
      {!loading && !failed && items.length === 0 && <p className="center muted">{t('empty')}</p>}

      <ul className="list">
        {items.map((tx) => {
          const expense = tx.type === 'debit'
          return (
            <li key={tx.id}>
              <button type="button" className="row-item" onClick={() => setSelected(tx)}>
                <span className="main">
                  <span className="title">{tx.description}</span>
                  <span className="sub">
                    {new Intl.DateTimeFormat(locale(), { day: '2-digit', month: 'short' }).format(parseIsoDate(tx.date))}
                    {tx.category ? ` · ${tx.category.name}` : ''}
                    {tx.attachment_count > 0 ? ' · 📎' : ''}
                  </span>
                </span>
                <span className={expense ? 'amount out' : 'amount in'}>
                  {expense ? '−' : '+'}
                  {formatMoney(Math.abs(Number(tx.amount)), tx.currency, locale())}
                </span>
              </button>
            </li>
          )
        })}
      </ul>

      {!loading && items.length < total && (
        <button type="button" className="secondary" onClick={loadMore}>
          {t('loadMore')} ({items.length}/{total})
        </button>
      )}
      {!loading && total > 0 && items.length >= total && (
        <p className="center muted">
          {total} {t('total')}
        </p>
      )}

      {selected && (
        <TransactionDetail
          transaction={selected}
          onClose={() => setSelected(null)}
          onChanged={() => {
            setReload((n) => n + 1)
          }}
        />
      )}
    </section>
  )
}
