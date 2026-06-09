import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { RadioGroup } from './Radio'

describe('RadioGroup', () => {
  it('renders options + picks one', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <RadioGroup
        label="Plan"
        defaultValue="free"
        onChange={onChange}
        options={[
          { value: 'free', label: 'Free' },
          { value: 'pro', label: 'Pro' },
        ]}
      />,
    )
    await user.click(screen.getByLabelText('Pro'))
    expect(onChange).toHaveBeenCalledWith('pro')
  })

  it('renders helper text', () => {
    render(
      <RadioGroup label="Plan" helperText="Pick one" options={[{ value: 'a', label: 'A' }]} />,
    )
    expect(screen.getByText('Pick one')).toBeInTheDocument()
  })
})
