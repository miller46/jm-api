#!/bin/sh

# Run database migrations before starting the application.
# golang-migrate uses advisory locks, so concurrent dyno boots are safe.

if [ -d /migrations ] && [ -n "$JM_API_DATABASE_URL" ]; then
  result=$(migrate -path /migrations -database "$JM_API_DATABASE_URL" up 2>&1)
  rc=$?

  if [ $rc -eq 0 ]; then
    echo "migrations: applied"
  elif echo "$result" | grep -q "no change"; then
    echo "migrations: up to date"
  else
    echo "migrations: failed ($result), resetting and retrying"
    migrate -path /migrations -database "$JM_API_DATABASE_URL" force -1 2>&1
    migrate -path /migrations -database "$JM_API_DATABASE_URL" up 2>&1 || echo "migrations: ERROR $result"
  fi
else
  echo "migrations: skipped (no /migrations dir or JM_API_DATABASE_URL not set)"
fi

exec "$@"
