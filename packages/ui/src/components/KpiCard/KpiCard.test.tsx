import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { KpiCard } from './KpiCard'

describe('KpiCard', () => {
  it('renders label + value', () => {
    render(<KpiCard label="Active users" value="12,840" />)
    expect(screen.getByText('Active users')).toBeInTheDocument()
    expect(screen.getByText('12,840')).toBeInTheDocument()
  })

  it('shows "—" when loading', () => {
    render(<KpiCard label="x" value="1" loading />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
