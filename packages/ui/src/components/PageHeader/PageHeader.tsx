/**
 * Page header — the standard top-of-page block for every full page.
 *
 *   <PageHeader
 *     title="Members"
 *     description="People with access to this workspace."
 *     actions={<Button variant="contained">Invite</Button>}
 *     breadcrumbs={[{ label: 'Settings' }, { label: 'Members' }]}
 *   />
 *
 * Typography sizes are theme-driven; do not pass overrides — the design
 * system owns the visual weight.
 */

import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import Breadcrumbs from '@mui/material/Breadcrumbs'
import Link from '@mui/material/Link'
import type { ReactNode } from 'react'

export type Crumb = { label: string; href?: string }

export type PageHeaderProps = {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  breadcrumbs?: Crumb[]
}

export function PageHeader({ title, description, actions, breadcrumbs }: PageHeaderProps) {
  return (
    <Stack spacing={1.5} sx={{ pb: 3 }}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumbs separator="/" sx={{ fontSize: '0.8125rem' }}>
          {breadcrumbs.map((c, i) =>
            c.href ? (
              <Link key={i} href={c.href} color="text.secondary" underline="hover">
                {c.label}
              </Link>
            ) : (
              <Typography key={i} variant="body2" color="text.secondary">
                {c.label}
              </Typography>
            ),
          )}
        </Breadcrumbs>
      )}
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        sx={{ alignItems: { md: 'center' }, justifyContent: 'space-between' }}
      >
        <Stack spacing={0.5} sx={{ minWidth: 0 }}>
          <Typography variant="h2" component="h1">
            {title}
          </Typography>
          {description && (
            <Typography variant="body1" color="text.secondary">
              {description}
            </Typography>
          )}
        </Stack>
        {actions && (
          <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
            {actions}
          </Stack>
        )}
      </Stack>
    </Stack>
  )
}
