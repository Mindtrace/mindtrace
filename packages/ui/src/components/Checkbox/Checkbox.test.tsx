import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Checkbox } from './Checkbox'

describe('Checkbox', () => {
  it('renders with a label', () => {
    render(<Checkbox label="Subscribe" />)
    expect(screen.getByLabelText('Subscribe')).toBeInTheDocument()
  })

  it('toggles via click + fires onChange', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<Checkbox label="Subscribe" onChange={onChange} />)
    const cb = screen.getByLabelText('Subscribe')
    await user.click(cb)
    expect(onChange).toHaveBeenCalled()
    expect(cb).toBeChecked()
  })

  it('renders helper text', () => {
    render(<Checkbox label="x" helperText="Description" />)
    expect(screen.getByText('Description')).toBeInTheDocument()
  })
})
