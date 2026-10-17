import { useState, type FormEvent } from 'react'
import { t, type MessageKey } from '@/lib/i18n'
import { LoginError, useSession, type LoginFailure } from '@/lib/session'

const MESSAGE: Record<LoginFailure, MessageKey> = {
  serverEmpty: 'serverInvalid',
  serverInvalid: 'serverInvalid',
  serverInsecure: 'serverInsecure',
  badCredentials: 'badCredentials',
  badCode: 'badCode',
  twoFactorExpired: 'sessionExpired',
  localAuthOff: 'localAuthOff',
  mfaRequired: 'mfaRequired',
  network: 'networkError',
  unknown: 'genericError',
}

/** A small eye / eye-with-a-line-through-it, drawn inline: the app has no icon library. */
function EyeIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {open ? (
        <>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
          <circle cx="12" cy="12" r="3" />
        </>
      ) : (
        <>
          <path d="M9.9 4.24A9.4 9.4 0 0 1 12 4c7 0 11 8 11 8a18.6 18.6 0 0 1-2.44 3.44M6.5 6.6C3.4 8.5 1 12 1 12s4 8 11 8a9.4 9.4 0 0 0 4.6-1.2" />
          <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </>
      )}
    </svg>
  )
}

export function LoginScreen() {
  const { signIn, completeTwoFactor, server, sessionExpired } = useSession()
  const [serverInput, setServerInput] = useState(server ?? '')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [tempToken, setTempToken] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<LoginFailure | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setFailure(null)
    try {
      if (tempToken) {
        await completeTwoFactor(tempToken, code)
      } else {
        const outcome = await signIn(serverInput, email, password)
        if (outcome.status === 'two-factor') setTempToken(outcome.tempToken)
      }
    } catch (error) {
      const code = error instanceof LoginError ? error.code : 'unknown'
      // The one-time token lasts minutes: when it is gone, start again from the password.
      if (code === 'twoFactorExpired') setTempToken(null)
      setFailure(code)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="screen login">
      <h1 className="brand">SyncroFin</h1>
      <form onSubmit={submit} noValidate>
        {tempToken ? (
          <>
            <h2>{t('twoFactorTitle')}</h2>
            <p className="hint">{t('twoFactorHint')}</p>
            <label>
              {t('code')}
              <input
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
              />
            </label>
          </>
        ) : (
          <>
            <label>
              {t('server')}
              <input
                value={serverInput}
                onChange={(e) => setServerInput(e.target.value)}
                inputMode="url"
                autoCapitalize="none"
                autoCorrect="off"
                autoComplete="url"
                placeholder="syncrofin.suaempresa.com"
              />
              <span className="hint">{t('serverHint')}</span>
            </label>
            <label>
              {t('email')}
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoCapitalize="none" autoComplete="username" />
            </label>
            <label>
              {t('password')}
              <div className="password-field">
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="reveal"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? t('hidePassword') : t('showPassword')}
                >
                  <EyeIcon open={showPassword} />
                </button>
              </div>
            </label>
          </>
        )}

        {sessionExpired && !failure && <p role="alert" className="notice">{t('sessionExpired')}</p>}
        {failure && <p role="alert" className="error">{t(MESSAGE[failure])}</p>}

        <button type="submit" className="primary" disabled={busy}>
          {busy ? t('signingIn') : tempToken ? t('verify') : t('signIn')}
        </button>
      </form>
    </main>
  )
}
