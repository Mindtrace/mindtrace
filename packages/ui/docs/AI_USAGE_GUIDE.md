# AI usage guide

How AI coding tools (and humans pairing with them) should use `@mindtrace/ui`.

## Rules

1. **Always import UI from `@mindtrace/ui`.** Do not reach for raw MUI in app code
   when a wrapper exists. The wrappers exist so theme/behavior overrides stay
   centralized.

   ```tsx
   // ✅ Preferred
   import { Button, TextField, Card } from '@mindtrace/ui'

   // ❌ Avoid in app code
   import Button from '@mui/material/Button'
   ```

   Raw MUI imports are acceptable when there's no wrapper *and* the primitive
   isn't already re-exported from `@mindtrace/ui` (we re-export layout, list,
   navigation, and overlay primitives — check `src/components/index.ts`).

2. **Wrap the app root in `MindtraceProvider`.** Theme + `CssBaseline` resets
   come from the provider — no per-page wrappers, no manual `ThemeProvider`.

   ```tsx
   import { MindtraceProvider } from '@mindtrace/ui'

   export function App() {
     return (
       <MindtraceProvider mode="light">
         <Router />
       </MindtraceProvider>
     )
   }
   ```

3. **Reuse before creating.** If a component already exists in this package,
   use it. Do not author a local lookalike in an app.

4. **Promote, don't duplicate.** If a generic UI pattern appears in two or more
   apps, promote it into `@mindtrace/ui`. App-local duplicates drift quickly.

5. **Keep the public surface generic.** Never add business-specific
   terminology to component names, prop names, defaults, or stories. See
   `PUBLIC_PACKAGE_BOUNDARIES.md` for the boundary rules.

6. **Storybook is the catalogue.** Before designing new UI, browse Storybook
   to find an existing pattern. See `STORYBOOK_USAGE.md`.

7. **Use design tokens.** Do not hardcode colors, spacing units, or radii. See
   `DESIGN_TOKENS.md`.

## When you don't know which component to use

Check `COMPONENT_GUIDELINES.md` — it covers when to reach for each component
(e.g. `Modal` vs `Drawer`, `Badge` vs `Chip`).
