import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Switch } from './Switch'

describe('Switch', () => {
  it('toggles on click', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<Switch label="Email me" onChange={onChange} />)
    const sw = screen.getByLabelText('Email me')
    await user.click(sw)
    expect(onChange).toHaveBeenCalled()
    expect(sw).toBeChecked()
  })
})
