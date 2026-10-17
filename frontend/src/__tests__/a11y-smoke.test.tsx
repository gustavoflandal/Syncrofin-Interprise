import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { renderWithProviders } from '@/test/utils'

expect.extend(matchers)

// Smoke tests only: jsdom has no layout, so colour-contrast is disabled here and covered by the
// design-token choices in index.css instead.
const axeOptions = { rules: { 'color-contrast': { enabled: false } } }

describe('accessibility smoke (axe)', () => {
  it('has no violations for buttons, including an icon button with a label', async () => {
    const { container } = renderWithProviders(
      <main>
        <Button>Save</Button>
        <Button aria-label="Close panel" size="icon">
          x
        </Button>
      </main>,
    )
    expect(await axe(container, axeOptions)).toHaveNoViolations()
  })

  it('has no violations for a labelled form field', async () => {
    const { container } = renderWithProviders(
      <main>
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" />
      </main>,
    )
    expect(await axe(container, axeOptions)).toHaveNoViolations()
  })

  it('has no violations for an open dialog', async () => {
    renderWithProviders(
      <Dialog open>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete account</DialogTitle>
            <DialogDescription>This cannot be undone.</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>,
    )
    const dialog = await screen.findByRole('dialog')
    expect(await axe(dialog, axeOptions)).toHaveNoViolations()
  })

  it('has no violations for a table with column headers', async () => {
    const { container } = renderWithProviders(
      <main>
        <table>
          <caption>Accounts</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Balance</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Checking</td>
              <td>10</td>
            </tr>
          </tbody>
        </table>
      </main>,
    )
    expect(await axe(container, axeOptions)).toHaveNoViolations()
  })
})
