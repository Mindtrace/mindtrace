/**
 * Monospaced inline text — for IDs, hashes, file paths, codes.
 *
 * Use instead of raw <code>; this picks up the theme's mono variant and
 * tabular-figures styling so columns of IDs line up.
 */

import Typography from '@mui/material/Typography'
import type { TypographyProps } from '@mui/material/Typography'
import type { ReactNode } from 'react'

export type MonoProps = Omit<TypographyProps, 'variant'> & { children: ReactNode }

export function Mono({ children, sx, ...rest }: MonoProps) {
  return (
    <Typography
      component="span"
      variant="mono"
      sx={[
        { fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
      {...rest}
    >
      {children}
    </Typography>
  )
}
