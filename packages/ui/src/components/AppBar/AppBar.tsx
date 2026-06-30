/**
 * AppBar — page header strip.
 *
 * Three slots — `brand` on the left, `center` in the middle, `actions`
 * on the right. Stateless and unopinionated: pass whatever components
 * (wordmark, breadcrumbs, search box, icon buttons, user menu) you want
 * in each slot.
 *
 * Renamed from MUI's AppBar to avoid colliding with the underlying
 * `@mui/material/AppBar` re-export. Use the MUI AppBar directly if you
 * need its position/elevation behaviors.
 */

import Box, { type BoxProps } from '@mui/material/Box'
import type { ReactNode } from 'react'

export type AppBarProps = {
  /** Left slot — typically a wordmark or logo. */
  brand?: ReactNode
  /** Middle slot — breadcrumbs, search, scope path indicator, etc. */
  center?: ReactNode
  /** Right slot — icon buttons, user menu, etc. */
  actions?: ReactNode
  /** Strip height in pixels. Default `60`. */
  height?: number
  /** Extra sx forwarded to the root. */
  sx?: BoxProps['sx']
}

export function AppBar({ brand, center, actions, height = 60, sx }: AppBarProps) {
  return (
    <Box
      component="header"
      sx={[
        (theme) => ({
          flex: '0 0 auto',
          height,
          px: 3,
          gap: 1,
          display: 'flex',
          alignItems: 'center',
          bgcolor:
            theme.palette.mode === 'dark' ? theme.palette.surface.subtle : theme.palette.background.default,
          borderBottom: 1,
          borderColor: 'divider',
        }),
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {brand && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, flexShrink: 0 }}>{brand}</Box>
      )}
      {center && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            minWidth: 0,
            pl: brand ? 2 : 0,
            ml: brand ? 2 : 0,
            borderLeft: brand ? 1 : 0,
            borderColor: 'divider',
          }}
        >
          {center}
        </Box>
      )}
      <Box sx={{ flexGrow: 1 }} />
      {actions && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>{actions}</Box>
      )}
    </Box>
  )
}
