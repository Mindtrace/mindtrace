## Testing Guide

Quick reference for running tests for the [mindtrace](https://github.com/Mindtrace/mindtrace) repo with `ds` commands.

### Requirements

- Python 3.12+
- git
- [uv](https://docs.astral.sh/uv/)
- ds-run
- Docker with Compose (both `docker-compose` v1 and `docker compose` v2 are supported)

### Setup

```bash
git clone https://github.com/Mindtrace/mindtrace.git
cd mindtrace/
uv sync --dev
uv tool install ds-run
```

### Basic Commands

All tests are run from the project's root.
```bash
# Run the standard test suite (unit + integration)
ds test

# Run only unit tests
ds test --unit

# Run only integration tests
ds test --integration

# Run only stress tests
ds test --stress

# Run both unit and integration tests. Same as `ds test`
ds test --unit --integration
```

Note: Integration tests automatically spin up required containers from [tests/docker-compose.yml](./tests/docker-compose.yml) (includes MinIO, Redis, RabbitMQ, and MongoDB).

### Specifying modules, directories and files

During development and/or debugging, it is often useful to run a limited set of tests repeatedly.  
For specifying one or more test paths or modules, use `ds test: paths` (note the colon `:` after `test`)

```bash
# Specific test files/directories
ds test: tests/unit/mindtrace/core/test_logger.py
ds test: tests/unit

# Module names (unit + integration by default)
ds test: core
ds test: services jobs

# Modules with flags
ds test: core --unit
ds test: services jobs --integration
```

### Available Modules

`apps`, `automation`, `cluster`, `core`, `database`, `datalake`, `hardware`, `jobs`, `models`, `registry`, `services`, `storage`, `ui`


### Coverage

Detailed code coverage (per-file and overall) is reported after the tests have finished.  
When running multiple test groups, e.g. unit + integration via `ds test`, reports are combined to provide a cumulative coverage.
