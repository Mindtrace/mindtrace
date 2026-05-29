/**
 * Storybook-only theme presets. These exist so reviewers can preview the
 * library against multiple brand palettes from the toolbar without
 * editing code. They are NOT exported from the public package — apps
 * build their own themes with `createTheme` (see `Foundations/Theme
 * Builder` for a worked example).
 */

import { createTheme, type Theme } from '@mui/material/styles'

import { darkTheme as builtinDark, lightTheme as builtinLight, getTheme } from '../src/theme'

type PresetInput = {
  mode: 'light' | 'dark'
  primary: string
  secondary?: string
  success?: string
  warning?: string
  error?: string
  info?: string
  backgroundDefault?: string
  backgroundPaper?: string
  textPrimary?: string
  borderRadius?: number
}

function preset(p: PresetInput): Theme {
  const root = getTheme(p.mode)
  return createTheme({
    ...root,
    palette: {
      ...root.palette,
      mode: p.mode,
      primary: { main: p.primary },
      ...(p.secondary ? { secondary: { main: p.secondary } } : {}),
      ...(p.success ? { success: { main: p.success } } : {}),
      ...(p.warning ? { warning: { main: p.warning } } : {}),
      ...(p.error ? { error: { main: p.error } } : {}),
      ...(p.info ? { info: { main: p.info } } : {}),
      background: {
        default: p.backgroundDefault ?? root.palette.background.default,
        paper: p.backgroundPaper ?? root.palette.background.paper,
      },
      text: {
        ...root.palette.text,
        primary: p.textPrimary ?? root.palette.text.primary,
      },
    },
    ...(p.borderRadius !== undefined ? { shape: { borderRadius: p.borderRadius } } : {}),
  })
}

export const themes: Record<string, Theme> = {
  'Mindtrace · Light': builtinLight,
  'Mindtrace · Dark': builtinDark,

  'Slate · Light': preset({
    mode: 'light',
    primary: '#2563EB',
    secondary: '#475569',
    success: '#059669',
    warning: '#D97706',
    error: '#DC2626',
    info: '#0EA5E9',
    backgroundDefault: '#F8FAFC',
    backgroundPaper: '#FFFFFF',
    textPrimary: '#0F172A',
    borderRadius: 6,
  }),

  'Emerald · Light': preset({
    mode: 'light',
    primary: '#15803D',
    secondary: '#3F3F46',
    success: '#16A34A',
    warning: '#CA8A04',
    error: '#B91C1C',
    info: '#0E7490',
    backgroundDefault: '#FAFAF9',
    backgroundPaper: '#FFFFFF',
    textPrimary: '#0C0A09',
    borderRadius: 14,
  }),

  'Amber · Light': preset({
    mode: 'light',
    primary: '#B45309',
    secondary: '#525252',
    success: '#16A34A',
    warning: '#D97706',
    error: '#DC2626',
    info: '#0891B2',
    backgroundDefault: '#FAF5EE',
    backgroundPaper: '#FFFFFF',
    textPrimary: '#1C1917',
    borderRadius: 10,
  }),

  'Indigo · Dark': preset({
    mode: 'dark',
    primary: '#818CF8',
    secondary: '#A1A1AA',
    success: '#4ADE80',
    warning: '#FBBF24',
    error: '#F87171',
    info: '#22D3EE',
    backgroundDefault: '#0B1020',
    backgroundPaper: '#141A2E',
    textPrimary: '#E2E8F0',
    borderRadius: 8,
  }),

  'Cyan · Dark': preset({
    mode: 'dark',
    primary: '#22D3EE',
    secondary: '#A1A1AA',
    success: '#4ADE80',
    warning: '#FBBF24',
    error: '#F87171',
    info: '#67E8F9',
    backgroundDefault: '#0A0A0A',
    backgroundPaper: '#171717',
    textPrimary: '#FAFAFA',
    borderRadius: 12,
  }),
}

export const defaultThemeKey = 'Mindtrace · Light'
