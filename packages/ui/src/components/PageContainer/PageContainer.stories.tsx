import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { PageContainer } from './PageContainer'

const meta = {
  title: 'Layout/PageContainer',
  component: PageContainer,
  tags: ['autodocs'],
  parameters: { layout: 'fullscreen' },
  argTypes: {
    fullBleed: { control: 'boolean' },
    embedded: { control: 'boolean' },
  },
  args: { fullBleed: false, embedded: false, children: null },
} satisfies Meta<typeof PageContainer>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: (args) => (
    <Box sx={{ height: 480, display: 'flex' }}>
      <PageContainer {...args}>
        <Typography variant="h4">Standard page</Typography>
        <Typography variant="body1" color="text.secondary">
          Default padding + gap apply.
        </Typography>
        {Array.from({ length: 10 }).map((_, i) => (
          <Box key={i} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
            Section {i + 1}
          </Box>
        ))}
      </PageContainer>
    </Box>
  ),
}

export const FullBleed: Story = {
  args: { fullBleed: true },
  render: (args) => (
    <Box sx={{ height: 480, display: 'flex' }}>
      <PageContainer {...args}>
        <Box
          sx={{
            flex: 1,
            display: 'grid',
            placeItems: 'center',
            bgcolor: 'surface.muted',
            color: 'text.secondary',
          }}
        >
          <Typography>Edge-to-edge canvas (no padding, no gap)</Typography>
        </Box>
      </PageContainer>
    </Box>
  ),
}

export const Embedded: Story = {
  args: { embedded: true },
  render: (args) => (
    <Box sx={{ height: 480, display: 'flex' }}>
      <PageContainer {...args}>
        <Typography variant="h5">Embedded mode</Typography>
        <Typography variant="body2" color="text.secondary">
          No padding when hosted inside another framed shell.
        </Typography>
      </PageContainer>
    </Box>
  ),
}
