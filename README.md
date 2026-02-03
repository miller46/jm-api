# JM API

A modular FastAPI service 

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

uvicorn jm_api.main:app --reload
```

The health check is available at `GET /api/v1/healthz`.

## Tests

```bash
python3 -m pytest
```

## Configuration

Environment variables are prefixed with `JM_API_` and can be loaded from `.env`.
Comma-separated values are supported for list settings like `ALLOW_ORIGINS` and
`ALLOWED_HOSTS`.

See `.env.example` for defaults and guidance.
