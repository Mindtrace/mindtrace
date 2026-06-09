import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Button } from './Button'

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Save</Button>)
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('fires onClick', async () => {
    const onClick = vi.fn()
    const user = userEvent.setup()
    render(<Button onClick={onClick}>Save</Button>)
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('is disabled when prop is set', () => {
    render(
      <Button onClick={() => {}} disabled>
        Save
      </Button>,
    )
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })
})
