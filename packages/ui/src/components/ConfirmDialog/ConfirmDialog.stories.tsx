import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'
import { useState } from 'react'

import { Button } from '../Button'
import { ConfirmDialog } from './ConfirmDialog'

const meta = {
  title: 'Components/ConfirmDialog',
  component: ConfirmDialog,
  tags: ['autodocs'],
  argTypes: {
    open: { control: 'boolean' },
    destructive: { control: 'boolean' },
    loading: { control: 'boolean' },
    title: { control: 'text' },
    description: { control: 'text' },
    confirmLabel: { control: 'text' },
    cancelLabel: { control: 'text' },
    onConfirm: { action: 'confirmed' },
    onCancel: { action: 'cancelled' },
  },
  args: {
    open: false,
    title: 'Delete project?',
    description: 'This action is permanent.',
    confirmLabel: 'Delete',
    destructive: true,
    onConfirm: fn(),
    onCancel: fn(),
  },
} satisfies Meta<typeof ConfirmDialog>

export default meta
type Story = StoryObj<typeof meta>

export const Trigger: Story = {
  render: (args) => {
    const [open, setOpen] = useState(false)
    return (
      <>
        <Button variant="contained" color="error" onClick={() => setOpen(true)}>
          Delete…
        </Button>
        <ConfirmDialog
          {...args}
          open={open}
          onConfirm={() => {
            setOpen(false)
            args.onConfirm()
          }}
          onCancel={() => {
            setOpen(false)
            args.onCancel()
          }}
        />
      </>
    )
  },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /delete…/i }))
    const dialog = await within(document.body).findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await expect(args.onConfirm).toHaveBeenCalledOnce()
  },
}

export const Loading: Story = { args: { open: true, loading: true } }

export const NonDestructive: Story = {
  args: {
    open: true,
    title: 'Publish changes?',
    description: 'Your team will see the updated content immediately.',
    confirmLabel: 'Publish',
    destructive: false,
  },
}

export const ForcedAcknowledgement: Story = {
  args: {
    open: true,
    title: 'Your session expired',
    description: 'Please sign in again to continue.',
    confirmLabel: 'OK',
    hideCancel: true,
    destructive: false,
  },
}
