# Design tokens

Tokens are the source of truth for color, spacing, type, radius, and z-index.
Components read from tokens via the MUI theme; app code should do the same.

Tokens live in `src/theme/tokens.ts` and the theme assembly in
`src/theme/index.ts`. Both are re-exported from `@mindtrace/ui/theme` and
`@mindtrace/ui/tokens`.

## Categories

### Spacing

Base unit is `8px`. Use MUI's `sx` spacing shorthand — `sx={{ p: 2 }}` ==
`padding: 16px`. Never inline raw pixel values.

### Typography

Standard MUI variants (`h1`–`h6`, `body1`, `body2`, `caption`, …) plus custom
variants for dense operational surfaces:

- `subheading` — h3-equivalent inline heading
- `sectionLabel` — small uppercase section label
- `metricLabel` — KPI tile label
- `tinyLabel` — micro uppercase label
- `microCaption` — smaller caption
- `mono` — IDs, hashes, code

The full scale lives in `src/theme/typography.ts`.

### Semantic colors

Use the palette tones (`primary`, `secondary`, `success`, `warning`, `error`,
`info`) for anything where meaning matters. Do not pick raw color values for
"a green button" — use `color="success"`.

### Status tones

`StatusBadge`, `StatusDot`, `NumberBadge`, and `KpiCard.delta` accept a
`tone` of `neutral | success | warning | error | info`. The mapping to actual
colors is centralized in tokens so dark mode and theme overrides stay in
sync.

### Surfaces and borders

`palette.surface.{subtle,muted,strong}` and `palette.border.{subtle,default,
strong}` give you neutral panel backgrounds and outlines that adapt to
light/dark mode. Prefer these over picking grey ramp values directly.

### Radii

`radii.{xs,sm,md,lg,xl,pill}`. `borderRadius` on `Card`, `Button`, etc. is
set by the theme — you should rarely need to override.

### Z-index

`zIndex.{content,rail,topBar,drawer,modal,snackbar,tooltip}`. Use these
instead of inventing magic numbers when stacking overlays.

## Rules

- **No raw hex in app code.** If you need a color, find a token. If no token
  fits, propose adding one — don't reach for `#7c3aed` in JSX.
- **No magic pixel values for spacing.** Use the spacing scale.
- **Use semantic names.** `palette.success.main`, not `'#16A34A'`.
- **Adapt to theme mode.** Use palette values (which switch with the theme)
  rather than mode-specific overrides where possible.
