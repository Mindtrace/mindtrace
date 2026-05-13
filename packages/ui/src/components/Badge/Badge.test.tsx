import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { Badge } from './Badge'

describe('Badge', () => {
  it('renders its label', () => {
    render(<Badge label="active" />)
    expect(screen.getByText('active')).toBeInTheDocument()
  })
})
