/**
 * PrimaryRail — collapsible left navigation rail.
 *
 * Structure:
 *   - `brand` slot at top
 *   - Collapse toggle hanging off the right edge
 *   - Scrollable list of sections
 *
 * Each section has an optional label (uppercase tiny label when expanded,
 * a thin divider when collapsed) and a list of items: icon + label
 * + optional badge.
 *
 * Active state is driven by `activeHref` (string match) or a custom
 * `isItemActive` function. Use `renderLink` to integrate with a router
 * (e.g. React Router's `<Link>`); by default items render as plain `<a>`.
 *
 * Collapse can be controlled (`collapsed` + `onCollapsedChange`) or
 * uncontrolled with optional `persistKey` for `localStorage` persistence.
 */

import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import Box from '@mui/material/Box'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useState, type ReactNode } from 'react'

export type PrimaryRailItem = {
  /** Stable identifier used for the active comparison + key. */
  href: string
  label: string
  icon?: ReactNode
  /** Optional badge rendered to the right when expanded. */
  badge?: ReactNode
}

export type PrimaryRailSection = {
  /** Section heading (shown only when expanded). */
  label?: string
  items: PrimaryRailItem[]
}

export type PrimaryRailProps = {
  /** Top-of-rail brand slot. */
  brand?: ReactNode
  /** Sections of nav items, rendered in order. */
  sections: PrimaryRailSection[]
  /** Currently-active route. Compared with each item's `href`. */
  activeHref?: string
  /** Override active-match logic if your routing pattern needs it. */
  isItemActive?: (item: PrimaryRailItem) => boolean
  /** Render an item's link — override to integrate with a router. */
  renderLink?: (item: PrimaryRailItem, content: ReactNode) => ReactNode
  /** Controlled collapsed state. */
  collapsed?: boolean
  /** Uncontrolled starting state. */
  defaultCollapsed?: boolean
  /** Called whenever the collapsed state changes. */
  onCollapsedChange?: (collapsed: boolean) => void
  /** Persist collapsed state in `localStorage` under this key. */
  persistKey?: string
  /** Collapsed rail width. Default `64`. */
  collapsedWidth?: number
  /** Expanded rail width. Default `220`. */
  expandedWidth?: number
  /** Show the collapse toggle button. Default `true`. */
  showCollapseToggle?: boolean
}

function defaultIsActive(activeHref: string | undefined, item: PrimaryRailItem): boolean {
  if (!activeHref) return false
  if (item.href === '/') return activeHref === '/'
  return activeHref === item.href || activeHref.startsWith(`${item.href}/`)
}

export function PrimaryRail({
  brand,
  sections,
  activeHref,
  isItemActive,
  renderLink,
  collapsed,
  defaultCollapsed = false,
  onCollapsedChange,
  persistKey,
  collapsedWidth = 64,
  expandedWidth = 220,
  showCollapseToggle = true,
}: PrimaryRailProps) {
  const isControlled = collapsed !== undefined
  const [uncontrolled, setUncontrolled] = useState<boolean>(() => {
    if (persistKey) {
      try {
        const stored = window.localStorage.getItem(persistKey)
        if (stored !== null) return stored === 'true'
      } catch {
        /* ignore */
      }
    }
    return defaultCollapsed
  })
  const isCollapsed = isControlled ? collapsed : uncontrolled

  useEffect(() => {
    if (!isControlled && persistKey) {
      try {
        window.localStorage.setItem(persistKey, String(uncontrolled))
      } catch {
        /* ignore */
      }
    }
  }, [isControlled, persistKey, uncontrolled])

  function toggle() {
    const next = !isCollapsed
    if (!isControlled) setUncontrolled(next)
    onCollapsedChange?.(next)
  }

  const width = isCollapsed ? collapsedWidth : expandedWidth
  const expanded = !isCollapsed

  return (
    <Box
      component="nav"
      aria-label="Primary navigation"
      sx={(theme) => ({
        flex: `0 0 ${width}px`,
        width,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        pt: 2,
        pb: 1,
        bgcolor: theme.palette.mode === 'dark' ? theme.palette.surface.subtle : theme.palette.background.paper,
        borderRight: 1,
        borderColor: 'divider',
        transition: 'width 160ms ease, flex-basis 160ms ease, padding 160ms ease',
        overflow: 'visible',
        position: 'relative',
      })}
    >
      {brand && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: expanded ? 'flex-start' : 'center',
            mb: 1.5,
            mx: expanded ? 1.5 : 0,
            minHeight: 36,
          }}
        >
          {brand}
        </Box>
      )}

      {showCollapseToggle && (
        <Tooltip title={expanded ? 'Collapse navigation' : 'Expand navigation'} placement="right" arrow>
          <IconButton
            onClick={toggle}
            aria-label={expanded ? 'Collapse navigation' : 'Expand navigation'}
            size="small"
            sx={(theme) => ({
              position: 'absolute',
              top: 28,
              right: -12,
              zIndex: theme.zIndex.appBar + 1,
              width: 24,
              height: 24,
              borderRadius: '50%',
              bgcolor: theme.palette.background.paper,
              border: 1,
              borderColor: 'divider',
              color: 'text.secondary',
              boxShadow: 1,
              '&:hover': {
                bgcolor: theme.palette.background.paper,
                color: 'primary.main',
                borderColor: 'primary.main',
              },
            })}
          >
            {expanded ? <ChevronLeftIcon sx={{ fontSize: 16 }} /> : <ChevronRightIcon sx={{ fontSize: 16 }} />}
          </IconButton>
        </Tooltip>
      )}

      <Box sx={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', minHeight: 0, pt: 0.5 }}>
        {sections.map((section, idx) => (
          <NavSection
            key={section.label ?? idx}
            section={section}
            expanded={expanded}
            showSeparator={idx > 0}
            isActive={(item) => isItemActive?.(item) ?? defaultIsActive(activeHref, item)}
            renderLink={renderLink}
          />
        ))}
      </Box>
    </Box>
  )
}

