# jm-api

A Go REST API built on chi v5 with PostgreSQL (sqlc + pgx v5), JWT authentication with session rotation, outbound webhook delivery, and a background task worker.

## Stack

| Component | Library |
|-----------|---------|
| Router | [chi v5](https://github.com/go-chi/chi) |
| Database driver | [pgx v5](https://github.com/jackc/pgx) |
| Query generation | [sqlc](https://sqlc.dev) |
| Migrations | [golang-migrate](https://github.com/golang-migrate/migrate) |
| Auth | [golang-jwt/jwt v5](https://github.com/golang-jwt/jwt) + bcrypt |
| Rate limiting | In-memory (dev) / Redis (prod) |
| Metrics | Prometheus |
| Tracing | OpenTelemetry (OTLP/HTTP export) |
| Logging | `log/slog` (structured JSON) |

## Prerequisites

- Go 1.25+
- PostgreSQL
- [golang-migrate CLI](https://github.com/golang-migrate/migrate/tree/master/cmd/migrate) (for running migrations manually)
- Redis (optional in dev, required in production)
- [sqlc](https://sqlc.dev) (only needed when modifying SQL queries)

## Getting Started

### 1. Set environment variables

At minimum you need a database URL:

```sh
export JM_API_DATABASE_URL="postgres://user:password@localhost:5432/jm_api?sslmode=disable"
```

### 2. Run migrations

```sh
make migrate-up
```

### 3. Start the API server

```sh
make run
```

The server starts on `0.0.0.0:8000` by default.

### 4. Start the background worker (optional)

In a separate terminal:

```sh
make worker
```

## Build

```sh
make build
# outputs: bin/api, bin/worker
```

## Docker

```sh
docker build -t jm-api .
docker run -e JM_API_DATABASE_URL="..." -p 8000:8000 jm-api
```

The image builds both `api` and `worker` binaries. The default `CMD` runs `api`. To run the worker instead:

```sh
docker run -e JM_API_DATABASE_URL="..." jm-api worker
```

## Testing

```sh
make test
# or
go test ./... -v -count=1
```

Test coverage includes handler integration tests backed by ephemeral Postgres via testcontainers-go.

To run only integration tests:

```sh
go test ./... -v -count=1 -tags integration
```

## API Reference

Base path: `/api/v1` (configurable via `JM_API_API_V1_PREFIX`)

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/live` | None | Liveness probe |
| GET | `/api/v1/health` | None | Health check with DB status |
| GET | `/api/v1/ready` | None | Readiness probe (same as `/health`) |
| GET | `/api/v1/healthz` | None | Simple liveness (Kubernetes style) |

### Meta

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/meta` | None | Version, git SHA, environment info |

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/signup` | None | Register a new user |
| POST | `/api/v1/auth/login` | None | Login, returns access token + sets cookies |
| POST | `/api/v1/auth/refresh` | Cookie + CSRF | Rotate refresh token, issue new access token |
| POST | `/api/v1/auth/logout` | Bearer | Revoke current session |
| GET | `/api/v1/auth/me` | Bearer | Get current user |
| GET | `/api/v1/auth/sessions` | Bearer | List all sessions |
| DELETE | `/api/v1/auth/sessions/{jti}` | Bearer | Revoke a specific session |
| POST | `/api/v1/auth/sessions/revoke-others` | Bearer | Revoke all sessions except current |

**Login rate limit:** 5 requests/minute. **Signup rate limit:** 5 requests/minute.

Login response:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```

The refresh token is set as an `HttpOnly; Secure; SameSite=Strict` cookie. A `csrf_token` cookie (readable by JS) is also set and must be echoed back as the `X-CSRF-Token` header on `/auth/refresh` requests.

### Bots

Bot reads are public. Writes require authentication (admin-only when `JM_API_BOTS_WRITE_ADMIN_ONLY=true`).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/bots` | None | List bots (paginated, filterable) |
| GET | `/api/v1/bots/{id}` | None | Get a bot by ID |
| POST | `/api/v1/bots` | Bearer | Create a bot |
| PUT | `/api/v1/bots/{id}` | Bearer | Update a bot |
| DELETE | `/api/v1/bots/{id}` | Bearer | Delete a bot |

List query parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (default: 1) |
| `per_page` | int | Results per page (default: 20, max: 100) |
| `rig_id` | string | Filter by rig ID |
| `kill_switch` | bool | Filter by kill switch state |
| `log_search` | string | Search in last run log |
| `create_at_from` | RFC3339 | Filter created after |
| `create_at_to` | RFC3339 | Filter created before |
| `last_update_at_from` | RFC3339 | Filter updated after |
| `last_update_at_to` | RFC3339 | Filter updated before |
| `last_run_at_from` | RFC3339 | Filter last run after |
| `last_run_at_to` | RFC3339 | Filter last run before |

Create/update body:
```json
{
  "rig_id": "my-rig-001",
  "kill_switch": false,
  "last_run_log": "optional log text"
}
```

Bot mutations dispatch webhook events (`bot.created`, `bot.updated`, `bot.deleted`).

### Webhooks

All webhook endpoints require authentication. Webhooks are user-scoped — users can only see and manage their own.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/webhooks` | Bearer | Create a webhook |
| GET | `/api/v1/webhooks` | Bearer | List webhooks for current user |
| PATCH | `/api/v1/webhooks/{id}` | Bearer | Update a webhook |
| DELETE | `/api/v1/webhooks/{id}` | Bearer | Delete a webhook |
| GET | `/api/v1/webhooks/{id}/deliveries` | Bearer | List delivery logs for a webhook |

Create body:
```json
{
  "target_url": "https://example.com/hook",
  "event_types": ["bot.created", "bot.updated"],
  "secret": "minimum-8-chars"
}
```

Supported event types: `bot.created`, `bot.updated`, `bot.deleted`, `bot.ran`

Webhook target URLs must be publicly reachable HTTPS or HTTP endpoints. `localhost`, `.local` domains, and private IP ranges are rejected.

**Delivery mechanism:** Up to 5 attempts with exponential backoff. Each delivery POSTs JSON with headers:
- `X-Webhook-Signature: sha256=<hmac-sha256 of body>`
- `X-Webhook-Event: <event-type>`
- `X-Webhook-Delivery: <event-id>`

### Tasks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/tasks` | Bearer | Enqueue a task |
| GET | `/api/v1/tasks/{id}` | Bearer | Get task status and result |

Create body:
```json
{
  "type": "echo",
  "payload": { "any": "json" }
}
```

Task statuses: `queued`, `processing`, `completed`, `failed`

### Admin

Requires authentication + admin role (`is_admin = true`).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/admin/break` | Admin | Trigger health break (makes health checks fail) |
| POST | `/api/v1/admin/break/reset` | Admin | Reset health break |
| GET | `/api/v1/admin/break/status` | Admin | Check health break state |

### Metrics

```
GET /metrics
```

Prometheus metrics exposed at `/metrics` (path configurable via `JM_API_METRICS_PATH`). Metrics tracked:

- `http_requests_total` — by method, endpoint pattern, status
- `http_request_duration_seconds` — histogram
- `http_request_errors_total` — 4xx/5xx requests
- `db_connection_attempts_total` — startup DB connection attempts by `result` (`success`/`failure`)

### Static Admin Dashboard

A static file dashboard is served at `/admin/`. Files are embedded in the binary from the `static/` directory.

## Authentication Flow

The API uses a dual-token scheme:

1. **Access token** — short-lived JWT (default 15 min) sent as `Authorization: Bearer <token>`
2. **Refresh token** — longer-lived JWT (default 7 days) stored in an `HttpOnly` cookie, never accessible to JavaScript

Token refresh rotates the refresh token on every use. If a revoked refresh token is presented (replay detection), all sessions for that user are immediately revoked.

Access tokens are validated using the signing key list (`JM_API_JWT_SIGNING_KEYS`), which supports multiple keys to enable zero-downtime key rotation.

## Configuration

All configuration is via environment variables with the `JM_API_` prefix. Unset variables use the listed defaults.

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_DATABASE_URL` | — | **Required.** PostgreSQL connection URL |
| `JM_API_ENVIRONMENT` | `development` | `development`, `staging`, or `production` |
| `JM_API_DEBUG` | `false` | Enable debug mode |
| `JM_API_APP_NAME` | `jm-api` | Application name (used in metrics labels) |
| `JM_API_APP_VERSION` | `0.1.0` | Application version |
| `JM_API_DB_CONNECT_RETRY_ENABLED` | `true` | Enable startup DB connection retries (API + worker) |
| `JM_API_DB_CONNECT_RETRY_MAX_ATTEMPTS` | `5` | Maximum startup DB connection attempts |
| `JM_API_DB_CONNECT_RETRY_INITIAL_DELAY_SECONDS` | `1` | Initial delay before retry (exponential backoff) |
| `JM_API_DB_CONNECT_RETRY_MAX_DELAY_SECONDS` | `30` | Maximum delay cap for retries |

### Database Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_DB_POOL_MAX_CONNS` | `20` | Maximum PostgreSQL connections in pool |
| `JM_API_DB_POOL_MIN_CONNS` | `2` | Minimum PostgreSQL connections maintained in pool |
| `DB_POOL_MAX_CONNS` | `20` | Legacy alias for `JM_API_DB_POOL_MAX_CONNS` |
| `DB_POOL_MIN_CONNS` | `2` | Legacy alias for `JM_API_DB_POOL_MIN_CONNS` |

Recommended sizing:
- Small (dev/test): max=10, min=2
- Medium (production): max=20, min=5
- Large (high-load): max=50, min=10

### Database Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_DB_POOL_MAX_CONNS` | `20` | Maximum PostgreSQL connections in pool |
| `JM_API_DB_POOL_MIN_CONNS` | `2` | Minimum PostgreSQL connections maintained in pool |
| `DB_POOL_MAX_CONNS` | `20` | Legacy alias for `JM_API_DB_POOL_MAX_CONNS` |
| `DB_POOL_MIN_CONNS` | `2` | Legacy alias for `JM_API_DB_POOL_MIN_CONNS` |

Recommended sizing:
- Small (dev/test): max=10, min=2
- Medium (production): max=20, min=5
- Large (high-load): max=50, min=10

### Database Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_DB_POOL_MAX_CONNS` | `20` | Maximum PostgreSQL connections in pool |
| `JM_API_DB_POOL_MIN_CONNS` | `2` | Minimum PostgreSQL connections maintained in pool |
| `DB_POOL_MAX_CONNS` | `20` | Legacy alias for `JM_API_DB_POOL_MAX_CONNS` |
| `DB_POOL_MIN_CONNS` | `2` | Legacy alias for `JM_API_DB_POOL_MIN_CONNS` |

Recommended sizing:
- Small (dev/test): max=10, min=2
- Medium (production): max=20, min=5
- Large (high-load): max=50, min=10

### Database Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_DB_POOL_MAX_CONNS` | `20` | Maximum PostgreSQL connections in pool |
| `JM_API_DB_POOL_MIN_CONNS` | `2` | Minimum PostgreSQL connections maintained in pool |
| `DB_POOL_MAX_CONNS` | `20` | Legacy alias for `JM_API_DB_POOL_MAX_CONNS` |
| `DB_POOL_MIN_CONNS` | `2` | Legacy alias for `JM_API_DB_POOL_MIN_CONNS` |

Recommended sizing:
- Small (dev/test): max=10, min=2
- Medium (production): max=20, min=5
- Large (high-load): max=50, min=10

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_SERVER_HOST` | `0.0.0.0` | Bind address |
| `JM_API_SERVER_PORT` | `8000` | Bind port |
| `JM_API_SHUTDOWN_TIMEOUT` | `30` | Graceful shutdown timeout (seconds) |
| `JM_API_API_V1_PREFIX` | `/api/v1` | API v1 route prefix |

### Request Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_REQUEST_TIMEOUT_DEFAULT` | `30s` | Default timeout for standard API handlers |
| `JM_API_REQUEST_TIMEOUT_BOT_QUERY` | `10s` | Timeout for `/bots` endpoints |
| `JM_API_REQUEST_TIMEOUT_WEBHOOK` | `60s` | Timeout for `/webhooks` endpoints |
| `JM_API_REQUEST_TIMEOUT_AUTH` | `5s` | Timeout for `/auth` endpoints |
| `JM_API_REQUEST_TIMEOUT_HEALTH` | `2s` | Timeout for health endpoints |

Timed responses return `504 Gateway Timeout` with JSON `{ "error": "Request timed out" }` and include the `X-Request-Timeout` response header.

### JWT & Sessions

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_JWT_SECRET_KEY` | `change-me-...` | Primary signing key. **Must be >= 32 bytes in production.** |
| `JM_API_JWT_SIGNING_KEYS` | — | Comma-separated list of signing keys (enables rotation). Falls back to `JM_API_JWT_SECRET_KEY`. |
| `JM_API_JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JM_API_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token lifetime (minutes) |
| `JM_API_JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime (days) |
| `JM_API_SESSION_CLEANUP_INTERVAL_SECONDS` | `300` | How often expired sessions are purged |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_RATE_LIMIT_STORAGE_URI` | `memory://` | `memory://` (dev) or a Redis URL (production required) |
| `JM_API_RATE_LIMIT_API_PER_MINUTE` | `120` | General API rate limit per minute |
| `JM_API_RATE_LIMIT_API_PER_HOUR` | `3000` | General API rate limit per hour |
| `JM_API_RATE_LIMIT_QUOTA_PER_DAY` | `10000` | Daily quota |
| `JM_API_RATE_LIMIT_QUOTA_PER_MONTH` | `200000` | Monthly quota |

Rate limit keys are per-user (authenticated) or per-IP (unauthenticated). Rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) are included on all responses.

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_REDIS_URL` | — | Redis host (omit to disable Redis) |
| `JM_API_REDIS_PORT` | `6379` | Redis port |
| `JM_API_REDIS_PASSWORD` | — | Redis password |
| `JM_API_REDIS_DB` | `0` | Redis database index |
| `JM_API_REDIS_CONNECTION_POOL_SIZE` | `10` | Minimum connection pool size |
| `JM_API_REDIS_CONNECTION_POOL_MAX` | `20` | Maximum connection pool size |
| `JM_API_REDIS_SOCKET_TIMEOUT` | `5` | Read/write timeout (seconds) |
| `JM_API_REDIS_SOCKET_CONNECT_TIMEOUT` | `5` | Connection timeout (seconds) |

If Redis is configured but the connection fails at startup, the server falls back to in-memory rate limiting with a warning.

### CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_ALLOW_ORIGINS` | — | Comma-separated list of allowed origins. CORS is disabled if unset. |
| `JM_API_CORS_ALLOW_CREDENTIALS` | `true` | Allow credentials |
| `JM_API_CORS_ALLOW_METHODS` | `*` | Comma-separated allowed methods |
| `JM_API_CORS_ALLOW_HEADERS` | `*` | Comma-separated allowed headers |

### Security Headers

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_SECURITY_HEADERS_ENABLED` | `true` | Enable security headers middleware |
| `JM_API_SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS` | `nosniff` | `X-Content-Type-Options` value |
| `JM_API_SECURITY_HEADER_X_FRAME_OPTIONS` | `DENY` | `X-Frame-Options` value |
| `JM_API_SECURITY_HEADER_HSTS_MAX_AGE` | `31536000` | HSTS max-age (seconds) |
| `JM_API_SECURITY_HEADER_HSTS_INCLUDE_SUBDOMAINS` | `true` | HSTS includeSubDomains |
| `JM_API_SECURITY_HEADER_HSTS_PRELOAD` | `false` | HSTS preload |

### Proxy & Hosts

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_ALLOWED_HOSTS` | — | Comma-separated list of allowed Host header values |
| `JM_API_TRUST_PROXY_HEADERS` | `false` | Trust `X-Forwarded-For` headers |
| `JM_API_TRUSTED_PROXY_CIDRS` | — | Required when `TRUST_PROXY_HEADERS=true`. Comma-separated CIDR list. |
| `JM_API_REQUEST_ID_HEADER` | `X-Request-ID` | Header used for request ID propagation |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `JM_API_LOG_JSON` | `true` | Emit JSON log lines |
| `JM_API_LOG_SAMPLE_RATE` | `1.0` | Log sampling rate (0.0–1.0) |
| `JM_API_SLOW_QUERY_THRESHOLD_MS` | `500` | Threshold for slow query warnings (ms) |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_METRICS_ENABLED` | `true` | Enable Prometheus metrics endpoint |
| `JM_API_METRICS_PATH` | `/metrics` | Path to expose metrics |
| `JM_API_TRACING_ENABLED` | `false` | Enable OTEL tracing |
| `JM_API_TRACING_SERVICE_NAME` | `jm-api` | Service name in traces |
| `JM_API_TRACING_SERVICE_VERSION` | `0.1.0` | Service version in traces |
| `JM_API_TRACING_JAEGER_HOST` | `localhost` | OTLP/HTTP export host |
| `JM_API_TRACING_JAEGER_PORT` | `6831` | OTLP/HTTP export port |

### Deployment

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_GIT_SHA` | — | Git commit SHA, exposed via `/api/meta` |
| `JM_API_DEPLOYED_AT` | — | Deployment timestamp, exposed via `/api/meta` |

### Bots

| Variable | Default | Description |
|----------|---------|-------------|
| `JM_API_BOTS_WRITE_ADMIN_ONLY` | `false` | Restrict bot create/update/delete to admin users |
| `JM_API_I_UNDERSTAND_RISK` | `false` | Set to `true` to allow non-admin bot writes in production |

## Production Requirements

The server enforces these additional validations when `JM_API_ENVIRONMENT` is `production` or `staging`:

- `JM_API_JWT_SECRET_KEY` must be at least 32 bytes
- `JM_API_RATE_LIMIT_STORAGE_URI` must not be `memory://` (Redis required)
- `JM_API_BOTS_WRITE_ADMIN_ONLY=true` or `JM_API_I_UNDERSTAND_RISK=true`
- If `JM_API_TRUST_PROXY_HEADERS=true`, `JM_API_TRUSTED_PROXY_CIDRS` must be set

## CI/CD Pipeline

Two GitHub Actions workflows automate testing and deployment.

### CI (`.github/workflows/ci.yml`)

Runs on every push to `main` and on pull requests targeting `main`.

**Job 1: `quality-gates`** (10 min timeout)
1. Checkout → Go setup (version from `go.mod`) → module cache
2. `go vet ./...`
3. Build `api` and `worker` binaries
4. Unit tests with race detection: `go test ./... -count=1 -race`

**Job 2: `integration-tests`** (15 min timeout, depends on `quality-gates`)
1. Starts a PostgreSQL 15 service container
2. Installs `golang-migrate` CLI v4.17.0
3. Runs all migrations against the test database
4. Runs integration tests: `go test ./... -count=1 -race -v -tags integration`
5. Uploads test output as a build artifact

### CD (`.github/workflows/deploy.yml`)

Runs on pushes to `main` only. Uses concurrency control — only one deploy runs at a time; new pushes cancel in-progress deploys.

1. Checkout with full history (`fetch-depth: 0`)
2. Configure `.netrc` for Heroku Git authentication
3. `git push` to Heroku (`https://git.heroku.com/<app>.git HEAD:main`)
4. Wait 30s for stabilization, then poll `/api/v1/health` up to 5 times (10s apart)
5. Report deployment status

### Required Secrets & Variables

| Name | Type | Used By | Description |
|------|------|---------|-------------|
| `JWT_SECRET_KEY` | Secret | CI | JWT signing key for integration tests |
| `HEROKU_API_KEY` | Secret | CD | Heroku API key for Git push auth |
| `HEROKU_APP_NAME` | Secret | CD | Target Heroku app name |
| `PRODUCTION_BASE_URL` | Variable | CD | Base URL for post-deploy health checks (e.g. `https://myapp.herokuapp.com`) |

## Deployment

### Heroku (Production)

The app deploys to Heroku automatically on every push to `main` via the CD workflow. Heroku detects the `Dockerfile` and builds the container.

**Initial setup:**

1. Create a Heroku app and attach a PostgreSQL add-on
2. Set config vars on Heroku:
   ```sh
   heroku config:set JM_API_DATABASE_URL="<postgres-url>" \
     JM_API_ENVIRONMENT=production \
     JM_API_JWT_SECRET_KEY="<min-32-byte-secret>" \
     JM_API_REDIS_URL="<redis-url>" \
     JM_API_BOTS_WRITE_ADMIN_ONLY=true \
     -a <app-name>
   ```
3. Add the required GitHub secrets (`HEROKU_API_KEY`, `HEROKU_APP_NAME`) and the `PRODUCTION_BASE_URL` variable in repo settings

**Running migrations in production:**

Migrations are bundled in the Docker image at `/migrations`. Run them manually via Heroku:

```sh
heroku run "migrate -path /migrations -database \$DATABASE_URL up" -a <app-name>
```

**Running the worker:**

The worker runs as a separate process. On Heroku, add a `worker` dyno type in your `Procfile` or scale it manually:

```sh
heroku ps:scale worker=1 -a <app-name>
```

### Docker (Self-Hosted)

Build and run the container directly:

```sh
docker build -t jm-api .

# Run the API
docker run -d --name jm-api \
  -e JM_API_DATABASE_URL="postgres://user:pass@host:5432/db" \
  -e JM_API_ENVIRONMENT=production \
  -e JM_API_JWT_SECRET_KEY="your-secret-key-min-32-bytes" \
  -p 8000:8000 \
  jm-api

# Run the worker
docker run -d --name jm-worker \
  -e JM_API_DATABASE_URL="postgres://user:pass@host:5432/db" \
  jm-api worker
```

The image includes a built-in health check that polls `/api/v1/live` every 30s.

### Observability Stack (Local)

A Docker Compose file provides Prometheus, Grafana, and Jaeger for local development:

```sh
docker compose -f docker-compose.observability.yml up -d
```

| Service | URL | Notes |
|---------|-----|-------|
| Prometheus | `http://localhost:9090` | Scrapes `/metrics` from `host.docker.internal:8000` |
| Grafana | `http://localhost:3000` | Default login: `admin` / `admin` |
| Jaeger | `http://localhost:16686` | Trace viewer UI |

To enable tracing in the API, set:

```sh
export JM_API_TRACING_ENABLED=true
export JM_API_TRACING_JAEGER_HOST=localhost
export JM_API_TRACING_JAEGER_PORT=6831
```

## Database Migrations

Migrations live in `internal/db/migrate/`. The `golang-migrate` CLI is used to apply them.

```sh
# Apply all pending migrations
make migrate-up

# Roll back the last migration
make migrate-down
```

The `JM_API_DATABASE_URL` environment variable must be set before running either command.

## Code Generation

SQL queries are defined in `internal/db/queries/` and the schema is inferred from migration files. After modifying either, regenerate the Go code:

```sh
make sqlc
# runs: sqlc generate
```

Generated files in `internal/db/sqlc/` are committed to the repository and must not be edited by hand.

## Background Worker

The worker polls the `tasks` table every 5 seconds for queued tasks, processing up to 10 per poll cycle. It uses a simple handler registry pattern:

```go
worker.RegisterHandler("my-task", func(ctx context.Context, payload json.RawMessage) (json.RawMessage, error) {
    // process payload
    return result, nil
})
```

Stale `processing` tasks (e.g. from a crash) are reset to `queued` on startup.

## Project Layout

```
cmd/
  api/        — API server entrypoint
  worker/     — Background worker entrypoint
internal/
  config/     — Environment-based configuration with production validation
  db/
    migrate/  — SQL migration files
    queries/  — sqlc query definitions
    sqlc/     — Generated database code (do not edit)
  handler/    — HTTP handlers (auth, bots, webhooks, tasks, health, admin, meta)
  middleware/ — Request ID, security headers, auth, rate limiting, shutdown guard
  model/      — Shared domain types and response structs
  observability/ — Logging (slog), Prometheus metrics, OTEL tracing setup
  service/    — Auth (JWT/bcrypt/sessions), webhook delivery, worker
  server/     — chi router assembly, dependency wiring, lifecycle management
static/       — Embedded admin dashboard assets
```
