# UI philosophy

`@mindtrace/ui` is built for **calm, data-heavy operational interfaces** —
admin tools, dashboards, internal back-offices, control panels — used daily by
expert users who care about throughput and predictability.

## Principles

- **Clarity over decoration.** Information density wins over visual flair.
  Operators should be able to scan a screen, find what they need, and act.
- **Predictable layouts.** Every page assembles from the same primitives
  (`PageHeader`, `SectionCard`, `FormSection`, `DataTable`). Users should
  never have to relearn navigation between screens.
- **Strong hierarchy.** Use type scale, weight, and spacing — not color or
  decoration — to communicate importance.
- **Accessible by default.** Components inherit MUI's accessibility work;
  stories ship with the a11y addon enabled.
- **Boring, reliable patterns.** Prefer the obvious solution. Operators
  remember interfaces by their consistency, not their cleverness.
- **Explicit status and feedback.** Use `StatusBadge`, `Alert`, `StatusDot` to
  surface state — never rely on color alone, never let users guess what's
  happening.
- **Avoid visual noise.** No decorative gradients, no flashy animations, no
  marketing-style hero blocks. The visual budget is small; spend it on data.

## What this is not

It is not a marketing site kit. It is not a flashy AI-product showcase. It is
not a place to experiment with novel interactions.

If a screen needs to feel exciting, it probably shouldn't be built from these
primitives — write something bespoke in the app and keep this library calm.
