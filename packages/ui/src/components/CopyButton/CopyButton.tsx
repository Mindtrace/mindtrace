/**
 * CopyButton — icon button that copies a string to the clipboard.
 *
 *   <Mono>{id}</Mono>
 *   <CopyButton value={id} />
 *
 * Shows a check icon for ~1.5s after success. Wrapped in a tooltip
 * unless `disableTooltip` is set.
 */

import CheckIcon from '@mui/icons-material/Check'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import IconButton, { type IconButtonProps } from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import { forwardRef } from 'react'

import { useCopyToClipboard } from '../../hooks/useCopyToClipboard'

export type CopyButtonProps = Omit<IconButtonProps, 'onClick' | 'children'> & {
  /** Text to copy when the button is clicked. */
  value: string
  /** Tooltip shown by default. */
  label?: string
  /** Tooltip shown right after a successful copy. */
  copiedLabel?: string
  /** Skip the tooltip entirely. */
  disableTooltip?: boolean
  /** Called after a copy attempt. Receives `true` on success. */
  onCopy?: (success: boolean) => void
}

export const CopyButton = forwardRef<HTMLButtonElement, CopyButtonProps>(function CopyButton(
  {
    value,
    label = 'Copy',
    copiedLabel = 'Copied',
    disableTooltip = false,
    onCopy,
    size = 'small',
    ...rest
  },
  ref,
) {
  const [copy, { copied }] = useCopyToClipboard()
  const handle = async () => {
    const ok = await copy(value)
    onCopy?.(ok)
  }
  const button = (
    <IconButton
      ref={ref}
      size={size}
      onClick={handle}
      aria-label={copied ? copiedLabel : label}
      {...rest}
    >
      {copied ? <CheckIcon fontSize="inherit" /> : <ContentCopyIcon fontSize="inherit" />}
    </IconButton>
  )
  if (disableTooltip) return button
  return <Tooltip title={copied ? copiedLabel : label}>{button}</Tooltip>
})
