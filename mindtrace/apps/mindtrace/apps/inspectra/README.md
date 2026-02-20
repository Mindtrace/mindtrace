# Inspectra Backend

Auth, organizations, and users with role-based access (SUPER_ADMIN and ADMIN). Uses **Mindtrace Mongo ODM** for all DB access and **FastAPI**-style auth.

---

## Quick start (dev)

### 1. Start MongoDB (Docker)

From the repo root:

```bash
cd docker/inspectra
cp .env.example .env
# Edit .env if needed (JWT_SECRET, etc.)
docker compose up -d mongo
```

Wait until mongo is healthy, then start the API (see below) or run the seed.

### 2. Backend env

From the **repo root** (or the directory that contains the `mindtrace` package):

```bash
cp mindtrace/apps/mindtrace/apps/inspectra/.env.example mindtrace/apps/mindtrace/apps/inspectra/.env
# Edit .env: set MONGO_URI if not using default localhost
```

For **Docker** runs, the API container uses the same `.env` as in `docker/inspectra/.env` (see Docker section).

### 3. Run the API (dev mode)

From the **repo root** (install deps first with `uv sync`):

```bash
uv run python -m mindtrace.apps.inspectra
```

The server restarts automatically when you edit Python files. Host/port come from `INSPECTRA__URL`.

Default bind: `0.0.0.0:8080` so the API is reachable at `http://localhost:8080` and at your machine’s IP (e.g. `http://192.168.50.228:8080`). Override with `INSPECTRA__URL` if needed.

### 4. Run the seed (first org + SUPER_ADMIN)

With MongoDB running and the same env (so `MONGO_URI` / `MONGO_DB_NAME` are set):

```bash
uv run python -m mindtrace.apps.inspectra.seed
```

The seed loads `.env` from the inspectra app directory (`mindtrace/apps/mindtrace/apps/inspectra/.env`) and from the current directory, so you can put `MONGO_URI` in either place. If MongoDB requires authentication (e.g. you started it via Docker from `docker/inspectra`), set `MONGO_URI` in that `.env` with **localhost** (not `mongo`) and credentials, e.g. `mongodb://inspectra_root:inspectra_root_password@localhost:27017/inspectra?authSource=admin` (use the same user/password as in the docker `MONGO_INITDB_ROOT_*` vars).

**If the seed fails with "Authentication failed":** Mongo only applies `MONGO_INITDB_ROOT_*` when the data volume is first created. If you changed those values after the first run, reset the volume and recreate: `cd docker/inspectra && docker compose down -v && docker compose up -d mongo`.

This creates:

- Organization **mindtrace** (if missing)
- A **SUPER_ADMIN** user (email/password from env, see below)

Seed env vars (optional; defaults shown):

| Variable | Default |
|----------|---------|
| `SEED_ORG_NAME` | `mindtrace` |
| `SEED_SUPER_ADMIN_EMAIL` | `superadmin@mindtrace.ai` |
| `SEED_SUPER_ADMIN_PASSWORD` | `ChangeMe123!` |
| `SEED_SUPER_ADMIN_FIRST_NAME` | `Mindtrace` |
| `SEED_SUPER_ADMIN_LAST_NAME` | `SuperAdmin` |
| `SEED_FORCE_UPDATE_PASSWORD` | (optional) `1`/`true`/`yes` to overwrite existing super admin password |

If the super admin user already exists but the password doesn’t match your `.env`, update it by running the seed with `SEED_FORCE_UPDATE_PASSWORD=1` (e.g. `SEED_FORCE_UPDATE_PASSWORD=1 uv run python -m mindtrace.apps.inspectra.seed`). You can also set `SEED_FORCE_UPDATE_PASSWORD=1` in `.env`.

After seeding, log in with that email/password to get a JWT.

---

## Docker (full stack)

From `docker/inspectra`:

```bash
cp .env.example .env
# Edit .env (JWT_SECRET, etc.)
docker compose up --build
```

- API: `http://localhost:8000` (host port from `API_PORT` in `.env`, default 8000)
- Mongo Express: `http://localhost:8081` (if enabled)

Then run the seed **inside** the API container (same env as API):

```bash
docker compose exec api python -m mindtrace.apps.inspectra.seed
```

Or run the seed locally with `uv` and `MONGO_URI` pointing at the host-exposed mongo:

```bash
uv run python -m mindtrace.apps.inspectra.seed
```

---

## Environment variables

Backend (API and seed) use these. Unprefixed vars are read as fallbacks (e.g. for Docker); otherwise use `INSPECTRA__*` if your config layer supports it.

| Variable | Description | Default |
|----------|-------------|---------|
| `INSPECTRA__URL` | Service bind URL (host:port) | `http://0.0.0.0:8080` |
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGO_DB_NAME` | Database name | `inspectra` |
| `JWT_SECRET` | Secret for signing JWTs | (set in .env) |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_EXPIRES_IN` | Access token TTL (seconds) | `900` |
| `REFRESH_TOKEN_EXPIRES_IN` | Refresh token TTL (seconds) | `604800` |
| `PASSWORD_MIN_LENGTH` | Min password length | `12` |
| `CORS_ALLOW_ORIGINS` | Comma-separated origins | `http://localhost:3000,...` |


---

## Roles

- **SUPER_ADMIN**: Create/update/deactivate organizations and users; assign any role; no org scope.
- **ADMIN**: Same as above but **only within their organization**; cannot create or update organizations; cannot create or assign SUPER_ADMIN.

Passwords must meet length and complexity rules (see `PASSWORD_MIN_LENGTH` and `validate_password_strength` in code).

---

## Project layout

```
inspectra/
├── __init__.py
├── __main__.py
├── dev.py            # Uvicorn app entry (dev:app) for --reload
├── inspectra.py      # InspectraService: middleware, app.state, registers routes
├── db.py             # MongoMindtraceODM init (User, Organization)
├── seed.py           # Seed script (default org + SUPER_ADMIN)
├── core/
│   ├── __init__.py
│   ├── settings.py   # Config (env: INSPECTRA__*, MONGO_URI, etc.)
│   ├── security.py  # JWT, password hashing, get_current_user
│   ├── deps.py       # require_super_admin, require_admin_or_super, get_inspectra_service
│   └── validation/   # validate_no_whitespace, etc.
├── routes/           # One module per domain (register(service) + handlers)
│   ├── auth.py
│   ├── organizations.py
│   └── users.py
├── models/           # Beanie documents (User, Organization, enums)
├── repositories/
│   ├── user_repository.py
│   └── organization_repository.py
├── schemas/
│   ├── auth.py
│   ├── user.py
│   └── organization.py
└── README.md
```
