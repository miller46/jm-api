#!/bin/sh
set -e

# Run migrations before starting the app (idempotent)
if [ -d /migrations ]; then
  migrate -path /migrations -database "$JM_API_DATABASE_URL" up || true
fi

exec "$@"
