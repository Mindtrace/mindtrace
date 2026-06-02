import { describe, expect, it, vi } from 'vitest'

import { render, screen, userEvent } from '../../test-utils'
import { Modal, ModalActions, ModalContent, ModalTitle } from './Modal'
import { Button } from '../Button'

describe('Modal', () => {
  it('renders when open', () => {
    render(
      <Modal open onClose={() => {}}>
        <ModalTitle>Title</ModalTitle>
        <ModalContent>Body</ModalContent>
      </Modal>,
    )
    expect(screen.getByText('Title')).toBeInTheDocument()
    expect(screen.getByText('Body')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(
      <Modal open={false} onClose={() => {}}>
        <ModalTitle>Hidden</ModalTitle>
      </Modal>,
    )
    expect(screen.queryByText('Hidden')).not.toBeInTheDocument()
  })

  it('fires onClose when escape is pressed', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <Modal open onClose={onClose}>
        <ModalTitle>X</ModalTitle>
        <ModalActions>
          <Button>Cancel</Button>
        </ModalActions>
      </Modal>,
    )
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
