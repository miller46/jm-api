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
    last_update_at = NOW()
WHERE id = $1
RETURNING *;
