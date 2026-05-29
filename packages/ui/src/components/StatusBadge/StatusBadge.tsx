/**
 * StatusBadge — labelled status chip with a semantic dot indicator.
 *
 * Tone is carried by the **dot**, not the text. Text uses
 * `text.primary` so it stays high-contrast against the tinted surface,
 * meeting WCAG AA at typical body sizes. The dot + the tinted bg
 * communicate the tone at a glance; the label stays readable.
 *
 *   <StatusBadge tone="success" label="Healthy" />
 *   <StatusBadge tone="warning" label="Degraded" pulse />
 *   <StatusBadge tone="error" label="Down" />
 */

import Chip from '@mui/material/Chip'
import { alpha, useTheme, type Theme } from '@mui/material/styles'

import { StatusDot, type StatusTone } from '../StatusDot/StatusDot'

export type StatusBadgeProps = {
  tone: StatusTone
  label: string
  pulse?: boolean
  size?: 'small' | 'medium'
}

function toneColor(theme: Theme, tone: StatusTone): string {
  if (tone === 'neutral') return theme.palette.text.secondary
  return theme.palette[tone].main
}

export function StatusBadge({ tone, label, pulse, size = 'small' }: StatusBadgeProps) {
  const theme = useTheme()
  const accent = toneColor(theme, tone)
  return (
    <Chip
      size={size}
      label={label}
      icon={<StatusDot tone={tone} pulse={pulse} size={8} sx={{ ml: 1.25 }} />}
      sx={{
        color: 'text.primary',
        bgcolor: alpha(accent, 0.12),
        border: `1px solid ${alpha(accent, 0.32)}`,
        fontWeight: 500,
        '& .MuiChip-icon': { color: accent, mr: -0.5 },
      }}
    />
  )
}
