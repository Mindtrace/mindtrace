/**
 * Toast system — global notification queue.
 *
 * Mount `<ToastProvider>` once at the app root. Children call
 * `useToast()` to push notifications:
 *
 *   const toast = useToast()
 *   toast.success('Saved')
 *   toast.error('Could not connect', { durationMs: 6000 })
 *   const id = toast.show({ severity: 'info', message: 'Working…', durationMs: null })
 *   toast.dismiss(id)
 */

import Alert, { type AlertColor } from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Portal from '@mui/material/Portal'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

export type ToastSeverity = AlertColor // 'success' | 'error' | 'warning' | 'info'

export type Toast = {
  id: string
  severity: ToastSeverity
  message: ReactNode
  /** Auto-dismiss after this many ms. `null` means "keep until dismissed." */
  durationMs: number | null
  /** Optional title rendered above the message. */
  title?: ReactNode
}

export type ToastInput = Omit<Toast, 'id' | 'durationMs'> & { durationMs?: number | null }

export type ToastApi = {
  show: (input: ToastInput) => string
  success: (message: ReactNode, opts?: Partial<ToastInput>) => string
  error: (message: ReactNode, opts?: Partial<ToastInput>) => string
  warning: (message: ReactNode, opts?: Partial<ToastInput>) => string
  info: (message: ReactNode, opts?: Partial<ToastInput>) => string
  dismiss: (id: string) => void
  clear: () => void
}

const ToastContext = createContext<ToastApi | null>(null)

export type ToastAnchor = {
  vertical: 'top' | 'bottom'
  horizontal: 'left' | 'center' | 'right'
}

export type ToastProviderProps = {
  children: ReactNode
  /** Stack anchor. Default `{ vertical: 'bottom', horizontal: 'right' }`. */
  anchorOrigin?: ToastAnchor
  /** Default auto-dismiss in ms. Default `5000`. */
  defaultDurationMs?: number
  /** Max simultaneous toasts before the oldest auto-drops. Default `5`. */
  max?: number
  /** Edge offset for the viewport in pixels. Default `24`. */
  offset?: number
}

let counter = 0
function genId() {
  counter += 1
  return `t-${Date.now().toString(36)}-${counter}`
}

export function ToastProvider({
  children,
  anchorOrigin = { vertical: 'bottom', horizontal: 'right' },
  defaultDurationMs = 5000,
  max = 5,
  offset = 24,
}: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const clear = useCallback(() => setToasts([]), [])

  const show = useCallback(
    (input: ToastInput): string => {
      const id = genId()
      const next: Toast = {
        id,
        severity: input.severity,
        message: input.message,
        title: input.title,
        durationMs: input.durationMs === undefined ? defaultDurationMs : input.durationMs,
      }
      setToasts((prev) => {
        const trimmed = prev.length >= max ? prev.slice(prev.length - max + 1) : prev
        return [...trimmed, next]
      })
      return id
    },
    [defaultDurationMs, max],
  )

  const api = useMemo<ToastApi>(
    () => ({
      show,
      success: (message, opts) => show({ severity: 'success', message, ...opts }),
      error: (message, opts) => show({ severity: 'error', message, ...opts }),
      warning: (message, opts) => show({ severity: 'warning', message, ...opts }),
      info: (message, opts) => show({ severity: 'info', message, ...opts }),
      dismiss,
      clear,
    }),
    [show, dismiss, clear],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      {toasts.length > 0 && (
        <Portal>
          <ToastViewport toasts={toasts} anchorOrigin={anchorOrigin} offset={offset} onDismiss={dismiss} />
        </Portal>
      )}
    </ToastContext.Provider>
  )
}

function ToastViewport({
  toasts,
  anchorOrigin,
  offset,
  onDismiss,
}: {
  toasts: Toast[]
  anchorOrigin: ToastAnchor
  offset: number
  onDismiss: (id: string) => void
}) {
  const isTop = anchorOrigin.vertical === 'top'
  const horizontal =
    anchorOrigin.horizontal === 'center'
      ? ({ left: '50%', transform: 'translateX(-50%)' } as const)
      : anchorOrigin.horizontal === 'left'
        ? ({ left: offset } as const)
        : ({ right: offset } as const)

  return (
    <Box
      role="region"
      aria-label="Notifications"
      sx={{
        position: 'fixed',
        zIndex: (theme) => theme.zIndex.snackbar,
        display: 'flex',
        flexDirection: isTop ? 'column' : 'column-reverse',
        gap: 1,
        pointerEvents: 'none',
        ...(isTop ? { top: offset } : { bottom: offset }),
        ...horizontal,
      }}
    >
      {toasts.map((t) => (
        <ToastRow key={t.id} toast={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </Box>
  )
}

function ToastRow({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  useEffect(() => {
    if (toast.durationMs == null) return
    const handle = setTimeout(onDismiss, toast.durationMs)
    return () => clearTimeout(handle)
  }, [toast.durationMs, onDismiss])

  return (
    <Alert
      severity={toast.severity}
      variant="filled"
      onClose={onDismiss}
      sx={{ minWidth: 280, maxWidth: 480, pointerEvents: 'auto' }}
    >
      {toast.title && (
        <Box component="strong" sx={{ display: 'block', mb: 0.25 }}>
          {toast.title}
        </Box>
      )}
      {toast.message}
    </Alert>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used inside <ToastProvider>')
  }
  return ctx
}