function NavSection({
  section,
  expanded,
  showSeparator,
  isActive,
  renderLink,
}: {
  section: PrimaryRailSection
  expanded: boolean
  showSeparator: boolean
  isActive: (item: PrimaryRailItem) => boolean
  renderLink?: PrimaryRailProps['renderLink']
}) {
  return (
    <Box sx={{ pb: 0.5 }}>
      {showSeparator && !expanded && (
        <Box sx={{ px: 1.25, py: 0.5 }}>
          <Divider sx={{ my: 0.25 }} />
        </Box>
      )}
      {expanded && section.label && (
        <Typography
          variant="tinyLabel"
          sx={{
            color: 'text.secondary',
            display: 'block',
            px: 1.5,
            pt: showSeparator ? 1.25 : 0.5,
            pb: 0.5,
          }}
        >
          {section.label}
        </Typography>
      )}
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: 0.25,
          px: expanded ? 1 : 0,
          alignItems: expanded ? 'stretch' : 'center',
        }}
      >
        {section.items.map((item) => (
          <NavRow key={item.href} item={item} expanded={expanded} active={isActive(item)} renderLink={renderLink} />
        ))}
      </Box>
    </Box>
  )
}

function NavRow({
  item,
  expanded,
  active,
  renderLink,
}: {
  item: PrimaryRailItem
  expanded: boolean
  active: boolean
  renderLink?: PrimaryRailProps['renderLink']
}) {
  const content = (
    <>
      <Box sx={{ display: 'inline-flex', '& .MuiSvgIcon-root': { fontSize: 20 } }}>{item.icon}</Box>
      {expanded && (
        <Typography
          sx={{
            fontSize: '0.83rem',
            fontWeight: active ? 600 : 500,
            color: 'inherit',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            flex: 1,
          }}
        >
          {item.label}
        </Typography>
      )}
      {expanded && item.badge != null && <Box sx={{ display: 'inline-flex' }}>{item.badge}</Box>}
    </>
  )

  const innerSx = {
    width: expanded ? '100%' : 40,
    height: 36,
    borderRadius: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: expanded ? 'flex-start' : 'center',
    gap: expanded ? 1.5 : 0,
    px: expanded ? 1.25 : 0,
    cursor: 'pointer',
    textDecoration: 'none',
    color: active ? 'primary.main' : 'text.secondary',
    bgcolor: active ? 'action.selected' : 'transparent',
    transition: 'background-color 120ms, color 120ms',
    '&:hover': {
      bgcolor: active ? 'action.selected' : 'action.hover',
      color: active ? 'primary.main' : 'text.primary',
    },
    flexShrink: 0,
  } as const

  const inner = renderLink ? (
    renderLink(item, <Box sx={innerSx}>{content}</Box>)
  ) : (
    <Box component="a" href={item.href} sx={innerSx}>
      {content}
    </Box>
  )

  if (expanded) return inner
  return (
    <Tooltip title={item.label} placement="right" arrow>
      <Box sx={{ display: 'inline-flex' }}>{inner}</Box>
    </Tooltip>
  )
}
