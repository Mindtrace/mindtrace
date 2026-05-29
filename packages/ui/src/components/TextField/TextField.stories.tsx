import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'

import { TextField } from './TextField'

const meta = {
  title: 'Components/TextField',
  component: TextField,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    label: { control: 'text' },
    placeholder: { control: 'text' },
    helperText: { control: 'text' },
    variant: { control: { type: 'inline-radio' }, options: ['outlined', 'filled', 'standard'] },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium'] },
    error: { control: 'boolean' },
    disabled: { control: 'boolean' },
    multiline: { control: 'boolean' },
    fullWidth: { control: 'boolean' },
    onChange: { action: 'changed' },
  },
  args: { label: 'Label', placeholder: 'Type here…', onChange: fn() },
} satisfies Meta<typeof TextField>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    const input = canvas.getByLabelText('Label')
    await userEvent.type(input, 'hello')
    await expect(args.onChange).toHaveBeenCalled()
    await expect(input).toHaveValue('hello')
  },
}

export const WithHelperText: Story = { args: { helperText: 'Optional helper text' } }

export const Error: Story = {
  args: { error: true, helperText: 'This value is required', value: '' },
}

export const Disabled: Story = { args: { disabled: true, value: 'Read-only value' } }

export const Multiline: Story = {
  args: { multiline: true, minRows: 3, placeholder: 'Describe…' },
  render: (args) => (
    <Stack sx={{ width: 360 }}>
      <TextField {...args} />
    </Stack>
  ),
}
