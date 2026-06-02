import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { createTheme } from '@mui/material/styles'
import type { Meta, StoryObj } from '@storybook/react'

import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { Button } from '../components/Button'
import { Card, CardActions, CardContent, CardHeader } from '../components/Card'
import { DataTable } from '../components/DataTable'
import { EmptyState } from '../components/EmptyState'
import { FilterChips } from '../components/FilterChips'
import { FormSection } from '../components/FormSection'
import { KpiCard } from '../components/KpiCard'
import { Mono } from '../components/Mono'
import { NumberBadge } from '../components/NumberBadge'
import { PageHeader } from '../components/PageHeader'
import { SectionCard } from '../components/SectionCard'
import { Select } from '../components/Select'
import { SeverityBadge } from '../components/SeverityBadge'
import { StatusBadge } from '../components/StatusBadge'
import { TextField } from '../components/TextField'
import { MindtraceProvider } from '../providers'
import { darkTheme as builtinDark, lightTheme as builtinLight, getTheme } from '../theme'

type Args = {
  /** Which built-in theme to start from. Custom colors apply on top. */
  base: 'mindtrace-light' | 'mindtrace-dark' | 'custom'
  mode: 'light' | 'dark'
  primary: string
  secondary: string
  success: string
  warning: string
  error: string
  info: string
  backgroundDefault: string
  backgroundPaper: string
  textPrimary: string
  fontFamily: string
  borderRadius: number
}

function buildTheme(a: Args) {
  if (a.base === 'mindtrace-light') return builtinLight
  if (a.base === 'mindtrace-dark') return builtinDark
  // Custom — overlay user colors onto a sane base for the chosen mode.
  const root = getTheme(a.mode)
  return createTheme({
    ...root,
    palette: {
      ...root.palette,
      mode: a.mode,
      primary: { main: a.primary },
      secondary: { main: a.secondary },
      success: { main: a.success },
      warning: { main: a.warning },
      error: { main: a.error },
      info: { main: a.info },
      background: {
        default: a.backgroundDefault,
        paper: a.backgroundPaper,
      },
      text: {
        ...root.palette.text,
        primary: a.textPrimary,
      },
    },
    typography: {
      ...root.typography,
      ...(a.fontFamily ? { fontFamily: a.fontFamily } : {}),
    },
    shape: { borderRadius: a.borderRadius },
  })
}

