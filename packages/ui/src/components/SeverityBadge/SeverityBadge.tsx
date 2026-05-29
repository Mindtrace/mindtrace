/**
 * SeverityBadge — labelled severity tag for events, alerts, incidents.
 *
 * Severity ladder: `critical > major > minor > info`. Two visual variants:
 *
 *   - `'solid'` (default) — white text on a solid tone background. The
 *     strongest, most accessible treatment; matches the classic severity
 *     convention (red Critical, amber Major, …). Use here.
 *   - `'tinted'` — tinted background + high-contrast `text.primary` with
 *     a colored left marker. Useful when severity badges sit alongside
 *     softer status chips and you don't want them to dominate.
 *
 * In both variants the tone-carrying surface is independent from the
 * text color, so contrast stays WCAG AA at the small size we use here.
 */

import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import { alpha, useTheme } from '@mui/material/styles'

export type Severity = 'critical' | 'major' | 'minor' | 'info'

const severityToken: Record<Severity, { label: string; palette: 'error' | 'warning' | 'info' | 'success' }> = {
  critical: { label: 'Critical', palette: 'error' },
  major: { label: 'Major', palette: 'warning' },
  minor: { label: 'Minor', palette: 'info' },
  info: { label: 'Info', palette: 'success' },
}

export type SeverityBadgeProps = {
  severity: Severity
  labelOverride?: string
  size?: 'small' | 'medium'
  variant?: 'solid' | 'tinted'
}

export function SeverityBadge({
  severity,
  labelOverride,
  size = 'small',
  variant = 'solid',
}: SeverityBadgeProps) {
  const theme = useTheme()
  const token = severityToken[severity]
  const color = theme.palette[token.palette].main
  const contrastText = theme.palette[token.palette].contrastText ?? '#fff'

  if (variant === 'solid') {
    return (
      <Chip
        size={size}
        label={labelOverride ?? token.label}
        sx={{
          color: contrastText,
          bgcolor: color,
          border: `1px solid ${color}`,
          fontWeight: 600,
          letterSpacing: '0.02em',
          textTransform: 'uppercase',
          fontSize: '0.6875rem',
        }}
      />
    )
  }

  return (
    <Chip
      size={size}
      label={labelOverride ?? token.label}
      icon={
        <Box
          component="span"
          sx={{ display: 'inline-block', width: 8, height: 8, bgcolor: color, borderRadius: '50%', ml: 1.25 }}
        />
      }
      sx={{
        color: 'text.primary',
        bgcolor: alpha(color, 0.12),
        border: `1px solid ${alpha(color, 0.32)}`,
        fontWeight: 600,
        letterSpacing: '0.02em',
        textTransform: 'uppercase',
        fontSize: '0.6875rem',
        '& .MuiChip-icon': { mr: -0.5 },
      }}
    />
  )
}
