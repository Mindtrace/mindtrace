import MuiTextField, { type TextFieldProps as MuiTextFieldProps } from '@mui/material/TextField'
import { forwardRef } from 'react'

export type TextFieldProps = MuiTextFieldProps

/**
 * Single- or multi-line text input. Thin wrapper around MUI TextField.
 *
 *   <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
 */
export const TextField = forwardRef<HTMLDivElement, TextFieldProps>(function TextField(props, ref) {
  return <MuiTextField ref={ref} {...props} />
})
