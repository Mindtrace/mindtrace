import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { Avatar } from './Avatar'

describe('Avatar', () => {
  it('derives initials from name', () => {
    render(<Avatar name="Avery Lin" />)
    expect(screen.getByText('AL')).toBeInTheDocument()
  })

  it('derives initials from email when name is missing', () => {
    render(<Avatar email="taylor.kim@example.com" />)
    expect(screen.getByText('TK')).toBeInTheDocument()
  })

  it('uses explicit initials override', () => {
    render(<Avatar name="Avery Lin" initials="XY" />)
    expect(screen.getByText('XY')).toBeInTheDocument()
  })

  it('shows "?" when no subject is given', () => {
    render(<Avatar />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('renders the image when src is provided', () => {
    render(<Avatar src="/me.png" alt="me" name="Avery Lin" />)
    expect(screen.getByRole('img', { name: 'me' })).toBeInTheDocument()
  })
})
