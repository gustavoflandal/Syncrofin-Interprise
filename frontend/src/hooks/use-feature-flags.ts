import { useQuery } from '@tanstack/react-query'
import { info } from '@/lib/api'
import { DEFAULT_MIN_PASSWORD_LENGTH } from '@/lib/password-policy'

/**
 * Reads /api/info once per session. Optional modules (agents, etc.) check
 * the returned flags so their nav items / routes stay hidden when the
 * server has the feature disabled.
 */
export function useFeatureFlags() {
  const { data, isLoading } = useQuery({
    queryKey: ['app-info'],
    queryFn: () => info.get(),
    staleTime: 1000 * 60 * 60,
  })
  return {
    isLoading,
    agentsEnabled: !!data?.features?.agents,
    emailEnabled: !!data?.features?.email,
    /** The shortest password the server accepts. */
    passwordMinLength: data?.password_min_length ?? DEFAULT_MIN_PASSWORD_LENGTH,
  }
}
