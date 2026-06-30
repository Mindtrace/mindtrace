import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { SeverityBadge } from './SeverityBadge'

describe('SeverityBadge', () => {
  it('renders Critical', () => {
    render(<SeverityBadge severity="critical" />)
    expect(screen.getByText('Critical')).toBeInTheDocument()
  })

  it('respects labelOverride', () => {
    render(<SeverityBadge severity="major" labelOverride="HIGH" />)
    expect(screen.getByText('HIGH')).toBeInTheDocument()
  })
})
