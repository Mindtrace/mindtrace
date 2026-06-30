import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'

import { StatusBadge } from './StatusBadge'

const meta = {
  title: 'Components/StatusBadge',
  component: StatusBadge,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: { type: 'inline-radio' },
      options: ['neutral', 'success', 'warning', 'error', 'info'],
    },
    label: { control: 'text' },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium'] },
    pulse: { control: 'boolean' },
  },
  args: { tone: 'success', label: 'Healthy' },
} satisfies Meta<typeof StatusBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const AllTones: Story = {
  render: () => (
    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
      <StatusBadge tone="success" label="Healthy" />
      <StatusBadge tone="warning" label="Degraded" pulse />
      <StatusBadge tone="error" label="Down" />
      <StatusBadge tone="info" label="Pending" />
      <StatusBadge tone="neutral" label="Idle" />
    </Stack>
  ),
}
