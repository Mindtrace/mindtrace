/**
 * Typography scale.
 *
 * Standard MUI variants plus six custom variants for dense operational
 * surfaces:
 *   - `subheading`    — h3-equivalent inline heading
 *   - `sectionLabel`  — small uppercase section label
 *   - `metricLabel`   — KPI tile label
 *   - `tinyLabel`     — micro uppercase label
 *   - `microCaption`  — smaller caption
 *   - `mono`          — IDs, hashes, code
 *   - `label`         — small uppercase label (alias of metricLabel kept for back-compat)
 */

import type { TypographyVariantsOptions, TypographyStyle } from '@mui/material/styles'
import { fontFamily, fontWeight } from './tokens'

declare module '@mui/material/styles' {
  interface TypographyVariants {
    subheading: TypographyStyle
    sectionLabel: TypographyStyle
    metricLabel: TypographyStyle
    tinyLabel: TypographyStyle
    microCaption: TypographyStyle
    mono: TypographyStyle
    label: TypographyStyle
  }
  interface TypographyVariantsOptions {
    subheading?: TypographyStyle
    sectionLabel?: TypographyStyle
    metricLabel?: TypographyStyle
    tinyLabel?: TypographyStyle
    microCaption?: TypographyStyle
    mono?: TypographyStyle
    label?: TypographyStyle
  }
}

declare module '@mui/material/Typography' {
  interface TypographyPropsVariantOverrides {
    subheading: true
    sectionLabel: true
    metricLabel: true
    tinyLabel: true
    microCaption: true
    mono: true
    label: true
  }
}

export const typography: TypographyVariantsOptions = {
  fontFamily: fontFamily.sans,
  fontWeightRegular: fontWeight.regular,
  fontWeightMedium: fontWeight.medium,
  fontWeightBold: fontWeight.semibold,

  h1: { fontWeight: fontWeight.semibold, fontSize: '2rem', letterSpacing: '-0.02em' },
  h2: { fontWeight: fontWeight.semibold, fontSize: '1.75rem', letterSpacing: '-0.02em' },
  h3: { fontWeight: fontWeight.semibold, fontSize: '1.5rem', letterSpacing: '-0.01em' },
  h4: { fontWeight: fontWeight.semibold, fontSize: '1.375rem', letterSpacing: '-0.01em' },
  h5: { fontWeight: fontWeight.semibold, fontSize: '1.125rem' },
  h6: { fontWeight: fontWeight.semibold, fontSize: '1rem' },
  subtitle1: { fontWeight: fontWeight.medium, fontSize: '0.9375rem' },
  subtitle2: {
    fontWeight: fontWeight.semibold,
    fontSize: '0.78rem',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  body1: { fontSize: '0.9375rem', lineHeight: 1.55 },
  body2: { fontSize: '0.8125rem', lineHeight: 1.5 },
  caption: { fontSize: '0.78rem', lineHeight: 1.4 },
  button: { textTransform: 'none', fontWeight: fontWeight.medium },

  subheading: {
    fontFamily: fontFamily.sans,
    fontWeight: fontWeight.semibold,
    fontSize: '0.95rem',
    letterSpacing: '-0.005em',
    lineHeight: 1.3,
  },
  sectionLabel: {
    fontFamily: fontFamily.sans,
    fontWeight: fontWeight.bold,
    fontSize: '0.75rem',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    lineHeight: 1.3,
  },
  metricLabel: {
    fontFamily: fontFamily.sans,
    fontWeight: fontWeight.semibold,
    fontSize: '0.78rem',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    lineHeight: 1.3,
  },
  tinyLabel: {
    fontFamily: fontFamily.sans,
    fontWeight: fontWeight.bold,
    fontSize: '0.72rem',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    lineHeight: 1.3,
  },
  microCaption: {
    fontFamily: fontFamily.sans,
    fontWeight: fontWeight.regular,
    fontSize: '0.78rem',
    lineHeight: 1.4,
  },
  mono: {
    fontFamily: fontFamily.mono,
    fontSize: '0.72rem',
    fontWeight: fontWeight.medium,
    lineHeight: 1.4,
  },
  // Back-compat alias for our existing `label` variant — same shape as metricLabel.
  label: {
    fontFamily: fontFamily.sans,
    fontWeight: fontWeight.semibold,
    fontSize: '0.78rem',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    lineHeight: 1.3,
  },
}

export const FONT_FAMILY_SANS = fontFamily.sans
export const FONT_FAMILY_MONO = fontFamily.mono
