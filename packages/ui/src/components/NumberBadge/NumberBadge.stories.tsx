import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { NumberBadge } from './NumberBadge'

const meta = {
  title: 'Components/NumberBadge',
  component: NumberBadge,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: { type: 'inline-radio' },
      options: ['neutral', 'success', 'warning', 'error', 'info'],
    },
    variant: { control: { type: 'inline-radio' }, options: ['subtle', 'solid'] },
    children: { control: 'text' },
  },
  args: { children: 3, tone: 'neutral', variant: 'subtle' },
} satisfies Meta<typeof NumberBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const AllTones: Story = {
  render: () => (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <NumberBadge>0</NumberBadge>
      <NumberBadge tone="info">5</NumberBadge>
      <NumberBadge tone="success">12</NumberBadge>
      <NumberBadge tone="warning">3</NumberBadge>
      <NumberBadge tone="error">99+</NumberBadge>
    </Stack>
  ),
}

export const Solid: Story = {
  render: () => (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <Typography variant="body2">Pending alerts</Typography>
      <NumberBadge tone="error" variant="solid">
        7
      </NumberBadge>
    </Stack>
  ),
}
