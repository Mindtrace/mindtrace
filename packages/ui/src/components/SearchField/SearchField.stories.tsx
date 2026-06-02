import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'
import { useState } from 'react'

import { SearchField } from './SearchField'

const meta = {
  title: 'Patterns/SearchField',
  component: SearchField,
  tags: ['autodocs'],
  argTypes: {
    placeholder: { control: 'text' },
    autoFocus: { control: 'boolean' },
    fullWidth: { control: 'boolean' },
    disableClear: { control: 'boolean' },
    onChange: { action: 'changed' },
  },
  args: {
    value: '',
    placeholder: 'Search…',
    maxWidth: 420,
    onChange: fn(),
  },
} satisfies Meta<typeof SearchField>

export default meta
type Story = StoryObj<typeof meta>

function Wrapper({ onChange, ...rest }: React.ComponentProps<typeof SearchField>) {
  const [v, setV] = useState(rest.value ?? '')
  return (
    <SearchField
      {...rest}
      value={v}
      onChange={(next) => { setV(next); onChange(next) }}
    />
  )
}

export const Default: Story = {
  render: (args) => <Wrapper {...args} />,
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    const input = canvas.getByPlaceholderText('Search…')
    await userEvent.type(input, 'engineering')
    await expect(args.onChange).toHaveBeenCalled()
    await expect(input).toHaveValue('engineering')
  },
}

export const Filled: Story = {
  args: { value: 'engineering' },
  render: (args) => <Wrapper {...args} />,
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByRole('button', { name: /clear/i }))
    await expect(args.onChange).toHaveBeenLastCalledWith('')
  },
}
