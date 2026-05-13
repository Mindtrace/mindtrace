/**
 * MindtraceProvider — drop-in MUI theme stack.
 *
 *   <MindtraceProvider mode="light">
 *     <App />
 *   </MindtraceProvider>
 *
 * Wraps:
 *   1. `StyledEngineProvider injectFirst` — emotion's <style> tags ship
 *      *before* any user CSS so utility class libraries keep working
 *      during a migration window.
 *   2. `ThemeProvider` with this library's theme (or a caller-supplied one).
 *   3. `CssBaseline enableColorScheme` (opt-out via `disableCssBaseline`).
 */

import CssBaseline from '@mui/material/CssBaseline'
import { StyledEngineProvider, ThemeProvider, type Theme } from '@mui/material/styles'
import type { ReactNode } from 'react'

import { getTheme, type ThemeMode } from '../theme'

export type MindtraceProviderProps = {
  children: ReactNode
  /** Theme variant. Defaults to `'light'`. Ignored when `theme` is supplied. */
  mode?: ThemeMode
  /** Caller-supplied MUI theme. Skip if you just want the built-in theme. */
  theme?: Theme
  /** Skip `<CssBaseline>` if the host app already resets styles. */
  disableCssBaseline?: boolean
}

export function MindtraceProvider({
  children,
  mode = 'light',
  theme,
  disableCssBaseline = false,
}: MindtraceProviderProps) {
  const resolvedTheme = theme ?? getTheme(mode)
  return (
    <StyledEngineProvider injectFirst>
      <ThemeProvider theme={resolvedTheme}>
        {disableCssBaseline ? null : <CssBaseline enableColorScheme />}
        {children}
      </ThemeProvider>
    </StyledEngineProvider>
  )
}
