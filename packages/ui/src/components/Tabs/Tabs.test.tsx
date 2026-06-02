import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Tabs } from './Tabs'

const tabs = [
  { value: 'overview', label: 'Overview', content: <div>Overview body</div> },
  { value: 'members', label: 'Members', content: <div>Members body</div> },
]

describe('Tabs', () => {
  it('renders the active panel and switches', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<Tabs tabs={tabs} defaultValue="overview" onChange={onChange} />)
    expect(screen.getByText('Overview body')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Members' }))
    expect(onChange).toHaveBeenLastCalledWith('members')
    expect(screen.getByText('Members body')).toBeInTheDocument()
  })

  it('renders a disabled tab as disabled', () => {
    render(
      <Tabs
        tabs={[
          { value: 'a', label: 'A', content: <div>A</div> },
          { value: 'b', label: 'B', content: <div>B</div>, disabled: true },
        ]}
        defaultValue="a"
      />,
    )
    expect(screen.getByRole('tab', { name: 'B' })).toBeDisabled()
  })
})
