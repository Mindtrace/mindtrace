import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MindtraceProvider } from './MindtraceProvider'

describe('MindtraceProvider', () => {
  it('renders children', () => {
    render(
      <MindtraceProvider>
        <span>hello</span>
      </MindtraceProvider>,
    )
    expect(screen.getByText('hello')).toBeInTheDocument()
  })

  it('omits CssBaseline when disabled', () => {
    render(
      <MindtraceProvider disableCssBaseline>
        <span>x</span>
      </MindtraceProvider>,
    )
    expect(screen.getByText('x')).toBeInTheDocument()
  })
})
