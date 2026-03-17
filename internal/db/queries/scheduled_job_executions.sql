-- name: CreateScheduledJobExecution :one
INSERT INTO scheduled_job_executions (job_id, started_at)
VALUES ($1, NOW())
RETURNING id, job_id, started_at, completed_at, success, output, error_message;

-- name: CompleteScheduledJobExecution :one
UPDATE scheduled_job_executions
SET completed_at = NOW(),
    success = $2,
    output = $3,
    error_message = $4
WHERE id = $1
RETURNING id, job_id, started_at, completed_at, success, output, error_message;

-- name: ListScheduledJobExecutionsByJobID :many
SELECT id, job_id, started_at, completed_at, success, output, error_message
FROM scheduled_job_executions
WHERE job_id = $1
ORDER BY started_at DESC
LIMIT $2;
