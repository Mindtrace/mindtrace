import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'
import { useState } from 'react'

import { Button } from '../Button'
import { Drawer } from './Drawer'

const meta = {
  title: 'Components/Drawer',
  component: Drawer,
  tags: ['autodocs'],
  argTypes: {
    anchor: {
      control: { type: 'inline-radio' },
      options: ['left', 'right', 'top', 'bottom'],
    },
    variant: {
      control: { type: 'inline-radio' },
      options: ['temporary', 'persistent', 'permanent'],
    },
    open: { control: 'boolean' },
    onClose: { action: 'closed' },
  },
  args: { anchor: 'right', open: false, onClose: fn() },
} satisfies Meta<typeof Drawer>

export default meta
type Story = StoryObj<typeof meta>

export const Trigger: Story = {
  render: (args) => {
    const [open, setOpen] = useState(false)
    return (
      <>
        <Button variant="outlined" onClick={() => setOpen(true)}>Open drawer</Button>
        <Drawer
          {...args}
          open={open}
          onClose={(event, reason) => {
            setOpen(false)
            args.onClose?.(event, reason)
          }}
        >
          <Box sx={{ width: 320, p: 3 }}>
            <Stack spacing={2}>
              <Typography variant="h6">Details</Typography>
              <Typography variant="body2" color="text.secondary">
                Drawers are good for secondary context that needs to stay scoped
                to the current page.
              </Typography>
              <Button variant="contained" onClick={() => setOpen(false)}>Close</Button>
            </Stack>
          </Box>
        </Drawer>
      </>
    )
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /open drawer/i }))
    const drawer = await within(document.body).findByText('Details')
    await expect(drawer).toBeVisible()
  },
}

export const Open: Story = {
  args: { open: true, anchor: 'right' },
  render: (args) => (
    <Drawer {...args}>
      <Box sx={{ width: 320, p: 3 }}>
        <Typography variant="h6">Details</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          A statically-open drawer for visual inspection.
        </Typography>
      </Box>
    </Drawer>
  ),
}
