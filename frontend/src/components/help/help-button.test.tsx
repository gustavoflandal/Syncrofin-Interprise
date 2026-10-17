import { afterEach, describe, expect, it, vi } from 'vitest'
import { Link, Route, Routes } from 'react-router-dom'
import { configure, screen, waitFor, within } from '@testing-library/react'

import { HelpButton } from '@/components/help/help-button'
import i18n from '@/lib/i18n'
import { isTypingTarget } from '@/help/typing'
import { renderWithProviders } from '@/test/utils'

// The manual pages are Markdown modules that vitest transforms the first time they
// are imported, which on a cold CI runner takes longer than testing-library's default
// 1 s wait. Slow to load is not a failure; not loading at all still is.
configure({ asyncUtilTimeout: 8000 })
vi.setConfig({ testTimeout: 20000 })

function App() {
  return (
    <>
      <Link to="/budgets">go to budgets</Link>
      <input aria-label="a field" />
      <Routes>
        <Route path="*" element={null} />
      </Routes>
      <HelpButton />
    </>
  )
}

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('isTypingTarget', () => {
  it('is true for fields and false for everything else', () => {
    expect(isTypingTarget(document.createElement('input'))).toBe(true)
    expect(isTypingTarget(document.createElement('textarea'))).toBe(true)
    expect(isTypingTarget(document.createElement('select'))).toBe(true)
    expect(isTypingTarget(document.createElement('button'))).toBe(false)
    expect(isTypingTarget(null)).toBe(false)
  })

  it('treats a rich-text box as a field', () => {
    const div = document.createElement('div')
    div.setAttribute('role', 'textbox')
    expect(isTypingTarget(div)).toBe(true)
  })
})

describe('HelpButton', () => {
  it('is on the screen and closed at first', () => {
    renderWithProviders(<App />, { route: '/transactions' })
    expect(screen.getByTestId('help-button')).toBeInTheDocument()
    expect(screen.queryByTestId('help-panel')).not.toBeInTheDocument()
  })

  it('opens the page about the screen the reader is on', async () => {
    await i18n.changeLanguage('pt-BR')
    const { user } = renderWithProviders(<App />, { route: '/transactions' })
    await user.click(screen.getByTestId('help-button'))

    const panel = await screen.findByTestId('help-panel')
    expect(await within(panel).findByRole('heading', { level: 1, name: /Transações/i })).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: /manual completo/i })).toHaveAttribute('href', '/help/transacoes')
    // Written in the reader's language: no "not translated" notice.
    expect(within(panel).queryByRole('note')).not.toBeInTheDocument()
  })

  it('says so when the manual is not translated into the reader’s language', async () => {
    const { user } = renderWithProviders(<App />, { route: '/budgets' })
    await user.click(screen.getByTestId('help-button'))

    const panel = await screen.findByTestId('help-panel')
    expect(await within(panel).findByRole('note')).toHaveTextContent(/portuguese/i)
    expect(within(panel).getByRole('link', { name: /full manual/i })).toHaveAttribute('href', '/help/orcamentos')
  })

  it('opens the introduction on a screen nobody mapped, not nothing', async () => {
    const { user } = renderWithProviders(<App />, { route: '/some/new/screen' })
    await user.click(screen.getByTestId('help-button'))
    const panel = await screen.findByTestId('help-panel')
    expect(within(panel).getByRole('link', { name: /full manual/i })).toHaveAttribute('href', '/help/introducao')
  })

  it('opens with ? and closes with ? again', async () => {
    const { user } = renderWithProviders(<App />, { route: '/goals' })
    await user.keyboard('?')
    expect(await screen.findByTestId('help-panel')).toBeInTheDocument()

    await user.keyboard('?')
    await waitFor(() => expect(screen.queryByTestId('help-panel')).not.toBeInTheDocument())
  })

  it('opens with F1', async () => {
    const { user } = renderWithProviders(<App />, { route: '/goals' })
    await user.keyboard('{F1}')
    expect(await screen.findByTestId('help-panel')).toBeInTheDocument()
  })

  it('does not steal a ? typed into a field', async () => {
    const { user } = renderWithProviders(<App />, { route: '/goals' })
    await user.click(screen.getByLabelText('a field'))
    await user.keyboard('what?')
    expect(screen.queryByTestId('help-panel')).not.toBeInTheDocument()
    expect(screen.getByLabelText('a field')).toHaveValue('what?')
  })

  it('closes with Escape and with the close button', async () => {
    const { user } = renderWithProviders(<App />, { route: '/goals' })
    await user.click(screen.getByTestId('help-button'))
    await screen.findByTestId('help-panel')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByTestId('help-panel')).not.toBeInTheDocument())

    await user.click(screen.getByTestId('help-button'))
    await user.click(await screen.findByRole('button', { name: /close/i }))
    await waitFor(() => expect(screen.queryByTestId('help-panel')).not.toBeInTheDocument())
  })

  it('does not appear inside the manual or on a public invoice link', () => {
    const manual = renderWithProviders(<App />, { route: '/help/painel' })
    expect(screen.queryByTestId('help-button')).not.toBeInTheDocument()
    manual.unmount()

    renderWithProviders(<App />, { route: '/i/some-token' })
    expect(screen.queryByTestId('help-button')).not.toBeInTheDocument()
  })

  it('stays out of the way on the public pages that are not help', () => {
    renderWithProviders(<App />, { route: '/login' })
    expect(screen.getByTestId('help-button')).toBeInTheDocument()
  })

  it('ignores ? and F1 where there is no help', async () => {
    const { user } = renderWithProviders(<App />, { route: '/help' })
    await user.keyboard('?')
    await user.keyboard('{F1}')
    expect(screen.queryByTestId('help-panel')).not.toBeInTheDocument()
  })

  it('closes when the reader moves to another screen', async () => {
    const { user } = renderWithProviders(<App />, { route: '/goals' })
    await user.click(screen.getByTestId('help-button'))
    const panel = await screen.findByTestId('help-panel')

    await user.click(within(panel).getByRole('link', { name: /full manual/i }))
    await waitFor(() => expect(screen.queryByTestId('help-panel')).not.toBeInTheDocument())
  })
})
