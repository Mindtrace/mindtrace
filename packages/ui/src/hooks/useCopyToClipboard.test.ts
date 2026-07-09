import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopyToClipboard } from './useCopyToClipboard'

describe('useCopyToClipboard', () => {
  let writeText: ReturnType<typeof vi.fn>

  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('writes to the clipboard + flips copied true', async () => {
    const { result } = renderHook(() => useCopyToClipboard({ resetMs: 1000 }))
    let ok: boolean | undefined
    await act(async () => {
      ok = await result.current[0]('hello')
    })
    expect(ok).toBe(true)
    expect(writeText).toHaveBeenCalledWith('hello')
    expect(result.current[1].copied).toBe(true)
  })

  it('resets copied after resetMs', async () => {
    const { result } = renderHook(() => useCopyToClipboard({ resetMs: 100 }))
    await act(async () => {
      await result.current[0]('x')
    })
    expect(result.current[1].copied).toBe(true)
    await waitFor(() => expect(result.current[1].copied).toBe(false), { timeout: 500 })
  })

  it('captures errors when clipboard write fails', async () => {
    writeText.mockRejectedValueOnce(new Error('denied'))
    const { result } = renderHook(() => useCopyToClipboard())
    let ok: boolean | undefined
    await act(async () => {
      ok = await result.current[0]('x')
    })
    expect(ok).toBe(false)
    expect(result.current[1].copied).toBe(false)
    expect(result.current[1].error?.message).toBe('denied')
  })
})
