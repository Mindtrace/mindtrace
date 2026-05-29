/**
 * AppShell — generic operational-interface frame.
 *
 * Layout:
 *   ┌─────┬───────────────────────────────────┐
 *   │     │ topBar                            │
 *   │ side├───────────────┬───────────────────┤
 *   │ bar │ children      │ rightRail         │
 *   │     │ (scrolls)     │ (optional)        │
 *   └─────┴───────────────┴───────────────────┘
 *
 * Flex with height: 100vh so inner regions own their own scrolling.
 * All regions are slots — pass whatever component fits. When `embedded`
 * is true the shell renders only `children` (no sidebar, topBar, or
 * rightRail), useful for iframe / micro-frontend embedding.
 */

import Box, { type BoxProps } from '@mui/material/Box'
import type { ReactNode } from 'react'

export type AppShellProps = {
  /** Primary left rail (typically a `<PrimaryRail>`). */
  sidebar?: ReactNode
  /** Header rendered above the main content. */
  topBar?: ReactNode
  /** Main content. Scrolls independently. */
  children: ReactNode
  /** Optional secondary right-side rail (inspector, agent panel, etc.). */
  rightRail?: ReactNode
  /** When true, suppresses every slot except `children`. */
  embedded?: boolean
  /** Inline padding for the main content (theme spacing units). Default `3.5`. */
  mainPx?: number | string
  /** Block padding for the main content (theme spacing units). Default `3`. */
  mainPy?: number | string
  /** Override the main scroll container's sx for full control. */
  mainSx?: BoxProps['sx']
}

export function AppShell({
  sidebar,
  topBar,
  children,
  rightRail,
  embedded = false,
  mainPx = 3.5,
  mainPy = 3,
  mainSx,
}: AppShellProps) {
  if (embedded) {
    return (
      <Box
        sx={{
          display: 'flex',
          height: '100vh',
          width: '100%',
          overflow: 'hidden',
          bgcolor: 'background.default',
        }}
      >
        <Box component="main" sx={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
          {children}
        </Box>
      </Box>
    )
  }

  return (
    <Box
      sx={{
        display: 'flex',
        height: '100vh',
        width: '100%',
        overflow: 'hidden',
        bgcolor: 'background.default',
      }}
    >
      {sidebar}
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {topBar}
        <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
          <Box
            component="main"
            sx={[
              {
                flex: 1,
                minHeight: 0,
                overflow: 'auto',
                px: mainPx,
                py: mainPy,
              },
              ...(Array.isArray(mainSx) ? mainSx : [mainSx]),
            ]}
          >
            {children}
          </Box>
          {rightRail}
        </Box>
      </Box>
    </Box>
  )
}
