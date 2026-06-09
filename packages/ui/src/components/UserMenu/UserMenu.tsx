/**
 * UserMenu — avatar trigger + dropdown for identity & account actions.
 *
 * Pure presentation: pass an identity (name/email/avatar), an optional
 * context slot (e.g. current workspace), an optional items slot (the
 * middle of the menu where account/admin links go), and a `onSignOut`
 * handler. No auth, scope, or role logic baked in.
 *
 *   <UserMenu
 *     name="Avery"
 *     email="avery@example.com"
 *     context={<Typography variant="caption">acme · production</Typography>}
 *     items={<>
 *       <MenuItem onClick={…}>Profile</MenuItem>
 *       <MenuItem onClick={…}>Settings</MenuItem>
 *     </>}
 *     onSignOut={handleSignOut}
 *   />
 */

import LogoutIcon from '@mui/icons-material/Logout'
import Avatar from '@mui/material/Avatar'
import Box from '@mui/material/Box'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useState, type ReactNode } from 'react'

export type UserMenuProps = {
  /** Display name. */
  name?: string
  /** Email or secondary identifier. */
  email?: string
  /** Image src for the avatar; if omitted, falls back to `initials`. */
  avatarSrc?: string
  /** Explicit avatar text. If omitted, derived from `name` or `email`. */
  initials?: string
  /** Optional context block rendered below identity (workspace, role, …). */
  context?: ReactNode
  /** Optional menu items rendered between identity and the sign-out row. */
  items?: ReactNode
  /** Sign-out handler. If omitted, no sign-out row is rendered. */
  onSignOut?: () => void
  /** Label for the sign-out menu item. Default `'Sign out'`. */
  signOutLabel?: string
  /** Width of the dropdown. Default `280`. */
  menuWidth?: number
}

function deriveInitials(nameOrEmail: string): string {
  const source = nameOrEmail.includes('@') ? nameOrEmail.split('@')[0] : nameOrEmail
  const parts = source.split(/[\s._-]+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

export function UserMenu({
  name,
  email,
  avatarSrc,
  initials,
  context,
  items,
  onSignOut,
  signOutLabel = 'Sign out',
  menuWidth = 280,
}: UserMenuProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const open = Boolean(anchorEl)

  const display = name?.trim() || email || 'Signed out'
  const computedInitials = initials ?? (name || email ? deriveInitials(name || email!) : '?')

  return (
    <>
      <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} aria-label="Account menu" size="small">
        <Avatar
          src={avatarSrc}
          sx={(theme) => ({
            width: 30,
            height: 30,
            fontSize: '0.75rem',
            fontWeight: 600,
            bgcolor: theme.palette.surface.muted,
            color: theme.palette.text.primary,
            border: `1px solid ${theme.palette.border.subtle}`,
          })}
        >
          {computedInitials}
        </Avatar>
      </IconButton>
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        slotProps={{ paper: { sx: { width: menuWidth } } }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Box sx={{ px: 2, py: 1.5 }}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
            <Avatar
              src={avatarSrc}
              sx={(theme) => ({
                width: 38,
                height: 38,
                fontSize: '0.8125rem',
                fontWeight: 600,
                bgcolor: theme.palette.surface.muted,
                color: theme.palette.text.primary,
              })}
            >
              {computedInitials}
            </Avatar>
            <Stack spacing={0.25} sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                {display}
              </Typography>
              {email && name && (
                <Typography variant="caption" color="text.secondary" noWrap>
                  {email}
                </Typography>
              )}
            </Stack>
          </Stack>
        </Box>

        {context && (
          <>
            <Divider />
            <Box sx={{ px: 2, py: 1.25 }}>{context}</Box>
          </>
        )}

        {items && (
          <>
            <Divider />
            {items}
          </>
        )}

        {onSignOut && (
          <>
            <Divider />
            <MenuItem
              onClick={() => {
                setAnchorEl(null)
                onSignOut()
              }}
              sx={(theme) => ({
                color: theme.palette.error.main,
                '&:hover': { bgcolor: theme.palette.error.main + '14' },
              })}
            >
              <ListItemIcon>
                <LogoutIcon fontSize="small" sx={{ color: 'inherit' }} />
              </ListItemIcon>
              <ListItemText>{signOutLabel}</ListItemText>
            </MenuItem>
          </>
        )}
      </Menu>
    </>
  )
}
