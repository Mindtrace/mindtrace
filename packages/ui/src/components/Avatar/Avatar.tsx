/**
 * Avatar — wraps MUI Avatar with two ergonomic defaults:
 *
 *   - When no `src` or `children` is given, falls back to **initials**
 *     derived from `name` or `email`.
 *   - When no `bgcolor` is given, derives a stable color from the
 *     subject string so the same person always gets the same tile color.
 *
 *   <Avatar name="Avery Lin" />              // → AL on a stable tile color
 *   <Avatar email="taylor@example.com" />    // → TA on a stable color
 *   <Avatar src="/me.png" />                 // image; no fallback
 *   <Avatar>?</Avatar>                       // explicit children
 */

import MuiAvatar, { type AvatarProps as MuiAvatarProps } from '@mui/material/Avatar'
import { forwardRef } from 'react'

import { brand, neutral } from '../../theme/tokens'

export type AvatarProps = Omit<MuiAvatarProps, 'children'> & {
  /** Subject's display name. Used to derive initials and a stable color. */
  name?: string
  /** Subject's email. Used to derive initials/color when `name` is missing. */
  email?: string
  /** Override the auto-derived initials. */
  initials?: string
  /** Tint algorithm. `'subject'` picks from a fixed palette via hash;
   *  `'neutral'` uses theme neutrals. Default `'subject'`. */
  tint?: 'subject' | 'neutral'
  /** Children — use when you want a custom glyph (e.g. an icon). */
  children?: MuiAvatarProps['children']
}

const TILE_COLORS = [
  brand.purple[500],
  brand.teal[500],
  brand.blue[500],
  '#EC4899', // pink
  '#F59E0B', // amber
  '#10B981', // emerald
  '#8B5CF6', // violet
  '#06B6D4', // cyan
  '#F97316', // orange
  '#6366F1', // indigo
] as const

function deriveInitials(nameOrEmail: string): string {
  const source = nameOrEmail.includes('@') ? nameOrEmail.split('@')[0] : nameOrEmail
  const parts = source.split(/[\s._-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

function deriveColor(s: string): string {
  return TILE_COLORS[hashString(s) % TILE_COLORS.length]
}

export const Avatar = forwardRef<HTMLDivElement, AvatarProps>(function Avatar(
  { name, email, initials, tint = 'subject', children, src, sx, ...rest },
  ref,
) {
  const subject = (name || email || '').trim()
  const text = children ?? (subject ? (initials ?? deriveInitials(subject)) : '?')
  const isImage = !!src
  const bg =
    tint === 'neutral'
      ? neutral[200]
      : subject
        ? deriveColor(subject)
        : neutral[400]

  return (
    <MuiAvatar
      ref={ref}
      src={src}
      sx={[
        {
          bgcolor: isImage ? undefined : bg,
          color: '#FFFFFF',
          fontSize: '0.78rem',
          fontWeight: 700,
          letterSpacing: '0.02em',
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
      {...rest}
    >
      {!isImage && text}
    </MuiAvatar>
  )
})
