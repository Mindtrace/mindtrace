import Box from '@mui/material/Box'
import GroupIcon from '@mui/icons-material/Group'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import type { Meta, StoryObj } from '@storybook/react'

import { KpiCard } from './KpiCard'

const meta = {
  title: 'Patterns/KpiCard',
  component: KpiCard,
  tags: ['autodocs'],
  argTypes: {
    label: { control: 'text' },
    value: { control: 'text' },
    hint: { control: 'text' },
    loading: { control: 'boolean' },
  },
  args: {
    label: 'Active users',
    value: '12,840',
    delta: { value: '+4.2%', tone: 'success' },
    icon: <TrendingUpIcon />,
  },
} satisfies Meta<typeof KpiCard>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Negative: Story = {
  args: {
    label: 'Error rate',
    value: '1.8%',
    delta: { value: '+0.3%', tone: 'error' },
  },
}

export const Loading: Story = { args: { loading: true } }

export const Grid: Story = {
  render: () => (
    <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
      <KpiCard label="Active users" value="12,840" icon={<GroupIcon />} />
      <KpiCard label="Projects" value="42" delta={{ value: '+3 this week', tone: 'success' }} />
      <KpiCard label="Open tickets" value={7} hint="across 3 teams" />
      <KpiCard label="Alerts" value={0} delta={{ value: 'all clear', tone: 'success' }} />
    </Box>
  ),
}
