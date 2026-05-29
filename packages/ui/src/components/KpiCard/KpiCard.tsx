/**
 * KpiCard — a single metric tile.
 *
 * Use for dashboards / overview pages where you want a row of high-level
 * numbers. Pairs with a trend delta and optional icon.
 *
 *   <KpiCard
 *     label="Active users"
 *     value="12,840"
 *     delta={{ value: '+4.2%', tone: 'success' }}
 *     icon={<TrendingUp />}
 *   />
 */

import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { alpha, useTheme } from '@mui/material/styles'
import type { ReactNode } from 'react'

import type { StatusTone } from '../StatusDot/StatusDot'

export type KpiDelta = {
  value: string
  tone: StatusTone
}

export type KpiCardProps = {
  label: string
  value: ReactNode
  delta?: KpiDelta
  icon?: ReactNode
  hint?: string
  loading?: boolean
}

export function KpiCard({ label, value, delta, icon, hint, loading }: KpiCardProps) {
  const theme = useTheme()
  const deltaTone = delta?.tone ?? 'neutral'
  const deltaColor =
    deltaTone === 'neutral'
      ? theme.palette.text.secondary
      : deltaTone === 'success'
        ? theme.palette.success.main
        : deltaTone === 'warning'
          ? theme.palette.warning.main
          : deltaTone === 'error'
            ? theme.palette.error.main
            : theme.palette.info.main

  return (
    <Box
      sx={(t) => ({
        position: 'relative',
        p: 2.5,
        borderRadius: 2,
        border: `1px solid ${t.palette.border.subtle}`,
        bgcolor: t.palette.background.paper,
        transition: 'border-color 120ms, box-shadow 120ms',
        '&:hover': {
          borderColor: t.palette.border.default,
          boxShadow: t.shadows[1],
        },
      })}
    >
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Stack spacing={1} sx={{ minWidth: 0 }}>
          <Typography variant="label" component="div" color="text.secondary">
            {label}
          </Typography>
          <Typography
            variant="h2"
            component="div"
            sx={{
              fontVariantNumeric: 'tabular-nums',
              opacity: loading ? 0.4 : 1,
              fontSize: '1.875rem',
              lineHeight: 1.1,
            }}
          >
            {loading ? '—' : value}
          </Typography>
          {delta && (
            <Typography
              variant="body2"
              sx={{ color: deltaColor, fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}
            >
              {delta.value}
            </Typography>
          )}
          {hint && (
            <Typography variant="caption" color="text.secondary">
              {hint}
            </Typography>
          )}
        </Stack>
        {icon && (
          <Box
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 40,
              height: 40,
              borderRadius: 1.5,
              bgcolor: alpha(theme.palette.primary.main, 0.12),
              color: theme.palette.primary.main,
              flexShrink: 0,
            }}
          >
            {icon}
          </Box>
        )}
      </Stack>
    </Box>
  )
}
