import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { NumberBadge } from './NumberBadge'

describe('NumberBadge', () => {
  it('renders its content', () => {
    render(<NumberBadge tone="error">99+</NumberBadge>)
    expect(screen.getByText('99+')).toBeInTheDocument()
  })
})
