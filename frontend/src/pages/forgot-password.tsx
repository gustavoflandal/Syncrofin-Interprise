import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MailCheck } from 'lucide-react'
import { auth as authApi } from '@/lib/api'
import { useFeatureFlags } from '@/hooks/use-feature-flags'
import { isServerUnreachable } from '@/lib/auth-errors'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { ShellLogo } from '@/components/shell-logo'
import type { AxiosError } from 'axios'

/**
 * Ask for a password-reset link.
 *
 * The answer is the same whether or not the address has an account, on
 * purpose: the server replies 202 either way, and this page never says which.
 * Otherwise the form is a free way to find out who uses the product.
 */
export default function ForgotPasswordPage() {
  const { t } = useTranslation()
  const { emailEnabled, isLoading: flagsLoading } = useFeatureFlags()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)
    try {
      await authApi.forgotPassword(email.trim())
      setSent(true)
    } catch (err) {
      if (isServerUnreachable(err)) setError(t('auth.serverError'))
      else if ((err as AxiosError)?.response?.status === 429) setError(t('auth.tooManyAttempts'))
      else setError(t('auth.forgotError'))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background px-4">
      <Card className="w-full max-w-[400px] shadow-sm">
        <div className="flex flex-col items-center pt-8 pb-2 px-8">
          <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center mb-4">
            {sent ? <MailCheck size={22} className="text-primary" /> : <ShellLogo size={22} className="text-primary" />}
          </div>
          <h1 className="text-xl font-semibold tracking-tight">{t('auth.forgotTitle')}</h1>
          <p className="text-sm text-muted-foreground mt-1 text-center">
            {sent ? t('auth.resetLinkSent') : t('auth.forgotDescription')}
          </p>
        </div>

        {!flagsLoading && !emailEnabled ? (
          // No mail server: promising a link would be a lie. Say what does work.
          <CardContent className="px-8 pt-4">
            <p role="status" className="p-3 text-sm text-muted-foreground bg-muted rounded-lg">
              {t('auth.emailNotConfigured')}
            </p>
          </CardContent>
        ) : sent ? null : (
          <form onSubmit={handleSubmit}>
            <CardContent className="space-y-4 px-8 pt-4">
              {error && (
                <div role="alert" className="p-3 text-sm text-destructive bg-destructive/10 rounded-lg">
                  {error}
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-sm">{t('auth.email')}</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={isLoading || !email.trim()}>
                {isLoading ? t('common.loading') : t('auth.sendResetLink')}
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
