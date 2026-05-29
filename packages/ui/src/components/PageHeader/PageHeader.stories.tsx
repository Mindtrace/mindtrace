import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../Button'
import { PageHeader } from './PageHeader'

const meta = {
  title: 'Patterns/PageHeader',
  component: PageHeader,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Standard top-of-page block. Every full page mounts one — never style page titles ad-hoc.',
      },
    },
  },
  argTypes: {
    title: { control: 'text' },
    description: { control: 'text' },
  },
  args: {
    title: 'Members',
    description: 'People with access to this workspace.',
  },
} satisfies Meta<typeof PageHeader>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const WithActions: Story = {
  args: {
    actions: (
      <>
        <Button variant="outlined">Export</Button>
        <Button variant="contained">Invite</Button>
      </>
    ),
  },
}

export const WithBreadcrumbs: Story = {
  args: {
    breadcrumbs: [{ label: 'Settings', href: '/settings' }, { label: 'Members' }],
  },
}

export const Full: Story = {
  args: {
    title: 'API tokens',
    description: 'Long-lived credentials used by scripts and services.',
    breadcrumbs: [{ label: 'Settings' }, { label: 'Security' }, { label: 'API tokens' }],
    actions: <Button variant="contained">Save changes</Button>,
  },
}
