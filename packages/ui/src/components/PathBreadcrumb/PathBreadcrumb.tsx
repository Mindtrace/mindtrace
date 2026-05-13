/**
 * PathBreadcrumb — segmented path display.
 *
 * Each segment renders as `[icon] label` and is separated by a `/`.
 * If a segment has an `items` array it becomes a popover-trigger that
 * shows a searchable list of siblings; otherwise it is read-only.
 * A `trailing` slot to the right of the path is useful for a role/scope
 * badge.
 *
 *   <PathBreadcrumb
 *     segments={[
 *       { id: 'org', label: 'Acme', icon: <Business />, items: orgs, currentId: org.id, onSelect: pickOrg },
 *       { id: 'team', label: 'Engineering', icon: <Group />, items: teams, currentId: team.id, onSelect: pickTeam },
 *     ]}
 *     trailing={<Badge label="admin" color="primary" />}
 *   />
 */

import CheckIcon from '@mui/icons-material/Check'
import ChevronDownIcon from '@mui/icons-material/KeyboardArrowDown'
import SearchIcon from '@mui/icons-material/Search'
import Box from '@mui/material/Box'
import Divider from '@mui/material/Divider'
import InputAdornment from '@mui/material/InputAdornment'
import Popover from '@mui/material/Popover'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { alpha, useTheme } from '@mui/material/styles'
import { useMemo, useState, type ReactNode } from 'react'

import { Button } from '../Button'

export type PathSegmentItem = {
  /** Stable identifier — compared to `currentId` for active styling. */
  id: string
  /** Display label. */
  label: string
  /** Secondary value shown right-aligned (e.g. role tag, kind). */
  secondary?: ReactNode
  /** Leading marker (e.g. a `<StatusDot>`). */
  leading?: ReactNode
}

export type PathSegment = {
  /** Stable identifier for React key + active comparison. */
  id: string
  /** Display label. `null` renders the `placeholder`. */
  label: string | null
  /** Leading icon. */
  icon?: ReactNode
  /** Items to show in the popover. Omit for read-only segments. */
  items?: PathSegmentItem[]
  /** Id of the currently-selected item; used for active styling. */
  currentId?: string | null
  /** Called when the user picks a popover item. */
  onSelect?: (id: string) => void
  /** Shown in the segment trigger when `label` is null. */
  placeholder?: string
  /** Override the popover search-field placeholder. */
  searchPlaceholder?: string
  /** Hidden when the segment has no items. Default `false`. */
  hideWhenEmpty?: boolean
}

export type PathBreadcrumbProps = {
  segments: PathSegment[]
  /** Separator rendered between segments. Default `/`. */
  separator?: ReactNode
  /** Trailing slot to the right of the path. */
  trailing?: ReactNode
}

const DEFAULT_SEPARATOR = (
  <Typography component="span" sx={{ px: 0.5, color: 'text.disabled', userSelect: 'none' }} variant="body2">
    /
  </Typography>
)

export function PathBreadcrumb({
  segments,
  separator = DEFAULT_SEPARATOR,
  trailing,
}: PathBreadcrumbProps) {
  const visible = segments.filter((s) => !(s.hideWhenEmpty && (!s.items || s.items.length === 0)))
  return (
    <Stack direction="row" spacing={0} sx={{ alignItems: 'center', minWidth: 0 }}>
      {visible.map((segment, idx) => (
        <Stack key={segment.id} direction="row" sx={{ alignItems: 'center', minWidth: 0 }}>
          {idx > 0 && separator}
          {segment.items && segment.items.length > 0 && segment.onSelect ? (
            <InteractiveSegment segment={segment} />
          ) : (
            <ReadOnlySegment segment={segment} />
          )}
        </Stack>
      ))}
      {trailing && <Box sx={{ ml: 1 }}>{trailing}</Box>}
    </Stack>
  )
}

