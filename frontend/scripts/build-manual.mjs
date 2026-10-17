#!/usr/bin/env node
/**
 * Builds docs/MANUAL.md, the whole manual as one Markdown file, from the same
 * pages the app shows (frontend/src/help/content/pt-BR/*.md).
 *
 *   npm run manual:build      write docs/MANUAL.md
 *   npm run manual:check      exit 1 if docs/MANUAL.md is out of date (used by CI)
 *
 * The pages are the source of truth; the file is generated so that it can be
 * read on GitHub, printed or sent to someone without an installation. Editing it
 * by hand is pointless, which is what the check is for.
 *
 * The order and the sections come from src/help/topics.ts, the same list the app's
 * table of contents uses, so the two cannot disagree.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const LANGUAGE = 'pt-BR'
const OUT = join(root, '..', 'docs', 'MANUAL.md')

const read = (path) => readFileSync(path, 'utf-8').replace(/\r\n/g, '\n')

// The topics, in order, with their section. topics.ts is TypeScript, and this
// script is plain Node, so read it as text: the entries are one per line.
const topicsSource = read(join(root, 'src', 'help', 'topics.ts'))
const topics = [...topicsSource.matchAll(/\{\s*id:\s*'([a-z0-9-]+)',\s*section:\s*'([a-z]+)'/g)].map((m) => ({
  id: m[1],
  section: m[2],
}))
const sectionOrder = [...topicsSource.matchAll(/export const HELP_SECTIONS[^=]*=\s*\[([^\]]*)\]/g)][0]?.[1]
  .match(/'([a-z]+)'/g)
  ?.map((s) => s.replaceAll("'", ''))
if (topics.length === 0 || !sectionOrder) {
  console.error('build-manual: could not read the topics from src/help/topics.ts')
  process.exit(2)
}

const sectionTitles = JSON.parse(read(join(root, 'src', 'locales', `${LANGUAGE}.json`))).help.section

/** A page as it appears in the single file: links rewritten, headings demoted. */
function render(id, markdown) {
  let inFence = false
  const lines = markdown.split('\n').map((line) => {
    if (/^```/.test(line)) inFence = !inFence
    if (inFence || !/^#{1,5}\s/.test(line)) return line
    return `#${line}`
  })
  const body = lines
    .join('\n')
    // help:<topic> is the app's link to another page; here it is an anchor.
    .replace(/\]\(help:([a-z0-9-]+)\)/g, '](#$1)')
    // The manual's own index.
    .replace(/\]\(\/help\)/g, '](#indice)')
    // Screenshots live in the app's public folder; from docs/ that is one level up.
    .replace(/\]\(\/manual-img\//g, '](../frontend/public/manual-img/')
    .trim()
  return `<a id="${id}"></a>\n\n${body}\n`
}

const pages = new Map()
for (const { id } of topics) {
  const file = join(root, 'src', 'help', 'content', LANGUAGE, `${id}.md`)
  if (!existsSync(file)) {
    console.error(`build-manual: ${id}.md is missing`)
    process.exit(2)
  }
  pages.set(id, read(file))
}

const title = (markdown) => /^#\s+(.+?)\s*$/m.exec(markdown)?.[1] ?? ''

const out = []
out.push('<!-- Gerado por `npm run manual:build` (frontend/). Não edite: edite as páginas em')
out.push('     frontend/src/help/content/pt-BR/ e gere de novo. -->')
out.push('')
out.push('# Manual do SyncroFin')
out.push('')
out.push('O mesmo conteúdo da ajuda dentro do sistema (botão **?** em cada tela), em um só arquivo.')
out.push('')
out.push('<a id="indice"></a>')
out.push('')
out.push('## Índice')
out.push('')
for (const section of sectionOrder) {
  const inSection = topics.filter((t) => t.section === section)
  if (inSection.length === 0) continue
  out.push(`**${sectionTitles[section]}**`)
  out.push('')
  for (const { id } of inSection) out.push(`- [${title(pages.get(id))}](#${id})`)
  out.push('')
}

for (const { id } of topics) {
  out.push('---')
  out.push('')
  out.push(render(id, pages.get(id)))
}

const result = out.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd() + '\n'

if (process.argv.includes('--check')) {
  const current = existsSync(OUT) ? read(OUT) : ''
  if (current !== result) {
    console.error('docs/MANUAL.md is out of date. Run `npm run manual:build` (in frontend/) and commit it.')
    process.exit(1)
  }
  console.log(`docs/MANUAL.md is up to date (${topics.length} pages).`)
} else {
  writeFileSync(OUT, result, { encoding: 'utf-8' })
  console.log(`docs/MANUAL.md written (${topics.length} pages, ${result.length} characters).`)
}
