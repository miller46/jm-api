-- name: ListScheduledJobs :many
SELECT *
FROM scheduled_jobs
WHERE (sqlc.narg('enabled')::boolean IS NULL OR is_enabled = sqlc.narg('enabled')::boolean)
  AND (sqlc.narg('search')::text IS NULL OR name ILIKE '%' || sqlc.narg('search')::text || '%')
ORDER BY next_run_at ASC NULLS LAST
LIMIT sqlc.narg('per_page')::int
OFFSET sqlc.narg('offset')::int;

-- name: GetScheduledJob :one
SELECT *
FROM scheduled_jobs
WHERE id = $1;

-- name: CreateScheduledJob :one
INSERT INTO scheduled_jobs (name, description, job_type, payload, cron_expression, next_run_at, is_enabled)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING *;

-- name: UpdateScheduledJob :one
UPDATE scheduled_jobs
SET name = COALESCE($2, name),
    description = COALESCE($3, description),
    job_type = COALESCE($4, job_type),
    payload = COALESCE($5, payload),
    cron_expression = COALESCE($6, cron_expression),
    next_run_at = COALESCE($7, next_run_at),
    is_enabled = COALESCE($8, is_enabled),
    updated_at = NOW()
WHERE id = $1
RETURNING *;

-- name: DeleteScheduledJob :exec
DELETE FROM scheduled_jobs WHERE id = $1;

-- name: CountScheduledJobs :one
SELECT COUNT(*) FROM scheduled_jobs
WHERE (sqlc.narg('enabled')::boolean IS NULL OR is_enabled = sqlc.narg('enabled')::boolean)
  AND (sqlc.narg('search')::text IS NULL OR name ILIKE '%' || sqlc.narg('search')::text || '%');

-- name: PickDueScheduledJobs :many
SELECT *
FROM scheduled_jobs
WHERE id IN (
    SELECT id
    FROM scheduled_jobs
    WHERE next_run_at <= NOW()
      AND is_enabled = TRUE
    ORDER BY next_run_at ASC
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
ORDER BY next_run_at ASC;

-- name: GetScheduledJobForUpdate :one
SELECT *
FROM scheduled_jobs
WHERE id = $1
FOR UPDATE;

-- name: UpdateScheduledJobNextRunAt :one
UPDATE scheduled_jobs
SET next_run_at = $2,
    updated_at = NOW()
WHERE id = $1
RETURNING *;
