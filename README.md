# JM API

JM API is a FastAPI + SQLAlchemy backend with JWT-based authentication, an admin web frontend, and built-in observability (metrics, tracing, structured logs).

## Overview

Current functionality includes:

- **Authentication**: signup, login, token refresh, logout, and `/auth/me` user introspection
- **Bots API**: CRUD endpoints with pagination and filter support
- **Admin frontend**: static UI served at `/admin` for login/signup and bot management
- **Observability**:
  - JSON structured logs with request IDs
  - Prometheus metrics endpoint
  - OpenTelemetry tracing (Jaeger exporter)
  - slow query logging
- **Safety defaults**: SQLite allowed for local dev, rejected for `staging`/`production`

## Quickstart (new developers)

1. **Install dependencies**

   ```bash
   uv sync
   ```

2. **Set required local environment variables**

   ```bash
   export JM_API_DATABASE_URL="sqlite:///./dev.db"
   export JM_API_JWT_SECRET_KEY="dev-secret-change-me"
   ```

3. **Run the API**

   ```bash
   uv run uvicorn jm_api.main:app --reload
   ```

4. **Open the app**
   - API docs: http://localhost:8000/docs
   - Admin UI: http://localhost:8000/admin

## Running tests

### Default test suite (unit + non-integration)

```bash
uv run pytest
```

### Integration tests (exact commands)

The project config excludes integration tests by default, so use `-o addopts=''` to run them explicitly.

```bash
# Run all integration tests
uv run pytest -o addopts='' -m integration tests/integration

# Run one integration test module
uv run pytest -o addopts='' -m integration tests/integration/test_integration.py
```

## URL map / routing

Assuming local server at `http://localhost:8000` and default API prefix `/api/v1`:

### Admin frontend

- `GET /admin` — static admin app mount
- `GET /admin/login.html` — admin login page
- `GET /admin/signup.html` — admin signup page
- `GET /admin/index.html` — admin dashboard

### Core/health + docs

- `GET /api/v1/healthz` — health check
- `GET /docs` — Swagger UI (when `JM_API_DOCS_ENABLED=true`)
- `GET /redoc` — ReDoc (when docs enabled)
- `GET /openapi.json` — OpenAPI schema (when docs enabled)

### Auth endpoints

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

### Bot endpoints

- `GET /api/v1/bots`
- `POST /api/v1/bots`
- `GET /api/v1/bots/{bot_id}`
- `PUT /api/v1/bots/{bot_id}`
- `DELETE /api/v1/bots/{bot_id}`

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

## Environment variables (local development)

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

### Auth/JWT settings

- `JM_API_JWT_ALGORITHM=HS256`
- `JM_API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15`
- `JM_API_JWT_REFRESH_TOKEN_EXPIRE_DAYS=7`

### Observability settings

- `JM_API_METRICS_ENABLED=true`
- `JM_API_METRICS_PATH=/metrics`
- `JM_API_SLOW_QUERY_THRESHOLD_MS=500`
- `JM_API_TRACING_ENABLED=false`
- `JM_API_TRACING_SERVICE_NAME=jm-api`
- `JM_API_TRACING_SERVICE_VERSION=0.1.0`
- `JM_API_TRACING_JAEGER_HOST=localhost`
- `JM_API_TRACING_JAEGER_PORT=6831`

## Optional: local observability stack

Start Prometheus + Grafana + Jaeger:

```bash
docker compose -f docker-compose.observability.yml up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Jaeger: http://localhost:16686

See `docs/observability.md` for dashboard/query examples.

## Project structure

```text
src/jm_api/
  main.py              # ASGI entrypoint
  app.py               # FastAPI app factory
  core/
    config.py          # pydantic-settings config (JM_API_*)
    logging.py         # structured logging
    observability.py   # metrics + tracing wiring
  api/
    routes/
      auth.py          # auth routes
      health.py        # health route
      bots.py          # bot CRUD routes
  models/
    bot.py
    user.py
  static/              # /admin frontend assets
tests/
  integration/         # real-server integration tests
```