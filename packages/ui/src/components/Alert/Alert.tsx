import MuiAlert, { type AlertProps as MuiAlertProps } from '@mui/material/Alert'
import AlertTitle, { type AlertTitleProps } from '@mui/material/AlertTitle'
import { forwardRef } from 'react'

export type AlertProps = MuiAlertProps

/**
 * Inline feedback message. Thin wrapper around MUI Alert.
 *
 *   <Alert severity="warning">Connection unstable. Retrying…</Alert>
 */
export const Alert = forwardRef<HTMLDivElement, AlertProps>(function Alert(props, ref) {
  return <MuiAlert ref={ref} {...props} />
})

export { AlertTitle }
export type { AlertTitleProps }
