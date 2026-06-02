/**
 * Custom shadow ramp. MUI's default 25-step ramp is heavy for this UI;
 * we use 5 distinct elevations and zero everything else so over-shadowing
 * is impossible.
 */

import type { Shadows } from '@mui/material/styles'

const NONE = 'none'

export function buildShadows(mode: 'light' | 'dark'): Shadows {
  if (mode === 'dark') {
    const e1 = '0 1px 2px 0 rgba(0,0,0,0.4)'
    const e2 = '0 2px 6px -1px rgba(0,0,0,0.5), 0 1px 2px 0 rgba(0,0,0,0.4)'
    const e3 = '0 6px 14px -4px rgba(0,0,0,0.55), 0 2px 4px -1px rgba(0,0,0,0.4)'
    const e4 = '0 12px 28px -8px rgba(0,0,0,0.6), 0 6px 12px -6px rgba(0,0,0,0.45)'
    const e5 = '0 24px 48px -12px rgba(0,0,0,0.7), 0 12px 24px -8px rgba(0,0,0,0.5)'
    return [NONE, e1, e2, e2, e3, e3, e3, e4, e4, e4, e4, e4, e4, e4, e4, e4, e5, e5, e5, e5, e5, e5, e5, e5, e5] as unknown as Shadows
  }
  const e1 = '0 1px 2px 0 rgba(15,23,42,0.06)'
  const e2 = '0 2px 6px -1px rgba(15,23,42,0.08), 0 1px 2px 0 rgba(15,23,42,0.05)'
  const e3 = '0 6px 14px -4px rgba(15,23,42,0.1), 0 2px 4px -1px rgba(15,23,42,0.06)'
  const e4 = '0 12px 28px -8px rgba(15,23,42,0.14), 0 6px 12px -6px rgba(15,23,42,0.08)'
  const e5 = '0 24px 48px -12px rgba(15,23,42,0.18), 0 12px 24px -8px rgba(15,23,42,0.1)'
  return [NONE, e1, e2, e2, e3, e3, e3, e4, e4, e4, e4, e4, e4, e4, e4, e4, e5, e5, e5, e5, e5, e5, e5, e5, e5] as unknown as Shadows
}
