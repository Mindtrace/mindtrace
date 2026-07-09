import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { Mono } from './Mono'

const meta = {
  title: 'Components/Mono',
  component: Mono,
  tags: ['autodocs'],
  argTypes: {
    children: { control: 'text' },
  },
  args: { children: 'a3b6e5bf6ff856d2509292e95c8f57f0df7017cf' },
} satisfies Meta<typeof Mono>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Inline: Story = {
  render: () => (
    <Stack spacing={1.5}>
      <Typography>
        Last commit: <Mono>2b3a6e8b</Mono> at 14:03 UTC.
      </Typography>
      <Typography>
        File path: <Mono>src/components/Button/Button.tsx</Mono>
      </Typography>
    </Stack>
  ),
}
