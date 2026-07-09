import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { fn } from '@storybook/test'

import { Switch } from './Switch'

const meta = {
  title: 'Components/Switch',
  component: Switch,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    label: { control: 'text' },
    helperText: { control: 'text' },
    disabled: { control: 'boolean' },
    labelPlacement: { control: { type: 'inline-radio' }, options: ['start', 'end'] },
    onChange: { action: 'changed' },
  },
  args: { label: 'Email me on failures', onChange: fn() },
} satisfies Meta<typeof Switch>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
export const WithHelperText: Story = {
  args: { helperText: 'Sends one email per incident.' },
}
export const States: Story = {
  render: (args) => (
    <Stack spacing={1.5}>
      <Switch {...args} label="Off" />
      <Switch {...args} label="On" defaultChecked />
      <Switch {...args} label="Disabled off" disabled />
      <Switch {...args} label="Disabled on" disabled defaultChecked />
    </Stack>
  ),
}
