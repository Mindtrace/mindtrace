import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})

// JSDOM doesn't ship a working clipboard API; tests that exercise
// `useCopyToClipboard` stub it via `Object.defineProperty(navigator, …)`.
