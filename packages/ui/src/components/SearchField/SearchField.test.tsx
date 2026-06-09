import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { SearchField } from './SearchField'

describe('SearchField', () => {
  it('fires onChange with the typed value', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<SearchField value="" onChange={onChange} />)
    await user.type(screen.getByPlaceholderText('Search…'), 'abc')
    expect(onChange).toHaveBeenCalled()
  })

  it('clears via the clear button', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<SearchField value="abc" onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /clear/i }))
    expect(onChange).toHaveBeenLastCalledWith('')
  })
})
