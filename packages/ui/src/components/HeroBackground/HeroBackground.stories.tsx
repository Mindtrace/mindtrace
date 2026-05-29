import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'

import { Button } from '../Button'
import { Card, CardActions, CardContent } from '../Card'
import { TextField } from '../TextField'
import { HeroBackground } from './HeroBackground'

const meta = {
  title: 'Patterns/HeroBackground',
  component: HeroBackground,
  tags: ['autodocs'],
  parameters: { layout: 'fullscreen' },
  argTypes: {
    professional: { control: 'boolean' },
  },
  args: { professional: false, children: null },
} satisfies Meta<typeof HeroBackground>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: (args) => (
    <HeroBackground {...args}>
      <Stack
        spacing={1}
        sx={{ alignItems: 'center', textAlign: 'center', py: { xs: 6, md: 10 } }}
      >
        <Typography variant="h2">Welcome back.</Typography>
        <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 480 }}>
          A calm, full-bleed decorative surface for landing, login, and welcome screens.
        </Typography>
      </Stack>
    </HeroBackground>
  ),
}

export const Professional: Story = {
  args: { professional: true },
  render: Default.render,
}

export const Login: Story = {
  render: (args) => (
    <HeroBackground {...args}>
      <Stack spacing={3} sx={{ alignItems: 'center', py: { xs: 6, md: 10 } }}>
        <Typography variant="h3">Sign in</Typography>
        <Card sx={{ width: 360 }}>
          <CardContent>
            <Stack spacing={2}>
              <TextField label="Email" placeholder="you@example.com" fullWidth />
              <TextField label="Password" type="password" fullWidth />
            </Stack>
          </CardContent>
          <CardActions sx={{ justifyContent: 'flex-end', px: 2, pb: 2 }}>
            <Button variant="contained" fullWidth>
              Continue
            </Button>
          </CardActions>
        </Card>
      </Stack>
    </HeroBackground>
  ),
}
