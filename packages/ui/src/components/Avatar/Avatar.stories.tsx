import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'

import { Avatar } from './Avatar'

const meta = {
  title: 'Components/Avatar',
  component: Avatar,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    name: { control: 'text' },
    email: { control: 'text' },
    initials: { control: 'text' },
    src: { control: 'text' },
    tint: { control: { type: 'inline-radio' }, options: ['subject', 'neutral'] },
  },
  args: { name: 'Avery Lin' },
} satisfies Meta<typeof Avatar>

export default meta
type Story = StoryObj<typeof meta>

export const FromName: Story = {}

export const FromEmail: Story = { args: { name: undefined, email: 'taylor.kim@example.com' } }

export const WithImage: Story = {
  args: { src: 'https://i.pravatar.cc/64?img=12' },
}

export const ManyPeople: Story = {
  render: () => (
    <Stack direction="row" spacing={1}>
      {['Avery Lin', 'Taylor Kim', 'Jordan Patel', 'Sam Reed', 'Chris Wu', 'Robin Khan'].map((n) => (
        <Avatar key={n} name={n} />
      ))}
    </Stack>
  ),
}

export const Sizes: Story = {
  render: () => (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <Avatar name="Avery Lin" sx={{ width: 24, height: 24, fontSize: '0.65rem' }} />
      <Avatar name="Avery Lin" />
      <Avatar name="Avery Lin" sx={{ width: 48, height: 48, fontSize: '1rem' }} />
      <Avatar name="Avery Lin" sx={{ width: 64, height: 64, fontSize: '1.25rem' }} />
    </Stack>
  ),
}

export const NoSubject: Story = { args: { name: undefined, email: undefined } }
