import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth-context'
import { refreshAccessToken } from '@/lib/access-token'
import { Card, CardContent } from '@/components/ui/card'
import { ShellLogo } from '@/components/shell-logo'

/**
 * The server ends the OIDC login with a redirect here and an `httpOnly` refresh cookie: no token
 * travels in the URL (where it would land in history, logs and referrers). This page trades the
 * cookie for an access token and goes in.
 */
export default function OIDCCallbackPage() {
  const navigate = useNavigate()
  const { loginWithToken } = useAuth()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    void refreshAccessToken().then((accessToken) => {
      if (cancelled) return
      if (!accessToken) {
        setFailed(true)
        return
      }
      loginWithToken(accessToken)
      navigate('/', { replace: true })
    })
    return () => {
      cancelled = true
    }
  }, [loginWithToken, navigate])

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background px-4">
      <Card className="w-full max-w-[380px] shadow-sm">
        <CardContent className="flex flex-col items-center gap-4 px-8 py-8 text-center">
          <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center">
            <ShellLogo size={22} className="text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Signing you in…</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {failed ? 'OIDC login did not start a session.' : 'Completing secure OIDC login.'}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
