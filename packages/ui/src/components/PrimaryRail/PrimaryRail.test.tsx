import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { PrimaryRail } from './PrimaryRail'

const sections = [
  {
    label: 'Workspace',
    items: [
      { href: '/', label: 'Dashboard' },
      { href: '/projects', label: 'Projects' },
    ],
  },
]

describe('PrimaryRail', () => {
  it('renders nav items', () => {
    render(<PrimaryRail sections={sections} />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Projects')).toBeInTheDocument()
  })

  it('toggles collapsed state via the toggle button', async () => {
    const onCollapsedChange = vi.fn()
    const user = userEvent.setup()
    render(<PrimaryRail sections={sections} onCollapsedChange={onCollapsedChange} />)
    await user.click(screen.getByRole('button', { name: /collapse navigation/i }))
    expect(onCollapsedChange).toHaveBeenCalledWith(true)
  })

  it('uses renderLink when provided', () => {
    const renderLink = vi.fn((_item, content) => <span data-testid="custom">{content}</span>)
    render(<PrimaryRail sections={sections} renderLink={renderLink} />)
    expect(renderLink).toHaveBeenCalled()
    expect(screen.getAllByTestId('custom').length).toBeGreaterThan(0)
  })
})
