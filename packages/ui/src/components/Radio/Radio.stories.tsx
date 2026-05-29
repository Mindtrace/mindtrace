import type { Meta, StoryObj } from '@storybook/react'
import { fn } from '@storybook/test'
import { useState } from 'react'

import { RadioGroup, type RadioOption } from './Radio'

const options: RadioOption[] = [
  { value: 'free', label: 'Free' },
  { value: 'pro', label: 'Pro' },
  { value: 'enterprise', label: 'Enterprise', disabled: true },
]

const meta = {
  title: 'Components/Radio',
  component: RadioGroup,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    label: { control: 'text' },
    helperText: { control: 'text' },
    error: { control: 'boolean' },
    onChange: { action: 'changed' },
  },
  args: { label: 'Plan', options, onChange: fn() },
} satisfies Meta<typeof RadioGroup>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = { args: { defaultValue: 'pro' } }

export const Interactive: Story = {
  render: (args) => {
    const [v, setV] = useState('free')
    return (
      <RadioGroup
        {...args}
        value={v}
        onChange={(next) => {
          setV(next)
          args.onChange?.(next)
        }}
      />
    )
  },
}

export const WithHelperText: Story = {
  args: { helperText: 'You can change this later in billing.' },
}

export const Error: Story = {
  args: { error: true, helperText: 'Please pick a plan.' },
}
