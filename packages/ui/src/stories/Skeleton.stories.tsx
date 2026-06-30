import Box from '@mui/material/Box'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import type { Meta, StoryObj } from '@storybook/react'

const meta = {
  title: 'Components/Skeleton',
  component: Skeleton,
  tags: ['autodocs'],
} satisfies Meta<typeof Skeleton>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <Box sx={{ maxWidth: 380 }}>
      <Stack spacing={1}>
        <Skeleton variant="rectangular" height={120} />
        <Skeleton width="60%" />
        <Skeleton width="40%" />
      </Stack>
    </Box>
  ),
}
