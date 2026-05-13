import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Select, type SelectOption } from './Select'

const options: SelectOption[] = [
  { value: 'sm', label: 'Small' },
  { value: 'md', label: 'Medium' },
  { value: 'lg', label: 'Large' },
]

describe('Select', () => {
  it('renders the default value', () => {
    render(<Select label="Size" options={options} defaultValue="md" />)
    expect(screen.getByText('Medium')).toBeInTheDocument()
  })

  it('opens and picks an option', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<Select label="Size" options={options} defaultValue="md" onChange={onChange} />)
    await user.click(screen.getByRole('combobox'))
    const option = await screen.findByRole('option', { name: 'Large' })
    await user.click(option)
    expect(onChange).toHaveBeenCalled()
  })

  it('renders helper text', () => {
    render(<Select label="Tier" options={options} helperText="Affects pricing" />)
    expect(screen.getByText('Affects pricing')).toBeInTheDocument()
  })
})
