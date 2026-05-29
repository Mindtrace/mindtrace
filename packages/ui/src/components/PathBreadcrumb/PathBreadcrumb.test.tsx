import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { PathBreadcrumb } from './PathBreadcrumb'

describe('PathBreadcrumb', () => {
  it('renders read-only segments', () => {
    render(
      <PathBreadcrumb
        segments={[
          { id: 'a', label: 'Acme' },
          { id: 'b', label: 'Engineering' },
        ]}
      />,
    )
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('Engineering')).toBeInTheDocument()
  })

  it('pops the dropdown and picks an item', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(
      <PathBreadcrumb
        segments={[
          {
            id: 'org',
            label: 'Acme',
            items: [
              { id: 'a', label: 'Acme' },
              { id: 'b', label: 'Globex' },
            ],
            currentId: 'a',
            onSelect,
          },
        ]}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Acme/i }))
    const option = await screen.findByRole('button', { name: /Globex/i })
    await user.click(option)
    expect(onSelect).toHaveBeenCalledWith('b')
  })
})
