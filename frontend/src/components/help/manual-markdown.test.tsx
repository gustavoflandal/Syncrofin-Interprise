import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

import { IMAGE_PREFIX, ManualMarkdown, TOPIC_LINK } from '@/components/help/manual-markdown'
import { renderWithProviders } from '@/test/utils'

const MARKDOWN = `# Título

Texto com [outro tópico](help:contas), [uma tela](/transactions), [um tópico que não existe](help:nao-existe)
e [um site](https://example.com).

<script>alert(1)</script>
`

describe('TOPIC_LINK', () => {
  it('matches only help:<id>', () => {
    expect(TOPIC_LINK.exec('help:contas')?.[1]).toBe('contas')
    expect(TOPIC_LINK.test('help:')).toBe(false)
    expect(TOPIC_LINK.test('https://help:contas')).toBe(false)
  })
})

describe('ManualMarkdown', () => {
  it('turns links into router links, plain text or new-tab links, by kind', () => {
    renderWithProviders(<ManualMarkdown>{MARKDOWN}</ManualMarkdown>)

    expect(screen.getByRole('link', { name: 'outro tópico' })).toHaveAttribute('href', '/help/contas')
    expect(screen.getByRole('link', { name: 'uma tela' })).toHaveAttribute('href', '/transactions')

    const external = screen.getByRole('link', { name: 'um site' })
    expect(external).toHaveAttribute('href', 'https://example.com')
    expect(external).toHaveAttribute('target', '_blank')
    expect(external).toHaveAttribute('rel', expect.stringContaining('noopener'))

    // A link to a topic that does not exist is not left dead.
    expect(screen.queryByRole('link', { name: 'um tópico que não existe' })).not.toBeInTheDocument()
    expect(screen.getByText('um tópico que não existe')).toBeInTheDocument()
  })

  it('never renders raw HTML from a page', () => {
    const { container } = renderWithProviders(<ManualMarkdown>{MARKDOWN}</ManualMarkdown>)
    expect(container.querySelector('script')).toBeNull()
  })

  it('tells the caller when an in-manual link is followed', async () => {
    const onNavigate = vi.fn()
    const { user } = renderWithProviders(<ManualMarkdown onNavigate={onNavigate}>{MARKDOWN}</ManualMarkdown>)
    await user.click(screen.getByRole('link', { name: 'outro tópico' }))
    expect(onNavigate).toHaveBeenCalledTimes(1)
  })

  it('keeps the same DOM when the parent re-renders, so scroll and selection survive', () => {
    // Regression: with the element types declared inline in the render, every re-render
    // (for example when the manual index finishes loading) rebuilt the whole page.
    const { rerender } = renderWithProviders(<ManualMarkdown onNavigate={() => {}}>{MARKDOWN}</ManualMarkdown>)
    const heading = screen.getByRole('heading', { level: 1, name: 'Título' })
    const link = screen.getByRole('link', { name: 'outro tópico' })

    rerender(<ManualMarkdown onNavigate={() => {}}>{MARKDOWN}</ManualMarkdown>)

    expect(screen.getByRole('heading', { level: 1, name: 'Título' })).toBe(heading)
    expect(screen.getByRole('link', { name: 'outro tópico' })).toBe(link)
    expect(heading).toBeInTheDocument()
  })
})

describe('ManualMarkdown images', () => {
  it('shows a screenshot from the app\'s own folder, with its description as a caption', () => {
    renderWithProviders(<ManualMarkdown>{`![Tela de login](${IMAGE_PREFIX}app-celular/login.png)`}</ManualMarkdown>)
    const image = screen.getByRole('img', { name: 'Tela de login' })
    expect(image).toHaveAttribute('src', `${IMAGE_PREFIX}app-celular/login.png`)
    expect(image).toHaveAttribute('loading', 'lazy')
    // The description is also printed under the picture, for a reader who cannot see it.
    expect(screen.getByText('Tela de login')).toBeInTheDocument()
  })

  it.each([
    ['another site', 'https://example.com/x.png'],
    ['a data: URL', 'data:image/png;base64,AAAA'],
    ['a path outside the folder', '/favicon.ico'],
    ['a path that climbs out of it', `${IMAGE_PREFIX}../secret.png`],
  ])('never loads %s: only the description is shown', (_label, src) => {
    const { container } = renderWithProviders(<ManualMarkdown>{`![descrição](${src})`}</ManualMarkdown>)
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('descrição')).toBeInTheDocument()
  })
})
