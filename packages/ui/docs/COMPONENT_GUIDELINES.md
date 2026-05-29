# Component guidelines

When to reach for which component.

## Inputs

### `Button`

Standard action button. Use `variant="contained"` for the primary action on a
page or in a form; `variant="outlined"` for secondary; `variant="text"` for
tertiary (e.g. "Cancel", "Dismiss"). Don't put more than one `contained`
button in the same action group.

### `TextField`

Single- or multi-line text input. Always provide a `label`. Use `helperText`
for guidance and `error` + `helperText` together for validation messages.

### `Select`

Single-value picker with a labelled dropdown. Use the `options` shortcut for a
flat list; pass children for grouped or custom-rendered items. For free-typed
or async-loaded values reach for MUI `Autocomplete` instead.

## Surfaces

### `Card`

A neutral surface. Use `CardHeader`, `CardContent`, `CardActions` for
structured layouts. For the common "panel under a heading" pattern use
`SectionCard` (less verbose).

### `SectionCard`

Card + title/subtitle/actions header in one element. Use this everywhere
inside a page body — it's the standard panel pattern.

## Feedback

### `Alert`

Inline feedback message — connection errors, validation summaries, deprecation
notices. Use a severity (`info`, `success`, `warning`, `error`). For
transient notifications, prefer `Snackbar`.

### `Badge`

Small labelled token. Wraps MUI Chip rather than MUI Badge. Use for tags,
inline labels, "active" markers. For severity ladders use `SeverityBadge`;
for status with a dot indicator use `StatusBadge`; for counters use
`NumberBadge`.

### `StatusBadge`

A chip with a colored dot indicator. Use for run state, alert state, job
status — anywhere you want to convey both a label and a tone at a glance.

### `SeverityBadge`

Severity ladder (`critical > major > minor > info`) styled with palette tones.
Use only for severity contexts — events, alerts, incidents — not generic
status.

### `StatusDot`

Just the dot. Use inline with a label when a full `StatusBadge` is too heavy.

### `NumberBadge`

Tiny pill for counts (e.g. "3 next to a sidebar item"). Distinct from MUI's
overlay Badge.

## Overlays

### `Modal` vs `Drawer`

- **`Modal`** for focused, blocking decisions: confirms, destructive actions,
  short forms the user must finish before continuing.
- **`Drawer`** for secondary context that needs to stay scoped to the current
  page but doesn't fully block the underlying surface: detail views, filters,
  side-panel editors.

Rule of thumb: if dismissing the overlay should leave the user exactly where
they were, `Drawer`. If they're committing or cancelling something, `Modal`.

## Patterns

### `PageHeader`

Standard top-of-page block. Every full page mounts one. Never style page
titles ad-hoc.

### `FormSection`

Grouped section of form fields with a heading, optional description, and
optional action slot (e.g. "Add row"). Stack multiple `FormSection`s for long
settings pages.

### `EmptyState`

Use for empty lists, "nothing here yet", and recoverable error views. Always
include a `title`; usually include a `description`; include an `action` only
if there's a meaningful next step.

### `DataTable`

Thin, typed wrapper around MUI Table for the common "list of objects with
named columns" case. For sorting, filtering, virtualization, or server-side
paging, reach for `@mui/x-data-grid` directly.

### `KpiCard`

Single metric tile for dashboards. Pair with `delta` for trend, `icon` for
visual anchor, `hint` for context.

### `FilterChips`

Row of selectable filter chips, multi-select or exclusive. Use above a list
or table for quick faceted filtering.

### `SearchField`

`TextField` preconfigured for search use, with a leading icon and clear
button. Use for any list/table filter input.

### `Mono`

Monospaced inline text for IDs, hashes, file paths, codes. Use this instead
of raw `<code>` so columns of IDs line up (tabular figures).
