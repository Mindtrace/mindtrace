# Public package boundaries

`@mindtrace/ui` is **public**. It is intended for eventual publication to
npm under a public scope. Everything here is visible to anyone who installs
the package or browses the source.

## What is allowed

- Generic operational-interface vocabulary: dashboards, forms, tables,
  workflows, status, layouts, feedback, navigation
- Design tokens (spacing, typography, semantic colors, radii)
- Thin wrappers around MUI primitives
- Generic patterns (PageHeader, FormSection, EmptyState, DataTable,
  KpiCard, SectionCard, FilterChips, SearchField, StatusBadge, etc.)
- Accessibility considerations
- React + MUI + emotion idioms

## What is forbidden

- Internal customer names
- Private product names
- Business-specific workflows (inspection runs, labelling pipelines,
  dataset/model/camera-specific behavior, datalake terminology, …)
- Private URLs (internal hosts, staging endpoints, customer portals)
- Real environment names
- Internal API routes
- Private architectural details from any specific Mindtrace product
- App-specific assumptions baked into component defaults

## Generalising internal concepts

When you have a component that looks generic but is named after an internal
concept, rename it on the way in:

- `DatasetSelector` → `ResourceSelector`
- `InspectionRunTable` → `DataTable`
- `ModelStatusBadge` → `StatusBadge`
- `CameraCard` → `ResourceCard`
- `LabellingWizard` → `Wizard`
- `DatalakeBrowser` → never expose this term publicly; rename or keep
  internal

## Rule of thumb

> The library contains **primitives and generic patterns only**. Domain
> workflows, private business logic, and product-specific composition stay
> in app code (or in a future private package).

If you find yourself reaching for a noun that names a Mindtrace business
concept, you are about to leak. Stop, generalise, and revisit. When in
doubt, keep it in the app.

## Pre-merge checklist

Before merging a PR that touches this package, grep the diff for known leaky
terms and confirm nothing slipped through:

```bash
grep -rin -E 'datalake|dataset|inspection|labelling|camera|recipe|defect|annotation' packages/ui/src packages/ui/docs
```

Result should be empty (or only obvious counter-examples like this very
checklist).