function ReadOnlySegment({ segment }: { segment: PathSegment }) {
  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', minWidth: 0, px: 1 }}>
      {segment.icon && (
        <Box sx={{ display: 'inline-flex', color: 'text.secondary', '& .MuiSvgIcon-root': { fontSize: 14 } }}>
          {segment.icon}
        </Box>
      )}
      <Typography
        variant="body2"
        sx={{
          fontWeight: 500,
          color: segment.label ? 'text.primary' : 'text.secondary',
          maxWidth: '14rem',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {segment.label ?? segment.placeholder ?? '—'}
      </Typography>
    </Stack>
  )
}

function InteractiveSegment({ segment }: { segment: PathSegment }) {
  const theme = useTheme()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const [query, setQuery] = useState('')
  const open = Boolean(anchorEl)

  const filtered = useMemo(() => {
    if (!segment.items) return []
    const q = query.trim().toLowerCase()
    if (!q) return segment.items
    return segment.items.filter((it) => it.label.toLowerCase().includes(q) || it.id.toLowerCase().includes(q))
  }, [segment.items, query])

  function close() {
    setAnchorEl(null)
    setQuery('')
  }

  return (
    <>
      <Button
        size="small"
        variant="text"
        onClick={(e) => setAnchorEl(e.currentTarget)}
        startIcon={segment.icon ? <Box sx={{ display: 'inline-flex', opacity: 0.7 }}>{segment.icon}</Box> : undefined}
        endIcon={
          <ChevronDownIcon
            sx={{
              fontSize: 14,
              opacity: 0.5,
              transition: 'transform 120ms',
              transform: open ? 'rotate(180deg)' : 'none',
            }}
          />
        }
        sx={{
          textTransform: 'none',
          fontWeight: 500,
          color: segment.label ? 'text.primary' : 'text.secondary',
          minWidth: 0,
          maxWidth: '14rem',
          '& .MuiButton-startIcon': { mr: 0.75 },
          '& .MuiButton-endIcon': { ml: 0.25 },
        }}
      >
        <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {segment.label ?? segment.placeholder ?? '—'}
        </Box>
      </Button>
      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={close}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        transformOrigin={{ vertical: 'top', horizontal: 'left' }}
        slotProps={{ paper: { sx: { width: 288, mt: 0.5 } } }}
      >
        <Box sx={{ p: 1 }}>
          <TextField
            autoFocus
            size="small"
            fullWidth
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={segment.searchPlaceholder ?? 'Search…'}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                  </InputAdornment>
                ),
              },
            }}
          />
        </Box>
        <Divider />
        <Box sx={{ maxHeight: 288, overflowY: 'auto', p: 0.5 }}>
          {filtered.length === 0 ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: 'block', textAlign: 'center', py: 3 }}
            >
              {segment.items && segment.items.length === 0 ? 'Nothing here.' : 'No matches.'}
            </Typography>
          ) : (
            filtered.map((it) => {
              const active = it.id === segment.currentId
              return (
                <Box
                  key={it.id}
                  component="button"
                  type="button"
                  onClick={() => {
                    segment.onSelect?.(it.id)
                    close()
                  }}
                  sx={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    py: 0.75,
                    px: 1,
                    border: 0,
                    borderRadius: 1,
                    bgcolor: active ? alpha(theme.palette.primary.main, 0.1) : 'transparent',
                    color: 'text.primary',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontFamily: theme.typography.fontFamily,
                    fontSize: '0.875rem',
                    fontWeight: active ? 600 : 400,
                    '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.06) },
                  }}
                >
                  {it.leading}
                  <Box
                    component="span"
                    sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  >
                    {it.label}
                  </Box>
                  {it.secondary && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}
                    >
                      {it.secondary}
                    </Typography>
                  )}
                  {active && <CheckIcon sx={{ fontSize: 16, color: 'primary.main' }} />}
                </Box>
              )
            })
          )}
        </Box>
      </Popover>
    </>
  )
}
