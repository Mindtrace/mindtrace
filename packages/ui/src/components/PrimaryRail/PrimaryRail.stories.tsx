import BarChartIcon from '@mui/icons-material/BarChart'
import DashboardIcon from '@mui/icons-material/Dashboard'
import FolderIcon from '@mui/icons-material/Folder'
import GroupIcon from '@mui/icons-material/Group'
import NotificationsIcon from '@mui/icons-material/Notifications'
import ReceiptIcon from '@mui/icons-material/Receipt'
import SettingsIcon from '@mui/icons-material/Settings'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, userEvent, within } from '@storybook/test'
import { useState } from 'react'

import { NumberBadge } from '../NumberBadge'
import { PrimaryRail, type PrimaryRailSection } from './PrimaryRail'

const sections: PrimaryRailSection[] = [
  {
    label: 'Workspace',
    items: [
      { href: '/', label: 'Dashboard', icon: <DashboardIcon /> },
      { href: '/projects', label: 'Projects', icon: <FolderIcon /> },
      { href: '/members', label: 'Members', icon: <GroupIcon /> },
      {
        href: '/alerts',
        label: 'Alerts',
        icon: <NotificationsIcon />,
        badge: <NumberBadge tone="error">3</NumberBadge>,
      },
      { href: '/reports', label: 'Reports', icon: <BarChartIcon /> },
    ],
  },
  {
    label: 'Admin',
    items: [
      { href: '/settings', label: 'Settings', icon: <SettingsIcon /> },
      { href: '/billing', label: 'Billing', icon: <ReceiptIcon /> },
    ],
  },
]

const meta = {
  title: 'Layout/PrimaryRail',
  component: PrimaryRail,
  tags: ['autodocs'],
  parameters: { layout: 'fullscreen' },
  argTypes: {
    activeHref: { control: 'text' },
    collapsed: { control: 'boolean' },
    collapsedWidth: { control: { type: 'number', min: 48, max: 120 } },
    expandedWidth: { control: { type: 'number', min: 160, max: 320 } },
    showCollapseToggle: { control: 'boolean' },
    onCollapsedChange: { action: 'collapsedChanged' },
  },
  args: {
    sections,
    activeHref: '/projects',
    showCollapseToggle: true,
    collapsedWidth: 64,
    expandedWidth: 220,
  },
} satisfies Meta<typeof PrimaryRail>

export default meta
type Story = StoryObj<typeof meta>

const Brand = (
  <Box sx={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
    <Typography sx={{ fontSize: '0.9rem', fontWeight: 700, lineHeight: 1.1 }}>Mindtrace</Typography>
    <Typography sx={{ fontSize: '0.78rem', color: 'primary.main', fontWeight: 500, lineHeight: 1.2 }}>
      Workspace
    </Typography>
  </Box>
)

/**
 * Stories use `renderLink` to handle clicks via React state instead of
 * triggering real browser navigation — otherwise clicks would break the
 * user out of Storybook's iframe. In a real app, `renderLink` is where
 * you'd return a `<Link>` from your router instead.
 */
function StoryShell(args: React.ComponentProps<typeof PrimaryRail>) {
  const [active, setActive] = useState(args.activeHref ?? '/projects')
  return (
    <Box sx={{ display: 'flex', height: 600, bgcolor: 'background.default' }}>
      <PrimaryRail
        {...args}
        activeHref={active}
        renderLink={(item, content) => (
          <Box
            component="a"
            href={item.href}
            onClick={(e) => {
              e.preventDefault()
              setActive(item.href)
            }}
            sx={{ textDecoration: 'none', color: 'inherit' }}
          >
            {content}
          </Box>
        )}
      />
      <Box sx={{ flex: 1, p: 3 }}>
        <Typography variant="caption" color="text.secondary">
          Active route
        </Typography>
        <Typography variant="h4">{active}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Click any item in the rail to see the active state move.
        </Typography>
      </Box>
    </Box>
  )
}

export const Expanded: Story = {
  args: { brand: Brand, collapsed: false },
  render: (args) => <StoryShell {...args} />,
}

export const Collapsed: Story = {
  args: { brand: Brand, collapsed: true },
  render: (args) => <StoryShell {...args} />,
}

export const Toggle: Story = {
  args: { brand: Brand },
  render: (args) => <StoryShell {...args} />,
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    const toggle = canvas.getByRole('button', { name: /collapse navigation|expand navigation/i })
    await userEvent.click(toggle)
    await expect(args.onCollapsedChange).toHaveBeenCalled()
  },
}

export const Navigate: Story = {
  args: { brand: Brand, collapsed: false },
  render: (args) => <StoryShell {...args} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByText('Members'))
    await expect(canvas.getByRole('heading', { name: '/members' })).toBeVisible()
    await userEvent.click(canvas.getByText('Settings'))
    await expect(canvas.getByRole('heading', { name: '/settings' })).toBeVisible()
  },
}

export const WithoutBrand: Story = {
  args: { collapsed: false },
  render: (args) => <StoryShell {...args} />,
}
