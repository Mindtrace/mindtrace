import MuiButton, { type ButtonProps as MuiButtonProps } from '@mui/material/Button'
import { forwardRef } from 'react'

export type ButtonProps = MuiButtonProps

/**
 * Standard action button. Thin wrapper around MUI Button — accepts every MUI prop.
 *
 *   <Button variant="contained" color="primary">Save changes</Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(props, ref) {
  return <MuiButton ref={ref} {...props} />
})
