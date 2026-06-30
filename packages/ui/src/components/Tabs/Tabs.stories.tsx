import GroupIcon from '@mui/icons-material/Group'
import HomeIcon from '@mui/icons-material/Home'
import SettingsIcon from '@mui/icons-material/Settings'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'

import { NumberBadge } from '../NumberBadge'
import { Tabs } from './Tabs'

const meta = {
  title: 'Components/Tabs',
  component: Tabs,
  tags: ['autodocs'],
  argTypes: {
    variant: { control: { type: 'inline-radio' }, options: ['standard', 'fullWidth', 'scrollable'] },
    onChange: { action: 'changed' },
  },
  args: {
    tabs: [
      { value: 'overview', label: 'Overview', content: <Typography>Overview body</Typography> },
      {
        value: 'members',
        label: 'Members',
        badge: <NumberBadge tone="info">3</NumberBadge>,
        content: <Typography>Members body</Typography>,
      },
      {
        value: 'settings',
        label: 'Settings',
        content: <Typography>Settings body</Typography>,
      },
    ],
    defaultValue: 'overview',
    onChange: fn(),
  },
} satisfies Meta<typeof Tabs>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('tab', { name: /members/i }))
    await expect(args.onChange).toHaveBeenLastCalledWith('members')
    await expect(canvas.getByText('Members body')).toBeVisible()
  },
}

export const WithIcons: Story = {
  args: {
    tabs: [
      { value: 'home', label: 'Home', icon: <HomeIcon />, content: <Typography>Home</Typography> },
      {
        value: 'people',
        label: 'People',
        icon: <GroupIcon />,
        content: <Typography>People</Typography>,
      },
      {
        value: 'settings',
        label: 'Settings',
        icon: <SettingsIcon />,
        content: <Typography>Settings</Typography>,
      },
    ],
    defaultValue: 'home',
  },
}

export const FullWidth: Story = { args: { variant: 'fullWidth' } }
