import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { Mono } from './Mono'

describe('Mono', () => {
  it('renders its content', () => {
    render(<Mono>abc123</Mono>)
    expect(screen.getByText('abc123')).toBeInTheDocument()
  })
})
