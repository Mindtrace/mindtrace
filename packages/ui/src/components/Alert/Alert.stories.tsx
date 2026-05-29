import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'

import { Alert, AlertTitle } from './Alert'

const meta = {
  title: 'Components/Alert',
  component: Alert,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    severity: {
      control: { type: 'inline-radio' },
      options: ['info', 'success', 'warning', 'error'],
    },
    variant: {
      control: { type: 'inline-radio' },
      options: ['standard', 'filled', 'outlined'],
    },
    onClose: { action: 'closed' },
  },
  args: { severity: 'info', children: 'Inline feedback message.' },
} satisfies Meta<typeof Alert>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Severities: Story = {
  render: (args) => (
    <Stack spacing={1.5} sx={{ width: 480 }}>
      <Alert {...args} severity="info">Build queued — waiting for an available runner.</Alert>
      <Alert {...args} severity="success">Changes saved.</Alert>
      <Alert {...args} severity="warning">You have unsaved edits in two tabs.</Alert>
      <Alert {...args} severity="error">Could not reach the API. Check your connection.</Alert>
    </Stack>
  ),
}

export const WithTitle: Story = {
  args: { severity: 'warning' },
  render: (args) => (
    <Alert {...args} sx={{ width: 480 }}>
      <AlertTitle>Heads up</AlertTitle>
      Permissions for this resource have changed. Review before continuing.
    </Alert>
  ),
}

export const Dismissible: Story = {
  args: { severity: 'info', onClose: fn(), children: 'Click the close icon to dismiss.' },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /close/i }))
    await expect(args.onClose).toHaveBeenCalled()
  },
}
