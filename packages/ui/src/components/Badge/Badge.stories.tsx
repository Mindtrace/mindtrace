import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { fn } from '@storybook/test'

import { Badge } from './Badge'

const meta = {
  title: 'Components/Badge',
  component: Badge,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    label: { control: 'text' },
    color: {
      control: { type: 'select' },
      options: ['default', 'primary', 'secondary', 'success', 'warning', 'error', 'info'],
    },
    variant: { control: { type: 'inline-radio' }, options: ['filled', 'outlined'] },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium'] },
    clickable: { control: 'boolean' },
    onClick: { action: 'clicked' },
    onDelete: { action: 'deleted' },
  },
  args: { label: 'pending', onClick: fn() },
} satisfies Meta<typeof Badge>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Colors: Story = {
  render: (args) => (
    <Stack direction="row" spacing={1}>
      <Badge {...args} label="default" color="default" />
      <Badge {...args} label="primary" color="primary" />
      <Badge {...args} label="success" color="success" />
      <Badge {...args} label="warning" color="warning" />
      <Badge {...args} label="error" color="error" />
      <Badge {...args} label="info" color="info" />
    </Stack>
  ),
}

export const Variants: Story = {
  render: (args) => (
    <Stack direction="row" spacing={1}>
      <Badge {...args} variant="filled" label="filled" color="primary" />
      <Badge {...args} variant="outlined" label="outlined" color="primary" />
    </Stack>
  ),
}

export const Deletable: Story = {
  args: { label: 'tag', onDelete: fn() },
}
