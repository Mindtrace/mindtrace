import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../Button'
import { TextField } from '../TextField'
import { FormSection } from './FormSection'

const meta = {
  title: 'Patterns/FormSection',
  component: FormSection,
  tags: ['autodocs'],
  argTypes: {
    title: { control: 'text' },
    description: { control: 'text' },
  },
  args: {
    title: 'Section title',
    description: 'Supporting copy under the heading.',
    children: null,
  },
} satisfies Meta<typeof FormSection>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    title: 'Profile',
    description: 'How you appear to teammates.',
  },
  render: (args) => (
    <Stack sx={{ maxWidth: 560 }}>
      <FormSection {...args}>
        <TextField label="Display name" defaultValue="Alex" />
        <TextField label="Email" defaultValue="alex@example.com" />
      </FormSection>
    </Stack>
  ),
}

export const WithActions: Story = {
  args: {
    title: 'API keys',
    description: 'Rotate or revoke long-lived credentials.',
    actions: <Button variant="outlined" size="small">Create key</Button>,
  },
  render: (args) => (
    <Stack sx={{ maxWidth: 560 }}>
      <FormSection {...args}>
        <TextField label="Active key" value="••••••••••••mtui" disabled />
      </FormSection>
    </Stack>
  ),
}
