import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'

import { Button } from './Button'

const meta = {
  title: 'Components/Button',
  component: Button,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    variant: { control: { type: 'inline-radio' }, options: ['contained', 'outlined', 'text'] },
    color: {
      control: { type: 'select' },
      options: ['primary', 'secondary', 'success', 'warning', 'error', 'info', 'inherit'],
    },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium', 'large'] },
    disabled: { control: 'boolean' },
    children: { control: 'text' },
    onClick: { action: 'clicked' },
  },
  args: { children: 'Save changes', variant: 'contained', color: 'primary', onClick: fn() },
} satisfies Meta<typeof Button>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /save changes/i }))
    await expect(args.onClick).toHaveBeenCalledOnce()
  },
}

export const Variants: Story = {
  render: (args) => (
    <Stack direction="row" spacing={1.5}>
      <Button {...args} variant="contained">Contained</Button>
      <Button {...args} variant="outlined">Outlined</Button>
      <Button {...args} variant="text">Text</Button>
    </Stack>
  ),
}

export const Sizes: Story = {
  render: (args) => (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <Button {...args} size="small">Small</Button>
      <Button {...args} size="medium">Medium</Button>
      <Button {...args} size="large">Large</Button>
    </Stack>
  ),
}

export const Disabled: Story = { args: { disabled: true } }
