import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import LogoutIcon from '@mui/icons-material/Logout'
import PersonIcon from '@mui/icons-material/Person'
import SettingsIcon from '@mui/icons-material/Settings'
import type { Meta, StoryObj } from '@storybook/react'
import { useState } from 'react'

const meta = {
  title: 'Components/Menu',
  component: Menu,
  tags: ['autodocs'],
  args: { open: false },
} satisfies Meta<typeof Menu>

export default meta
type Story = StoryObj<typeof meta>

function Demo() {
  const [el, setEl] = useState<HTMLElement | null>(null)
  return (
    <>
      <Button variant="outlined" onClick={(e) => setEl(e.currentTarget)}>
        Open menu
      </Button>
      <Menu anchorEl={el} open={Boolean(el)} onClose={() => setEl(null)}>
        <MenuItem onClick={() => setEl(null)}>
          <ListItemIcon>
            <PersonIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Profile</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => setEl(null)}>
          <ListItemIcon>
            <SettingsIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Settings</ListItemText>
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => setEl(null)}>
          <ListItemIcon>
            <LogoutIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Sign out</ListItemText>
        </MenuItem>
      </Menu>
    </>
  )
}

export const Default: Story = { render: () => <Demo /> }
