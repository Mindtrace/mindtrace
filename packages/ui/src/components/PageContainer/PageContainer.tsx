/**
 * PageContainer — the scrollable region that hosts a route's content.
 *
 * Applies standard page padding by default. Use `fullBleed` for
 * canvas-style pages (editors, maps, full-screen workspaces) that own
 * their own padding. Use `embedded` to drop padding entirely when the
 * shell is hosted inside another frame.
 *
 * Stateless. No router awareness — callers decide when to set the flags.
 */

import Box, { type BoxProps } from '@mui/material/Box'
import type { ReactNode } from 'react'

export type PageContainerProps = {
  children: ReactNode
  /** Skip default padding/gap — the page owns its own layout. */
  fullBleed?: boolean
  /** Drop all padding (use inside an embedded shell). */
  embedded?: boolean
  /** Forward extra sx to the container. */
  sx?: BoxProps['sx']
}

export function PageContainer({ children, fullBleed = false, embedded = false, sx }: PageContainerProps) {
  return (
    <Box
      sx={[
        {
          position: 'relative',
          zIndex: 0,
          display: 'flex',
          flex: 1,
          minHeight: 0,
          flexDirection: 'column',
          ...(fullBleed
            ? { p: 0, gap: 0 }
            : embedded
              ? { p: 0 }
              : { p: { xs: 2, md: 3 }, gap: 2 }),
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {children}
    </Box>
  )
}
