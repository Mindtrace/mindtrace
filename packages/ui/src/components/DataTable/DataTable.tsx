/**
 * DataTable — a thin, typed wrapper around MUI Table for the common
 * "render a list of objects as rows with named columns" case.
 *
 * For complex needs (sorting, filtering, virtualization, server-side
 * paging) reach for `@mui/x-data-grid` directly. This is the cheap path.
 *
 *   <DataTable
 *     rows={items}
 *     columns={[
 *       { id: 'name', label: 'Name' },
 *       { id: 'status', label: 'Status', render: (r) => <StatusBadge ... /> },
 *       { id: 'created_at', label: 'Created', align: 'right',
 *         render: (r) => fmtDate(r.created_at) },
 *     ]}
 *     getRowKey={(r) => r.id}
 *     onRowClick={(r) => navigate(`/x/${r.id}`)}
 *     empty="No items yet."
 *   />
 */

import Box from '@mui/material/Box'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'

import { EmptyState } from '../EmptyState/EmptyState'

export type Column<Row> = {
  id: string
  label: ReactNode
  align?: 'left' | 'right' | 'center'
  width?: number | string
  render?: (row: Row) => ReactNode
}

export type DataTableProps<Row> = {
  rows: Row[]
  columns: Column<Row>[]
  getRowKey: (row: Row) => string
  onRowClick?: (row: Row) => void
  empty?: ReactNode
  loading?: boolean
  /** Reduce row height (small) or use comfortable defaults (medium). */
  density?: 'small' | 'medium'
}

export function DataTable<Row>({
  rows,
  columns,
  getRowKey,
  onRowClick,
  empty,
  loading,
  density = 'small',
}: DataTableProps<Row>) {
  if (!loading && rows.length === 0) {
    return (
      <EmptyState
        title="No results"
        description={typeof empty === 'string' ? empty : 'Nothing to show here.'}
      />
    )
  }
  return (
    <TableContainer>
      <Table size={density} stickyHeader>
        <TableHead>
          <TableRow>
            {columns.map((col) => (
              <TableCell key={col.id} align={col.align} sx={{ width: col.width }}>
                {col.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow
              key={getRowKey(row)}
              hover={Boolean(onRowClick)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              sx={{
                cursor: onRowClick ? 'pointer' : 'default',
                '&:last-child td': { borderBottom: 0 },
              }}
            >
              {columns.map((col) => (
                <TableCell key={col.id} align={col.align}>
                  {col.render ? col.render(row) : renderDefault(row, col.id)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {loading && (
        <Box sx={{ textAlign: 'center', py: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Loading…
          </Typography>
        </Box>
      )}
    </TableContainer>
  )
}

function renderDefault<Row>(row: Row, id: string): ReactNode {
  const v = (row as Record<string, unknown>)[id]
  if (v == null) return '—'
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v)
  return JSON.stringify(v)
}
