import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../Button'
import { EmptyState } from '../EmptyState'
import { PageLayout } from './PageLayout'

const meta = {
  title: 'Patterns/PageLayout',
  component: PageLayout,
  tags: ['autodocs'],
  parameters: { layout: 'fullscreen' },
  argTypes: {
    title: { control: 'text' },
    description: { control: 'text' },
    fullBleed: { control: 'boolean' },
    embedded: { control: 'boolean' },
  },
  args: {
    title: 'Members',
    description: 'People with access to this workspace.',
    breadcrumbs: [{ label: 'Settings' }, { label: 'Members' }],
    actions: <Button variant="contained">Invite</Button>,
  },
} satisfies Meta<typeof PageLayout>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: (args) => (
    <PageLayout {...args}>
      <EmptyState title="No members yet" description="Invite someone to get started." />
    </PageLayout>
  ),
}

export const WithTabs: Story = {
  render: (args) => (
    <PageLayout
      {...args}
      tabs={{
        defaultValue: 'active',
        tabs: [
          { value: 'active', label: 'Active', content: <Typography>Active members</Typography> },
          { value: 'invited', label: 'Invited', content: <Typography>Invited members</Typography> },
          { value: 'archived', label: 'Archived', content: <Typography>Archived members</Typography> },
        ],
      }}
    />
  ),
}
