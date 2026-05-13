# Storybook usage

Storybook is the canonical visual catalogue for `@mindtrace/ui`. It is the
source of truth for what each component looks like, what props it accepts,
and how to compose it.

## Workflow

1. **Before designing or building UI**, browse Storybook to find an existing
   component or pattern. Many things you might want to build already exist.
2. **When you change a component**, add or update its story. A change without
   a corresponding story update is a missed opportunity to verify the result.
3. **When you build a new component**, ship a story alongside it. Stories
   live next to the component file:
   `src/components/<Name>/<Name>.stories.tsx`.
4. **Use Storybook to compare app UI against the shared library.** If you
   find yourself rebuilding something that exists, switch to the shared
   version. If you find yourself extending a pattern in two apps, promote it
   here.

## Running Storybook

```bash
npm run storybook         # dev server on :6006
npm run build:storybook   # static build into storybook-static/
```

## Story conventions

- **Titles** use one of three top-level prefixes: `Foundations/…`,
  `Components/…`, `Patterns/…`.
- **Tags** include `'autodocs'` so Storybook generates a prop table.
- **Examples are generic.** No private data, no internal customer names, no
  business-specific workflows.
- **Show common variants.** Default, disabled, loading, error — wherever
  relevant. Stories are documentation; one happy-path story is rarely enough.

## What stories shouldn't include

- Screenshots of internal apps
- Real customer or environment names
- Internal URLs, API routes, or service hostnames
- Domain-specific data (datasets, models, cameras, inspection workflows,
  labelling pipelines, etc.) — substitute generic placeholders
