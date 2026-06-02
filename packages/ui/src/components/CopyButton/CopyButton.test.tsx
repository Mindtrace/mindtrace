import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent } from '@testing-library/react'

import { render, screen, waitFor } from '../../test-utils'
import { CopyButton } from './CopyButton'

describe('CopyButton', () => {
  let writeText: ReturnType<typeof vi.fn>

  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('writes value on click + fires onCopy', async () => {
    const onCopy = vi.fn()
    render(<CopyButton value="abc" onCopy={onCopy} disableTooltip />)
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('abc'))
    await waitFor(() => expect(onCopy).toHaveBeenCalledWith(true))
  })
})