function Showcase(_args: Args) {
  return (
    <Stack spacing={4}>
      <Section title="Buttons">
        <Stack direction="row" spacing={1.5} sx={{ flexWrap: 'wrap', gap: 1 }}>
          <Button variant="contained">Primary</Button>
          <Button variant="outlined">Outlined</Button>
          <Button variant="text">Text</Button>
          <Button variant="contained" color="secondary">Secondary</Button>
          <Button variant="contained" color="success">Success</Button>
          <Button variant="contained" color="warning">Warning</Button>
          <Button variant="contained" color="error">Error</Button>
          <Button variant="contained" color="info">Info</Button>
          <Button variant="contained" disabled>Disabled</Button>
        </Stack>
      </Section>

      <Section title="Inputs">
        <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
          <TextField label="Name" placeholder="Type here…" sx={{ minWidth: 220 }} />
          <TextField label="Email" defaultValue="me@example.com" sx={{ minWidth: 220 }} />
          <TextField label="Error" error helperText="This field is required" sx={{ minWidth: 220 }} />
          <Select
            label="Tier"
            defaultValue="pro"
            options={[
              { value: 'free', label: 'Free' },
              { value: 'pro', label: 'Pro' },
              { value: 'enterprise', label: 'Enterprise' },
            ]}
            sx={{ minWidth: 220 }}
          />
        </Stack>
      </Section>

      <Section title="Status & feedback">
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <StatusBadge tone="success" label="Healthy" />
            <StatusBadge tone="warning" label="Degraded" pulse />
            <StatusBadge tone="error" label="Down" />
            <StatusBadge tone="info" label="Pending" />
            <StatusBadge tone="neutral" label="Idle" />
          </Stack>
          <Stack direction="row" spacing={1}>
            <SeverityBadge severity="critical" />
            <SeverityBadge severity="major" />
            <SeverityBadge severity="minor" />
            <SeverityBadge severity="info" />
          </Stack>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
            <Badge label="default" />
            <Badge label="primary" color="primary" />
            <Badge label="success" color="success" />
            <Badge label="warning" color="warning" />
            <Badge label="error" color="error" />
            <NumberBadge tone="info">5</NumberBadge>
            <NumberBadge tone="error" variant="solid">99+</NumberBadge>
          </Stack>
          <Alert severity="info">Info — connection established.</Alert>
          <Alert severity="success">Success — changes saved.</Alert>
          <Alert severity="warning">Warning — unsaved edits.</Alert>
          <Alert severity="error">Error — could not reach the API.</Alert>
        </Stack>
      </Section>

      <Section title="Cards & layout">
        <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
          <Card sx={{ width: 280 }}>
            <CardHeader title="Plain card" subheader="Updated just now" />
            <CardContent>
              <Typography variant="body2" color="text.secondary">
                Wraps MUI Card. Picks up theme palette and radius.
              </Typography>
            </CardContent>
            <CardActions sx={{ justifyContent: 'flex-end' }}>
              <Button variant="text" size="small">Cancel</Button>
              <Button variant="contained" size="small">Save</Button>
            </CardActions>
          </Card>
          <SectionCard title="Webhooks" subtitle="HTTP endpoints" sx={{ width: 320 }}>
            <Typography variant="body2" color="text.secondary">
              SectionCard composes Card + header in one element.
            </Typography>
          </SectionCard>
          <KpiCard label="Active users" value="12,840" delta={{ value: '+4.2%', tone: 'success' }} />
        </Stack>
      </Section>

      <Section title="Page header + form">
        <Stack spacing={2}>
          <PageHeader
            title="Members"
            description="People with access to this workspace."
            breadcrumbs={[{ label: 'Settings' }, { label: 'Members' }]}
            actions={<Button variant="contained">Invite</Button>}
          />
          <FormSection title="Profile" description="How you appear to teammates.">
            <TextField label="Display name" defaultValue="Alex" />
            <TextField label="Email" defaultValue="alex@example.com" />
          </FormSection>
        </Stack>
      </Section>

      <Section title="Data + filters + IDs">
        <Stack spacing={2}>
          <FilterChips
            options={[
              { id: 'all', label: 'All', count: 256 },
              { id: 'pending', label: 'Pending', count: 12 },
              { id: 'in-progress', label: 'In progress', count: 3 },
              { id: 'completed', label: 'Completed', count: 41 },
            ]}
            selected={['pending']}
            onChange={() => {}}
          />
          <DataTable
            rows={[
              { id: 'j-9241', name: 'nightly-report', status: 'success' as const, duration: '142 ms' },
              { id: 'j-9240', name: 'image-resize', status: 'warning' as const, duration: '312 ms' },
              { id: 'j-9239', name: 'image-resize', status: 'error' as const, duration: '0 ms' },
            ]}
            getRowKey={(r) => r.id}
            columns={[
              { id: 'id', label: 'ID', render: (r) => <Mono>{r.id}</Mono> },
              { id: 'name', label: 'Job' },
              { id: 'status', label: 'Status', render: (r) => <StatusBadge tone={r.status} label={r.status} /> },
              { id: 'duration', label: 'Duration', align: 'right' },
            ]}
          />
        </Stack>
      </Section>

      <Section title="Empty state">
        <EmptyState
          title="Nothing here yet"
          description="When data shows up, it'll appear in this surface."
          action={<Button variant="contained">Get started</Button>}
        />
      </Section>
    </Stack>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="tinyLabel" color="text.secondary">
        {title}
      </Typography>
      {children}
    </Stack>
  )
}

