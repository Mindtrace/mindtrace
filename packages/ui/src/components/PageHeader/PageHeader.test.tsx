import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { PageHeader } from './PageHeader'

describe('PageHeader', () => {
  it('renders title, description, breadcrumbs', () => {
    render(
      <PageHeader
        title="Members"
        description="People with access"
        breadcrumbs={[{ label: 'Settings' }, { label: 'Members' }]}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(screen.getByText('People with access')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })
})
