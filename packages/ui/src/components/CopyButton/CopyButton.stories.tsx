import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { fn } from '@storybook/test'

import { Mono } from '../Mono'
import { CopyButton } from './CopyButton'

const meta = {
  title: 'Components/CopyButton',
  component: CopyButton,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    value: { control: 'text' },
    label: { control: 'text' },
    copiedLabel: { control: 'text' },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium', 'large'] },
    onCopy: { action: 'copied' },
  },
  args: { value: 'a3b6e5bf6ff856d2509292e95c8f57f0df7017cf', onCopy: fn() },
} satisfies Meta<typeof CopyButton>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const WithMono: Story = {
  render: (args) => (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
      <Mono>{args.value}</Mono>
      <CopyButton {...args} />
    </Stack>
  ),
}
