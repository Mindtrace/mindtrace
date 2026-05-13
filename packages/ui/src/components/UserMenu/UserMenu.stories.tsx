import KeyIcon from '@mui/icons-material/VpnKey'
import PersonIcon from '@mui/icons-material/Person'
import SettingsIcon from '@mui/icons-material/Settings'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'

import { Badge } from '../Badge'
import { UserMenu } from './UserMenu'

const meta = {
  title: 'Layout/UserMenu',
  component: UserMenu,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    name: { control: 'text' },
    email: { control: 'text' },
    initials: { control: 'text' },
    signOutLabel: { control: 'text' },
    menuWidth: { control: { type: 'number', min: 200, max: 400 } },
    onSignOut: { action: 'signedOut' },
  },
  args: {
    name: 'Avery Lin',
    email: 'avery@example.com',
    onSignOut: fn(),
  },
} satisfies Meta<typeof UserMenu>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /account menu/i }))
    const menu = await within(document.body).findByRole('menu')
    await expect(menu).toBeVisible()
  },
}

export const WithContext: Story = {
  args: {
    context: (
      <Stack spacing={0.5}>
        <Typography variant="label" color="text.secondary">
          Current workspace
        </Typography>
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
          <Typography variant="mono">acme</Typography>
          <Badge label="admin" color="primary" size="small" />
        </Stack>
      </Stack>
    ),
  },
}

export const WithItems: Story = {
  args: {
    items: (
      <>
        <MenuItem>
          <ListItemIcon>
            <PersonIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Profile</ListItemText>
        </MenuItem>
        <MenuItem>
          <ListItemIcon>
            <KeyIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>API tokens</ListItemText>
        </MenuItem>
        <MenuItem>
          <ListItemIcon>
            <SettingsIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Settings</ListItemText>
        </MenuItem>
      </>
    ),
  },
}

export const SignOutFlow: Story = {
  args: {
    items: (
      <MenuItem>
        <ListItemIcon>
          <PersonIcon fontSize="small" />
        </ListItemIcon>
        <ListItemText>Profile</ListItemText>
      </MenuItem>
    ),
  },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /account menu/i }))
    const signOut = await within(document.body).findByText(/sign out/i)
    await userEvent.click(signOut)
    await expect(args.onSignOut).toHaveBeenCalledOnce()
  },
}

export const SignedOut: Story = {
  args: {
    name: undefined,
    email: undefined,
    onSignOut: undefined,
  },
}
