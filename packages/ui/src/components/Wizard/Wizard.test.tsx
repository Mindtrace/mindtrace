import { useEffect } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Wizard, type WizardHelpers } from './Wizard'

const steps = [
  { key: 'one', title: 'Step one' },
  { key: 'two', title: 'Step two' },
  { key: 'three', title: 'Step three' },
]

function AutoValid({ helpers }: { helpers: WizardHelpers }) {
  useEffect(() => {
    helpers.setValid(true)
  }, [helpers])
  return <div>step body</div>
}

describe('Wizard', () => {
  it('advances through steps and fires onFinish', async () => {
    const onFinish = vi.fn()
    const user = userEvent.setup()
    render(
      <Wizard
        steps={steps}
        renderStep={(_, helpers) => <AutoValid helpers={helpers} />}
        onFinish={onFinish}
      />,
    )
    await user.click(screen.getByRole('button', { name: /next/i }))
    await user.click(screen.getByRole('button', { name: /next/i }))
    await user.click(screen.getByRole('button', { name: /finish/i }))
    expect(onFinish).toHaveBeenCalled()
  })

  it('disables Next when step is invalid', () => {
    render(<Wizard steps={steps} renderStep={() => <div>x</div>} />)
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
  })
})
