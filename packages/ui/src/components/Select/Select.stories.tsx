import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'
import { useState } from 'react'

import { Select, type SelectOption } from './Select'

const options: SelectOption[] = [
  { value: 'sm', label: 'Small' },
  { value: 'md', label: 'Medium' },
  { value: 'lg', label: 'Large' },
  { value: 'xl', label: 'Extra large', disabled: true },
]

const meta = {
  title: 'Components/Select',
  component: Select,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    label: { control: 'text' },
    helperText: { control: 'text' },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium'] },
    fullWidth: { control: 'boolean' },
    error: { control: 'boolean' },
    onChange: { action: 'changed' },
  },
  args: { label: 'Size', onChange: fn() },
} satisfies Meta<typeof Select>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: { options, defaultValue: 'md', sx: { minWidth: 220 } },
}

export const Interactive: Story = {
  args: { options, sx: { minWidth: 220 } },
  render: (args) => {
    const [value, setValue] = useState<string>('md')
    return (
      <Select
        {...args}
        value={value}
        onChange={(e, child) => {
          const next = e.target.value as string
          setValue(next)
          args.onChange?.(e, child)
        }}
      />
    )
  },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('combobox'))
    const option = await within(document.body).findByRole('option', { name: 'Large' })
    await userEvent.click(option)
    await expect(args.onChange).toHaveBeenCalled()
  },
}

export const WithHelperText: Story = {
  args: {
    label: 'Tier',
    helperText: 'Affects pricing and quotas.',
    options: [
      { value: 'free', label: 'Free' },
      { value: 'pro', label: 'Pro' },
      { value: 'enterprise', label: 'Enterprise' },
    ],
    defaultValue: '',
    sx: { minWidth: 220 },
  },
}

export const Error: Story = {
  args: {
    label: 'Region',
    error: true,
    helperText: 'Please select a region.',
    options: [
      { value: 'us', label: 'United States' },
      { value: 'eu', label: 'Europe' },
    ],
    defaultValue: '',
    sx: { minWidth: 220 },
  },
}
