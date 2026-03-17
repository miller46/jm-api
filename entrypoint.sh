#!/bin/sh

# Run database migrations before starting the application.
# golang-migrate uses advisory locks, so concurrent dyno boots are safe.

if [ -d /migrations ] && [ -n "$JM_API_DATABASE_URL" ]; then
  result=$(migrate -path /migrations -database "$JM_API_DATABASE_URL" up 2>&1)
  rc=$?

  if [ $rc -eq 0 ]; then
    echo "migrations: $result"
  elif echo "$result" | grep -q "no change"; then
    echo "migrations: up to date"
  elif echo "$result" | grep -qi "dirty"; then
    echo "migrations: dirty state detected, clearing and retrying"
    # version prints "<number>" to stdout and "dirty" info to stderr
    dirty_ver=$(migrate -path /migrations -database "$JM_API_DATABASE_URL" version 2>/dev/null)
    if [ -n "$dirty_ver" ]; then
      # force sets the version without running the migration, clearing dirty flag.
      # Then re-apply from that version onward (migrations use IF NOT EXISTS).
      migrate -path /migrations -database "$JM_API_DATABASE_URL" force "$dirty_ver"
      migrate -path /migrations -database "$JM_API_DATABASE_URL" up 2>&1
      echo "migrations: recovered from dirty state"
    else
      echo "migrations: ERROR could not determine dirty version"
    fi
  else
    echo "migrations: WARNING $result"
  fi
else
  echo "migrations: skipped (no /migrations dir or JM_API_DATABASE_URL not set)"
fi

exec "$@"
