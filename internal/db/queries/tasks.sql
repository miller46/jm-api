-- name: GetTaskByID :one
SELECT * FROM tasks WHERE id = $1;

-- name: CreateTask :one
INSERT INTO tasks (id, type, payload, status, create_at, last_update_at)
VALUES ($1, $2, $3, 'queued', NOW(), NOW())
RETURNING *;

-- name: PickQueuedTask :one
UPDATE tasks
SET status = 'processing',
    processing_started_at = NOW(),
    last_update_at = NOW()
WHERE id = (
    SELECT id FROM tasks
    WHERE (status = 'queued' OR (status = 'failed' AND retry_count < 5))
    ORDER BY create_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;

-- name: CompleteTask :one
UPDATE tasks
SET status = 'completed',
    result = $2,
    error = NULL,
    completed_at = NOW(),
    last_update_at = NOW()
WHERE id = $1
RETURNING *;

-- name: FailTask :one
UPDATE tasks
SET status = 'failed',
    error = $2,
    retry_count = retry_count + 1,
    last_update_at = NOW()
WHERE id = $1
RETURNING *;

-- name: ResetStaleTasks :exec
UPDATE tasks
SET status = 'queued',
    processing_started_at = NULL,
    last_update_at = NOW()
WHERE status = 'processing'
  AND processing_started_at < NOW() - INTERVAL '5 minutes';
