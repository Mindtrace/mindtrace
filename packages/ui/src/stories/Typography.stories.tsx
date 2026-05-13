import type { Meta, StoryObj } from '@storybook/react'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'

const VARIANTS = [
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'subtitle1',
  'subtitle2',
  'body1',
  'body2',
  'caption',
  'overline',
  'button',
  'mono',
  'label',
] as const

function TypographyShowcase() {
  return (
    <Stack spacing={2.5} divider={<Box sx={{ borderTop: 1, borderColor: 'divider' }} />}>
      {VARIANTS.map((v) => (
        <Stack key={v} direction="row" spacing={3} sx={{ alignItems: 'baseline' }}>
          <Box sx={{ width: 90, flexShrink: 0 }}>
            <Typography variant="mono" sx={{ color: 'text.secondary', fontSize: '0.75rem' }}>
              {v}
            </Typography>
          </Box>
          <Typography variant={v}>The quick brown fox jumps over the lazy dog — 0123456789</Typography>
        </Stack>
      ))}
    </Stack>
  )
}

const meta: Meta = {
  title: 'Foundations/Typography',
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj

export const AllVariants: Story = {
  render: () => <TypographyShowcase />,
}
