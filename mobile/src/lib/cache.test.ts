import { beforeEach, describe, expect, it } from 'vitest'
import { loadLookups, saveLookups } from '@/lib/cache'

const SERVER = 'https://fin.exemplo.com'

const accounts = [
  { id: 'acc-1', name: 'Corrente', type: 'checking', currency: 'BRL' },
  { id: 'acc-2', name: 'Poupança', type: 'savings', currency: 'BRL' },
]

const categories = [
  { id: 'cat-1', name: 'Alimentação' },
  { id: 'cat-2', name: 'Transporte', color: '#3366cc' },
]

beforeEach(async () => {
  // Save + overwrite with empty to reset the in-memory store between tests.
  await saveLookups(SERVER, 'ws-1', [], [])
  await saveLookups(SERVER, 'ws-2', [], [])
  await saveLookups(SERVER, null, [], [])
})

describe('cache', () => {
  it('returns null when nothing is cached', async () => {
    expect(await loadLookups('https://other.com', 'ws-x')).toBeNull()
  })

  it('saves and loads accounts and categories', async () => {
    await saveLookups(SERVER, 'ws-1', accounts, categories)
    const cached = await loadLookups(SERVER, 'ws-1')
    expect(cached).not.toBeNull()
    expect(cached!.accounts).toEqual(accounts)
    expect(cached!.categories).toEqual(categories)
  })

  it('keeps caches scoped to server + workspace', async () => {
    await saveLookups(SERVER, 'ws-1', accounts, categories)
    await saveLookups(SERVER, 'ws-2', [accounts[0]], [])

    const ws1 = await loadLookups(SERVER, 'ws-1')
    const ws2 = await loadLookups(SERVER, 'ws-2')
    expect(ws1!.accounts).toHaveLength(2)
    expect(ws2!.accounts).toHaveLength(1)
    expect(ws2!.categories).toEqual([])
  })

  it('handles null workspace', async () => {
    await saveLookups(SERVER, null, accounts, categories)
    const cached = await loadLookups(SERVER, null)
    expect(cached!.accounts).toEqual(accounts)
  })

  it('overwrites on save', async () => {
    await saveLookups(SERVER, 'ws-1', accounts, categories)
    await saveLookups(SERVER, 'ws-1', [accounts[0]], [])
    const cached = await loadLookups(SERVER, 'ws-1')
    expect(cached!.accounts).toHaveLength(1)
    expect(cached!.categories).toEqual([])
  })
})
