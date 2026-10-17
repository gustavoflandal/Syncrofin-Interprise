import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { auth } from '@/lib/api'
import { MFA_REQUIRED_EVENT } from '@/lib/mfa-events'

export const MFA_STATUS_KEY = ['mfa-status'] as const

/**
 * Where this session stands with the instance's second-factor rule.
 *
 * The server is what enforces it (every route answers 403 to a session that owes a second factor);
 * this only lets the screen say so instead of showing a page full of errors.
 */
export function useMfaStatus(enabled: boolean) {
  const queryClient = useQueryClient()

  useEffect(() => {
    const refetch = () => void queryClient.invalidateQueries({ queryKey: MFA_STATUS_KEY })
    window.addEventListener(MFA_REQUIRED_EVENT, refetch)
    return () => window.removeEventListener(MFA_REQUIRED_EVENT, refetch)
  }, [queryClient])

  return useQuery({
    queryKey: MFA_STATUS_KEY,
    queryFn: () => auth.mfaStatus(),
    enabled,
    staleTime: 60_000,
    retry: false,
  })
}
