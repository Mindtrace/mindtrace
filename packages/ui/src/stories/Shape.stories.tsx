import type { Meta, StoryObj } from '@storybook/react'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { radius, spacing } from '../theme/shape'

function ShapeShowcase() {
  return (
    <Stack spacing={5}>
      <Stack spacing={2}>
        <Typography variant="overline" color="text.secondary">
          Radius scale
        </Typography>
        <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap', gap: 3 }}>
          {Object.entries(radius).map(([name, value]) => (
            <Stack key={name} spacing={1} sx={{ alignItems: 'center' }}>
              <Box
                sx={{
                  width: 80,
                  height: 80,
                  bgcolor: 'primary.main',
                  borderRadius: `${value}px`,
                }}
              />
              <Typography variant="caption" sx={{ fontWeight: 600 }}>
                {name}
              </Typography>
              <Typography variant="mono" sx={{ fontSize: '0.6875rem', color: 'text.secondary' }}>
                {value}px
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Stack>

      <Stack spacing={2}>
        <Typography variant="overline" color="text.secondary">
          Spacing (theme.spacing = {spacing}px)
        </Typography>
        <Stack spacing={1.5}>
          {[1, 1.5, 2, 3, 4, 6, 8].map((n) => (
            <Stack key={n} direction="row" spacing={2} sx={{ alignItems: 'center' }}>
              <Typography variant="mono" sx={{ width: 60, fontSize: '0.75rem' }}>
                spacing({n})
              </Typography>
              <Box sx={{ height: 12, bgcolor: 'primary.main', borderRadius: 0.5, width: n * spacing * 1 }} />
              <Typography variant="caption" color="text.secondary">
                {n * spacing}px
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Stack>
    </Stack>
  )
}

const meta: Meta = {
  title: 'Foundations/Shape',
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj

export const Default: Story = {
  render: () => <ShapeShowcase />,
}
