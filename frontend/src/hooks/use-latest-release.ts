import { useQuery } from '@tanstack/react-query'
import { useAutoUpdateCheck } from '@/hooks/use-auto-update-check'

/**
 * Where to look for a newer version. Empty (the default) means the browser makes no such request: it would
 * tell a third party (GitHub) that this instance exists and when someone opens it, and a private repository
 * has nothing to answer with anyway. Set VITE_RELEASES_API_URL at build time (for example
 * https://api.github.com/repos/<owner>/<repo>/releases/latest) and add its origin to CSP_CONNECT_EXTRA.
 */
const LATEST_RELEASE_URL: string = import.meta.env.VITE_RELEASES_API_URL ?? ''

const SIX_HOURS = 1000 * 60 * 60 * 6

export type LatestRelease = {
  tagName: string
  htmlUrl: string
}

async function fetchLatestRelease(): Promise<LatestRelease | null> {
  const response = await fetch(LATEST_RELEASE_URL, {
    headers: { Accept: 'application/vnd.github+json' },
  })
  if (!response.ok) return null
  const payload = (await response.json()) as {
    tag_name?: string
    html_url?: string
  }
  if (!payload.tag_name || !payload.html_url) return null
  return { tagName: payload.tag_name, htmlUrl: payload.html_url }
}

export function useLatestRelease() {
  const { enabled } = useAutoUpdateCheck()
  return useQuery<LatestRelease | null>({
    queryKey: ['latest-release', LATEST_RELEASE_URL],
    queryFn: fetchLatestRelease,
    enabled: enabled && LATEST_RELEASE_URL !== '',
    staleTime: SIX_HOURS,
    gcTime: SIX_HOURS,
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}
