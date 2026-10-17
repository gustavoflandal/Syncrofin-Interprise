import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = path.resolve(import.meta.dirname, '..')
const read = (file: string) => readFileSync(path.join(ROOT, file), 'utf-8')

const nginx = read('default.conf.template')
const headers = read('security-headers.inc.template')

/** The body of every `location ... { ... }` block (none of them nest). */
function locations(config: string): { name: string; body: string }[] {
  return [...config.matchAll(/location\s+([^{]+)\{([^}]*)\}/g)].map((m) => ({ name: m[1].trim(), body: m[2] }))
}

describe('nginx security headers', () => {
  it('has the locations this test expects to guard', () => {
    expect(locations(nginx).map((l) => l.name)).toEqual(expect.arrayContaining(['/api/', '= /sw.js', '= /manifest.webmanifest', '= /index.html', '/']))
  })

  it('includes the header file in every location: nginx drops server-level add_header from any location that sets its own', () => {
    const without = locations(nginx).filter((l) => !l.body.includes('security-headers.inc'))
    expect(without.map((l) => l.name)).toEqual([])
  })

  it('also includes it at the server level, for anything no location covers', () => {
    const serverLevel = nginx.split('location')[0]
    expect(serverLevel).toContain('security-headers.inc')
  })

  it('does not advertise the nginx version', () => {
    expect(nginx).toContain('server_tokens off;')
  })

  it.each([
    'X-Content-Type-Options "nosniff"',
    'X-Frame-Options "DENY"',
    'Referrer-Policy',
    'Permissions-Policy',
    'Cross-Origin-Opener-Policy',
    'Strict-Transport-Security',
    'Content-Security-Policy',
  ])('sends %s', (header) => {
    expect(headers).toContain(header)
  })

  it('sends every header with "always", so error responses carry them too', () => {
    const lines = headers.split('\n').filter((l) => l.startsWith('add_header'))
    expect(lines.length).toBeGreaterThanOrEqual(7)
    for (const line of lines) expect(line).toMatch(/ always;$/)
  })

  it('only sends HSTS behind an HTTPS proxy (an empty value omits the header)', () => {
    expect(nginx).toMatch(/map \$http_x_forwarded_proto \$hsts_header/)
    expect(nginx).toMatch(/default\s+""/)
  })
})

describe('Content-Security-Policy', () => {
  const csp = /add_header Content-Security-Policy "([^"]+)"/.exec(headers)?.[1] ?? ''
  const directive = (name: string) => csp.split(';').map((d) => d.trim()).find((d) => d.startsWith(name + ' ')) ?? ''

  it('is present', () => {
    expect(csp).not.toBe('')
  })

  it('runs only the app\'s own scripts: no inline script, no eval, no other origin', () => {
    expect(directive('script-src')).toBe("script-src 'self'")
  })

  it('cannot be framed, and cannot frame anything but itself and blobs', () => {
    expect(directive('frame-ancestors')).toBe("frame-ancestors 'none'")
    expect(directive('frame-src')).toBe("frame-src 'self' blob:")
  })

  it('fetches from its own origin only, unless the operator adds one on purpose', () => {
    expect(directive('connect-src')).toMatch(/^connect-src 'self' \$\{CSP_CONNECT_EXTRA\}$/)
    expect(directive('default-src')).toBe("default-src 'self'")
    expect(directive('base-uri')).toBe("base-uri 'self'")
    expect(directive('form-action')).toBe("form-action 'self'")
  })

  it('takes fonts from itself (the font ships with the app)', () => {
    expect(directive('font-src')).toBe("font-src 'self'")
  })

  it('has an empty CSP_CONNECT_EXTRA by default in the image', () => {
    expect(read('Dockerfile')).toMatch(/ENV CSP_CONNECT_EXTRA=""/)
  })

  it('is shipped: the image copies the header file next to the server config', () => {
    expect(read('Dockerfile')).toContain('security-headers.inc.template')
  })
})

describe('no request to a third party', () => {
  it('index.html loads nothing from another origin (no Google Fonts)', () => {
    const html = read('index.html')
    expect(html.match(/https?:\/\/[^"' )]+/g) ?? []).toEqual([])
  })

  it('the stylesheet imports no remote font', () => {
    expect(read('src/index.css')).not.toMatch(/https?:\/\//)
  })

  it('does not look for updates on a third-party host unless the operator configures one', () => {
    const hook = read('src/hooks/use-latest-release.ts')
    expect(hook).not.toMatch(/api\.github\.com\/repos\/[^\s'"]+\/releases\/latest'/)
    expect(hook).toContain('VITE_RELEASES_API_URL')
  })
})
