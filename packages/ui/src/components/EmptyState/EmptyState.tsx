/**
 * Empty / zero-data state. Use for empty lists, "nothing here yet", and
 * recoverable error views.
 */

import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'

export type EmptyStateProps = {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <Stack
      spacing={1.5}
      sx={(theme) => ({
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        py: 6,
        px: 3,
        color: theme.palette.text.secondary,
      })}
    >
      {icon && <Stack sx={{ fontSize: 32, color: 'text.disabled' }}>{icon}</Stack>}
      <Typography variant="h5" component="p" color="text.primary">
        {title}
      </Typography>
      {description && (
        <Typography variant="body2" sx={{ maxWidth: 480 }}>
          {description}
        </Typography>
      )}
      {action && <Stack sx={{ pt: 1 }}>{action}</Stack>}
    </Stack>
  )
}
