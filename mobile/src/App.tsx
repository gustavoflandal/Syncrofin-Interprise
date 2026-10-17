import { useCallback, useEffect, useState } from 'react'
import { t } from '@/lib/i18n'
import { SessionProvider, useSession } from '@/lib/session'
import { hasPendingItems } from '@/screens/PendingQueue'
import { LoginScreen } from '@/screens/Login'
import { NewTransactionScreen } from '@/screens/NewTransaction'
import { TransactionsScreen } from '@/screens/Transactions'

type Tab = 'new' | 'list'

function Shell() {
  const { server, workspaces, workspaceId, chooseWorkspace, signOut } = useSession()
  const [tab, setTab] = useState<Tab>('new')
  // Bumped after a save so the list, if it is mounted next, starts from fresh data.
  const [refreshKey, setRefreshKey] = useState(0)
  const [confirmSignOut, setConfirmSignOut] = useState(false)

  async function trySignOut() {
    if (await hasPendingItems(server, workspaceId)) {
      setConfirmSignOut(true)
      return
    }
    await signOut()
  }

  return (
    <div className="shell">
      <header className="topbar">
        <h1 className="brand small">SyncroFin</h1>
        {workspaces.length > 1 && (
          <select
            aria-label={t('workspace')}
            value={workspaceId ?? ''}
            onChange={(e) => void chooseWorkspace(e.target.value || null)}
          >
            <option value="">{t('workspace')}</option>
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        )}
        <button type="button" className="link" onClick={() => void trySignOut()}>
          {t('signOut')}
        </button>
      </header>

      {confirmSignOut && (
        <p className="notice" role="alert">
          {t('signOutPendingWarning')}{' '}
          <button type="button" className="link" onClick={() => void signOut()}>
            {t('signOutAnyway')}
          </button>{' '}
          <button type="button" className="link" onClick={() => setConfirmSignOut(false)}>
            {t('cancel')}
          </button>
        </p>
      )}

      <main className="content">
        {tab === 'new' ? (
          <NewTransactionScreen onSaved={() => setRefreshKey((n) => n + 1)} />
        ) : (
          <TransactionsScreen refreshKey={refreshKey} />
        )}
      </main>

      <nav className="tabs" aria-label="SyncroFin">
        <button type="button" className={tab === 'new' ? 'on' : ''} aria-current={tab === 'new' ? 'page' : undefined} onClick={() => setTab('new')}>
          {t('tabNew')}
        </button>
        <button type="button" className={tab === 'list' ? 'on' : ''} aria-current={tab === 'list' ? 'page' : undefined} onClick={() => setTab('list')}>
          {t('tabList')}
        </button>
      </nav>
    </div>
  )
}

/**
 * Shown instead of the app when a restored session has not been confirmed with biometrics yet.
 * Prompts on its own as soon as it appears — the person should not have to find a button first.
 */
function LockScreen() {
  const { unlock, signOut } = useSession()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const tryUnlock = useCallback(async () => {
    setBusy(true)
    setFailed(false)
    try {
      await unlock({ reason: t('biometricPrompt'), cancelTitle: t('biometricUsePassword') })
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }, [unlock])

  // Only on mount: `tryUnlock` itself changing (it doesn't) is the only thing that should
  // re-run this — a re-render from `failed`/`busy` changing must not re-prompt on its own.
  useEffect(() => {
    void tryUnlock()
  }, [tryUnlock])

  return (
    <main className="screen login center">
      <h1 className="brand">SyncroFin</h1>
      <p>{t('biometricPrompt')}</p>
      {failed && (
        <p role="alert" className="error">
          {t('biometricFailed')}
        </p>
      )}
      <button type="button" className="primary" disabled={busy} onClick={() => void tryUnlock()}>
        {t('tryAgain')}
      </button>
      <button type="button" className="link" onClick={() => void signOut()}>
        {t('biometricUsePassword')}
      </button>
    </main>
  )
}

function Gate() {
  const { ready, authenticated, locked } = useSession()
  if (!ready) return <p className="center muted splash">{t('loading')}</p>
  if (authenticated && locked) return <LockScreen />
  return authenticated ? <Shell /> : <LoginScreen />
}

export default function App() {
  return (
    <SessionProvider>
      <Gate />
    </SessionProvider>
  )
}
