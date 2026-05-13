import { useCallback, useEffect, useRef, useState } from 'react'

export type CopyState = {
  /** True for `resetMs` after a successful copy, then resets. */
  copied: boolean
  /** Last clipboard error (browser API rejection or absent API). */
  error: Error | null
}

export type UseCopyToClipboardOptions = {
  /** How long the `copied` flag stays true. Default `1500` ms. */
  resetMs?: number
}

/**
 * Copy-to-clipboard hook with a self-clearing `copied` flag.
 *
 *   const [copy, { copied }] = useCopyToClipboard()
 *   <Button onClick={() => copy('abc')}>{copied ? 'Copied' : 'Copy'}</Button>
 *
 * Returns a tuple of (`copy(text) => Promise<boolean>`, state). The
 * promise resolves to `true` when the write succeeds.
 */
export function useCopyToClipboard(
  options: UseCopyToClipboardOptions = {},
): [copy: (text: string) => Promise<boolean>, state: CopyState] {
  const { resetMs = 1500 } = options
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  const copy = useCallback(
    async (text: string) => {
      try {
        if (!navigator?.clipboard?.writeText) {
          throw new Error('Clipboard API unavailable')
        }
        await navigator.clipboard.writeText(text)
        setCopied(true)
        setError(null)
        if (timeoutRef.current) clearTimeout(timeoutRef.current)
        timeoutRef.current = setTimeout(() => setCopied(false), resetMs)
        return true
      } catch (e) {
        setCopied(false)
        setError(e instanceof Error ? e : new Error(String(e)))
        return false
      }
    },
    [resetMs],
  )

  return [copy, { copied, error }]
}
