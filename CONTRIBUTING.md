## Contributing to Mindtrace

Thank you for your interest in contributing to Mindtrace!  
This guide will help you get started with contributing to the project.  

The Mindtrace project is organized into the following modules:  
`apps`, `automation`, `cluster`, `core`, `database`, `datalake`, `hardware`, `jobs`, `models`, `registry`, `services`, `storage`, `ui`  
When contributing, ensure your changes respect the modular architecture and dependency boundaries.  


### Prerequisites

- Python 3.12+
- Git
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose - For integration tests (both `docker-compose` v1 and `docker compose` v2 are supported)


### Setup

1. **Fork the repository:**
   - [Fork your copy of the mindtrace repo](https://github.com/Mindtrace/mindtrace/fork)
   - Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/mindtrace.git
   cd mindtrace/
   ```

2. **Install dependencies:**
   ```bash
   uv sync --dev
   uv tool install ds-run
   uv tool install ruff
   ```

3. **Verify your setup:**
   ```bash
   ds test --unit
   ```


### Development Workflow

#### 1. Create a Branch

Create a new branch from `dev` with a descriptive name:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/short-description
# or
git checkout -b fix/issue-description
# or
git checkout -b docs/update-description
```

#### 2. Make Changes

- **Focus on small, atomic changes** - Keep your PRs focused and manageable
- **Write clear, descriptive code** with proper naming conventions
- **Add docstrings** for new functions and classes using [Google-style docstrings](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html)
- **Use type hints** for better code clarity and IDE support
- **Add unit tests** for new functionality (`tests/unit/mindtrace/[module]`)
- **Add integration tests** where applicable (`tests/integration/mindtrace/[module]`)

#### 3. Code Quality

Before committing, ensure your code meets quality standards:

```bash
# Check for linting issues
ruff check

# Check formatting
ruff format --check

# Apply auto-fixes for linting and formatting
ruff check --fix
ruff format
```

#### 4. Testing

Run the standard test suite and ensure that tests pass locally before submitting your PR.  
```bash
ds test
```
Ensure that code coverage does not regress.  
For more details on running tests, including running smaller test sets for iterative development, see [TESTING.md](./TESTING.md)

#### 5. Commit Changes

Make small, focused commits with clear messages:

```bash
git add .
git commit -m "feat: add new feature description"
# or
git commit -m "fix: resolve issue with specific component"
# or
git commit -m "docs: update API documentation"
```

#### 6. Push and Create Pull Request

```bash
git push origin your-branch-name
```

Then create a pull request to the `dev` branch on the main repo: [https://github.com/Mindtrace/mindtrace](https://github.com/Mindtrace/mindtrace).


### Pull Request Guidelines

#### PR Title and Description

Your pull request should include:

- **Clear, descriptive title** that summarizes the change
- **Detailed description** covering:
  - **Scope and motivation** - What problem does this solve?
  - **Changes included** - What was modified, added, or removed?
  - **How to test** - Specific steps to verify the changes work
  - **Impact** - Any breaking changes, potential concerns, or side effects


#### Requirements Checklist

- [x] All tests pass (`ds test`)
- [x] Code is properly formatted (`ruff format --check`)
- [x] No linting issues (`ruff check`)
- [x] PR targets the `dev` branch
- [x] Tests added for new functionality
- [x] No regression in test coverage
- [x] Documentation updated as needed
- [x] Useful commit messages
- [x] Links to relevant issues/PRs/discussions, if any


### Code Review Process

1. **Automated Checks** - All PRs run automated tests, linting, and formatting checks. Please ensure they pass
2. **Review** - Maintainers will review your code and may request clarifications and/or changes
3. **Merge** - Once approved, your PR will be merged to `dev` and included in the next release cycle


---

Thank you for contributing to Mindtrace and helping to improve it! 🎉
