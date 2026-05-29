import MuiCard, { type CardProps as MuiCardProps } from '@mui/material/Card'
import CardActions, { type CardActionsProps } from '@mui/material/CardActions'
import CardContent, { type CardContentProps } from '@mui/material/CardContent'
import CardHeader, { type CardHeaderProps } from '@mui/material/CardHeader'
import { forwardRef } from 'react'

export type CardProps = MuiCardProps

/**
 * Surface for grouped content. Thin wrapper around MUI Card; pair with
 * `CardHeader`, `CardContent`, `CardActions` re-exports.
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(props, ref) {
  return <MuiCard ref={ref} {...props} />
})

export { CardActions, CardContent, CardHeader }
export type { CardActionsProps, CardContentProps, CardHeaderProps }
