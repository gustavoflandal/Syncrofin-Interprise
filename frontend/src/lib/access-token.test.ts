import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'

import { getAccessToken, refreshAccessToken, setAccessToken } from '@/lib/access-token'

vi.mock('axios', () => ({ default: { post: vi.fn() } }))
const post = vi.mocked(axios.post)

beforeEach(() => {
  vi.clearAllMocks()
  setAccessToken(null)
})

describe('refreshAccessToken', () => {
  it('trades the cookie for an access token and keeps it in memory only', async () => {
    post.mockResolvedValue({ data: { access_token: 'fresh' } })

    expect(await refreshAccessToken()).toBe('fresh')
    expect(getAccessToken()).toBe('fresh')
    expect(post).toHaveBeenCalledWith('/api/auth/refresh')
    expect(Object.values({ ...localStorage })).not.toContain('fresh')
  })

  it('shares one request among callers that ask together (the refresh token rotates on use)', async () => {
    let resolve!: (value: unknown) => void
    post.mockReturnValue(new Promise((r) => (resolve = r)) as never)

    const calls = [refreshAccessToken(), refreshAccessToken(), refreshAccessToken()]
    resolve({ data: { access_token: 'one' } })

    expect(await Promise.all(calls)).toEqual(['one', 'one', 'one'])
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('asks again on the next need, not only once', async () => {
    post.mockResolvedValueOnce({ data: { access_token: 'a' } }).mockResolvedValueOnce({ data: { access_token: 'b' } })

    expect(await refreshAccessToken()).toBe('a')
    expect(await refreshAccessToken()).toBe('b')
  })

  it('answers null, and forgets the token, when there is no session', async () => {
    setAccessToken('stale')
    post.mockRejectedValue(new Error('401'))

    expect(await refreshAccessToken()).toBeNull()
    expect(getAccessToken()).toBeNull()
  })
})
