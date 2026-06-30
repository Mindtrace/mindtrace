/**
 * Tiny status indicator dot. Pairs with a label for inline status display.
 *
 *   <StatusDot tone="success" /> Healthy
 *   <StatusDot tone="warning" /> Degraded
 *   <StatusDot tone="error" />   Down
 */

import Box from '@mui/material/Box'
import type { SxProps, Theme } from '@mui/material/styles'

export type StatusTone = 'neutral' | 'success' | 'warning' | 'error' | 'info'

const toneToColor = {
  neutral: 'text.disabled',
  success: 'success.main',
  warning: 'warning.main',
  error: 'error.main',
  info: 'info.main',
} as const

export type StatusDotProps = {
  tone?: StatusTone
  size?: number
  pulse?: boolean
  sx?: SxProps<Theme>
}

export function StatusDot({ tone = 'neutral', size = 8, pulse = false, sx }: StatusDotProps) {
  return (
    <Box
      component="span"
      role="presentation"
      sx={[
        {
          display: 'inline-block',
          width: size,
          height: size,
          borderRadius: '50%',
          bgcolor: toneToColor[tone],
          flexShrink: 0,
          ...(pulse && {
            animation: 'mindtrace-pulse 1.6s ease-in-out infinite',
            '@keyframes mindtrace-pulse': {
              '0%, 100%': { opacity: 1 },
              '50%': { opacity: 0.45 },
            },
          }),
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    />
  )
}
