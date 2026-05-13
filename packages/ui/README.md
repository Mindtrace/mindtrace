# @mindtrace/ui

React components and theme primitives for calm, data-heavy operational
interfaces. Built on MUI, themed and pre-wrapped so the same components work
the same way across every surface that consumes it.

## Install

```bash
npm install @mindtrace/ui @mui/material @emotion/react @emotion/styled
```

`@mui/icons-material` is an optional peer — install it if you use any
icon-bearing primitive (KpiCard, SearchField, etc.) or want icons in your
own UI:

```bash
npm install @mui/icons-material
```

## Quick start

```tsx
import { MindtraceProvider, Button } from '@mindtrace/ui'

export function App() {
  return (
    <MindtraceProvider>
      <Button variant="contained">Save changes</Button>
    </MindtraceProvider>
  )
}
```

`MindtraceProvider` wraps your app with the MUI theme stack
(`StyledEngineProvider` → `ThemeProvider` → `CssBaseline`). It accepts:

- `mode` — `'light' | 'dark'` (default `'light'`)
- `theme` — caller-supplied MUI theme (skip if you want the built-in one)
- `disableCssBaseline` — opt out of `<CssBaseline>` if the host already
  resets styles

## What ships

- **Provider** — `MindtraceProvider`
- **Theme** — `lightTheme`, `darkTheme`, `getTheme(mode)`, palette,
  typography, design tokens. Available at the package root and at the
  `@mindtrace/ui/theme` and `@mindtrace/ui/tokens` subpaths for finer-grained
  imports.
- **Thin MUI wrappers** — `Button`, `TextField`, `Select`, `Card`, `Badge`,
  `Alert`, `Modal`, `Drawer`
- **Generic patterns** — `PageHeader`, `FormSection`, `EmptyState`,
  `DataTable`, `KpiCard`, `SectionCard`, `FilterChips`, `SearchField`,
  `StatusDot`, `StatusBadge`, `SeverityBadge`, `NumberBadge`, `Mono`
- **MUI primitive re-exports** — `Box`, `Stack`, `Grid`, `Container`,
  `Typography`, `Tooltip`, `Chip`, `Tabs`, `Menu`, `Table`, etc. Convenient
  so app code rarely has to reach for `@mui/material` directly.

## Storybook

Storybook is the canonical visual catalogue. Every component here ships with
at least one story.

```bash
npm run storybook         # dev server on :6006
npm run build:storybook   # static build → storybook-static/
```

See [`docs/STORYBOOK_USAGE.md`](./docs/STORYBOOK_USAGE.md) for conventions.

## Public package boundary

This package is intended for public publication. It contains **primitives and
generic patterns only** — no internal customer names, no private product
terminology, no business-specific workflows. See
[`docs/PUBLIC_PACKAGE_BOUNDARIES.md`](./docs/PUBLIC_PACKAGE_BOUNDARIES.md).

## Develop

```bash
npm install
npm run storybook         # dev server on :6006
npm run build:storybook   # static build → storybook-static/
npm run build             # tsup → dist/ (ESM + CJS + .d.ts)
npm run typecheck         # tsc --noEmit
```

## Testing

Tests run on **vitest** + **@testing-library/react** + **jsdom**. Every
component ships a smoke test, plus interaction tests on the behavioral
ones (forms, dialogs, navigation, toasts, etc.).

### Standard entry — `npm test`

