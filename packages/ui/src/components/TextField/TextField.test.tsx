import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { TextField } from './TextField'

describe('TextField', () => {
  it('renders label + accepts typed input', async () => {
    const user = userEvent.setup()
    render(<TextField label="Name" />)
    const input = screen.getByLabelText('Name')
    await user.type(input, 'Avery')
    expect(input).toHaveValue('Avery')
  })

  it('fires onChange', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<TextField label="Name" onChange={onChange} />)
    await user.type(screen.getByLabelText('Name'), 'a')
    expect(onChange).toHaveBeenCalled()
  })

  it('shows helper text + error state', () => {
    render(<TextField label="Email" error helperText="Required" />)
    expect(screen.getByText('Required')).toBeInTheDocument()
  })
})
