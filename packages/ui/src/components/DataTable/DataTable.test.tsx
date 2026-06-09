import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { DataTable } from './DataTable'

type Row = { id: string; name: string }
const rows: Row[] = [
  { id: 'a', name: 'Alice' },
  { id: 'b', name: 'Bob' },
]
const columns = [
  { id: 'id', label: 'ID' },
  { id: 'name', label: 'Name' },
]

describe('DataTable', () => {
  it('renders rows + columns', () => {
    render(<DataTable rows={rows} columns={columns} getRowKey={(r) => r.id} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('ID')).toBeInTheDocument()
  })

  it('shows empty state', () => {
    render(<DataTable rows={[]} columns={columns} getRowKey={(r: Row) => r.id} empty="None" />)
    expect(screen.getByText('None')).toBeInTheDocument()
  })

  it('fires onRowClick', async () => {
    const onRowClick = vi.fn()
    const user = userEvent.setup()
    render(<DataTable rows={rows} columns={columns} getRowKey={(r) => r.id} onRowClick={onRowClick} />)
    await user.click(screen.getByText('Alice'))
    expect(onRowClick).toHaveBeenCalledWith(rows[0])
  })

  it('falls back to a dash for non-primitive cells (no crash on circular refs)', () => {
    // A circular object would throw if the default renderer called JSON.stringify.
    const circular: { self?: unknown } = {}
    circular.self = circular
    const objRows = [{ id: 'x', meta: circular }]
    expect(() =>
      render(
        <DataTable
          rows={objRows}
          columns={[
            { id: 'id', label: 'ID' },
            { id: 'meta', label: 'Meta' },
          ]}
          getRowKey={(r) => r.id}
        />,
      ),
    ).not.toThrow()
    // The non-primitive cell renders the em-dash placeholder, not raw JSON.
    expect(screen.getByText('x')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
