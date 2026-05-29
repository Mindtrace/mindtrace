import Dialog, { type DialogProps } from '@mui/material/Dialog'
import DialogActions, { type DialogActionsProps } from '@mui/material/DialogActions'
import DialogContent, { type DialogContentProps } from '@mui/material/DialogContent'
import DialogContentText, { type DialogContentTextProps } from '@mui/material/DialogContentText'
import DialogTitle, { type DialogTitleProps } from '@mui/material/DialogTitle'
import { forwardRef } from 'react'

export type ModalProps = DialogProps

/**
 * Centered modal dialog. Thin wrapper around MUI Dialog — re-exports
 * `ModalTitle`, `ModalContent`, `ModalContentText`, `ModalActions` for
 * structured layouts.
 *
 *   <Modal open={open} onClose={close}>
 *     <ModalTitle>Confirm</ModalTitle>
 *     <ModalContent>Are you sure?</ModalContent>
 *     <ModalActions>…</ModalActions>
 *   </Modal>
 */
export const Modal = forwardRef<HTMLDivElement, ModalProps>(function Modal(props, ref) {
  return <Dialog ref={ref} {...props} />
})

export const ModalTitle = DialogTitle
export const ModalContent = DialogContent
export const ModalContentText = DialogContentText
export const ModalActions = DialogActions
export type ModalTitleProps = DialogTitleProps
export type ModalContentProps = DialogContentProps
export type ModalContentTextProps = DialogContentTextProps
export type ModalActionsProps = DialogActionsProps
