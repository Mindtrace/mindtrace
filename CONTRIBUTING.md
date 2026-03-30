# Contributing to Mindtrace

Thanks for your interest in contributing to Mindtrace.

Mindtrace is a modular project, so contributions should respect module boundaries and dependency direction. The main modules include:

`apps`, `automation`, `cluster`, `core`, `database`, `datalake`, `hardware`, `jobs`, `models`, `registry`, `services`, `storage`, and `ui`.

## Before You Start

You will need:

- Python 3.12+
- Git
- [uv](https://docs.astral.sh/uv/)
- Docker (recommended for integration tests and backend services)

## Setup

### 1. Fork and clone

Fork the repository, then clone your fork locally:

```bash
git clone https://github.com/YOUR_USERNAME/mindtrace.git && cd mindtrace
```

### 2. Install dependencies

```bash
uv sync --dev --all-extras
uv tool install ds-run
uv tool install ruff
```

### 3. Verify your environment

```bash
ds test --unit
```

## Development Workflow

### 1. Create a branch from `dev`

```bash
git checkout dev
git pull origin dev
git checkout -b feature/short-description
```

Use a descriptive branch name, for example:

- `feature/add-service-endpoint`
- `fix/redis-timeout-handling`
- `docs/update-registry-readme`

### 2. Make focused changes

Prefer small, atomic pull requests.

As you work:

- keep changes scoped to a clear purpose
- use clear names and type hints
- follow [Google's Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- add docstrings for new public functions and classes using Google-style Python docstrings
- update relevant tests
- update relevant README files when behavior or public interfaces change
- add or update samples in `samples/[module]/` when new functionality needs example usage

For documentation work specifically:

- keep top-level READMEs as practical guides, not full API references
- use module READMEs for deeper walkthroughs
- prefer human-readable example links over raw file paths when possible
- keep examples and prose aligned with [Google's Python Style Guide](https://google.github.io/styleguide/pyguide.html) where applicable

## Code Quality

Run linting and formatting before you commit:

```bash
ruff check
ruff format --check
```

To auto-fix where possible:

```bash
ruff check --fix
ruff format
```

## Testing

Run the test suite relevant to your change.

### Fast local loop

```bash
ds test --unit
```

### Full local test run

```bash
ds test
```

### Module-specific test runs

Examples:

```bash
ds test: services
ds test: --unit services

ds test: registry
ds test: --unit registry
```

For more detail, see [TESTING.md](./TESTING.md).

## Commits

Use small, focused commits with clear messages.

Examples:

```bash
git commit -m "feat: add Redis queue priority support"
git commit -m "fix: handle missing registry metadata"
git commit -m "docs: rewrite services README"
```

## Pull Requests

Open pull requests against the `dev` branch.

Your PR should include:

- a clear title
- a short explanation of the problem or goal
- a summary of what changed
- testing notes explaining how you verified the change
- links to any relevant issues, PRs, or discussions

### PR checklist

Before opening a PR, make sure:

- [ ] the PR targets `dev`
- [ ] tests pass locally for the affected scope
- [ ] `ruff check` passes
- [ ] formatting is clean
- [ ] documentation is updated where needed
- [ ] samples are updated where needed
- [ ] commit messages are clear and useful

## Review Process

Typical review flow:

1. automated checks run
2. maintainers review the change
3. follow-up fixes or clarifications are requested if needed
4. once approved, the PR is merged into `dev`

## Contribution Tips

A few things that help a lot:

- prefer clear examples over clever abstractions
- keep public APIs typed and documented
- when changing a module README, make sure the examples match the actual current code
- if there are real sample files in `samples/`, link to them from the relevant README
- if there are no real external examples, do not add a self-referential “Examples” section

Thanks for helping improve Mindtrace.
