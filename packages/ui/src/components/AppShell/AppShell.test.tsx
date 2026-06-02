import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders sidebar / topBar / main slots', () => {
    render(
      <AppShell sidebar={<aside>nav</aside>} topBar={<header>bar</header>}>
        <main>body</main>
      </AppShell>,
    )
    expect(screen.getByText('nav')).toBeInTheDocument()
    expect(screen.getByText('bar')).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })

  it('hides slots when embedded', () => {
    render(
      <AppShell embedded sidebar={<aside>nav</aside>} topBar={<header>bar</header>}>
        <main>body</main>
      </AppShell>,
    )
    expect(screen.queryByText('nav')).not.toBeInTheDocument()
    expect(screen.queryByText('bar')).not.toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })
})
