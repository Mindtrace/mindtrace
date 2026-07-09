/**
 * NumberBadge — tiny pill for inline counts.
 *
 * Two variants:
 *   - `'subtle'` (default) — high-contrast `text.primary` on a tinted
 *     background. Tone is carried by the bg hue; text stays legible.
 *   - `'solid'` — `contrastText` on a solid tone background. Use when
 *     the count is the visual focus (e.g. error counters on tab titles).
 *
 * Distinct from MUI's `Badge`, which is for absolute-positioned overlays
 * on icons.
 */

import Box from '@mui/material/Box'
import { alpha, useTheme } from '@mui/material/styles'
import type { ReactNode } from 'react'

import type { StatusTone } from '../StatusDot/StatusDot'

export type NumberBadgeProps = {
  children: ReactNode
  tone?: StatusTone
  variant?: 'subtle' | 'solid'
}

export function NumberBadge({ children, tone = 'neutral', variant = 'subtle' }: NumberBadgeProps) {
  const theme = useTheme()

  const accent =
    tone === 'neutral'
      ? theme.palette.text.secondary
      : theme.palette[tone].main
  const contrastText =
    tone === 'neutral'
      ? theme.palette.background.paper
      : theme.palette[tone].contrastText ?? '#fff'

  return (
    <Box
      component="span"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 18,
        height: 18,
        px: 0.75,
        borderRadius: 9999,
        fontSize: '0.6875rem',
        fontWeight: 600,
        lineHeight: 1,
        fontVariantNumeric: 'tabular-nums',
        ...(variant === 'subtle'
          ? {
              color: 'text.primary',
              bgcolor: alpha(accent, 0.16),
              border: `1px solid ${alpha(accent, 0.28)}`,
            }
          : { color: contrastText, bgcolor: accent }),
      }}
    >
      {children}
    </Box>
  )
}
