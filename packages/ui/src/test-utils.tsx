/**
 * Test helpers — wrap renders in `MindtraceProvider` so theme tokens are
 * available, and re-export `render` + `screen` + `userEvent` for tests.
 */

import { render as rtlRender, type RenderOptions } from '@testing-library/react'
import { type ReactElement, type ReactNode } from 'react'

import { MindtraceProvider } from './providers'

function Wrapper({ children }: { children: ReactNode }) {
  return <MindtraceProvider>{children}</MindtraceProvider>
}

export function render(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return rtlRender(ui, { wrapper: Wrapper, ...options })
}

export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
