import MuiDrawer, { type DrawerProps as MuiDrawerProps } from '@mui/material/Drawer'
import { forwardRef } from 'react'

export type DrawerProps = MuiDrawerProps

/**
 * Edge-anchored sliding panel. Thin wrapper around MUI Drawer.
 *
 *   <Drawer anchor="right" open={open} onClose={close}>…</Drawer>
 */
export const Drawer = forwardRef<HTMLDivElement, DrawerProps>(function Drawer(props, ref) {
  return <MuiDrawer ref={ref} {...props} />
})
