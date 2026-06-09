import CircularProgress from '@mui/material/CircularProgress'
import LinearProgress from '@mui/material/LinearProgress'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

const meta: Meta = {
  title: 'Components/Progress',
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj

export const Linear: Story = {
  render: () => (
    <Stack spacing={2} sx={{ maxWidth: 360 }}>
      <LinearProgress />
      <LinearProgress variant="determinate" value={42} />
      <Typography variant="caption">42% — determinate</Typography>
    </Stack>
  ),
}

export const Circular: Story = {
  render: () => (
    <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
      <CircularProgress size={16} />
      <CircularProgress size={24} />
      <CircularProgress size={36} />
    </Stack>
  ),
}
