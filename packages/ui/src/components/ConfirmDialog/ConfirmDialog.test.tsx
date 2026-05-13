import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders title + description', () => {
    render(
      <ConfirmDialog
        open
        title="Delete?"
        description="Permanent."
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByText('Delete?')).toBeInTheDocument()
    expect(screen.getByText('Permanent.')).toBeInTheDocument()
  })

  it('fires onConfirm and onCancel', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    const user = userEvent.setup()
    render(
      <ConfirmDialog
        open
        title="Delete?"
        confirmLabel="Delete"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).toHaveBeenCalled()
  })

  it('disables buttons when loading', () => {
    render(
      <ConfirmDialog open title="X" loading onConfirm={() => {}} onCancel={() => {}} />,
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
  })

  it('hides cancel when hideCancel is set', () => {
    render(
      <ConfirmDialog open title="X" hideCancel onConfirm={() => {}} onCancel={() => {}} />,
    )
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
  })
})
