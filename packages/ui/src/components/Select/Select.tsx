import FormControl from '@mui/material/FormControl'
import FormHelperText from '@mui/material/FormHelperText'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import MuiSelect, { type SelectProps as MuiSelectProps } from '@mui/material/Select'
import { useId } from 'react'

export type SelectOption<T extends string | number = string> = {
  value: T
  label: string
  disabled?: boolean
}

export type SelectProps<T extends string | number = string> = Omit<MuiSelectProps<T>, 'children'> & {
  /** Convenience for a flat list of options. Use MUI Select's `children` for grouped/custom rendering. */
  options?: SelectOption<T>[]
  /** Helper text below the select. */
  helperText?: string
}

/**
 * Single-value select. Wraps MUI Select with an `options` shortcut + label/helper wiring.
 *
 *   <Select label="Environment" options={[{ value: 'a', label: 'A' }]} value={env} onChange={…} />
 */
export function Select<T extends string | number = string>({
  options,
  helperText,
  label,
  id,
  fullWidth,
  size,
  error,
  ...rest
}: SelectProps<T>) {
  const autoId = useId()
  const fieldId = id ?? `mt-select-${autoId}`
  const labelId = `${fieldId}-label`
  return (
    <FormControl fullWidth={fullWidth} size={size} error={error}>
      {label ? <InputLabel id={labelId}>{label}</InputLabel> : null}
      <MuiSelect<T> labelId={label ? labelId : undefined} id={fieldId} label={label} {...rest}>
        {options?.map((o) => (
          <MenuItem key={String(o.value)} value={o.value} disabled={o.disabled}>
            {o.label}
          </MenuItem>
        ))}
      </MuiSelect>
      {helperText ? <FormHelperText>{helperText}</FormHelperText> : null}
    </FormControl>
  )
}
