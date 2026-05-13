import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { AppBar } from './AppBar'

describe('AppBar', () => {
  it('renders brand / center / actions slots', () => {
    render(<AppBar brand={<div>brand</div>} center={<div>center</div>} actions={<div>actions</div>} />)
    expect(screen.getByText('brand')).toBeInTheDocument()
    expect(screen.getByText('center')).toBeInTheDocument()
    expect(screen.getByText('actions')).toBeInTheDocument()
  })
})
