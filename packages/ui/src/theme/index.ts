/**
 * Theme entrypoint — light + dark MUI themes built from the design tokens.
 */

import { createTheme, type Theme } from '@mui/material/styles'

import { buildComponents } from './components'
import { darkPalette, lightPalette } from './palette'
import { buildShadows } from './shadows'
import { shape, spacing } from './shape'
import { typography } from './typography'

export type ThemeMode = 'light' | 'dark'

export function getTheme(mode: ThemeMode): Theme {
  return mode === 'dark' ? darkTheme : lightTheme
}

export const lightTheme: Theme = createTheme({
  palette: lightPalette,
  shape,
  spacing,
  typography,
  shadows: buildShadows('light'),
  components: buildComponents('light'),
  transitions: { duration: { shortest: 120, shorter: 120, short: 200, standard: 200, complex: 320 } },
})

export const darkTheme: Theme = createTheme({
  palette: darkPalette,
  shape,
  spacing,
  typography,
  shadows: buildShadows('dark'),
  components: buildComponents('dark'),
  transitions: { duration: { shortest: 120, shorter: 120, short: 200, standard: 200, complex: 320 } },
})

export { lightPalette, darkPalette, typography, shape, spacing, buildComponents }
export * from './tokens'
