import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import FormHelperText from '@mui/material/FormHelperText'
import FormLabel from '@mui/material/FormLabel'
import MuiRadio, { type RadioProps as MuiRadioProps } from '@mui/material/Radio'
import MuiRadioGroup, { type RadioGroupProps as MuiRadioGroupProps } from '@mui/material/RadioGroup'
import type { ReactNode } from 'react'

export type RadioProps = MuiRadioProps & { label?: ReactNode }

/**
 * Single radio input. Typically used inside a `RadioGroup`. Use the
 * `label` prop to avoid composing FormControlLabel manually.
 */
export function Radio({ label, ...rest }: RadioProps) {
  const control = <MuiRadio {...rest} />
  if (label === undefined) return control
  return <FormControlLabel control={control} label={label} />
}

export type RadioOption<T extends string = string> = {
  value: T
  label: ReactNode
  disabled?: boolean
}

export type RadioGroupProps<T extends string = string> = Omit<MuiRadioGroupProps, 'onChange'> & {
  /** Group heading. */
  label?: ReactNode
  /** Helper text under the group. */
  helperText?: ReactNode
  /** Show validation error styling. */
  error?: boolean
  /** Convenience for a flat list of radios. Use children for custom rendering. */
  options?: RadioOption<T>[]
  onChange?: (value: T) => void
}

/**
 * Group of radio inputs sharing a name. Renders an optional heading +
 * helper text and supports a flat `options` array.
 *
 *   <RadioGroup
 *     label="Plan"
 *     value={plan}
 *     onChange={setPlan}
 *     options={[{ value: 'free', label: 'Free' }, { value: 'pro', label: 'Pro' }]}
 *   />
 */
export function RadioGroup<T extends string = string>({
  label,
  helperText,
  error,
  options,
  onChange,
  children,
  ...rest
}: RadioGroupProps<T>) {
  return (
    <FormControl error={error} component="fieldset">
      {label && <FormLabel component="legend">{label}</FormLabel>}
      <MuiRadioGroup {...rest} onChange={(_, v) => onChange?.(v as T)}>
        {options
          ? options.map((o) => (
              <FormControlLabel
                key={String(o.value)}
                value={o.value}
                control={<MuiRadio />}
                label={o.label}
                disabled={o.disabled}
              />
            ))
          : children}
      </MuiRadioGroup>
      {helperText && <FormHelperText>{helperText}</FormHelperText>}
    </FormControl>
  )
}
