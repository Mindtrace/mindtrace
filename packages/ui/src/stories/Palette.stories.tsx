import type { Meta, StoryObj } from '@storybook/react'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'

function Swatch({ label, color, foreground }: { label: string; color: string; foreground?: string }) {
  return (
    <Stack
      sx={{
        borderRadius: 1,
        overflow: 'hidden',
        border: '1px solid',
        borderColor: 'border.subtle',
        minWidth: 140,
      }}
    >
      <Box sx={{ bgcolor: color, height: 72, display: 'flex', alignItems: 'flex-end', p: 1 }}>
        {foreground && (
          <Typography variant="caption" sx={{ color: foreground, fontWeight: 600 }}>
            Aa
          </Typography>
        )}
      </Box>
      <Stack sx={{ p: 1, bgcolor: 'background.paper' }}>
        <Typography variant="caption" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
        <Typography variant="mono" sx={{ fontSize: '0.6875rem', color: 'text.secondary' }}>
          {color}
        </Typography>
      </Stack>
    </Stack>
  )
}

function PaletteShowcase() {
  const theme = useTheme()
  const p = theme.palette
  const groups = [
    {
      title: 'Brand & status',
      items: [
        { label: 'primary.main', color: p.primary.main, foreground: p.primary.contrastText },
        { label: 'primary.dark', color: p.primary.dark, foreground: p.primary.contrastText },
        { label: 'primary.light', color: p.primary.light, foreground: p.primary.contrastText },
        { label: 'secondary.main', color: p.secondary.main, foreground: p.secondary.contrastText },
        { label: 'success.main', color: p.success.main, foreground: p.success.contrastText },
        { label: 'warning.main', color: p.warning.main, foreground: p.warning.contrastText },
        { label: 'error.main', color: p.error.main, foreground: p.error.contrastText },
        { label: 'info.main', color: p.info.main, foreground: p.info.contrastText },
      ],
    },
    {
      title: 'Backgrounds & surfaces',
      items: [
        { label: 'background.default', color: p.background.default, foreground: p.text.primary },
        { label: 'background.paper', color: p.background.paper, foreground: p.text.primary },
        { label: 'surface.subtle', color: p.surface.subtle, foreground: p.text.primary },
        { label: 'surface.muted', color: p.surface.muted, foreground: p.text.primary },
        { label: 'surface.strong', color: p.surface.strong, foreground: p.text.primary },
      ],
    },
    {
      title: 'Text & borders',
      items: [
        { label: 'text.primary', color: p.text.primary, foreground: p.background.paper },
        { label: 'text.secondary', color: p.text.secondary, foreground: p.background.paper },
        { label: 'text.disabled', color: p.text.disabled, foreground: p.background.paper },
        { label: 'divider', color: typeof p.divider === 'string' ? p.divider : '#e2e8f0' },
        { label: 'border.subtle', color: p.border.subtle as string },
        { label: 'border.default', color: p.border.default as string },
        { label: 'border.strong', color: p.border.strong as string },
      ],
    },
    {
      title: 'Grey ramp',
      items: ([50, 100, 200, 300, 400, 500, 600, 700, 800, 900] as const).map((shade) => ({
        label: `grey.${shade}`,
        color: p.grey[shade],
        foreground: shade >= 500 ? '#fff' : p.text.primary,
      })),
    },
  ]
  return (
    <Stack spacing={4}>
      {groups.map((g) => (
        <Stack key={g.title} spacing={1.5}>
          <Typography variant="overline" color="text.secondary">
            {g.title}
          </Typography>
          <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
            {g.items.map((it) => (
              <Swatch key={it.label} label={it.label} color={it.color} foreground={it.foreground} />
            ))}
          </Box>
        </Stack>
      ))}
    </Stack>
  )
}

const meta: Meta = {
  title: 'Foundations/Palette',
  parameters: { layout: 'padded' },
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj

export const Default: Story = {
  render: () => <PaletteShowcase />,
}
