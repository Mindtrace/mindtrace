import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'
import { useState } from 'react'

import { FilterChips, type FilterOption } from './FilterChips'

const options: FilterOption[] = [
  { id: 'pending', label: 'Pending', count: 12 },
  { id: 'in-progress', label: 'In progress', count: 3 },
  { id: 'completed', label: 'Completed', count: 41 },
  { id: 'archived', label: 'Archived', count: 200 },
]

const meta = {
  title: 'Patterns/FilterChips',
  component: FilterChips,
  tags: ['autodocs'],
  argTypes: {
    exclusive: { control: 'boolean' },
    size: { control: { type: 'inline-radio' }, options: ['small', 'medium'] },
    onChange: { action: 'changed' },
  },
  args: {
    options,
    selected: ['pending'],
    onChange: fn(),
  },
} satisfies Meta<typeof FilterChips>

export default meta
type Story = StoryObj<typeof meta>

function Wrapper({ exclusive, size, onChange }: { exclusive?: boolean; size?: 'small' | 'medium'; onChange: (next: string[]) => void }) {
  const [selected, setSelected] = useState<string[]>(['pending'])
  return (
    <FilterChips
      options={options}
      selected={selected}
      onChange={(next) => { setSelected(next); onChange(next) }}
      exclusive={exclusive}
      size={size}
    />
  )
}

export const MultiSelect: Story = {
  render: (args) => <Wrapper exclusive={args.exclusive} size={args.size} onChange={args.onChange} />,
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    await userEvent.click(canvas.getByText(/Completed/))
    await expect(args.onChange).toHaveBeenCalled()
  },
}

export const Exclusive: Story = {
  args: { exclusive: true },
  render: (args) => <Wrapper exclusive={args.exclusive} size={args.size} onChange={args.onChange} />,
}
