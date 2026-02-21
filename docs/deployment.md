# Deployment Guide

This guide provides a repeatable container deployment workflow for `jm-api`.

## 1) Build and run

```bash
# from repository root
docker build -t ghcr.io/miller46/jm-api:$(git rev-parse --short HEAD) .
cp .env.example .env
# edit .env values for target environment
docker run --rm -p 8000:8000 --env-file .env ghcr.io/miller46/jm-api:$(git rev-parse --short HEAD)
```

Health endpoint:

```bash
curl -f http://localhost:8000/api/v1/live
```

## 2) Migration flow at deploy time

Run migrations **before** switching traffic to a new container image.

```bash
# same image tag you will deploy
docker run --rm --env-file .env ghcr.io/miller46/jm-api:<tag> alembic upgrade head
```

Recommended strategy:
- Kubernetes: run as a pre-deploy Job / init task.
- Docker Compose or VM: run one-off migration container before restarting app.

If migrations fail, do not promote the new app container.

## 3) Startup command

Image default startup command:

```bash
gunicorn jm_api.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-2}
```

Container has a built-in health check against `${JM_API_API_V1_PREFIX}/live`.

## 4) Rollback procedure

Use immutable tags (git SHA or semver), never `latest`.

1. Identify previous known-good tag, e.g. `ghcr.io/miller46/jm-api:abc1234`.
2. Pull previous tag:
   ```bash
   docker pull ghcr.io/miller46/jm-api:abc1234
   ```
3. Redeploy using that tag.
4. If a migration introduced incompatible schema, run targeted Alembic downgrade:
   ```bash
   docker run --rm --env-file .env ghcr.io/miller46/jm-api:abc1234 alembic downgrade -1
   ```
   Only downgrade when validated safe for data integrity.

## 5) Platform examples

### Docker Compose

```yaml
services:
  api:
    image: ghcr.io/miller46/jm-api:${IMAGE_TAG}
    env_file: .env
    ports: ["8000:8000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/live')"]
```

### Kubernetes

- Migration: `Job` running `alembic upgrade head`
- API: `Deployment` with readiness probe `GET /api/v1/ready`
- Liveness probe: `GET /api/v1/live`

### Fly.io / Railway

- Set env vars from `.env.example`
- Set startup command to default image CMD (or leave default)
- Ensure persistent managed Postgres + Redis are configured

## 6) Fresh-environment checklist (<30 min target)

1. Provision Postgres and Redis.
2. Fill `.env` from `.env.example` with production values.
3. Build/pull release image by immutable tag.
4. Run `alembic upgrade head` via one-off container.
5. Start API container(s).
6. Verify `/api/v1/live`, `/api/v1/ready`, `/api/v1/health`.
7. Smoke test auth + bot list endpoint.
