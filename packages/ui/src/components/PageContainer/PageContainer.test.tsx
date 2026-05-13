import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { PageContainer } from './PageContainer'

describe('PageContainer', () => {
  it('renders children', () => {
    render(
      <PageContainer>
        <div>body</div>
      </PageContainer>,
    )
    expect(screen.getByText('body')).toBeInTheDocument()
  })
})
