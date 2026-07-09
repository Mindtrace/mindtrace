import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'
import { useState } from 'react'

import { AppBar } from '../AppBar'
import { Button } from '../Button'
import { PrimaryRail, type PrimaryRailSection } from '../PrimaryRail'
import { UserMenu } from '../UserMenu'
import { AppShell } from './AppShell'

const sections: PrimaryRailSection[] = [
  {
    label: 'Workspace',
    items: [
      { href: '/', label: 'Dashboard' },
      { href: '/projects', label: 'Projects' },
      { href: '/members', label: 'Members' },
    ],
  },
  {
    label: 'Admin',
    items: [
      { href: '/settings', label: 'Settings' },
      { href: '/billing', label: 'Billing' },
    ],
  },
]

function PlaceholderContent() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Typography variant="h4">Page title</Typography>
      <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 640 }}>
        The shell composes a sidebar, a top bar, and an optional right rail
        around scrolling main content. Each region is a slot — the shell owns
        layout, you own contents.
      </Typography>
      {Array.from({ length: 30 }).map((_, i) => (
        <Box key={i} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
          Body row {i + 1}
        </Box>
      ))}
    </Box>
  )
}

const meta = {
  title: 'Layout/AppShell',
  component: AppShell,
  parameters: { layout: 'fullscreen' },
  tags: ['autodocs'],
  argTypes: {
    embedded: { control: 'boolean' },
  },
  args: { embedded: false, children: null },
} satisfies Meta<typeof AppShell>

export default meta
type Story = StoryObj<typeof meta>

function StatefulRail() {
  const [active, setActive] = useState('/projects')
  return (
    <PrimaryRail
      brand={<Typography sx={{ fontWeight: 700 }}>Mindtrace</Typography>}
      sections={sections}
      activeHref={active}
      renderLink={(item, content) => (
        <Box
          component="a"
          href={item.href}
          onClick={(e) => {
            e.preventDefault()
            setActive(item.href)
          }}
          sx={{ textDecoration: 'none', color: 'inherit' }}
        >
          {content}
        </Box>
      )}
    />
  )
}

export const Default: Story = {
  render: (args) => (
    <AppShell
      {...args}
      sidebar={<StatefulRail />}
      topBar={
        <AppBar
          brand={<Typography sx={{ fontWeight: 700 }}>Mindtrace</Typography>}
          actions={<UserMenu name="Avery Lin" email="avery@example.com" onSignOut={() => {}} />}
        />
      }
    >
      <PlaceholderContent />
    </AppShell>
  ),
}

export const WithRightRail: Story = {
  render: (args) => (
    <AppShell
      {...args}
      sidebar={<StatefulRail />}
      topBar={<AppBar brand={<Typography sx={{ fontWeight: 700 }}>Mindtrace</Typography>} actions={<Button size="small">Action</Button>} />}
      rightRail={
        <Box
          sx={(theme) => ({
            flex: '0 0 320px',
            borderLeft: 1,
            borderColor: 'divider',
            p: 2,
            bgcolor: theme.palette.surface.subtle,
          })}
        >
          <Typography variant="h6">Inspector</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Optional right rail for inspector / agent / detail panels.
          </Typography>
        </Box>
      }
    >
      <PlaceholderContent />
    </AppShell>
  ),
}

export const Embedded: Story = {
  args: { embedded: true },
  render: (args) => (
    <AppShell {...args}>
      <Box sx={{ p: 3 }}>
        <Typography variant="h5">Embedded mode</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          When `embedded`, the shell hides sidebar / top bar / right rail and
          renders only `children`. Useful for iframe or micro-frontend hosts.
        </Typography>
      </Box>
    </AppShell>
  ),
}
