import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import { configure, screen, within } from '@testing-library/react'

import HelpPage from '@/pages/help'
import i18n from '@/lib/i18n'
import { TOPICS } from '@/help/topics'
import { renderWithProviders } from '@/test/utils'

// The manual pages are Markdown modules that vitest transforms the first time they
// are imported, which on a cold CI runner takes longer than testing-library's default
// 1 s wait. Slow to load is not a failure; not loading at all still is.
configure({ asyncUtilTimeout: 8000 })
vi.setConfig({ testTimeout: 20000 })

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

function renderManual(route: string) {
  return renderWithProviders(
    <>
      <Routes>
        <Route path="/help" element={<HelpPage />} />
        <Route path="/help/:topic" element={<HelpPage />} />
        <Route path="*" element={<p>somewhere else</p>} />
      </Routes>
      <Where />
    </>,
    { route },
  )
}

beforeEach(async () => {
  await i18n.changeLanguage('pt-BR')
})
afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('manual page', () => {
  it('opens on the introduction', async () => {
    renderManual('/help')
    expect(await screen.findByRole('heading', { level: 1, name: /Introdução ao SyncroFin/ })).toBeInTheDocument()
  })

  it('shows the topic in the URL', async () => {
    renderManual('/help/contas')
    expect(await screen.findByRole('heading', { level: 1, name: /Contas/ })).toBeInTheDocument()
  })

  it('lists every topic in the table of contents, by section', async () => {
    renderManual('/help/painel')
    const toc = await screen.findByRole('navigation', { name: /Conteúdo do manual/ })
    // Titles arrive once the manual has loaded.
    // Loading all 27 pages is slower under a busy full-suite run than alone.
    await within(toc).findByRole('link', { name: /Transações/ }, { timeout: 8000 })
    expect(within(toc).getAllByRole('link')).toHaveLength(TOPICS.length)
    expect(within(toc).getByRole('link', { name: /Painel/ })).toHaveAttribute('aria-current', 'page')
  })

  it('sends an unknown topic to the index instead of a blank page', async () => {
    renderManual('/help/not-a-topic')
    expect(await screen.findByRole('heading', { level: 1, name: /Introdução ao SyncroFin/ })).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/help$/)
  })

  it('walks to the next and the previous topic', async () => {
    const { user } = renderManual('/help/introducao')
    await screen.findByRole('heading', { level: 1, name: /Introdução/ })

    await user.click(await screen.findByRole('link', { name: /Próximo|Next/ }))
    expect(screen.getByTestId('where')).toHaveTextContent('/help/primeiros-passos')

    await user.click(await screen.findByRole('link', { name: /Anterior|Previous/ }))
    expect(screen.getByTestId('where')).toHaveTextContent('/help/introducao')
  })

  it('follows a link from one topic to another inside the manual', async () => {
    const { user } = renderManual('/help/cobrancas')
    const article = await screen.findByRole('heading', { level: 1, name: /Cobranças/ })
    expect(article).toBeInTheDocument()

    // A "help:<topic>" link in the text (not the one in the index) becomes a real route.
    const link = await within(screen.getByRole('main')).findByRole('link', { name: 'Conciliação' })
    expect(link).toHaveAttribute('href', '/help/conciliacao')
    await user.click(link)
    expect(await screen.findByRole('heading', { level: 1, name: /Conciliação/ })).toBeInTheDocument()
  })

  it('searches without caring about accents', async () => {
    const { user } = renderManual('/help')
    await screen.findByRole('heading', { level: 1, name: /Introdução/ })

    await user.type(screen.getByRole('searchbox'), 'conciliacao')
    // Several topics mention it; the one named for it ranks first.
    const results = await screen.findAllByRole('button', { name: /Conciliação/ }, { timeout: 8000 })
    expect(results[0]).toHaveTextContent(/^Conciliação/)
    await user.click(results[0])

    expect(screen.getByTestId('where')).toHaveTextContent('/help/conciliacao')
    // Picking a result clears the search, and the topic is shown.
    expect(screen.getByRole('searchbox')).toHaveValue('')
  })

  it('says so when nothing matches', async () => {
    const { user } = renderManual('/help')
    await screen.findByRole('heading', { level: 1, name: /Introdução/ })
    await user.type(screen.getByRole('searchbox'), 'zzzzqqqq')
    expect(await screen.findByText(/zzzzqqqq/)).toBeInTheDocument()
  })

  it('warns when the manual is not translated into the language in use', async () => {
    await i18n.changeLanguage('es')
    renderManual('/help/contas')
    expect(await screen.findByRole('note')).toBeInTheDocument()
  })
})
