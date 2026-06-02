import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { HeroBackground } from './HeroBackground'

describe('HeroBackground', () => {
  it('renders children', () => {
    render(
      <HeroBackground>
        <h1>Sign in</h1>
      </HeroBackground>,
    )
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})
