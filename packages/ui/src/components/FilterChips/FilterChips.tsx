/**
 * FilterChips — a row of selectable chips, multi-select.
 *
 *   <FilterChips
 *     options={[{ id: 'pending', label: 'Pending' }, ...]}
 *     selected={['pending']}
 *     onChange={setSelected}
 *   />
 */

import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'

export type FilterOption<Id extends string = string> = {
  id: Id
  label: string
  count?: number
}

export type FilterChipsProps<Id extends string = string> = {
  options: FilterOption<Id>[]
  selected: Id[]
  onChange: (next: Id[]) => void
  /** When true, only one chip can be selected at a time. */
  exclusive?: boolean
  size?: 'small' | 'medium'
}

export function FilterChips<Id extends string = string>({
  options,
  selected,
  onChange,
  exclusive,
  size = 'small',
}: FilterChipsProps<Id>) {
  function toggle(id: Id) {
    if (exclusive) {
      onChange(selected.includes(id) ? [] : [id])
      return
    }
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])
  }
  return (
    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
      {options.map((opt) => {
        const active = selected.includes(opt.id)
        return (
          <Chip
            key={opt.id}
            size={size}
            label={opt.count != null ? `${opt.label} · ${opt.count}` : opt.label}
            clickable
            onClick={() => toggle(opt.id)}
            variant={active ? 'filled' : 'outlined'}
            color={active ? 'primary' : 'default'}
            sx={{ fontWeight: 500 }}
          />
        )
      })}
    </Stack>
  )
}
