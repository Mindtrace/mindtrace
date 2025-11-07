# Inspectra

Inspectra Platform for analytics and insights.

## High-Level Architecture

  - **Reflex UI & State**: All UI pages live under `inspectra/pages`. Each page is paired with a Page State within the same file that implements the page. Global states are defined under 
`inspectra/state`.

- **Services Layer**: Business workflows belong in `inspectra/backend/services`. Services orchestrate repositories, security helpers, and cross-cutting logic (e.g., `AuthService` handles credential checks + JWT generation; `UserService` owns registration and lifecycle operations).
- **Repository Layer**: Persistence logic is isolated in `inspectra/backend/db/repos`. Repositories offer thin, async helpers over Beanie models and never contain business rules.
- **Models**: MongoDB document definitions sit in `inspectra/backend/db/models`, each extending the shared `MindtraceDocument`. 
- **DB Initialization**: `inspectra/backend/db/init.py` exposes `init_db`/`ensure_db_init` to configure the Motor client and register models once per process.

## Repository Pattern

- Repos inherit from `AutoInitRepo`, which wraps every coroutine with `ensure_db_init`. Authors do **not** call the DB initializer manually inside repo methods.
- Methods stay focused on CRUD primitives: finders (`get_by_email`), mutators (`assign_scope`), creation helpers (`create_user`). Avoid embedding business rules or request validation.
- Higher layers (services/states) translate domain requests into repo calls.

## Service Pattern

- Services compose multiple repos, security utilities, and other services to implement workflows.
- Example: `AuthService.login` verifies credentials through `UserRepo`, ensures account status, and issues a signed JWT with role/persona claims using `create_jwt_token`.


## Working With Models

- Add new document types under `inspectra/backend/db/models`, inheriting from `MindtraceDocument`. Define indexes in the nested `Settings` class and normalize fields inside lifecycle hooks.
- Expose models in `inspectra/backend/db/models/__init__.py` so they are registered during `init_beanie`.

## Database Lifecycle

- Application bootstrap (`inspectra/inspectra.py`) keeps things synchronous—do not call `asyncio.run` there.
- For scripts (e.g., seeding), call `await init_db()` before using repos. Example: `inspectra/backend/db/seed.py` seeds demo data via services.
## Development Guidelines

- **Additions**
  - Put persistence helpers in a repo module; expose them via a service that houses orchestration logic.
  - Share cross-cutting utilities in `inspectra/utils` (e.g., password hashing, JWT helpers).
- Page and Component states should be implmemented in the same file as the page or component it belongs to. This is to enforce the distinction between specific page/component state and global state.
- **Testing & Seeding**
  - Use `seed.py` as a reference for writing async scripts that interact with the DB through services.
  - Prefer integration-style tests that exercise services and states rather than hitting repos directly.

## Getting Started

1. Install dependencies: `uv sync`
2. Configure environment: copy `.env.dev` template, set `MONGO_URI`, `DB_NAME`, `JWT_SECRET`, etc.
3. Run the Reflex dev server: `reflex run` from the repo root.
4. Seed demo data (optional): `python -m inspectra.backend.db.seed`.
