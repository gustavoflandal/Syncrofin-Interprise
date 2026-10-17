import { beforeEach, describe, expect, it } from 'vitest'
import * as queue from '@/lib/queue'

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

async function reset() {
  // No dedicated "clear all" in the module (it is never needed on-device): drain whatever the
  // previous test left in the in-memory fallback.
  for (const item of await queue.list(SERVER, WORKSPACE)) await queue.remove(item.clientId)
  for (const item of await queue.list(SERVER, null)) await queue.remove(item.clientId)
}

beforeEach(reset)

describe('queue', () => {
  it('starts empty', async () => {
    expect(await queue.list(SERVER, WORKSPACE)).toEqual([])
  })

  it('adds an item as pending, oldest first', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c1' }), photo: null })
    await queue.enqueue({ clientId: 'c2', server: SERVER, workspaceId: WORKSPACE, payload: payload({ client_id: 'c2', description: 'Café' }), photo: null })

    const items = await queue.list(SERVER, WORKSPACE)
    expect(items.map((i) => i.clientId)).toEqual(['c1', 'c2'])
    expect(items[0].status).toBe('pending')
    expect(items[0].error).toBeNull()
  })

  it('keeps items scoped to their server and workspace', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: 'ws-1', payload: payload(), photo: null })
    await queue.enqueue({ clientId: 'c2', server: SERVER, workspaceId: 'ws-2', payload: payload(), photo: null })
    await queue.enqueue({ clientId: 'c3', server: 'https://other.exemplo.com', workspaceId: 'ws-1', payload: payload(), photo: null })

    expect((await queue.list(SERVER, 'ws-1')).map((i) => i.clientId)).toEqual(['c1'])
    expect((await queue.list(SERVER, 'ws-2')).map((i) => i.clientId)).toEqual(['c2'])
    expect((await queue.list('https://other.exemplo.com', 'ws-1')).map((i) => i.clientId)).toEqual(['c3'])

    await queue.remove('c2')
    await queue.remove('c3')
  })

  it('updates status and, for a failure, the reason', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload(), photo: null })
    await queue.setStatus('c1', 'failed', 'Account not found')

    const [item] = await queue.list(SERVER, WORKSPACE)
    expect(item.status).toBe('failed')
    expect(item.error).toBe('Account not found')
  })

  it('removes an item', async () => {
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload(), photo: null })
    await queue.remove('c1')
    expect(await queue.list(SERVER, WORKSPACE)).toEqual([])
  })

  it('saves and reads a photo back', async () => {
    const photo = new Blob(['jpeg-bytes'], { type: 'image/jpeg' })
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload(), photo })

    const [item] = await queue.list(SERVER, WORKSPACE)
    expect(item.photo).not.toBeNull()
    const readBack = await queue.readPhoto(item.photo!)
    expect(readBack).not.toBeNull()
    expect(readBack!.type).toBe('image/jpeg')
  })

  it('notifies subscribers on every mutation', async () => {
    let calls = 0
    const unsubscribe = queue.subscribe(() => (calls += 1))
    await queue.enqueue({ clientId: 'c1', server: SERVER, workspaceId: WORKSPACE, payload: payload(), photo: null })
    await queue.setStatus('c1', 'synced')
    await queue.remove('c1')
    unsubscribe()
    await queue.enqueue({ clientId: 'c2', server: SERVER, workspaceId: WORKSPACE, payload: payload(), photo: null })

    expect(calls).toBe(3) // enqueue, setStatus, remove — not the enqueue after unsubscribing
    await queue.remove('c2')
  })
})
