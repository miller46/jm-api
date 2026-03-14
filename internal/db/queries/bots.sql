-- name: GetBotByID :one
SELECT * FROM bots WHERE id = $1;

-- name: ListBots :many
SELECT * FROM bots
WHERE
    (sqlc.narg('rig_id')::varchar IS NULL OR rig_id = sqlc.narg('rig_id')) AND
    (sqlc.narg('kill_switch')::boolean IS NULL OR kill_switch = sqlc.narg('kill_switch')) AND
    (sqlc.narg('log_search')::varchar IS NULL OR last_run_log ILIKE '%' || sqlc.narg('log_search') || '%') AND
    (sqlc.narg('create_at_from')::timestamptz IS NULL OR create_at >= sqlc.narg('create_at_from')) AND
    (sqlc.narg('create_at_to')::timestamptz IS NULL OR create_at <= sqlc.narg('create_at_to')) AND
    (sqlc.narg('last_update_at_from')::timestamptz IS NULL OR last_update_at >= sqlc.narg('last_update_at_from')) AND
    (sqlc.narg('last_update_at_to')::timestamptz IS NULL OR last_update_at <= sqlc.narg('last_update_at_to')) AND
    (sqlc.narg('last_run_at_from')::timestamptz IS NULL OR last_run_at >= sqlc.narg('last_run_at_from')) AND
    (sqlc.narg('last_run_at_to')::timestamptz IS NULL OR last_run_at <= sqlc.narg('last_run_at_to'))
ORDER BY create_at DESC, id DESC
LIMIT $1 OFFSET $2;

-- name: CountBots :one
SELECT COUNT(*) FROM bots
WHERE
    (sqlc.narg('rig_id')::varchar IS NULL OR rig_id = sqlc.narg('rig_id')) AND
    (sqlc.narg('kill_switch')::boolean IS NULL OR kill_switch = sqlc.narg('kill_switch')) AND
    (sqlc.narg('log_search')::varchar IS NULL OR last_run_log ILIKE '%' || sqlc.narg('log_search') || '%') AND
    (sqlc.narg('create_at_from')::timestamptz IS NULL OR create_at >= sqlc.narg('create_at_from')) AND
    (sqlc.narg('create_at_to')::timestamptz IS NULL OR create_at <= sqlc.narg('create_at_to')) AND
    (sqlc.narg('last_update_at_from')::timestamptz IS NULL OR last_update_at >= sqlc.narg('last_update_at_from')) AND
    (sqlc.narg('last_update_at_to')::timestamptz IS NULL OR last_update_at <= sqlc.narg('last_update_at_to')) AND
    (sqlc.narg('last_run_at_from')::timestamptz IS NULL OR last_run_at >= sqlc.narg('last_run_at_from')) AND
    (sqlc.narg('last_run_at_to')::timestamptz IS NULL OR last_run_at <= sqlc.narg('last_run_at_to'));

-- name: CreateBot :one
INSERT INTO bots (id, rig_id, kill_switch, last_run_log, create_at, last_update_at)
VALUES ($1, $2, $3, $4, NOW(), NOW())
RETURNING *;

-- name: UpdateBot :one
UPDATE bots
SET rig_id = COALESCE(sqlc.narg('rig_id'), rig_id),
    kill_switch = COALESCE(sqlc.narg('kill_switch'), kill_switch),
    last_run_log = COALESCE(sqlc.narg('last_run_log'), last_run_log),
    last_run_at = COALESCE(sqlc.narg('last_run_at'), last_run_at),
    last_update_at = NOW()
WHERE id = $1
RETURNING *;

-- name: DeleteBot :exec
DELETE FROM bots WHERE id = $1;
