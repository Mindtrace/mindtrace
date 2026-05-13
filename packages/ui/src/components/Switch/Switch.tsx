import FormControlLabel from '@mui/material/FormControlLabel'
import FormHelperText from '@mui/material/FormHelperText'
import Stack from '@mui/material/Stack'
import MuiSwitch, { type SwitchProps as MuiSwitchProps } from '@mui/material/Switch'
import type { ReactNode } from 'react'

export type SwitchProps = MuiSwitchProps & {
  label?: ReactNode
  helperText?: ReactNode
  labelPlacement?: 'start' | 'end'
}

/**
 * Toggle. Wraps MUI Switch with an optional inline label + helper text.
 *
 *   <Switch label="Email me on failures" checked={v} onChange={(_, n) => setV(n)} />
 */
export function Switch({ label, helperText, labelPlacement = 'end', sx, ...rest }: SwitchProps) {
  const control = <MuiSwitch {...rest} />
  if (!label && !helperText) return control
  return (
    <Stack spacing={0.25} sx={{ display: 'inline-flex' }}>
      <FormControlLabel control={control} label={label ?? ''} labelPlacement={labelPlacement} sx={sx} />
      {helperText && (
        <FormHelperText sx={{ ml: labelPlacement === 'start' ? 0 : 6.25 }}>{helperText}</FormHelperText>
      )}
    </Stack>
  )
}
