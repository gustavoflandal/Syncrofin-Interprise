import { useEffect, useState } from 'react'
import { locale, t } from '@/lib/i18n'
import { formatMoney } from '@/lib/money'
import * as queue from '@/lib/queue'
import { useSession } from '@/lib/session'
import { syncNow } from '@/lib/sync'

/** Above this many pending items, nudge toward syncing instead of piling on forever. */
const LARGE_QUEUE = 50
/** How long a synced item keeps showing its green check before it drops off this panel — by
 * then it is already visible in the regular list on the next natural reload. */
const SYNCED_GRACE_MS = 4_000

/**
 * Lançamentos made offline, above the month list — visible regardless of which month is
 * selected, since a pending item from today should not hide behind last month's page. Marks
 * each with a red dot (pending/sending), a green check (just synced) or a warning (the server
 * rejected it). `onSynced` lets the list above re-fetch so a newly-arrived item shows up there.
 */
export function PendingQueue({ onSynced }: { onSynced: () => void }) {
  const { api, server, workspaceId } = useSession()
  const [items, setItems] = useState<queue.QueueItem[]>([])

  useEffect(() => {
    if (!server) return
    let cancelled = false
    const refresh = () => {
      void queue.list(server, workspaceId).then((next) => {
        if (!cancelled) setItems(next)
      })
    }
    refresh()
    const unsubscribe = queue.subscribe(refresh)
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [server, workspaceId])

  // A newly-synced item is worth telling the list about (so it shows up there), and worth
  // clearing from here after its check has had a moment to be seen.
  useEffect(() => {
    const synced = items.filter((item) => item.status === 'synced')
    if (synced.length === 0) return
    onSynced()
    const timers = synced.map((item) => setTimeout(() => void queue.remove(item.clientId), SYNCED_GRACE_MS))
    return () => timers.forEach(clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the synced ids should re-arm the timers
  }, [items.map((i) => (i.status === 'synced' ? i.clientId : '')).join(',')])

  if (!server || items.length === 0) return null

  const pendingCount = items.filter((item) => item.status !== 'synced').length

  return (
    <section className="queue" aria-label={t('queueSection')}>
      <div className="queue-head">
        <h2>
          {t('queueSection')} ({pendingCount})
        </h2>
        <button type="button" className="link" onClick={() => void syncNow(api, server, workspaceId)}>
          {t('syncNow')}
        </button>
      </div>

      {pendingCount > LARGE_QUEUE && <p className="notice">{t('queueLarge')}</p>}

      <ul className="list">
        {items.map((item) => (
          <li key={item.clientId}>
            <span className="row-item queue-item">
              <span className={`dot ${item.status}`} aria-hidden="true" />
              <span className="main">
                <span className="title">{item.payload.description}</span>
                <span className="sub">
                  {item.status === 'pending' && t('queuePending')}
                  {item.status === 'syncing' && t('queueSyncing')}
                  {item.status === 'synced' && t('queueSynced')}
                  {item.status === 'failed' && `${t('queueFailed')}: ${item.error ?? ''}`}
                </span>
              </span>
              <span className={item.payload.type === 'debit' ? 'amount out' : 'amount in'}>
                {item.payload.type === 'debit' ? '−' : '+'}
                {formatMoney(Number(item.payload.amount), item.payload.currency ?? 'BRL', locale())}
              </span>
              {item.status === 'failed' && (
                <span className="row">
                  <button type="button" className="link" onClick={() => void queue.setStatus(item.clientId, 'pending')}>
                    {t('tryAgain')}
                  </button>
                  <button type="button" className="link" onClick={() => void queue.remove(item.clientId)}>
                    {t('delete')}
                  </button>
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Whether `useSession().signOut()` should be preceded by a warning — read by `Shell`. */
export async function hasPendingItems(server: string | null, workspaceId: string | null): Promise<boolean> {
  if (!server) return false
  const items = await queue.list(server, workspaceId)
  return items.some((item) => item.status !== 'synced')
}
