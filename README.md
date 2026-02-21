# jm-api

[![Integration Tests](https://github.com/miller46/jm-api/actions/workflows/integration-tests.yml/badge.svg?branch=main)](https://github.com/miller46/jm-api/actions/workflows/integration-tests.yml)

FastAPI + SQLAlchemy backend with JWT auth, bot management endpoints, a small admin web UI, and built-in observability.

## What this project includes

- Auth API: signup, login, refresh, logout, current user, and session management
- Bot API: CRUD + pagination + filter support
- Admin frontend served at `/admin`
- Alembic migrations
- Observability: structured logs, request IDs, Prometheus metrics, optional OpenTelemetry tracing

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

## Quick start

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

Open:

- Swagger docs: http://localhost:8000/docs
- Admin UI: http://localhost:8000/admin
- Health check: http://localhost:8000/api/v1/healthz

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
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"rig_id":1,"name":"bot-a"}'
```

By default, writes are open to authenticated users. To require admin-only writes:

```bash
export JM_API_BOTS_WRITE_ADMIN_ONLY=true
```

## Key endpoints

- Health: `GET /api/v1/healthz`
- Auth:
  - `POST /api/v1/auth/signup`
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/refresh`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/auth/me`
  - `GET /api/v1/auth/sessions`
  - `DELETE /api/v1/auth/sessions/{session_jti}`
  - `POST /api/v1/auth/sessions/revoke-others`
- Bots:
  - `GET /api/v1/bots`
  - `POST /api/v1/bots`
  - `GET /api/v1/bots/{bot_id}`
  - `PUT /api/v1/bots/{bot_id}`
  - `DELETE /api/v1/bots/{bot_id}`
- Metrics: `GET /metrics`

## Testing

Run default tests (excludes integration marker):

```bash
uv run pytest
```

Run integration tests explicitly:

```bash
uv run pytest -o addopts='' -m integration tests/integration
```

## Deployment/process notes

Procfile uses Gunicorn + Uvicorn workers:

```bash
gunicorn jm_api.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-2}
```

## Additional docs

- Observability details: `docs/observability.md`
