# jm-api

[![Integration Tests](https://github.com/miller46/jm-api/actions/workflows/integration-tests.yml/badge.svg?branch=main)](https://github.com/miller46/jm-api/actions/workflows/integration-tests.yml)

FastAPI + SQLAlchemy backend with JWT auth, bot management endpoints, a small admin web UI, and built-in observability.

## What this project includes

- Auth API: signup, login, refresh, logout, current user, and session management
- Bot API: CRUD + pagination + filter support
- Admin frontend served at `/admin`
- Alembic migrations
- Observability: structured logs, request IDs, Prometheus metrics, optional OpenTelemetry tracing
- Safety defaults: SQLite allowed for local dev, rejected for `staging`/`production`
- Bot write protection is secure by default (`JM_API_BOTS_WRITE_ADMIN_ONLY=true`)

## Project structure

```text
src/jm_api/
  app.py                 # FastAPI app factory and middleware wiring
  main.py                # ASGI entrypoint (jm_api.main:app)
  api/
    router.py            # top-level API router (/api/v1)
    routes/
      auth.py            # auth + session endpoints
      bots.py            # bot CRUD endpoints
      health.py          # health check endpoint
    generic/             # reusable CRUD/filter helpers
  core/
    config.py            # JM_API_* settings
    logging.py           # structured logging setup
    observability.py     # metrics + tracing setup
    lifespan.py          # startup/shutdown lifecycle
  db/
    session.py           # SQLAlchemy session dependency
    migrations.py        # migration-state checks
  models/                # SQLAlchemy models
  schemas/               # pydantic request/response schemas
  middleware/
    request_id.py
  static/                # admin frontend assets
alembic/                 # DB migrations
tests/
  unit + API tests       # default pytest run
  integration/           # full-stack integration tests
```

## Quickstart

### 1) Install dependencies

```bash
uv sync
```

### 2) Configure local environment

```bash
export JM_API_DATABASE_URL="sqlite:///./dev.db"
export JM_API_JWT_SECRET_KEY="dev-secret-change-me"
```

Optional but common for local work:

```bash
export JM_API_ENVIRONMENT=development
export JM_API_DOCS_ENABLED=true
export JM_API_API_V1_PREFIX=/api/v1
```

### 3) Run database migrations

```bash
make migrate
```

### 4) Start the API

```bash
uv run uvicorn jm_api.main:app --reload
```

Production process model (Procfile):

```bash
gunicorn jm_api.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-2}
```

Open:

- Swagger docs: http://localhost:8000/docs
- Admin UI: http://localhost:8000/admin
- Liveness check: http://localhost:8000/api/v1/live
- Readiness check: http://localhost:8000/api/v1/ready
- Deep health check: http://localhost:8000/api/v1/health

## Basic usage examples

Base URL assumes `http://localhost:8000/api/v1`.

### Signup

```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"secret123"}'
```

### Login

```bash
curl -i -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"secret123"}'
```

Notes:
- Response contains `access_token`
- Login also sets `refresh_token` and `csrf_token` cookies
- Response header includes `X-CSRF-Token`

### List bots

```bash
curl "http://localhost:8000/api/v1/bots?page=1&per_page=20"
```

### Create bot

```bash
curl -X POST http://localhost:8000/api/v1/bots \
  -H "Content-Type: application/json" \
  -d '{"rig_id":1,"name":"bot-a"}'
```

By default, writes are admin-only. To opt out:

```bash
export JM_API_BOTS_WRITE_ADMIN_ONLY=false
```

## Rate limiting and quotas

The API enforces global throttling and identity-based quotas.

- API-wide limits (per identity):
  - `JM_API_RATE_LIMIT_API_PER_MINUTE` (default: `120`)
  - `JM_API_RATE_LIMIT_API_PER_HOUR` (default: `3000`)
- Per-identity quotas:
  - `JM_API_RATE_LIMIT_QUOTA_PER_DAY` (default: `10000`)
  - `JM_API_RATE_LIMIT_QUOTA_PER_MONTH` (default: `200000`)
- Storage backend:
  - `JM_API_RATE_LIMIT_STORAGE_URI` (default: `memory://`)
  - Use Redis in multi-worker deployments, e.g. `redis://localhost:6379/0`

Identity is determined as:
- Authenticated requests: per user (`Authorization: Bearer ...`)
- Anonymous requests: per client IP

When limits are exceeded, API returns `429 Too Many Requests` with:
- `Retry-After`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

Login and signup also retain their stricter endpoint-specific protection (`5 per 15 minutes`).

## URL map / routing

Assuming local server at `http://localhost:8000` and default API prefix `/api/v1`:

### Admin frontend

- `GET /admin` — static admin app mount
- `GET /admin/login.html` — admin login page
- `GET /admin/signup.html` — admin signup page
- `GET /admin/index.html` — admin dashboard

### Core/health + docs

- `GET /api/v1/live` — liveness probe (process is running)
- `GET /api/v1/ready` — readiness probe (DB + migrations checks)
- `GET /api/v1/health` — deep health check (DB connectivity + migration state)
- `GET /api/v1/healthz` — legacy compatibility health endpoint
- `GET /docs` — Swagger UI (when `JM_API_DOCS_ENABLED=true`)
- `GET /redoc` — ReDoc (when docs enabled)
- `GET /openapi.json` — OpenAPI schema (when docs enabled)

### Auth endpoints

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/sessions`
- `DELETE /api/v1/auth/sessions/{session_jti}`
- `POST /api/v1/auth/sessions/revoke-others`

### Bot endpoints

- `GET /api/v1/bots`
- `POST /api/v1/bots` *(admin only by default; set `JM_API_BOTS_WRITE_ADMIN_ONLY=false` to opt out)*
- `GET /api/v1/bots/{bot_id}`
- `PUT /api/v1/bots/{bot_id}` *(admin only by default; set `JM_API_BOTS_WRITE_ADMIN_ONLY=false` to opt out)*
- `DELETE /api/v1/bots/{bot_id}` *(admin only by default; set `JM_API_BOTS_WRITE_ADMIN_ONLY=false` to opt out)*

`GET /api/v1/bots` supports:

- `page`, `per_page`
- `rig_id`
- `kill_switch`
- `log_search`
- `create_at_after`, `create_at_before`
- `last_update_at_after`, `last_update_at_before`
- `last_run_at_after`, `last_run_at_before`

### Metrics / observability endpoints

- `GET /metrics` — Prometheus scrape endpoint (default)

## Environment variables

All settings use the `JM_API_` prefix.

### Required

- `JM_API_DATABASE_URL` (example: `sqlite:///./dev.db`)
- `JM_API_JWT_SECRET_KEY` (set a non-default value)

### Commonly used local settings

- `JM_API_ENVIRONMENT=development`
- `JM_API_DEBUG=false`
- `JM_API_API_V1_PREFIX=/api/v1`
- `JM_API_DOCS_ENABLED=true`
- `JM_API_LOG_LEVEL=INFO`
- `JM_API_LOG_JSON=true`
- `JM_API_REQUEST_ID_HEADER=X-Request-ID`
- `JM_API_ALLOW_ORIGINS=http://localhost:3000,http://localhost:8000`
- `JM_API_ALLOWED_HOSTS=localhost,127.0.0.1`
- `JM_API_BOTS_WRITE_ADMIN_ONLY=false` *(development default; required `true` in staging/production unless risk override is explicitly set)*
- `JM_API_I_UNDERSTAND_RISK=false` *(escape hatch for temporary production exception when disabling admin-only bot writes)*
- `JM_API_RATE_LIMIT_STORAGE_URI=memory://` *(development default; use Redis in staging/production)*
- `JM_API_TRUST_PROXY_HEADERS=false`
- `JM_API_TRUSTED_PROXY_CIDRS=` *(comma-separated, e.g. `10.0.0.0/8,172.16.0.0/12`)*

### Production/staging startup invariants (fail-fast)

When `JM_API_ENVIRONMENT` is `staging` or `production`, the app validates and refuses to start if any invariant is violated:

- `JM_API_RATE_LIMIT_STORAGE_URI` **must not** be `memory://` (use Redis)
- `JM_API_BOTS_WRITE_ADMIN_ONLY` must be `true`, unless `JM_API_I_UNDERSTAND_RISK=true` is explicitly set for a temporary exception
- `JM_API_TRUST_PROXY_HEADERS=true` requires `JM_API_TRUSTED_PROXY_CIDRS` to be configured
- JWT signing material must be at least 32 bytes per key (`JM_API_JWT_SECRET_KEY` or each key in `JM_API_JWT_SIGNING_KEYS`)

In `development` and `test`, these checks are intentionally relaxed for local convenience.

### Auth/JWT settings

- `JM_API_JWT_ALGORITHM=HS256`
- `JM_API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15`
- `JM_API_JWT_REFRESH_TOKEN_EXPIRE_DAYS=7`

### Session store settings (refresh-token revocation)

Refresh-token revocation is persisted in SQL via the `session_tokens` table.

### Security hardening for internet exposure

- **CSRF protection**: refresh/logout/session-management endpoints require `X-CSRF-Token` matching the `csrf_token` cookie (double-submit cookie pattern).
- **Session binding**: refresh-token rotation is bound to a device fingerprint (`user-agent` hash) and source IP subnet (`/24` IPv4, `/64` IPv6).
- **JWT secret rotation**: configure `JM_API_JWT_SIGNING_KEYS` as comma-separated keys. If set, only these keys are used (first signs new JWTs; all verify during rollover). `JM_API_JWT_SECRET_KEY` is used only when `JM_API_JWT_SIGNING_KEYS` is empty.
- **Security audit logs**: auth actions emit structured `security.audit` events including `event_type`, `outcome`, `ip`, `user_agent`, and optional risk flags.

### Production/staging startup invariants (fail-fast)

When `JM_API_ENVIRONMENT` is `staging` or `production`, startup will fail unless all of the following are true:

- `JM_API_RATE_LIMIT_STORAGE_URI` is **not** `memory://` (Redis required)
- `JM_API_BOTS_WRITE_ADMIN_ONLY=true` *(or set `JM_API_I_UNDERSTAND_RISK=true` for an explicit temporary exception)*
- if `JM_API_TRUST_PROXY_HEADERS=true`, then `JM_API_TRUSTED_PROXY_CIDRS` must be configured with valid CIDRs
- Effective JWT signing key(s) must be at least 32 bytes (`JM_API_JWT_SECRET_KEY` or each entry in `JM_API_JWT_SIGNING_KEYS`)

- `JM_API_SESSION_CLEANUP_INTERVAL_SECONDS=300` (opportunistic cleanup interval in API process)

### Observability settings

- `JM_API_METRICS_ENABLED=true`
- `JM_API_METRICS_PATH=/metrics`
- `JM_API_SLOW_QUERY_THRESHOLD_MS=500`
- `JM_API_TRACING_ENABLED=false`
- `JM_API_TRACING_SERVICE_NAME=jm-api`
- `JM_API_TRACING_SERVICE_VERSION=0.1.0`
- `JM_API_TRACING_JAEGER_HOST=localhost`
- `JM_API_TRACING_JAEGER_PORT=6831`

## Database migrations (Alembic)

This project uses Alembic for schema migrations.

### Commands

```bash
# Apply all migrations
make migrate

# Create a new migration from model changes
make migrate-create msg="describe change"
```

You can also run Alembic directly:

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"
```

### Workflow

1. Update SQLAlchemy models.
2. Generate a migration (`make migrate-create ...`).
3. Review/edit generated migration in `alembic/versions/`.
4. Apply locally (`make migrate`).
5. Run tests.

### Bot table index strategy

Migration `20260220_000002_add_bots_indexes` adds explicit indexes for the most common bot list/filter patterns:

- Single-column: `rig_id`, `kill_switch`, `create_at`, `last_update_at`, `last_run_at`
- Composite: `(rig_id, kill_switch)` and `(kill_switch, last_run_at)`

> Note: this codebase uses `create_at`/`last_update_at` column names (not `created_at`/`last_updated_at`).

To validate planner improvements in PostgreSQL, run:

```sql
EXPLAIN ANALYZE SELECT * FROM bots WHERE rig_id = 'rig-001';
EXPLAIN ANALYZE SELECT * FROM bots WHERE kill_switch = false;
EXPLAIN ANALYZE SELECT * FROM bots ORDER BY create_at DESC LIMIT 50;
EXPLAIN ANALYZE SELECT * FROM bots WHERE kill_switch = false ORDER BY last_run_at DESC LIMIT 50;
```

### Startup migration gate

On startup, the API verifies that the DB revision matches the Alembic head revision.
If the DB is behind (or uninitialized), the app fails fast with an instruction to run migrations.

You can disable this check in test/local scenarios:

- `JM_API_DB_MIGRATION_CHECK_ENABLED=false`

## CI pipeline

GitHub Actions runs the `CI` workflow on pushes and pull requests to `main`.

Order of checks:
- `quality-gates` job (fast-fail):
  - `ruff check .` (lint)
  - `mypy` (type checks)
  - `bandit -r src` (security scan)
  - `pip-audit -r requirements.txt` (dependency vulnerability scan)
- `integration-tests` job:
  - runs only after `quality-gates` passes
  - validates Alembic migrations and runs integration tests

Because `integration-tests` depends on `quality-gates`, any failing lint/type/security/dependency check blocks merges on protected branches.

## Testing

Run default tests (excludes integration marker):

```bash
uv run pytest
```

Run integration tests explicitly:

```bash
uv run pytest -o addopts='' -m integration tests/integration
```

## Container deployment

Deployment artifacts added in this repository:

- `Dockerfile` (multi-stage, non-root runtime user, built-in health check)
- `.dockerignore` (reduced build context)
- `.env.example` (documented runtime environment template)
- `docs/deployment.md` (startup, migration flow, rollback, platform examples)

Typical flow:

```bash
docker build -t ghcr.io/miller46/jm-api:<tag> .
docker run --rm --env-file .env -p 8000:8000 ghcr.io/miller46/jm-api:<tag>
```

Run migrations before app rollout:

```bash
docker run --rm --env-file .env ghcr.io/miller46/jm-api:<tag> alembic upgrade head
```

See `docs/deployment.md` for complete deployment and rollback runbooks.

## Optional: local observability stack

Start Prometheus + Grafana + Jaeger:

```bash
docker compose -f docker-compose.observability.yml up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Jaeger: http://localhost:16686

See `docs/observability.md` for dashboard/query examples.