/**
 * Demonstrates the real consumer pattern: wrap the app once in
 * `MindtraceProvider` at the root, passing the constructed `theme`.
 * Every descendant — including all `@mindtrace/ui` components — reads
 * from that theme via MUI's context.
 */
function ThemeBuilderShell(args: Args) {
  const theme = buildTheme(args)
  return (
    <MindtraceProvider theme={theme}>
      <Box sx={{ bgcolor: 'background.default', color: 'text.primary', p: 3, borderRadius: 1 }}>
        <Showcase {...args} />
      </Box>
    </MindtraceProvider>
  )
}

const meta = {
  title: 'Foundations/Theme Builder',
  parameters: {
    layout: 'padded',
    docs: {
      description: {
        component:
          'Author a theme inline and see every component re-render against it. Pick a built-in theme to start, or switch `base` to `custom` to override individual colors, font, and radius. Useful for validating the library against non-Mindtrace brand palettes before adopting it.',
      },
    },
  },
  tags: ['autodocs'],
  argTypes: {
    base: {
      control: { type: 'inline-radio' },
      options: ['mindtrace-light', 'mindtrace-dark', 'custom'],
      description: 'Start from a built-in theme or build a custom one.',
    },
    mode: { control: { type: 'inline-radio' }, options: ['light', 'dark'], if: { arg: 'base', eq: 'custom' } },
    primary: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    secondary: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    success: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    warning: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    error: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    info: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    backgroundDefault: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    backgroundPaper: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    textPrimary: { control: 'color', if: { arg: 'base', eq: 'custom' } },
    fontFamily: { control: 'text', if: { arg: 'base', eq: 'custom' } },
    borderRadius: {
      control: { type: 'range', min: 0, max: 24, step: 1 },
      if: { arg: 'base', eq: 'custom' },
    },
  },
  args: {
    base: 'custom',
    mode: 'light',
    primary: '#7C3AED',
    secondary: '#52525B',
    success: '#16A34A',
    warning: '#D97706',
    error: '#DC2626',
    info: '#0891B2',
    backgroundDefault: '#FAFAFA',
    backgroundPaper: '#FFFFFF',
    textPrimary: '#18181B',
    fontFamily: '',
    borderRadius: 10,
  } satisfies Args,
  render: (args) => <ThemeBuilderShell {...(args as Args)} />,
} satisfies Meta<Args>

export default meta
type Story = StoryObj<typeof meta>

export const MindtraceLight: Story = { args: { base: 'mindtrace-light' } }
export const MindtraceDark: Story = { args: { base: 'mindtrace-dark' } }

export const CustomBlue: Story = {
  args: {
    base: 'custom',
    primary: '#2563EB',
    secondary: '#475569',
    success: '#059669',
    warning: '#D97706',
    error: '#DC2626',
    info: '#0EA5E9',
    backgroundDefault: '#F8FAFC',
    backgroundPaper: '#FFFFFF',
    textPrimary: '#0F172A',
    borderRadius: 6,
  },
}

export const CustomGreen: Story = {
  args: {
    base: 'custom',
    primary: '#15803D',
    secondary: '#3F3F46',
    success: '#16A34A',
    warning: '#CA8A04',
    error: '#B91C1C',
    info: '#0E7490',
    backgroundDefault: '#FAFAF9',
    backgroundPaper: '#FFFFFF',
    textPrimary: '#0C0A09',
    borderRadius: 14,
  },
}

export const CustomDark: Story = {
  args: {
    base: 'custom',
    mode: 'dark',
    primary: '#22D3EE',
    secondary: '#A1A1AA',
    success: '#4ADE80',
    warning: '#FBBF24',
    error: '#F87171',
    info: '#67E8F9',
    backgroundDefault: '#0A0A0A',
    backgroundPaper: '#171717',
    textPrimary: '#FAFAFA',
    borderRadius: 12,
  },
}

export const Playground: Story = {}
