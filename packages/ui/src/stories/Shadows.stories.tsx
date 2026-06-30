import type { Meta, StoryObj } from '@storybook/react'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'

function ShadowsShowcase() {
  const theme = useTheme()
  // Sample every distinct elevation step
  const elevations = [0, 1, 2, 4, 7, 16] as const
  return (
    <Stack spacing={3}>
      <Typography variant="overline" color="text.secondary">
        Elevation ramp
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 4 }}>
        {elevations.map((n) => (
          <Stack key={n} spacing={1} sx={{ alignItems: 'center' }}>
            <Box
              sx={{
                width: 120,
                height: 120,
                bgcolor: 'background.paper',
                borderRadius: 2,
                boxShadow: theme.shadows[n],
                border: '1px solid',
                borderColor: 'border.subtle',
              }}
            />
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              shadows[{n}]
            </Typography>
          </Stack>
        ))}
      </Box>
    </Stack>
  )
}

const meta: Meta = {
  title: 'Foundations/Shadows',
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj

export const Default: Story = {
  render: () => <ShadowsShowcase />,
}