From the package directory (or via any consumer's CI):

```bash
npm test                  # full suite, one shot
npm run test:watch        # watch mode
npm run test:coverage     # coverage report → coverage/
```

All three are thin wrappers around vitest; flags after the script name
pass through.

```bash
npm test -- src/components/Button   # specific path / glob
npm test -- --reporter=verbose      # any vitest flag
```

### Inside a vitest invocation

If you want full control, call vitest directly:

```bash
npx vitest run                      # one shot
npx vitest                          # watch mode
npx vitest run src/components/Button
```

### Optional: monorepo `ds` shortcut

When this package lives inside the Mindtrace monorepo, the repo's
`ds-run` workflow exposes a thin wrapper so the team has the same
`ds`-flavored UX as the Python suite:

```bash
ds test_ui                          # full suite — same as `npm test`
ds test_ui --watch
ds test_ui --coverage
ds test_ui: src/components/Button
```

Under the hood `ds test_ui` shells into
[`scripts/run-tests.sh`](./scripts/run-tests.sh) in this package, so
either entry point ends up at the same vitest run.

### Where tests live

Co-located with the code, ending in `.test.ts(x)`:

```
src/
├── components/
│   ├── Button/
│   │   ├── Button.tsx
│   │   ├── Button.test.tsx          ← smoke + interaction
│   │   └── Button.stories.tsx
│   └── …
├── hooks/
│   └── useCopyToClipboard.test.ts
├── providers/
│   └── MindtraceProvider.test.tsx
└── test-utils.tsx                   ← wraps render() in MindtraceProvider
```

Use `render` / `screen` / `userEvent` from `src/test-utils.tsx` — it
wraps every render in `MindtraceProvider` so theme tokens (`palette.surface.*`,
`palette.border.*`) resolve.

### Writing a new test

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen, userEvent } from '../../test-utils'
import { MyComponent } from './MyComponent'

describe('MyComponent', () => {
  it('does the thing', async () => {
    const onAction = vi.fn()
    const user = userEvent.setup()
    render(<MyComponent onAction={onAction} />)
    await user.click(screen.getByRole('button', { name: /do it/i }))
    expect(onAction).toHaveBeenCalledOnce()
  })
})
```

Two gotchas worth remembering:

- **Disabled MUI elements** have `pointer-events: none`. `userEvent.click`
  refuses to click them — assert `.toBeDisabled()` directly instead.
- **Clipboard tests** must stub `navigator` with `vi.stubGlobal('navigator',
  { clipboard: { writeText } })`, and the `CopyButton` interaction needs
  `fireEvent.click` (not `userEvent.click`) — see
  `src/components/CopyButton/CopyButton.test.tsx` for the pattern.

### Layout

```
packages/ui/
├── docs/                  ← AI / human guides (see below)
├── src/
│   ├── index.ts           ← top-level barrel
│   ├── providers/
│   │   └── MindtraceProvider.tsx
│   ├── theme/             ← palette, typography, tokens, etc.
│   ├── components/        ← wrappers + bespoke + MUI re-exports
│   │   ├── Button/
│   │   │   ├── Button.tsx
│   │   │   ├── Button.stories.tsx
│   │   │   └── index.ts
│   │   └── …
│   └── stories/           ← foundation stories (palette, type, shape, …)
├── .storybook/
└── package.json
```

### Docs

The [`docs/`](./docs) folder is designed for both humans and AI tools:

- [`AI_USAGE_GUIDE.md`](./docs/AI_USAGE_GUIDE.md) — rules for AI coding tools
- [`UI_PHILOSOPHY.md`](./docs/UI_PHILOSOPHY.md) — what this UI is for
- [`COMPONENT_GUIDELINES.md`](./docs/COMPONENT_GUIDELINES.md) — when to use each component
- [`STORYBOOK_USAGE.md`](./docs/STORYBOOK_USAGE.md) — Storybook as source of truth
- [`DESIGN_TOKENS.md`](./docs/DESIGN_TOKENS.md) — tokens and how to use them
- [`PUBLIC_PACKAGE_BOUNDARIES.md`](./docs/PUBLIC_PACKAGE_BOUNDARIES.md) — what's allowed / forbidden in this package

## Publishing

Because this is a scoped package, **public publishing requires
`--access public` on first publish**:

```bash
npm run build             # build artefacts into dist/
npm pack --dry-run        # inspect what would ship
npm publish --access public
```

## License

Apache-2.0.
