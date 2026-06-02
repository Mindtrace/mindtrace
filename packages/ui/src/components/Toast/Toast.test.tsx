import { useRef } from 'react'
import { describe, expect, it } from 'vitest'

import { render, screen, userEvent, waitFor, within } from '../../test-utils'
import { Button } from '../Button'
import { ToastProvider, useToast } from './ToastProvider'

function App() {
  const t = useToast()
  return (
    <div>
      <Button onClick={() => t.success('Saved')}>Save</Button>
      <Button onClick={() => t.error('Could not reach the API')}>Fail</Button>
      <Button onClick={() => t.clear()}>Clear</Button>
    </div>
  )
}

function StickyApp() {
  const t = useToast()
  const n = useRef(0)
  return (
    <div>
      {/* A sticky toast never auto-dismisses (durationMs: null). */}
      <Button onClick={() => t.info('Sticky note', { durationMs: null })}>Sticky</Button>
      {/* Non-sticky filler toasts (long duration so they don't fire mid-test),
          each with a distinct label. These are the ones trimming may drop. */}
      <Button onClick={() => t.success(`Filler ${(n.current += 1)}`, { durationMs: 100000 })}>Filler</Button>
    </div>
  )
}

describe('Toast', () => {
  it('shows a success toast on demand', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <App />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
  })

  it('auto-dismisses after the duration', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider defaultDurationMs={150}>
        <App />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
    await waitFor(
      () => {
        expect(screen.queryByText('Saved')).not.toBeInTheDocument()
      },
      { timeout: 1000 },
    )
  })

  it('clear() drops all queued toasts', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <App />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await user.click(screen.getByRole('button', { name: 'Fail' }))
    const region = await screen.findByRole('region', { name: 'Notifications' })
    expect(within(region).getByText('Saved')).toBeInTheDocument()
    expect(within(region).getByText('Could not reach the API')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    expect(within(region).queryByText('Saved')).not.toBeInTheDocument()
    expect(within(region).queryByText('Could not reach the API')).not.toBeInTheDocument()
  })

  it('keeps sticky toasts when trimming to max, dropping oldest non-sticky first', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider max={2}>
        <StickyApp />
      </ToastProvider>,
    )
    const sticky = screen.getByRole('button', { name: 'Sticky' })
    const filler = screen.getByRole('button', { name: 'Filler' })

    await user.click(sticky) // [Sticky]
    await user.click(filler) // [Sticky, Filler 1]
    await user.click(filler) // over max → drop Filler 1 → [Sticky, Filler 2]
    await user.click(filler) // over max → drop Filler 2 → [Sticky, Filler 3]

    const region = await screen.findByRole('region', { name: 'Notifications' })
    // The sticky toast is the oldest, yet it must survive the trimming.
    expect(within(region).getByText('Sticky note')).toBeInTheDocument()
    // Only the newest non-sticky filler remains; older ones were dropped.
    expect(within(region).getByText('Filler 3')).toBeInTheDocument()
    expect(within(region).queryByText('Filler 1')).not.toBeInTheDocument()
    expect(within(region).queryByText('Filler 2')).not.toBeInTheDocument()
  })
})
