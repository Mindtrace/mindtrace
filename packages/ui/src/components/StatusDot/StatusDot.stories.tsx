import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { StatusDot } from './StatusDot'

const meta = {
  title: 'Components/StatusDot',
  component: StatusDot,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: { type: 'inline-radio' },
      options: ['neutral', 'success', 'warning', 'error', 'info'],
    },
    size: { control: { type: 'range', min: 4, max: 20, step: 1 } },
    pulse: { control: 'boolean' },
  },
  args: { tone: 'success', size: 8, pulse: false },
} satisfies Meta<typeof StatusDot>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const AllTones: Story = {
  render: () => (
    <Stack spacing={1.5}>
      {(['neutral', 'success', 'warning', 'error', 'info'] as const).map((tone) => (
        <Stack direction="row" spacing={1.5} key={tone} sx={{ alignItems: 'center' }}>
          <StatusDot tone={tone} />
          <Typography variant="body2">{tone}</Typography>
        </Stack>
      ))}
    </Stack>
  ),
}

export const Pulse: Story = {
  args: { pulse: true, tone: 'warning', size: 10 },
}
