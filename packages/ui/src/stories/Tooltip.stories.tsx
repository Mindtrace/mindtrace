import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import type { Meta, StoryObj } from '@storybook/react'

const meta = {
  title: 'Components/Tooltip',
  component: Tooltip,
  tags: ['autodocs'],
  args: { title: '', children: <span /> },
} satisfies Meta<typeof Tooltip>

export default meta
type Story = StoryObj<typeof meta>

export const Placements: Story = {
  render: () => (
    <Stack direction="row" spacing={3} sx={{ p: 5 }}>
      <Tooltip title="Top" placement="top">
        <Button variant="outlined">Top</Button>
      </Tooltip>
      <Tooltip title="Right" placement="right">
        <Button variant="outlined">Right</Button>
      </Tooltip>
      <Tooltip title="Bottom" placement="bottom">
        <Button variant="outlined">Bottom</Button>
      </Tooltip>
      <Tooltip title="Left" placement="left">
        <Button variant="outlined">Left</Button>
      </Tooltip>
    </Stack>
  ),
}
