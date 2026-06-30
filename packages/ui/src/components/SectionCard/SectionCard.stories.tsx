import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../Button'
import { SectionCard } from './SectionCard'

const meta = {
  title: 'Patterns/SectionCard',
  component: SectionCard,
  tags: ['autodocs'],
  argTypes: {
    title: { control: 'text' },
    subtitle: { control: 'text' },
    disablePadding: { control: 'boolean' },
  },
  args: { title: 'Section', children: null },
} satisfies Meta<typeof SectionCard>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    title: 'Settings',
    children: <Typography color="text.secondary">Card body content.</Typography>,
  },
}

export const WithSubtitle: Story = {
  args: {
    title: 'Webhooks',
    subtitle: 'HTTP endpoints we call when events fire in this workspace.',
    children: <Typography color="text.secondary">Card body content.</Typography>,
  },
}

export const WithActions: Story = {
  args: {
    title: 'Active notifications',
    actions: <Button size="small">View all</Button>,
    children: <Typography color="text.secondary">Card body content.</Typography>,
  },
}

export const DisablePadding: Story = {
  args: {
    title: 'Recent activity',
    disablePadding: true,
    children: (
      <Stack
        sx={(theme) => ({
          borderTop: `1px solid ${theme.palette.border.subtle}`,
          py: 4,
          textAlign: 'center',
        })}
      >
        <Typography color="text.secondary">Table body would sit edge-to-edge here.</Typography>
      </Stack>
    ),
  },
}
