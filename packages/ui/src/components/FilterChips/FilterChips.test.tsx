import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { FilterChips } from './FilterChips'

const options = [
  { id: 'a', label: 'A' },
  { id: 'b', label: 'B' },
]

describe('FilterChips', () => {
  it('toggles selection', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<FilterChips options={options} selected={[]} onChange={onChange} />)
    await user.click(screen.getByText('A'))
    expect(onChange).toHaveBeenCalledWith(['a'])
  })

  it('replaces selection when exclusive', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<FilterChips options={options} selected={['a']} exclusive onChange={onChange} />)
    await user.click(screen.getByText('B'))
    expect(onChange).toHaveBeenCalledWith(['b'])
  })
})
