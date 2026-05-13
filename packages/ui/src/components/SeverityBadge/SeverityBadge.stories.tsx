import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'

import { SeverityBadge } from './SeverityBadge'

const meta = {
  title: 'Components/SeverityBadge',
  component: SeverityBadge,
  tags: ['autodocs'],
  argTypes: {
    severity: {
      control: { type: 'inline-radio' },
      options: ['critical', 'major', 'minor', 'info'],
    },
    labelOverride: { control: 'text' },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium'] },
  },
  args: { severity: 'major' },
} satisfies Meta<typeof SeverityBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const All: Story = {
  render: () => (
    <Stack direction="row" spacing={1}>
      <SeverityBadge severity="critical" />
      <SeverityBadge severity="major" />
      <SeverityBadge severity="minor" />
      <SeverityBadge severity="info" />
    </Stack>
  ),
}
