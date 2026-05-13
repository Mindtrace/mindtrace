/**
 * MUI palette options for light + dark modes.
 *
 * Purple brand accent with zinc-toned neutrals. Hierarchy maintained
 * through deliberate contrast steps.
 */

import type { PaletteOptions } from '@mui/material/styles'
import { brand, neutral, semantic } from './tokens'

declare module '@mui/material/styles' {
  interface Palette {
    surface: { subtle: string; muted: string; strong: string }
    border: { subtle: string; default: string; strong: string }
  }
  interface PaletteOptions {
    surface?: { subtle: string; muted: string; strong: string }
    border?: { subtle: string; default: string; strong: string }
  }
}

export const lightPalette: PaletteOptions = {
  mode: 'light',
  primary: {
    main: brand.purple[600],
    light: brand.purple[500],
    dark: brand.purple[700],
    contrastText: '#FFFFFF',
  },
  secondary: {
    main: neutral[700],
    light: neutral[600],
    dark: neutral[800],
    contrastText: '#FFFFFF',
  },
  background: {
    default: neutral[50],
    paper: '#FFFFFF',
  },
  divider: neutral[200],
  text: {
    primary: neutral[900],
    secondary: neutral[500],
    disabled: neutral[400],
  },
  action: {
    hover: 'rgba(24, 24, 27, 0.04)',
    selected: 'rgba(124, 58, 237, 0.08)',
    disabled: neutral[300],
    disabledBackground: neutral[100],
    focus: 'rgba(124, 58, 237, 0.14)',
  },
  error: semantic.error,
  warning: semantic.warning,
  success: semantic.success,
  info: semantic.info,
  grey: neutral as unknown as PaletteOptions['grey'],
  surface: { subtle: neutral[50], muted: neutral[100], strong: neutral[200] },
  border: {
    subtle: 'rgba(0,0,0,0.06)',
    default: 'rgba(0,0,0,0.10)',
    strong: 'rgba(0,0,0,0.18)',
  },
}

export const darkPalette: PaletteOptions = {
  mode: 'dark',
  primary: {
    main: brand.purple[400],
    light: brand.purple[300],
    dark: brand.purple[500],
    contrastText: '#FFFFFF',
  },
  secondary: {
    main: neutral[300],
    light: neutral[200],
    dark: neutral[400],
    contrastText: neutral[950],
  },
  background: {
    default: neutral[950],
    paper: neutral[900],
  },
  divider: 'rgba(255, 255, 255, 0.08)',
  text: {
    primary: neutral[50],
    secondary: neutral[400],
    disabled: neutral[600],
  },
  action: {
    hover: 'rgba(255, 255, 255, 0.04)',
    selected: 'rgba(167, 139, 250, 0.12)',
    disabled: neutral[700],
    disabledBackground: neutral[800],
    focus: 'rgba(167, 139, 250, 0.20)',
  },
  error: { main: '#F87171', light: '#FCA5A5', dark: '#EF4444' },
  warning: { main: '#FBBF24', light: '#FCD34D', dark: '#F59E0B' },
  success: { main: '#4ADE80', light: '#86EFAC', dark: '#22C55E' },
  info: { main: '#22D3EE', light: '#67E8F9', dark: '#06B6D4' },
  grey: neutral as unknown as PaletteOptions['grey'],
  surface: { subtle: '#111116', muted: neutral[800], strong: neutral[700] },
  border: {
    subtle: 'rgba(255,255,255,0.06)',
    default: 'rgba(255,255,255,0.12)',
    strong: 'rgba(255,255,255,0.20)',
  },
}
