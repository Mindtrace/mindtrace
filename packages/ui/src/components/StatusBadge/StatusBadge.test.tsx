import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders the label', () => {
    render(<StatusBadge tone="success" label="Healthy" />)
    expect(screen.getByText('Healthy')).toBeInTheDocument()
  })
})
