-- name: ListScheduledJobs :many
SELECT id, name, description, job_type, payload, cron_expression, next_run_at, last_run_at, enabled, last_error, created_at, updated_at
FROM scheduled_jobs
WHERE (sqlc.narg('enabled')::boolean IS NULL OR enabled = sqlc.narg('enabled')::boolean)
  AND (sqlc.narg('search')::text IS NULL OR name ILIKE '%' || sqlc.narg('search')::text || '%')
ORDER BY next_run_at ASC NULLS LAST
LIMIT sqlc.narg('per_page')::int
OFFSET sqlc.narg('offset')::int;

-- name: GetScheduledJob :one
SELECT id, name, description, job_type, payload, cron_expression, next_run_at, last_run_at, enabled, last_error, created_at, updated_at
FROM scheduled_jobs
WHERE id = $1;

-- name: CreateScheduledJob :one
INSERT INTO scheduled_jobs (name, description, job_type, payload, cron_expression, next_run_at, enabled)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING id, name, description, job_type, payload, cron_expression, next_run_at, last_run_at, enabled, last_error, created_at, updated_at;

-- name: UpdateScheduledJob :one
UPDATE scheduled_jobs
SET name = COALESCE($2, name),
    description = COALESCE($3, description),
    job_type = COALESCE($4, job_type),
    payload = COALESCE($5, payload),
    cron_expression = COALESCE($6, cron_expression),
    next_run_at = COALESCE($7, next_run_at),
    enabled = COALESCE($8, enabled),
    last_error = COALESCE($9, last_error),
    updated_at = NOW()
WHERE id = $1
RETURNING id, name, description, job_type, payload, cron_expression, next_run_at, last_run_at, enabled, last_error, created_at, updated_at;

-- name: DeleteScheduledJob :exec
DELETE FROM scheduled_jobs WHERE id = $1;

-- name: CountScheduledJobs :one
SELECT COUNT(*) FROM scheduled_jobs
WHERE (sqlc.narg('enabled')::boolean IS NULL OR enabled = sqlc.narg('enabled')::boolean)
  AND (sqlc.narg('search')::text IS NULL OR name ILIKE '%' || sqlc.narg('search')::text || '%');
