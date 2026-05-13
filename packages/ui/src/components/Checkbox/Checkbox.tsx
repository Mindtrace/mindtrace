import FormControlLabel from '@mui/material/FormControlLabel'
import FormHelperText from '@mui/material/FormHelperText'
import MuiCheckbox, { type CheckboxProps as MuiCheckboxProps } from '@mui/material/Checkbox'
import Stack from '@mui/material/Stack'
import type { ReactNode } from 'react'

export type CheckboxProps = MuiCheckboxProps & {
  /** Inline label shown to the right of the box. */
  label?: ReactNode
  /** Description shown beneath the label. */
  helperText?: ReactNode
  /** Place the label on the left instead of the right. */
  labelPlacement?: 'start' | 'end'
}

/**
 * Boolean input with an optional inline label + helper text. Wraps MUI
 * Checkbox + FormControlLabel so callers don't have to compose them.
 *
 *   <Checkbox label="Subscribe to updates" checked={v} onChange={(_, n) => setV(n)} />
 */
export function Checkbox({
  label,
  helperText,
  labelPlacement = 'end',
  sx,
  ...rest
}: CheckboxProps) {
  const control = <MuiCheckbox {...rest} />
  if (!label && !helperText) return control
  return (
    <Stack spacing={0.25} sx={{ display: 'inline-flex' }}>
      <FormControlLabel control={control} label={label ?? ''} labelPlacement={labelPlacement} sx={sx} />
      {helperText && (
        <FormHelperText sx={{ ml: labelPlacement === 'start' ? 0 : 3.75 }}>
          {helperText}
        </FormHelperText>
      )}
    </Stack>
  )
}
