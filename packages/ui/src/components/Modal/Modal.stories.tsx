import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'
import { useState } from 'react'

import { Button } from '../Button'
import { Modal, ModalActions, ModalContent, ModalContentText, ModalTitle } from './Modal'

const meta = {
  title: 'Components/Modal',
  component: Modal,
  tags: ['autodocs'],
  argTypes: {
    open: { control: 'boolean' },
    fullScreen: { control: 'boolean' },
    maxWidth: {
      control: { type: 'select' },
      options: [false, 'xs', 'sm', 'md', 'lg', 'xl'],
    },
    onClose: { action: 'closed' },
  },
  args: { open: false, onClose: fn() },
} satisfies Meta<typeof Modal>

export default meta
type Story = StoryObj<typeof meta>

export const Trigger: Story = {
  render: (args) => {
    const [open, setOpen] = useState(false)
    return (
      <>
        <Button variant="contained" onClick={() => setOpen(true)}>
          Open modal
        </Button>
        <Modal
          {...args}
          open={open}
          onClose={(event, reason) => {
            setOpen(false)
            args.onClose?.(event, reason)
          }}
        >
          <ModalTitle>Discard changes?</ModalTitle>
          <ModalContent>
            <ModalContentText>
              You have unsaved edits. Discarding will lose them permanently.
            </ModalContentText>
          </ModalContent>
          <ModalActions>
            <Button variant="text" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="contained" color="error" onClick={() => setOpen(false)}>
              Discard
            </Button>
          </ModalActions>
        </Modal>
      </>
    )
  },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /open modal/i }))
    const dialog = await within(document.body).findByRole('dialog')
    const cancel = await within(dialog).findByRole('button', { name: /cancel/i })
    await userEvent.click(cancel)
    await expect(args.onClose).not.toHaveBeenCalled()
  },
}

export const Open: Story = {
  args: { open: true },
  render: (args) => (
    <Modal {...args}>
      <ModalTitle>Notice</ModalTitle>
      <ModalContent>
        <ModalContentText>A statically-open modal for visual inspection.</ModalContentText>
      </ModalContent>
      <ModalActions>
        <Button variant="contained">OK</Button>
      </ModalActions>
    </Modal>
  ),
}
