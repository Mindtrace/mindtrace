/**
 * Section card — the standard "panel of content under a heading".
 *
 * Combines Card + an internal header row into one element so consumers
 * don't have to assemble CardHeader / CardContent every time. Pairs well
 * with table bodies, grouped settings, and dashboard tiles.
 */

import Card, { type CardProps } from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { ReactNode, ElementType } from 'react'

export type SectionCardProps = {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  /** Render-as element, defaults to `<section>`. */
  component?: ElementType
  /** Drop the inner padding when the body owns its own layout (e.g. tables). */
  disablePadding?: boolean
  /** Forwarded to the underlying Card. */
  sx?: CardProps['sx']
}

export function SectionCard({
  title,
  subtitle,
  actions,
  children,
  component = 'section',
  disablePadding = false,
  sx,
}: SectionCardProps) {
  return (
    <Card component={component} sx={sx}>
      {(title || subtitle || actions) && (
        <Stack
          direction="row"
          spacing={2}
          sx={{
            alignItems: 'center',
            justifyContent: 'space-between',
            px: 3,
            pt: 2.5,
            pb: title ? 1.5 : 2,
          }}
        >
          <Stack spacing={0.25} sx={{ minWidth: 0 }}>
            {title && (
              <Typography variant="h5" component="h2">
                {title}
              </Typography>
            )}
            {subtitle && (
              <Typography variant="body2" color="text.secondary">
                {subtitle}
              </Typography>
            )}
          </Stack>
          {actions && (
            <Stack direction="row" spacing={1}>
              {actions}
            </Stack>
          )}
        </Stack>
      )}
      <CardContent sx={{ p: disablePadding ? 0 : 3, pt: title ? 0 : 3, '&:last-child': { pb: disablePadding ? 0 : 3 } }}>
        {children}
      </CardContent>
    </Card>
  )
}
