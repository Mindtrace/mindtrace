import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { UserMenu } from './UserMenu'

describe('UserMenu', () => {
  it('shows the identity in the dropdown', async () => {
    const user = userEvent.setup()
    render(<UserMenu name="Avery Lin" email="avery@example.com" onSignOut={() => {}} />)
    await user.click(screen.getByRole('button', { name: /account menu/i }))
    expect(await screen.findByText('Avery Lin')).toBeInTheDocument()
    expect(screen.getByText('avery@example.com')).toBeInTheDocument()
  })

  it('fires onSignOut', async () => {
    const onSignOut = vi.fn()
    const user = userEvent.setup()
    render(<UserMenu name="Avery" onSignOut={onSignOut} />)
    await user.click(screen.getByRole('button', { name: /account menu/i }))
    await user.click(await screen.findByText(/sign out/i))
    expect(onSignOut).toHaveBeenCalled()
  })
})
