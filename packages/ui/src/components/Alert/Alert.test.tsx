import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Alert } from './Alert'

describe('Alert', () => {
  it('renders message', () => {
    render(<Alert severity="info">All good</Alert>)
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('fires onClose when dismiss is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <Alert severity="info" onClose={onClose}>
        msg
      </Alert>,
    )
    await user.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
