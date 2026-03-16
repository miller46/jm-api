-- name: CreateFailedTask :one
INSERT INTO failed_tasks (
    original_task_id,
    task_type,
    payload,
    error_message,
    error_stack,
    attempt_count,
    final_attempt_at,
    create_at
) VALUES (
    $1,
    $2,
    $3,
    $4,
    $5,
    $6,
    NOW(),
    NOW()
)
ON CONFLICT (original_task_id) DO UPDATE SET
    task_type = EXCLUDED.task_type,
    payload = EXCLUDED.payload,
    error_message = EXCLUDED.error_message,
    error_stack = EXCLUDED.error_stack,
    attempt_count = EXCLUDED.attempt_count,
    final_attempt_at = EXCLUDED.final_attempt_at
RETURNING *;
