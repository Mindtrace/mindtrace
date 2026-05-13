import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { fn } from '@storybook/test'

import { Checkbox } from './Checkbox'

const meta = {
  title: 'Components/Checkbox',
  component: Checkbox,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    label: { control: 'text' },
    helperText: { control: 'text' },
    disabled: { control: 'boolean' },
    indeterminate: { control: 'boolean' },
    labelPlacement: { control: { type: 'inline-radio' }, options: ['start', 'end'] },
    onChange: { action: 'changed' },
  },
  args: { label: 'Subscribe to updates', onChange: fn() },
} satisfies Meta<typeof Checkbox>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
export const WithHelperText: Story = { args: { helperText: 'You can unsubscribe any time.' } }
export const States: Story = {
  render: (args) => (
    <Stack spacing={1.5}>
      <Checkbox {...args} label="Unchecked" />
      <Checkbox {...args} label="Checked" defaultChecked />
      <Checkbox {...args} label="Indeterminate" indeterminate />
      <Checkbox {...args} label="Disabled" disabled />
      <Checkbox {...args} label="Disabled + checked" disabled defaultChecked />
    </Stack>
  ),
}
