/**
 * ConfirmDialog — preset over Modal for the "are you sure?" pattern.
 *
 *   <ConfirmDialog
 *     open={open}
 *     title="Delete project?"
 *     description="This action is permanent."
 *     destructive
 *     confirmLabel="Delete"
 *     loading={deleting}
 *     onConfirm={handleDelete}
 *     onCancel={close}
 *   />
 *
 * Renders a focused dialog with a description body, cancel button,
 * and a primary confirm button (red when `destructive`). When `loading`
 * is true the confirm button shows a spinner and disables both buttons.
 */

import CircularProgress from '@mui/material/CircularProgress'
import { type ReactNode } from 'react'

import { Button } from '../Button'
import { Modal, ModalActions, ModalContent, ModalContentText, ModalTitle } from '../Modal'

export type ConfirmDialogProps = {
  open: boolean
  title: ReactNode
  description?: ReactNode
  /** Extra body content rendered below the description. */
  children?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Red confirm button + warning tone. */
  destructive?: boolean
  /** Show a spinner on confirm; disable both buttons. */
  loading?: boolean
  /** Confirm handler. May be async — pair with `loading` to drive UI. */
  onConfirm: () => void | Promise<void>
  /** Cancel handler. Also called when the backdrop is clicked. */
  onCancel: () => void
  /** Hide the cancel button (e.g. for forced acknowledgements). */
  hideCancel?: boolean
  /** Max width forwarded to the dialog. Default `'xs'`. */
  maxWidth?: 'xs' | 'sm' | 'md'
}

export function ConfirmDialog({
  open,
  title,
  description,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  loading = false,
  onConfirm,
  onCancel,
  hideCancel = false,
  maxWidth = 'xs',
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={loading ? undefined : onCancel}
      maxWidth={maxWidth}
      fullWidth
      aria-labelledby="confirm-dialog-title"
    >
      <ModalTitle id="confirm-dialog-title">{title}</ModalTitle>
      {(description || children) && (
        <ModalContent>
          {description && <ModalContentText>{description}</ModalContentText>}
          {children}
        </ModalContent>
      )}
      <ModalActions>
        {!hideCancel && (
          <Button variant="text" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
        )}
        <Button
          variant="contained"
          color={destructive ? 'error' : 'primary'}
          onClick={onConfirm}
          disabled={loading}
          startIcon={loading ? <CircularProgress size={14} color="inherit" /> : undefined}
        >
          {confirmLabel}
        </Button>
      </ModalActions>
    </Modal>
  )
}
