import Box from '@mui/material/Box'
import Grid from '@mui/material/Grid'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

const meta: Meta = {
  title: 'Foundations/Stack & Grid',
  tags: ['autodocs'],
}

export default meta
type Story = StoryObj

function Cell({ n }: { n: number }) {
  return (
    <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'surface.subtle' }}>
      <Typography variant="body2">{n}</Typography>
    </Paper>
  )
}

export const StackRow: Story = {
  render: () => (
    <Stack direction="row" spacing={2}>
      {[1, 2, 3, 4].map((n) => (
        <Cell key={n} n={n} />
      ))}
    </Stack>
  ),
}

export const StackColumn: Story = {
  render: () => (
    <Stack spacing={2}>
      {[1, 2, 3].map((n) => (
        <Cell key={n} n={n} />
      ))}
    </Stack>
  ),
}

export const GridSplit: Story = {
  render: () => (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 8 }}>
        <Cell n={1} />
      </Grid>
      <Grid size={{ xs: 12, md: 4 }}>
        <Cell n={2} />
      </Grid>
      <Grid size={{ xs: 6, md: 4 }}>
        <Cell n={3} />
      </Grid>
      <Grid size={{ xs: 6, md: 4 }}>
        <Cell n={4} />
      </Grid>
      <Grid size={{ xs: 12, md: 4 }}>
        <Cell n={5} />
      </Grid>
    </Grid>
  ),
}

export const ResponsiveBox: Story = {
  render: () => (
    <Box
      sx={{
        display: 'grid',
        gap: 2,
        gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: 'repeat(4, 1fr)' },
      }}
    >
      {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
        <Cell key={n} n={n} />
      ))}
    </Box>
  ),
}
