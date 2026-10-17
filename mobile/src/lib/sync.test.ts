import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, type Api, type Transaction } from '@/lib/api'
import * as queue from '@/lib/queue'
import { drainQueue } from '@/lib/sync'

const SERVER = 'https://fin.exemplo.com'
const WORKSPACE = 'ws-1'

const payload = (over: Record<string, unknown> = {}) => ({
  description: 'Almoço',
  amount: '35.00',
  date: '2026-09-10',
  type: 'debit' as const,
  account_id: 'acc-1',
  client_id: 'client-1',
  ...over,
})

const txn = (id: string, description: string): Transaction => ({
  id,
  description,
  amount: '35.00',
  date: '2026-09-10',
  type: 'debit',
  currency: 'BRL',
  status: 'posted',
  attachment_count: 0,
})

function fakeApi(over: Partial<Api> = {}): Api {
  return {
    login: vi.fn(),
    verifyTwoFactor: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
    mfaStatus: vi.fn(),
    workspaces: vi.fn(),
    currentWorkspace: vi.fn(),
    accounts: vi.fn(),
    categories: vi.fn(),
    transactions: vi.fn(),
    createTransaction: vi.fn(),
    attachments: vi.fn(),
    uploadAttachment: vi.fn(),
    attachmentDataUrl: vi.fn(),
    ...over,
  } as Api
}

async function clear() {
  for (const item of await queue.list(SERVER, WORKSPACE)) await queue.remove(item.clientId)
}

beforeEach(clear)

describe('drainQueue', () => {
  it('syncs a pending item and uploads its photo', async () => {
    const photo = new Blob(['jpeg'], { type: 'image/jpeg' })
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c1' }), photo })
    const createTransaction = vi.fn().mockResolvedValue(txn('new-1', 'Almoço'))
    const uploadAttachment = vi.fn().mockResolvedValue({ id: 'att-1' })
    const api = fakeApi({ createTransaction, uploadAttachment })

    await drainQueue(api, SERVER, WORKSPACE)

    expect(createTransaction).toHaveBeenCalledWith(expect.objectContaining({ client_id: 'c1' }))
    expect(uploadAttachment).toHaveBeenCalledWith('new-1', expect.any(Blob), expect.any(String))
    const [item] = await queue.list(SERVER, WORKSPACE)
    expect(item.status).toBe('synced')
  })

  it('marks synced even when the photo upload itself fails', async () => {
    const photo = new Blob(['jpeg'], { type: 'image/jpeg' })
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c1' }), photo })
    const api = fakeApi({
      createTransaction: vi.fn().mockResolvedValue(txn('new-1', 'Almoço')),
      uploadAttachment: vi.fn().mockRejectedValue(new ApiError(500, 'disk full')),
    })

    await drainQueue(api, SERVER, WORKSPACE)

    expect((await queue.list(SERVER, WORKSPACE))[0].status).toBe('synced')
  })

  it('stops on a network error and leaves the item pending, for the next trigger to retry', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c1' }), photo: null })
    await queue.enqueue({ clientId: 'c2', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c2' }), photo: null })
    const createTransaction = vi.fn().mockRejectedValue(new NetworkError('offline'))
    const api = fakeApi({ createTransaction })

    await drainQueue(api, SERVER, WORKSPACE)

    expect(createTransaction).toHaveBeenCalledTimes(1) // never reached c2
    const items = await queue.list(SERVER, WORKSPACE)
    expect(items.map((i) => i.status)).toEqual(['pending', 'pending'])
  })

  it('stops (without marking failed) when the session expired offline, so it resumes on the next sign-in', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c1' }), photo: null })
    const api = fakeApi({ createTransaction: vi.fn().mockRejectedValue(new ApiError(401, 'Unauthorized')) })

    await drainQueue(api, SERVER, WORKSPACE)

    expect((await queue.list(SERVER, WORKSPACE))[0].status).toBe('pending')
  })

  it('marks a genuine rejection failed with the reason, and still tries the next item', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c1' }), photo: null })
    await queue.enqueue({ clientId: 'c2', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c2' }), photo: null })
    const createTransaction = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(400, 'Account not found'))
      .mockResolvedValueOnce(txn('new-2', 'Almoço'))
    const api = fakeApi({ createTransaction })

    await drainQueue(api, SERVER, WORKSPACE)

    expect(createTransaction).toHaveBeenCalledTimes(2)
    const items = await queue.list(SERVER, WORKSPACE)
    expect(items[0]).toMatchObject({ status: 'failed', error: 'Account not found' })
    expect(items[1].status).toBe('synced')
  })

  it('skips an item already marked synced (a re-run while one is still in flight)', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c1' }), photo: null })
    await queue.setStatus('c1', 'synced')
    const createTransaction = vi.fn()

    await drainQueue(fakeApi({ createTransaction }), SERVER, WORKSPACE)

    expect(createTransaction).not.toHaveBeenCalled()
  })
})
