-- name: ListScheduledJobs :many
SELECT *
FROM scheduled_jobs
WHERE deleted_at IS NULL
  AND (sqlc.narg('enabled')::boolean IS NULL OR is_enabled = sqlc.narg('enabled')::boolean)
  AND (sqlc.narg('search')::text IS NULL OR name ILIKE '%' || sqlc.narg('search')::text || '%')
ORDER BY next_run_at ASC NULLS LAST
LIMIT sqlc.narg('per_page')::int
OFFSET sqlc.narg('offset')::int;

-- name: GetScheduledJob :one
SELECT *
FROM scheduled_jobs
WHERE id = $1
  AND deleted_at IS NULL;

-- name: CreateScheduledJob :one
INSERT INTO scheduled_jobs (name, description, job_type, payload, cron_expression, next_run_at, is_enabled)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING *;

-- name: UpdateScheduledJob :one
UPDATE scheduled_jobs
SET name = $2,
    description = $3,
    job_type = $4,
    payload = $5,
    cron_expression = $6,
    next_run_at = $7,
    is_enabled = $8,
    updated_at = NOW()
WHERE id = $1
  AND deleted_at IS NULL
RETURNING *;

-- name: DeleteScheduledJob :exec
UPDATE scheduled_jobs
SET deleted_at = NOW(),
    updated_at = NOW()
WHERE id = $1
  AND deleted_at IS NULL;

-- name: CountScheduledJobs :one
SELECT COUNT(*) FROM scheduled_jobs
WHERE deleted_at IS NULL
  AND (sqlc.narg('enabled')::boolean IS NULL OR is_enabled = sqlc.narg('enabled')::boolean)
  AND (sqlc.narg('search')::text IS NULL OR name ILIKE '%' || sqlc.narg('search')::text || '%');

-- name: PickDueScheduledJobs :many
SELECT *
FROM scheduled_jobs
WHERE id IN (
    SELECT id
    FROM scheduled_jobs
    WHERE next_run_at <= NOW()
      AND is_enabled = TRUE
      AND deleted_at IS NULL
    ORDER BY next_run_at ASC
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
ORDER BY next_run_at ASC;

-- name: GetScheduledJobForUpdate :one
SELECT *
FROM scheduled_jobs
WHERE id = $1
  AND deleted_at IS NULL
FOR UPDATE;

-- name: UpdateScheduledJobNextRunAt :one
UPDATE scheduled_jobs
SET next_run_at = $2,
    updated_at = NOW()
WHERE id = $1
RETURNING *;

-- name: GetScheduledJobByName :one
SELECT *
FROM scheduled_jobs
WHERE name = $1
  AND deleted_at IS NULL;
