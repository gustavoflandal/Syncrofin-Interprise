import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { auth as authApi } from '@/lib/api'
import { isServerUnreachable } from '@/lib/auth-errors'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { ShellLogo } from '@/components/shell-logo'
import { passwordErrorText } from '@/lib/password-policy'
import { useFeatureFlags } from '@/hooks/use-feature-flags'
import type { AxiosError } from 'axios'

/**
 * Choose a new password from an e-mailed link.
 *
 * The same page serves two arrivals: someone who forgot their password, and
 * someone just invited who has no password yet (`?invited=1`). The token in
 * the URL is the whole credential, so it is read once and never rendered,
 * stored or sent anywhere but the reset endpoint.
 */
export default function ResetPasswordPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { passwordMinLength } = useFeatureFlags()
  const [params] = useSearchParams()
  // Read once into state, then scrubbed from the URL below: the token is a
  // credential, and an address bar (history, a screenshot, a shared screen)
  // is a poor place to leave one.
  const [token] = useState(() => params.get('token') ?? '')
  const invited = params.get('invited') === '1'

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (token) navigate(invited ? '/reset-password?invited=1' : '/reset-password', { replace: true })
  }, [token, invited, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password.length < passwordMinLength) {
      setError(t('auth.passwordTooShort', { min: passwordMinLength }))
      return
    }
    if (password !== confirmPassword) {
      setError(t('auth.passwordMismatch'))
      return
    }

    setIsLoading(true)
    try {
      await authApi.resetPassword(token, password)
      toast.success(t('auth.resetSuccess'))
      navigate('/login', { replace: true })
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: unknown }>
      const detail = axiosErr?.response?.data?.detail
      if (isServerUnreachable(err)) setError(t('auth.serverError'))
      else if (axiosErr?.response?.status === 429) setError(t('auth.tooManyAttempts'))
      else if (detail === 'RESET_PASSWORD_BAD_TOKEN') setError(t('auth.resetInvalidToken'))
      else setError(passwordErrorText(t, err, passwordMinLength, t('auth.resetError')))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background px-4">
      <Card className="w-full max-w-[400px] shadow-sm">
        <div className="flex flex-col items-center pt-8 pb-2 px-8">
          <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center mb-4">
            <ShellLogo size={22} className="text-primary" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">
            {invited ? t('auth.resetInvitedTitle') : t('auth.resetTitle')}
          </h1>
          <p className="text-sm text-muted-foreground mt-1 text-center">
            {invited ? t('auth.resetInvitedDescription') : t('auth.resetDescription')}
          </p>
        </div>

        {!token ? (
          <CardContent className="px-8 pt-4">
            <p role="alert" className="p-3 text-sm text-destructive bg-destructive/10 rounded-lg">
              {t('auth.resetMissingToken')}
            </p>
          </CardContent>
        ) : (
          <form onSubmit={handleSubmit}>
            <CardContent className="space-y-4 px-8 pt-4">
              {error && (
                <div role="alert" className="p-3 text-sm text-destructive bg-destructive/10 rounded-lg">
                  {error}
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="new-password" className="text-sm">{t('auth.newPassword')}</Label>
                <Input
                  id="new-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={passwordMinLength}
                  required
                />
                <p className="text-xs text-muted-foreground">{t('passwordPolicy.hint', { min: passwordMinLength })}</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="confirm-password" className="text-sm">{t('auth.confirmPassword')}</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? t('common.loading') : t('auth.resetButton')}
              </Button>
            </CardContent>
          </form>
        )}

        <CardFooter className="flex flex-col gap-2 px-8 pb-8 pt-4">
          <Link to="/login" className="text-sm text-primary font-medium hover:underline">
            {t('auth.backToLogin')}
          </Link>
        </CardFooter>
      </Card>
    </div>
  )
}
