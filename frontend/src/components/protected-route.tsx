import { Navigate } from 'react-router-dom'
import { useAuth } from '@/contexts/auth-context'
import { useMfaStatus } from '@/hooks/use-mfa-status'
import { MfaEnrollmentGate } from '@/components/mfa-enrollment-gate'

function Spinner() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
    </div>
  )
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth()
  // The server holds back a session that owes the instance a second factor; this is what tells the
  // person why, and lets them fix it. An unreachable answer never blocks the screen: the server still does.
  const mfa = useMfaStatus(!!token && !isLoading)

  if (isLoading || (token && mfa.isPending)) return <Spinner />

  if (!token) {
    return <Navigate to="/login" replace />
  }

  if (mfa.data?.blocked) return <MfaEnrollmentGate />

  return <>{children}</>
}
