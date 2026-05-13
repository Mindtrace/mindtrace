import type { Meta, StoryObj } from '@storybook/react'
import { expect, fn, userEvent, within } from '@storybook/test'

import { Mono } from '../Mono'
import { StatusBadge } from '../StatusBadge'
import { DataTable } from './DataTable'

type Job = {
  id: string
  name: string
  status: 'success' | 'warning' | 'error'
  duration_ms: number
  ts: string
}

const rows: Job[] = [
  { id: 'j-9241', name: 'nightly-report', status: 'success', duration_ms: 142, ts: '2026-05-08 14:03' },
  { id: 'j-9240', name: 'nightly-report', status: 'success', duration_ms: 138, ts: '2026-05-08 14:02' },
  { id: 'j-9239', name: 'image-resize', status: 'warning', duration_ms: 312, ts: '2026-05-08 14:01' },
  { id: 'j-9238', name: 'image-resize', status: 'error', duration_ms: 0, ts: '2026-05-08 14:00' },
  { id: 'j-9237', name: 'nightly-report', status: 'success', duration_ms: 134, ts: '2026-05-08 13:59' },
]

const columns = [
  { id: 'id', label: 'ID', render: (r: Job) => <Mono>{r.id}</Mono> },
  { id: 'name', label: 'Job' },
  { id: 'status', label: 'Status', render: (r: Job) => <StatusBadge tone={r.status} label={r.status} /> },
  {
    id: 'duration_ms',
    label: 'Duration',
    align: 'right' as const,
    render: (r: Job) => `${r.duration_ms} ms`,
  },
  { id: 'ts', label: 'When', render: (r: Job) => <Mono>{r.ts}</Mono> },
]

const meta = {
  title: 'Patterns/DataTable',
  component: DataTable<Job>,
  tags: ['autodocs'],
  argTypes: {
    density: { control: { type: 'inline-radio' }, options: ['small', 'medium'] },
    loading: { control: 'boolean' },
    onRowClick: { action: 'rowClicked' },
  },
  args: {
    rows,
    columns,
    getRowKey: (r: Job) => r.id,
    density: 'small',
  },
} satisfies Meta<typeof DataTable<Job>>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Clickable: Story = {
  args: { onRowClick: fn() },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement)
    const firstId = await canvas.findByText('j-9241')
    await userEvent.click(firstId)
    await expect(args.onRowClick).toHaveBeenCalled()
  },
}

export const Loading: Story = { args: { loading: true } }

export const Empty: Story = {
  args: {
    rows: [],
    empty: 'No jobs in the last 24h.',
  },
}
