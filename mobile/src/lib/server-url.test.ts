import { describe, expect, it } from 'vitest'
import { normalizeServerUrl } from '@/lib/server-url'

describe('normalizeServerUrl', () => {
  it('adds https to a bare host', () => {
    expect(normalizeServerUrl('syncrofin.exemplo.com')).toEqual({ ok: true, url: 'https://syncrofin.exemplo.com' })
  })

  it('drops the trailing slash and keeps a sub-path', () => {
    expect(normalizeServerUrl('https://exemplo.com/')).toEqual({ ok: true, url: 'https://exemplo.com' })
    expect(normalizeServerUrl('https://exemplo.com/syncrofin/')).toEqual({ ok: true, url: 'https://exemplo.com/syncrofin' })
  })

  it('trims spaces and keeps the port', () => {
    expect(normalizeServerUrl('  https://exemplo.com:8443  ')).toEqual({ ok: true, url: 'https://exemplo.com:8443' })
  })

  it('refuses plain http on the internet, where a password would travel in the clear', () => {
    expect(normalizeServerUrl('http://syncrofin.exemplo.com')).toEqual({ ok: false, error: 'insecure' })
    expect(normalizeServerUrl('http://192.168.1.10:3000')).toEqual({ ok: false, error: 'insecure' })
  })

  it('accepts http only for the emulator and localhost (development)', () => {
    expect(normalizeServerUrl('http://10.0.2.2:8000')).toEqual({ ok: true, url: 'http://10.0.2.2:8000' })
    expect(normalizeServerUrl('http://localhost:8000')).toEqual({ ok: true, url: 'http://localhost:8000' })
  })

  it('rejects empty and malformed input, and other schemes', () => {
    expect(normalizeServerUrl('   ')).toEqual({ ok: false, error: 'empty' })
    expect(normalizeServerUrl('https://')).toEqual({ ok: false, error: 'invalid' })
    expect(normalizeServerUrl('ftp://exemplo.com')).toEqual({ ok: false, error: 'invalid' })
    expect(normalizeServerUrl('javascript://exemplo.com')).toEqual({ ok: false, error: 'invalid' })
  })
})
