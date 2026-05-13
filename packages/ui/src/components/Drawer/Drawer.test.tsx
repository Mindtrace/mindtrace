import { describe, expect, it } from 'vitest'

import { render, screen } from '../../test-utils'
import { Drawer } from './Drawer'

describe('Drawer', () => {
  it('renders contents when open', () => {
    render(
      <Drawer open onClose={() => {}}>
        <div>panel</div>
      </Drawer>,
    )
    expect(screen.getByText('panel')).toBeInTheDocument()
  })
})
