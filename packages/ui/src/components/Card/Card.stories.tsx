import Typography from '@mui/material/Typography'
import type { Meta, StoryObj } from '@storybook/react'
import { fn } from '@storybook/test'

import { Button } from '../Button'
import { Card, CardActions, CardContent, CardHeader } from './Card'

const meta = {
  title: 'Components/Card',
  component: Card,
  tags: ['autodocs'],
  parameters: { layout: 'centered' },
  argTypes: {
    variant: { control: { type: 'inline-radio' }, options: ['elevation', 'outlined'] },
    raised: { control: 'boolean' },
    onClick: { action: 'clicked' },
  },
  args: { onClick: fn() },
} satisfies Meta<typeof Card>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: { sx: { width: 320 } },
  render: (args) => (
    <Card {...args}>
      <CardContent>
        <Typography variant="h6">Card title</Typography>
        <Typography variant="body2" color="text.secondary">
          A neutral surface for grouping related content.
        </Typography>
      </CardContent>
    </Card>
  ),
}

export const WithHeaderAndActions: Story = {
  args: { sx: { width: 360 } },
  render: (args) => (
    <Card {...args}>
      <CardHeader title="Summary" subheader="Updated just now" />
      <CardContent>
        <Typography variant="body2" color="text.secondary">
          Compact card layout with a header, body copy, and footer actions.
        </Typography>
      </CardContent>
      <CardActions sx={{ justifyContent: 'flex-end' }}>
        <Button variant="text">Dismiss</Button>
        <Button variant="contained">View details</Button>
      </CardActions>
    </Card>
  ),
}
