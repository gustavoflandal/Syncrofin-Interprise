import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { Fingerprint, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/contexts/auth-context'
import { useLocalAuthEnabled } from '@/hooks/use-local-auth'
import { MFA_STATUS_KEY } from '@/hooks/use-mfa-status'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ShellLogo } from '@/components/shell-logo'
import { TwoFactorSetup } from '@/components/two-factor-setup'
import { PasskeyManagementDialog } from '@/components/passkey-management-dialog'

/**
 * What a person sees, instead of the app, when the instance requires a second factor and this
 * session has none. The only things they can do are the two ways to get one, and sign out: the
 * server refuses everything else until they have.
 */
export function MfaEnrollmentGate() {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const queryClient = useQueryClient()
  const localAuthEnabled = useLocalAuthEnabled()
  const [twoFactorOpen, setTwoFactorOpen] = useState(false)
  const [passkeysOpen, setPasskeysOpen] = useState(false)

  // Finishing either dialog may have made this session verified: ask the server again.
  const recheck = () => void queryClient.invalidateQueries({ queryKey: MFA_STATUS_KEY })

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-[460px] shadow-sm">
        <CardContent className="flex flex-col gap-5 px-8 py-8">
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10">
              <ShellLogo size={22} className="text-primary" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">{t('auth.mfaRequiredTitle')}</h1>
            <p className="text-sm text-muted-foreground">{t('auth.mfaRequiredBody')}</p>
          </div>

          <div className="flex flex-col gap-2">
            <Button onClick={() => setTwoFactorOpen(true)} className="w-full">
              <ShieldCheck className="mr-2 h-4 w-4" />
              {t('auth.mfaSetUpApp')}
            </Button>
            <Button variant="outline" onClick={() => setPasskeysOpen(true)} className="w-full">
              <Fingerprint className="mr-2 h-4 w-4" />
              {t('auth.mfaUsePasskey')}
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">{t('auth.mfaRequiredHint')}</p>

          <Button variant="link" onClick={logout} className="self-center text-muted-foreground">
            {t('auth.logout')}
          </Button>
        </CardContent>
      </Card>

      <TwoFactorSetup
        open={twoFactorOpen}
        onClose={() => {
          setTwoFactorOpen(false)
          recheck()
        }}
        localAuthEnabled={localAuthEnabled}
      />
      <PasskeyManagementDialog
        open={passkeysOpen}
        onClose={() => {
          setPasskeysOpen(false)
          recheck()
        }}
        localAuthEnabled={localAuthEnabled}
      />
    </div>
  )
}
