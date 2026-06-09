import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders title + description', () => {
    render(<EmptyState title="Empty" description="Nothing here yet." />)
    expect(screen.getByText('Empty')).toBeInTheDocument()
    expect(screen.getByText('Nothing here yet.')).toBeInTheDocument()
  })
})
