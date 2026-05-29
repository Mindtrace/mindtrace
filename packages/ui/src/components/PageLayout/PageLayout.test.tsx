import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { PageLayout } from './PageLayout'

describe('PageLayout', () => {
  it('composes PageHeader + body', () => {
    render(
      <PageLayout title="Members" description="People">
        <div>body</div>
      </PageLayout>,
    )
    expect(screen.getByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })

  it('renders tabs when provided', () => {
    render(
      <PageLayout
        title="X"
        tabs={{
          defaultValue: 'a',
          tabs: [
            { value: 'a', label: 'A', content: <div>A body</div> },
            { value: 'b', label: 'B', content: <div>B body</div> },
          ],
        }}
      />,
    )
    expect(screen.getByText('A body')).toBeInTheDocument()
  })
})
