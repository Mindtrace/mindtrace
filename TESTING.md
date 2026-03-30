# Testing Guide

This guide covers the standard way to run tests in the [Mindtrace](https://github.com/Mindtrace/mindtrace) repo using `ds`.

## Requirements

You will need:

- Python 3.12+
- Git
- [uv](https://docs.astral.sh/uv/)
- `ds-run`
- Docker (recommended for integration tests and backend services)

## Setup

```bash
git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
uv sync --dev --all-extras
uv tool install ds-run
```

Run test commands from the repository root.

## Common Commands

### Standard test suite

```bash
ds test
```

This runs the standard suite, which typically means unit + integration tests.

### Unit tests only

```bash
ds test --unit
```

### Integration tests only

```bash
ds test --integration
```

### Stress tests only

```bash
ds test --stress
```

### Explicit unit + integration

```bash
ds test --unit --integration
```

This is equivalent to the standard `ds test` flow.

## Module-Specific Test Runs

For day-to-day development, it is usually faster to test only the module you are working on.

Use `ds test:` (with a colon) when you want to target specific modules, directories, or files.

### Module examples

```bash
ds test: core
ds test: services
ds test: registry
```

### Module + scope examples

```bash
ds test: core --unit
ds test: services --unit
ds test: jobs --integration
```

### Multiple modules

```bash
ds test: services jobs
ds test: database registry --unit
```

## Running Specific Test Paths

You can also point directly at files or directories.

```bash
ds test: tests/unit/mindtrace/core/test_logger.py
ds test: tests/unit
ds test: tests/integration/mindtrace/services
```

This is especially useful when iterating on a single failing test or a small test group.

## Available Test Scopes

Mindtrace currently has these main scopes:

- `unit`
- `integration`
- `stress`

And the main modules include:

`apps`, `automation`, `cluster`, `core`, `database`, `datalake`, `hardware`, `jobs`, `models`, `registry`, `services`, `storage`, and `ui`.

## Integration Test Infrastructure

Integration tests may start supporting services automatically using Docker Compose.

Relevant files include:

- [`tests/docker-compose.yml`](./tests/docker-compose.yml)
- [`tests/docker-compose-standard-ports.yml`](./tests/docker-compose-standard-ports.yml)

These integration environments include services such as:

- MinIO
- Redis
- RabbitMQ
- MongoDB

If integration tests fail unexpectedly, make sure Docker is available and healthy.

## Recommended Local Workflow

A good default workflow is:

```bash
# Fast iteration while coding
ds test: your-module --unit

# Broader verification before opening a PR
ds test: your-module

# Full project verification when needed
ds test
```

For example:

```bash
ds test: services --unit
ds test: services
ds test
```

## Coverage

Coverage is reported after test runs.

When multiple test groups are run together, coverage is combined so you can see cumulative results across the selected scopes.

As a general rule:

- do not let coverage regress for the area you changed
- add tests for new behavior
- prefer focused unit tests first, then add integration coverage where it matters

## Troubleshooting

### `ds` command not found

Install `ds-run`:

```bash
uv tool install ds-run
```

### Dependency or environment issues

Re-sync the environment:

```bash
uv sync --dev --all-extras
```

### Integration tests failing unexpectedly

Check that Docker is running and that the required backend containers can start cleanly.

### Need the fastest feedback loop

Run a specific module or file instead of the full suite:

```bash
ds test: core --unit
ds test: tests/unit/mindtrace/core/test_logger.py
```
