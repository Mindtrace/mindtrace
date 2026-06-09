import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, userEvent, within } from '@storybook/test'

import { Button } from '../Button'
import { ToastProvider, useToast, type ToastAnchor } from './ToastProvider'

const meta = {
  title: 'Components/Toast',
  component: ToastProvider,
  tags: ['autodocs'],
  argTypes: {
    anchorOrigin: { control: false },
    defaultDurationMs: { control: { type: 'number' } },
    max: { control: { type: 'number', min: 1, max: 10 } },
  },
  args: { defaultDurationMs: 5000, max: 5, children: null },
} satisfies Meta<typeof ToastProvider>

export default meta
type Story = StoryObj<typeof meta>

function Demo({ anchorOrigin }: { anchorOrigin?: ToastAnchor }) {
  return (
    <ToastProvider anchorOrigin={anchorOrigin}>
      <DemoContent />
    </ToastProvider>
  )
}

function DemoContent() {
  const toast = useToast()
  return (
    <Stack spacing={1.5} sx={{ alignItems: 'flex-start' }}>
      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
        <Button variant="contained" color="success" onClick={() => toast.success('Saved.')}>
          Success
        </Button>
        <Button variant="contained" color="error" onClick={() => toast.error('Could not reach the API.')}>
          Error
        </Button>
        <Button variant="contained" color="warning" onClick={() => toast.warning('Your session expires in 2 min.')}>
          Warning
        </Button>
        <Button variant="contained" color="info" onClick={() => toast.info('Connection established.')}>
          Info
        </Button>
        <Button variant="text" onClick={() => toast.clear()}>
          Clear all
        </Button>
      </Stack>
      <Button
        variant="outlined"
        onClick={() =>
          toast.show({
            severity: 'info',
            title: 'Long-running job',
            message: 'Will not auto-dismiss.',
            durationMs: null,
          })
        }
      >
        Persistent (no auto-dismiss)
      </Button>
    </Stack>
  )
}

export const Default: Story = {
  render: () => <Demo />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: 'Success' }))
    const toast = await within(document.body).findByText('Saved.')
    await expect(toast).toBeVisible()
  },
}

export const TopRight: Story = {
  render: () => <Demo anchorOrigin={{ vertical: 'top', horizontal: 'right' }} />,
}

export const BottomCenter: Story = {
  render: () => <Demo anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />,
}
