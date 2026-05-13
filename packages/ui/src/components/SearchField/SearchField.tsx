/**
 * SearchField — a `TextField` preconfigured for search use.
 *
 *   <SearchField value={q} onChange={setQ} placeholder="Search runs…" />
 *
 * Includes a leading search icon and a clear-button when value is set.
 * Use for any list/table filter input; consistent affordance across the
 * app means users never have to learn it twice.
 */

import ClearIcon from '@mui/icons-material/Close'
import SearchIcon from '@mui/icons-material/Search'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import TextField from '@mui/material/TextField'
import type { ChangeEvent } from 'react'

export type SearchFieldProps = {
  value: string
  onChange: (next: string) => void
  placeholder?: string
  autoFocus?: boolean
  fullWidth?: boolean
  /** Visual width override; default is `fullWidth`. */
  maxWidth?: number | string
  /** Disable the clear button. */
  disableClear?: boolean
}

export function SearchField({
  value,
  onChange,
  placeholder = 'Search…',
  autoFocus,
  fullWidth = true,
  maxWidth,
  disableClear,
}: SearchFieldProps) {
  return (
    <TextField
      placeholder={placeholder}
      value={value}
      autoFocus={autoFocus}
      fullWidth={fullWidth}
      onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
      sx={{ maxWidth }}
      slotProps={{
        input: {
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" sx={{ color: 'text.secondary' }} />
            </InputAdornment>
          ),
          endAdornment:
            value && !disableClear ? (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => onChange('')} aria-label="Clear search">
                  <ClearIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ) : undefined,
        },
      }}
    />
  )
}
