import { describe, expect, it } from 'vitest'

import { render } from '../../test-utils'
import { StatusDot } from './StatusDot'

describe('StatusDot', () => {
  it('renders without crashing', () => {
    const { container } = render(<StatusDot tone="success" />)
    expect(container.querySelector('span')).toBeInTheDocument()
  })
})
