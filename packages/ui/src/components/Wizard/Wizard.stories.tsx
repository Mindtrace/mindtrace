import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'
import { useEffect } from 'react'

import { TextField } from '../TextField'
import { Wizard, type WizardHelpers, type WizardStep } from './Wizard'

const steps: WizardStep[] = [
  { key: 'identity', title: 'Identity', description: 'Who is this user?' },
  { key: 'access', title: 'Access', description: 'What can they do?' },
  { key: 'review', title: 'Review', description: 'Confirm and submit' },
]

function StepBody({ keyName, helpers }: { keyName: string; helpers: WizardHelpers }) {
  // Auto-mark every step valid after a tick so the demo is navigable.
  useEffect(() => {
    helpers.setValid(true)
  }, [helpers])
  return (
    <Stack spacing={2} sx={{ maxWidth: 480 }}>
      <Typography variant="body2" color="text.secondary">
        Body for the <strong>{keyName}</strong> step. Replace with your form fields.
      </Typography>
      <TextField label="Example field" placeholder="…" />
    </Stack>
  )
}

const meta = {
  title: 'Patterns/Wizard',
  component: Wizard,
  tags: ['autodocs'],
  parameters: { layout: 'fullscreen' },
  argTypes: {
    layout: { control: { type: 'inline-radio' }, options: ['sidebar', 'top'] },
    onCancel: { action: 'cancelled' },
    onFinish: { action: 'finished' },
    onStepChange: { action: 'stepChanged' },
  },
  args: {
    steps,
    layout: 'sidebar',
    title: 'New user',
    onCancel: fn(),
    onFinish: fn(),
    onStepChange: fn(),
    renderStep: (key, helpers) => <StepBody keyName={key} helpers={helpers} />,
  },
} satisfies Meta<typeof Wizard>

export default meta
type Story = StoryObj<typeof meta>

export const Sidebar: Story = {}

export const Top: Story = { args: { layout: 'top' } }

export const FlowToFinish: Story = {
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    // Step 1 → 2
    let next = await canvas.findByRole('button', { name: /next/i })
    await userEvent.click(next)
    // Step 2 → 3
    next = await canvas.findByRole('button', { name: /next/i })
    await userEvent.click(next)
    // Finish
    const finish = await canvas.findByRole('button', { name: /finish/i })
    await userEvent.click(finish)
    await expect(args.onFinish).toHaveBeenCalledOnce()
  },
}
