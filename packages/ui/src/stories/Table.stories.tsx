import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import type { Meta, StoryObj } from '@storybook/react'

const meta = {
  title: 'Components/Table',
  component: Table,
  tags: ['autodocs'],
} satisfies Meta<typeof Table>

export default meta
type Story = StoryObj<typeof meta>

const rows = [
  { id: 'r-9241', pipeline: 'weld-detect-v3', latency: 142, status: 'success' },
  { id: 'r-9240', pipeline: 'weld-detect-v3', latency: 138, status: 'success' },
  { id: 'r-9239', pipeline: 'spatter-classify-v2', latency: 312, status: 'warning' },
  { id: 'r-9238', pipeline: 'spatter-classify-v2', latency: 0, status: 'error' },
]

export const Default: Story = {
  render: () => (
    <Paper>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Pipeline</TableCell>
              <TableCell align="right">Latency</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell>{r.id}</TableCell>
                <TableCell>{r.pipeline}</TableCell>
                <TableCell align="right">{r.latency} ms</TableCell>
                <TableCell>{r.status}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  ),
}
