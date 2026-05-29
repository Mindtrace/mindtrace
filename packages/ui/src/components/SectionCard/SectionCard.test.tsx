import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { SectionCard } from './SectionCard'

describe('SectionCard', () => {
  it('renders title, subtitle, and body', () => {
    render(
      <SectionCard title="Webhooks" subtitle="HTTP endpoints">
        <div>body</div>
      </SectionCard>,
    )
    expect(screen.getByText('Webhooks')).toBeInTheDocument()
    expect(screen.getByText('HTTP endpoints')).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })
})
