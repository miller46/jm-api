# JM API

A modular FastAPI service backed by SQLAlchemy.

## Quickstart

```bash
uv pip install -e ".[dev]"

JM_API_DATABASE_URL=sqlite:///./dev.db uv run uvicorn jm_api.main:app --reload
```

`DATABASE_URL` is required (no default). For local development any SQLite URL works.
SQLite is rejected when `ENVIRONMENT` is `production` or `staging`.

## Project Structure

```
src/jm_api/
  main.py              # ASGI entry point
  app.py               # FastAPI factory (create_app)
  core/
    config.py          # Pydantic Settings (JM_API_ prefix)
    lifespan.py        # Startup/shutdown (DB init & dispose)
    logging.py         # Structured logging config
  db/
    base.py            # Declarative base, TimestampedIdBase, ID generation
    session.py         # Engine, session factory, get_db dependency
  models/
    bot.py             # Bot SQLAlchemy model
  schemas/
    bot.py             # Bot Pydantic response schemas
  api/
    router.py          # Top-level API router
    routes/
      health.py        # GET /healthz
      bots.py          # GET /bots, GET /bots/{bot_id}
  middleware/
    request_id.py      # X-Request-ID middleware
```

## API Endpoints

All routes are prefixed with `/api/v1` by default.

| Method | Path               | Description                                      |
|--------|--------------------|--------------------------------------------------|
| GET    | `/healthz`         | Health check                                     |
| GET    | `/bots`            | List bots (paginated, filterable)                |
| GET    | `/bots/{bot_id}`   | Get a single bot by ID                           |

### Bot List Filters

`GET /bots` supports the following query parameters:

- `page`, `per_page` — pagination (default 1 / 20, max 100)
- `rig_id` — exact match
- `kill_switch` — boolean filter
- `log_search` — case-insensitive substring search on `last_run_log`
- `create_at_after`, `create_at_before` — date range
- `last_update_at_after`, `last_update_at_before` — date range
- `last_run_at_after`, `last_run_at_before` — date range

## Tests

```bash
uv run pytest
```

## Configuration

Environment variables are prefixed with `JM_API_` and can be loaded from `.env`.
Comma-separated values are supported for list settings like `ALLOW_ORIGINS` and
`ALLOWED_HOSTS`.

| Variable              | Default          | Notes                                     |
|-----------------------|------------------|-------------------------------------------|
| `DATABASE_URL`        | *(required)*     | SQLAlchemy connection string              |
| `ENVIRONMENT`         | `development`    | `production`/`staging` reject SQLite      |
| `DEBUG`               | `false`          |                                           |
| `LOG_LEVEL`           | `INFO`           |                                           |
| `API_V1_PREFIX`       | `/api/v1`        |                                           |
| `DOCS_ENABLED`        | `true`           | Toggles `/docs`, `/redoc`, `/openapi.json` |
| `REQUEST_ID_HEADER`   | `X-Request-ID`   |                                           |
| `ALLOW_ORIGINS`       | *(empty)*        | Comma-separated CORS origins              |
| `ALLOWED_HOSTS`       | *(empty)*        | Comma-separated trusted hosts             |

See `.env.example` for defaults and guidance.
