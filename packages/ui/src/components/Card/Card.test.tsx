import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { Card, CardContent } from './Card'

describe('Card', () => {
  it('renders children', () => {
    render(
      <Card>
        <CardContent>body</CardContent>
      </Card>,
    )
    expect(screen.getByText('body')).toBeInTheDocument()
  })
})
