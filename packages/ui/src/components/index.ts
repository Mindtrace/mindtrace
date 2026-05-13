/**
 * Public component surface for `@mindtrace/ui`.
 *
 * Three groups:
 *   1. Thin wrappers around MUI: `Button`, `TextField`, `Select`, `Checkbox`,
 *      `Switch`, `Radio`, `Card`, `Badge`, `Alert`, `Modal`, `Drawer`,
 *      `Tabs`, `Avatar`. Use these in app code instead of reaching for MUI
 *      directly so theme/behavior overrides stay centralized.
 *   2. Bespoke patterns: `PageHeader`, `FormSection`, `EmptyState`, `DataTable`,
 *      `KpiCard`, `SectionCard`, `FilterChips`, `SearchField`, `StatusDot`,
 *      `StatusBadge`, `SeverityBadge`, `NumberBadge`, `Mono`, `Wizard`,
 *      `PathBreadcrumb`, `PageLayout`, `ConfirmDialog`, `Toast`, `CopyButton`.
 *   3. Raw MUI re-exports for layout/utility primitives that don't warrant
 *      a wrapper: `Box`, `Stack`, `Container`, `Grid`, `Divider`, `Typography`,
 *      `Link`, `IconButton`, `Tooltip`, `Chip`, etc.
 *
 * Brand-specific elements (logos, layout shells) live in consuming apps —
 * this library stays brand-agnostic.
 */

// ── Wrappers ─────────────────────────────────────────────────────────────
export * from './Alert'
export * from './Avatar'
export * from './Badge'
export * from './Button'
export * from './Card'
export * from './Checkbox'
export * from './ConfirmDialog'
export * from './CopyButton'
export * from './Drawer'
export * from './FormSection'
export * from './Modal'
export * from './Radio'
export * from './Select'
export * from './Switch'
export * from './Tabs'
export * from './TextField'
export * from './Toast'

// ── Layout primitives ────────────────────────────────────────────────────
export * from './AppBar'
export * from './AppShell'
export * from './HeroBackground'
export * from './PageContainer'
export * from './PageLayout'
export * from './PrimaryRail'
export * from './UserMenu'

// ── Bespoke patterns ────────────────────────────────────────────────────
export * from './DataTable'
export * from './EmptyState'
export * from './FilterChips'
export * from './KpiCard'
export * from './Mono'
export * from './NumberBadge'
export * from './PageHeader'
export * from './PathBreadcrumb'
export * from './SearchField'
export * from './SectionCard'
export * from './SeverityBadge'
export * from './StatusBadge'
export * from './StatusDot'
export * from './Wizard'

// ── Layout primitives (MUI re-exports) ──────────────────────────────────
export { default as Box } from '@mui/material/Box'
export { default as Container } from '@mui/material/Container'
export { default as Grid } from '@mui/material/Grid'
export { default as Stack } from '@mui/material/Stack'
export { default as Divider } from '@mui/material/Divider'

// ── Surfaces ────────────────────────────────────────────────────────────
export { default as Paper } from '@mui/material/Paper'

// ── Typography primitives ───────────────────────────────────────────────
export { default as Typography } from '@mui/material/Typography'
export { default as Link } from '@mui/material/Link'

// ── Input primitives (building blocks not already covered by wrappers) ──
export { default as ButtonGroup } from '@mui/material/ButtonGroup'
export { default as IconButton } from '@mui/material/IconButton'
export { default as InputAdornment } from '@mui/material/InputAdornment'
export { default as InputLabel } from '@mui/material/InputLabel'
export { default as OutlinedInput } from '@mui/material/OutlinedInput'
export { default as FormControl } from '@mui/material/FormControl'
export { default as FormControlLabel } from '@mui/material/FormControlLabel'
export { default as FormHelperText } from '@mui/material/FormHelperText'
export { default as FormGroup } from '@mui/material/FormGroup'
export { default as MenuItem } from '@mui/material/MenuItem'
export { default as Slider } from '@mui/material/Slider'
export { default as Autocomplete } from '@mui/material/Autocomplete'
export { default as ToggleButton } from '@mui/material/ToggleButton'
export { default as ToggleButtonGroup } from '@mui/material/ToggleButtonGroup'

// ── Data display ────────────────────────────────────────────────────────
export { default as Chip } from '@mui/material/Chip'
export { default as AvatarGroup } from '@mui/material/AvatarGroup'
export { default as Tooltip } from '@mui/material/Tooltip'
export { default as List } from '@mui/material/List'
export { default as ListItem } from '@mui/material/ListItem'
export { default as ListItemButton } from '@mui/material/ListItemButton'
export { default as ListItemIcon } from '@mui/material/ListItemIcon'
export { default as ListItemText } from '@mui/material/ListItemText'
export { default as ListSubheader } from '@mui/material/ListSubheader'
export { default as Table } from '@mui/material/Table'
export { default as TableBody } from '@mui/material/TableBody'
export { default as TableCell } from '@mui/material/TableCell'
export { default as TableContainer } from '@mui/material/TableContainer'
export { default as TableFooter } from '@mui/material/TableFooter'
export { default as TableHead } from '@mui/material/TableHead'
export { default as TablePagination } from '@mui/material/TablePagination'
export { default as TableRow } from '@mui/material/TableRow'
export { default as TableSortLabel } from '@mui/material/TableSortLabel'

// ── Feedback ────────────────────────────────────────────────────────────
export { default as CircularProgress } from '@mui/material/CircularProgress'
export { default as LinearProgress } from '@mui/material/LinearProgress'
export { default as Skeleton } from '@mui/material/Skeleton'
export { default as Snackbar } from '@mui/material/Snackbar'

// ── Overlay / navigation ────────────────────────────────────────────────
export { default as Menu } from '@mui/material/Menu'
export { default as Popover } from '@mui/material/Popover'
export { default as Popper } from '@mui/material/Popper'
export { default as Toolbar } from '@mui/material/Toolbar'
export { default as Breadcrumbs } from '@mui/material/Breadcrumbs'
export { default as Pagination } from '@mui/material/Pagination'
export { default as Stepper } from '@mui/material/Stepper'
export { default as Step } from '@mui/material/Step'
export { default as StepLabel } from '@mui/material/StepLabel'
export { default as StepContent } from '@mui/material/StepContent'
export { default as Accordion } from '@mui/material/Accordion'
export { default as AccordionSummary } from '@mui/material/AccordionSummary'
export { default as AccordionDetails } from '@mui/material/AccordionDetails'
export { default as Collapse } from '@mui/material/Collapse'
export { default as Fade } from '@mui/material/Fade'

// ── Style utilities ─────────────────────────────────────────────────────
export { styled, useTheme as useMuiTheme, alpha } from '@mui/material/styles'
export type { Theme, SxProps } from '@mui/material/styles'
