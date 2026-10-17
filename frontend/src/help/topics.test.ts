import { readFileSync, readdirSync, existsSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { DEFAULT_TOPIC, HELP_SECTIONS, TOPICS, TOPIC_IDS, helpAvailableAt, isTopicId, topicForPath } from '@/help/topics'
import { SOURCE_LANGUAGE, titleOf } from '@/help/loader'
import { IMAGE_PREFIX } from '@/components/help/manual-markdown'

const SRC = path.resolve(import.meta.dirname, '..')
const CONTENT = path.join(import.meta.dirname, 'content')
const PUBLIC = path.resolve(SRC, '..', 'public')

const read = (file: string) => readFileSync(file, 'utf-8')
const appSource = read(path.join(SRC, 'App.tsx'))

// Routes that are intentionally not part of the manual.
const NO_TOPIC = new Set(['*', '/i/:token', '/help', '/help/:topic'])

const routes = [...appSource.matchAll(/<Route\s+path="([^"]+)"/g)].map((m) => m[1])

// A URL for a router pattern: "/groups/:id" -> "/groups/1".
const concrete = (pattern: string) => pattern.replace(/:[A-Za-z]+/g, '1')

describe('help topics', () => {
  it('has unique ids and only known sections', () => {
    expect(new Set(TOPIC_IDS).size).toBe(TOPIC_IDS.length)
    for (const topic of TOPICS) expect(HELP_SECTIONS).toContain(topic.section)
  })

  it('reads the router, so the test is not vacuous', () => {
    expect(routes.length).toBeGreaterThan(20)
    expect(routes).toContain('/transactions')
  })

  it.each(routes.filter((r) => !NO_TOPIC.has(r)))('route %s has a topic of its own', (route) => {
    // A new screen without a manual page is exactly what this catches: the help
    // button would silently open the introduction on a screen nobody documented.
    expect(topicForPath(concrete(route))).not.toBe(DEFAULT_TOPIC)
  })

  it('has no stale path: every pattern maps to a real route', () => {
    const known = new Set(routes)
    for (const topic of TOPICS) {
      for (const pattern of topic.paths) expect(known, `${topic.id} -> ${pattern}`).toContain(pattern)
    }
  })

  it('claims each path for exactly one topic', () => {
    const seen = new Map<string, string>()
    for (const topic of TOPICS) {
      for (const pattern of topic.paths) {
        expect(seen.get(pattern), `${pattern} claimed by ${seen.get(pattern)} and ${topic.id}`).toBeUndefined()
        seen.set(pattern, topic.id)
      }
    }
  })

  it('falls back to the introduction for an unknown screen', () => {
    expect(topicForPath('/nowhere/at/all')).toBe(DEFAULT_TOPIC)
  })

  it('does not treat a longer URL as a shorter route', () => {
    expect(topicForPath('/accounts/9')).toBe('contas')
    expect(topicForPath('/groups/9')).toBe('grupos')
    expect(topicForPath('/agents/connections')).toBe('agentes')
  })

  it('knows its own ids', () => {
    expect(isTopicId('painel')).toBe(true)
    expect(isTopicId('nope')).toBe(false)
    expect(isTopicId(undefined)).toBe(false)
  })

  it('offers no help inside the manual or on a public invoice link', () => {
    expect(helpAvailableAt('/help')).toBe(false)
    expect(helpAvailableAt('/help/painel')).toBe(false)
    expect(helpAvailableAt('/i/abc123')).toBe(false)
    expect(helpAvailableAt('/')).toBe(true)
    expect(helpAvailableAt('/login')).toBe(true)
    // "/invoices" starts with "/i" but is a screen of the product.
    expect(helpAvailableAt('/invoices')).toBe(true)
    expect(helpAvailableAt('/import')).toBe(true)
  })
})

describe('manual content', () => {
  const dir = path.join(CONTENT, SOURCE_LANGUAGE)
  const file = (id: string) => path.join(dir, `${id}.md`)

  it.each(TOPIC_IDS)('%s has a written page with a title', (id) => {
    expect(existsSync(file(id)), `${id}.md is missing`).toBe(true)
    const markdown = read(file(id))
    expect(titleOf(markdown), `${id}.md needs a "# Title" first line`).not.toBe('')
    expect(markdown.trimStart().startsWith('# ')).toBe(true)
    expect(markdown.length).toBeGreaterThan(500)
  })

  it('has no page that the table of contents does not list', () => {
    const files = readdirSync(dir).filter((f) => f.endsWith('.md')).map((f) => f.replace(/\.md$/, ''))
    expect(files.filter((id) => !TOPIC_IDS.includes(id))).toEqual([])
  })

  it('only translates topics that exist', () => {
    for (const language of readdirSync(CONTENT)) {
      const ids = readdirSync(path.join(CONTENT, language)).map((f) => f.replace(/\.md$/, ''))
      expect(ids.filter((id) => !TOPIC_IDS.includes(id)), language).toEqual([])
    }
  })

  it('links only to topics and screens that exist', () => {
    const broken: string[] = []
    for (const id of TOPIC_IDS) {
      const markdown = read(file(id))
      // Images are checked by their own test below.
      for (const [, target] of markdown.matchAll(/(?<!!)\[[^\]]*\]\(([^)\s]+)\)/g)) {
        if (target.startsWith('help:')) {
          if (!isTopicId(target.slice(5))) broken.push(`${id}: ${target}`)
        } else if (target.startsWith('/')) {
          if (!routes.includes(target)) broken.push(`${id}: ${target}`)
        } else if (!/^https?:\/\//.test(target)) {
          broken.push(`${id}: ${target}`)
        }
      }
    }
    expect(broken).toEqual([])
  })

  it('shows only screenshots that ship with the app, each with a description', () => {
    const problems: string[] = []
    for (const id of TOPIC_IDS) {
      for (const [, alt, target] of read(file(id)).matchAll(/!\[([^\]]*)\]\(([^)\s]+)\)/g)) {
        if (!alt.trim()) problems.push(`${id}: ${target} has no description (alt text)`)
        if (!target.startsWith(IMAGE_PREFIX) || target.includes('..')) {
          problems.push(`${id}: ${target} is not under ${IMAGE_PREFIX}`)
        } else if (!existsSync(path.join(PUBLIC, target))) {
          problems.push(`${id}: ${target} does not exist in frontend/public`)
        }
      }
    }
    expect(problems).toEqual([])
  })

  it('has no screenshot in public/manual-img that no page uses', () => {
    const used = new Set<string>()
    for (const id of TOPIC_IDS) {
      for (const [, target] of read(file(id)).matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)) used.add(target)
    }
    const shipped: string[] = []
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name)
        if (entry.isDirectory()) walk(full)
        else shipped.push('/' + path.relative(PUBLIC, full).split(path.sep).join('/'))
      }
    }
    walk(path.join(PUBLIC, IMAGE_PREFIX))
    expect(shipped.filter((file) => !used.has(file))).toEqual([])
  })

  it('is reachable: every topic is linked from another one or is a first stop', () => {
    const linked = new Set<string>()
    for (const id of TOPIC_IDS) {
      for (const [, target] of read(file(id)).matchAll(/\]\(help:([a-z0-9-]+)\)/g)) {
        if (target !== id) linked.add(target)
      }
    }
    const orphans = TOPIC_IDS.filter((id) => !linked.has(id) && id !== DEFAULT_TOPIC)
    // The table of contents lists everything, so an unlinked topic is not lost;
    // this only flags the ones no other page ever points readers to.
    expect(orphans).toEqual([])
  })
})
