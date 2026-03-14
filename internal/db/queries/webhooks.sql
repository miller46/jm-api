-- name: GetWebhookByID :one
SELECT * FROM webhooks WHERE id = $1;

-- name: ListWebhooksByUserID :many
SELECT * FROM webhooks WHERE user_id = $1 ORDER BY create_at DESC;

-- name: ListActiveWebhooksByEventType :many
SELECT * FROM webhooks
WHERE is_active = TRUE
  AND event_types @> sqlc.arg('event_type_json')::jsonb;

-- name: CreateWebhook :one
INSERT INTO webhooks (id, user_id, target_url, secret, event_types, is_active, create_at, last_update_at)
VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
RETURNING *;

-- name: UpdateWebhook :one
UPDATE webhooks
SET target_url = COALESCE(sqlc.narg('target_url'), target_url),
    secret = COALESCE(sqlc.narg('secret'), secret),
    event_types = COALESCE(sqlc.narg('event_types'), event_types),
    is_active = COALESCE(sqlc.narg('is_active'), is_active),
    last_update_at = NOW()
WHERE id = $1
RETURNING *;

-- name: DeleteWebhook :exec
DELETE FROM webhooks WHERE id = $1;

-- name: CreateWebhookDeliveryLog :one
INSERT INTO webhook_delivery_logs (id, webhook_id, event_id, event_type, success, attempts, status_code, response_body, error_message, create_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
RETURNING *;

-- name: ListDeliveryLogsByWebhookID :many
SELECT * FROM webhook_delivery_logs
WHERE webhook_id = $1
ORDER BY create_at DESC
LIMIT 100;
