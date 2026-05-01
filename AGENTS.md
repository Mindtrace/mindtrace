# AGENTS.md — Guidance for AI Agents Working in This Repository

This document is a practical operating contract for autonomous or
semi-autonomous coding agents making changes in the `mindtrace`
repository.

It complements:

- `README.md` — project overview, modules, layered architecture
- `CONTRIBUTING.md` — workflow and code quality expectations
- `TESTING.md` — how to run tests using `ds`

---

## Goals for Agent Contributions

Agents should optimize for:

1. Small, reviewable diffs
2. Respecting the modular / layered architecture
3. Passing unit tests and lint checks
4. Keeping public APIs stable unless explicitly requested
5. Updating docs or samples when behavior changes

---

## Repository Mental Model (High Level)

Mindtrace is a modular Python framework with many submodules
(e.g., `core`, `services`, `registry`, `jobs`, etc.) and a layered
architecture where dependency direction matters.

### Modules (non-exhaustive)

`apps`, `agents`, `automation`, `cluster`, `core`, `database`, `datalake`,
`hardware`, `jobs`, `models`, `registry`, `services`, `storage`, `ui`

### Dependency Boundaries (Critical)

Changes must respect the layered architecture described in `README.md`.

Higher layers must not introduce dependency edges that violate intended
direction.

If a change requires a new dependency edge, prefer:

- Moving shared abstractions “down” into a lower layer (often `core`)
- Using interfaces / protocols with dependency injection
- Adding integration hooks instead of direct imports

---

## Setup & Tooling Expectations

Agents should assume local development uses:

- Python 3.12+
- `uv` for dependency syncing
- `ruff` for linting and formatting
- `ds` commands for testing

### Canonical Setup

```bash
uv sync --dev
uv tool install ds-run
uv tool install ruff
```

---

## Change Protocol (Safe Development Rules)

### 1) Keep Changes Atomic

Prefer one intent per PR:

- One bug fix
- One feature slice
- One refactor without behavior change

Avoid unrelated refactors unless explicitly requested.

### 2) Prefer Local, Minimal Edits

- Do not reformat unrelated files
- Do not rename broad symbols unless required
- Avoid mass import sorting changes unless explicitly part of the task

### 3) Add Tests With Your Change

Tests should live in:

- `tests/unit/mindtrace/<module>/...`
- `tests/integration/mindtrace/<module>/...`

If fixing a bug, add a regression test that fails without the fix.

### 4) Update Docs or Samples When Behavior Changes

If user-facing behavior changes:

- Update module READMEs or top-level docs
- Update or add samples under `samples/<module>/`

---

## Testing Contract

### During Development

Agents should run focused unit tests relevant to their changes:

```bash
ds test --unit
ds test: <module>
ds test: tests/unit/mindtrace/<module>/
ds test: tests/unit/mindtrace/<module>/file.py::TestName
```

Avoid running the full integration test suite during normal development,
as integration tests are long-running and CI-managed.

### Before Pushing Changes

Agents must ensure:

```bash
ds test --unit
```

passes cleanly.

### Integration Tests

Integration tests are executed in CI and are not required locally unless
explicitly requested.

---

## Code Quality Contract

### Style

- Use type hints
- Use clear, descriptive naming
- Add Google-style docstrings for new functions/classes

### Lint & Format

Ensure the following pass before proposing changes:

```bash
ruff check
ruff format --check
```

Auto-fix only when necessary:

```bash
ruff check --fix
ruff format
```

---

## Branching Rules

- Never push directly to `dev` or `main`.
- Always create a feature branch named:
  `openclaw/<timestamp>-<short-summary>`
- Always open a PR targeting `dev`.
- Never merge PRs.
- Never approve PRs.

---

## PR Expectations

When opening or updating a PR, include:

- What changed (high-level summary)
- Why it changed
- How to test (exact commands)
- Any breaking changes or migration notes

---

## Quick Agent Checklist

Before finalizing work:

- [ ] Change is scoped and minimal
- [ ] Architecture boundaries respected
- [ ] Tests added/updated appropriately
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `ds test --unit` passes
- [ ] Docs/samples updated if behavior changed

---

## Where to Look First

- Architecture overview: `README.md`
- Contribution workflow: `CONTRIBUTING.md`
- Testing patterns: `TESTING.md`
