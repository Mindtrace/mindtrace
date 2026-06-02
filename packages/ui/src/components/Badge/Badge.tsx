import Chip, { type ChipProps } from '@mui/material/Chip'
import { forwardRef } from 'react'

export type BadgeProps = ChipProps

/**
 * Inline label/tag. Wraps MUI Chip rather than MUI Badge because the
 * common product use-case here is "small labelled token", not "counter dot".
 * For dot/counter overlay semantics, import MUI Badge directly.
 *
 *   <Badge label="active" color="primary" size="small" />
 */
export const Badge = forwardRef<HTMLDivElement, BadgeProps>(function Badge(props, ref) {
  return <Chip ref={ref} size="small" variant="outlined" {...props} />
})
