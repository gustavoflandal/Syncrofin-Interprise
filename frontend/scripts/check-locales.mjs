#!/usr/bin/env node
/**
 * Translation completeness report.
 *
 *   npm run i18n:check                 report every locale against en.json
 *   npm run i18n:check -- --strict     exit 1 if a *maintained* locale has gaps
 *   npm run i18n:check -- --list pt-PT print the missing keys of one locale
 *
 * `en` is the source of truth and the runtime fallback, so a key missing from
 * another locale is not a crash: the user sees English for that string. That is
 * exactly why gaps go unnoticed, and why this exists.
 *
 * MAINTAINED lists the locales the project commits to keeping complete. Every
 * other locale is reported but never fails the build. Shrinking or growing the
 * list is the decision the ROADMAP calls "reduce the i18n scope".
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const MAINTAINED = ['en', 'pt-BR', 'es']
const dir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'locales')

// i18next stores plurals as `key_one`, `key_other`, ... and each language needs
// a different set (English two forms, Russian four). Comparing them literally
// would flag every plural as missing or extra; they are one key, "key".
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/

function flatten(obj, prefix = '', out = new Set()) {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) flatten(value, path, out)
    else out.add(path.replace(PLURAL_SUFFIX, ''))
  }
  return out
}

const read = (code) => JSON.parse(readFileSync(join(dir, `${code}.json`), 'utf-8'))
const load = (code) => flatten(read(code))

// Leaf values by (plural-normalised) key, to spot strings still in English.
function leaves(obj, prefix = '', out = new Map()) {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) leaves(value, path, out)
    else out.set(path.replace(PLURAL_SUFFIX, ''), value)
  }
  return out
}
const sourceValues = leaves(read('en'))
const codes = readdirSync(dir).filter((f) => f.endsWith('.json')).map((f) => f.replace('.json', '')).sort()
const source = load('en')

const args = process.argv.slice(2)
const strict = args.includes('--strict')
const listIdx = args.indexOf('--list')
const listCode = listIdx >= 0 ? args[listIdx + 1] : null

const rows = codes
  .filter((c) => c !== 'en')
  .map((code) => {
    const keys = load(code)
    const missing = [...source].filter((k) => !keys.has(k))
    const extra = [...keys].filter((k) => !source.has(k))
    // Present but still English: how a locale gets to "complete" without being
    // translated. Includes legitimately identical strings (brand names, "OK"), so
    // read it as an upper bound on the translation backlog, not an exact count.
    const values = leaves(read(code))
    const untranslated = [...values].filter(([k, v]) => sourceValues.get(k) === v).length
    return { code, missing, extra, untranslated, coverage: 1 - missing.length / source.size }
  })

if (listCode) {
  const row = rows.find((r) => r.code === listCode)
  if (!row) {
    console.error(`Unknown locale: ${listCode}`)
    process.exit(2)
  }
  row.missing.forEach((k) => console.log(k))
  process.exit(0)
}

console.log(`Source: en.json (${source.size} keys)\n`)
console.log('locale   coverage  missing  extra  same-as-en  maintained')
for (const r of rows) {
  const flag = MAINTAINED.includes(r.code) ? 'yes' : 'no'
  console.log(
    `${r.code.padEnd(8)} ${(r.coverage * 100).toFixed(1).padStart(7)}%  ${String(r.missing.length).padStart(7)}  ${String(r.extra.length).padStart(5)}  ${String(r.untranslated).padStart(10)}  ${flag}`,
  )
}

const broken = rows.filter((r) => MAINTAINED.includes(r.code) && (r.missing.length || r.extra.length))
if (broken.length) {
  console.log(`\nMaintained locales out of sync: ${broken.map((r) => r.code).join(', ')}`)
  console.log('Run with --list <locale> to see the keys.')
  if (strict) process.exit(1)
}
