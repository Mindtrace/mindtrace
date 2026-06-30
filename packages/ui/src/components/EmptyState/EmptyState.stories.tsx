import InboxIcon from '@mui/icons-material/Inbox'
import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../Button'
import { EmptyState } from './EmptyState'

const meta = {
  title: 'Patterns/EmptyState',
  component: EmptyState,
  tags: ['autodocs'],
  argTypes: {
    title: { control: 'text' },
    description: { control: 'text' },
  },
  args: {
    title: 'No items yet',
    description: "When something happens here, it'll show up.",
  },
} satisfies Meta<typeof EmptyState>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const WithAction: Story = {
  args: {
    icon: <InboxIcon fontSize="inherit" />,
    title: 'Inbox empty',
    description: 'Nothing assigned to you. Browse the workspace to pick up new items.',
    action: <Button variant="contained">Browse workspace</Button>,
  },
}
