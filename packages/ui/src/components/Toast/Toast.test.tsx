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
})
