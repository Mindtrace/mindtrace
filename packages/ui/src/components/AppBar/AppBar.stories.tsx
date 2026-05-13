import DarkModeIcon from '@mui/icons-material/DarkMode'
import HelpOutlineIcon from '@mui/icons-material/Help'
import SearchIcon from '@mui/icons-material/Search'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../Button'
import { SearchField } from '../SearchField'
import { UserMenu } from '../UserMenu'
import { AppBar } from './AppBar'

const Brand = (
  <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.6 }}>
    <Typography sx={{ fontSize: '1rem', fontWeight: 700, letterSpacing: '-0.01em' }}>
      Mindtrace
    </Typography>
    <Typography sx={{ fontSize: '1rem', fontWeight: 500, color: 'primary.main' }}>
      Workspace
    </Typography>
  </Box>
)

const meta = {
  title: 'Layout/AppBar',
  component: AppBar,
  tags: ['autodocs'],
  parameters: { layout: 'fullscreen' },
  argTypes: {
    height: { control: { type: 'number', min: 48, max: 96, step: 4 } },
  },
  args: { height: 60 },
} satisfies Meta<typeof AppBar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: { brand: Brand },
}

export const WithActions: Story = {
  args: {
    brand: Brand,
    actions: (
      <>
        <IconButton size="small" aria-label="Help">
          <HelpOutlineIcon fontSize="small" />
        </IconButton>
        <IconButton size="small" aria-label="Toggle theme">
          <DarkModeIcon fontSize="small" />
        </IconButton>
        <UserMenu name="Avery Lin" email="avery@example.com" onSignOut={() => {}} />
      </>
    ),
  },
}

export const WithCenterSearch: Story = {
  args: {
    brand: Brand,
    center: (
      <Box sx={{ width: 320 }}>
        <SearchField value="" onChange={() => {}} placeholder="Search workspace…" />
      </Box>
    ),
    actions: (
      <>
        <IconButton size="small" aria-label="Search">
          <SearchIcon fontSize="small" />
        </IconButton>
        <Button variant="contained" size="small">Invite</Button>
      </>
    ),
  },
}

export const WithBreadcrumb: Story = {
  args: {
    brand: Brand,
    center: (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Typography variant="mono" sx={{ fontSize: '0.8125rem' }}>workspace</Typography>
        <Typography variant="caption" color="text.secondary">/</Typography>
        <Typography variant="mono" sx={{ fontSize: '0.8125rem' }}>projects</Typography>
        <Typography variant="caption" color="text.secondary">/</Typography>
        <Typography variant="mono" sx={{ fontSize: '0.8125rem' }}>p-42</Typography>
      </Box>
    ),
  },
}
