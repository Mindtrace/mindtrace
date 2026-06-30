import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { FormSection } from './FormSection'

describe('FormSection', () => {
  it('renders title, description, and children', () => {
    render(
      <FormSection title="Profile" description="How you appear to others">
        <div>body</div>
      </FormSection>,
    )
    expect(screen.getByText('Profile')).toBeInTheDocument()
    expect(screen.getByText('How you appear to others')).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })
})
