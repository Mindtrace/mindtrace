import BusinessIcon from '@mui/icons-material/Business'
import FactoryIcon from '@mui/icons-material/Factory'
import GroupIcon from '@mui/icons-material/Group'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'

import { Badge } from '../Badge'
import { StatusDot } from '../StatusDot'
import { PathBreadcrumb, type PathSegment } from './PathBreadcrumb'

const orgs = [
  { id: 'acme', label: 'Acme Corp', secondary: 'admin', leading: <StatusDot tone="error" size={6} /> },
  { id: 'globex', label: 'Globex Industries', secondary: 'engineer', leading: <StatusDot tone="warning" size={6} /> },
  { id: 'initech', label: 'Initech', secondary: 'viewer', leading: <StatusDot tone="neutral" size={6} /> },
]

const teams = [
  { id: 'eng', label: 'Engineering', secondary: 'admin' },
  { id: 'ops', label: 'Operations', secondary: 'engineer' },
  { id: 'design', label: 'Design', secondary: 'viewer' },
]

const meta = {
  title: 'Patterns/PathBreadcrumb',
  component: PathBreadcrumb,
  tags: ['autodocs'],
  parameters: { layout: 'padded' },
} satisfies Meta<typeof PathBreadcrumb>

export default meta
type Story = StoryObj<typeof meta>

export const ReadOnly: Story = {
  args: {
    segments: [
      { id: 'org', label: 'Acme Corp', icon: <BusinessIcon /> },
      { id: 'team', label: 'Engineering', icon: <GroupIcon /> },
      { id: 'project', label: 'Onboarding', icon: <FactoryIcon /> },
    ],
  },
}

export const WithTrailingBadge: Story = {
  args: {
    segments: [
      { id: 'org', label: 'Acme Corp', icon: <BusinessIcon /> },
      { id: 'team', label: 'Engineering', icon: <GroupIcon /> },
    ],
    trailing: <Badge label="admin" color="primary" size="small" />,
  },
}

export const Interactive: Story = {
  args: {
    segments: [
      {
        id: 'org',
        label: 'Acme Corp',
        icon: <BusinessIcon />,
        items: orgs,
        currentId: 'acme',
        onSelect: fn() as PathSegment['onSelect'],
        searchPlaceholder: 'Search organization…',
      },
      {
        id: 'team',
        label: 'Engineering',
        icon: <GroupIcon />,
        items: teams,
        currentId: 'eng',
        onSelect: fn() as PathSegment['onSelect'],
        searchPlaceholder: 'Search team…',
      },
    ],
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /acme corp/i }))
    const list = await within(document.body).findByRole('button', { name: /globex industries/i })
    await expect(list).toBeVisible()
    await userEvent.click(list)
  },
}

export const MixedReadOnlyAndInteractive: Story = {
  args: {
    segments: [
      { id: 'org', label: 'Acme Corp', icon: <BusinessIcon /> },
      {
        id: 'team',
        label: 'Engineering',
        icon: <GroupIcon />,
        items: teams,
        currentId: 'eng',
        onSelect: fn() as PathSegment['onSelect'],
      },
      { id: 'project', label: 'Onboarding', icon: <FactoryIcon /> },
    ],
    trailing: <Badge label="admin" color="primary" size="small" />,
  },
}

export const Empty: Story = {
  args: {
    segments: [
      { id: 'org', label: null, icon: <BusinessIcon />, placeholder: 'Select organization' },
    ],
  },
}
