-- name: CreateSessionToken :one
INSERT INTO session_tokens (token_jti, user_id, issued_at, expires_at, rotated_from_jti, user_agent_hash, ip_subnet)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING *;

-- name: GetSessionToken :one
SELECT * FROM session_tokens WHERE token_jti = $1;

-- name: ListUserSessions :many
SELECT * FROM session_tokens
WHERE user_id = $1
  AND revoked_at IS NULL
  AND expires_at > NOW()
ORDER BY issued_at DESC;

-- name: RevokeSessionToken :exec
UPDATE session_tokens
SET revoked_at = NOW()
WHERE token_jti = $1;

-- name: RevokeAllUserSessions :execrows
UPDATE session_tokens
SET revoked_at = NOW()
WHERE user_id = $1
  AND revoked_at IS NULL
  AND token_jti != $2;

-- name: CleanupExpiredSessions :exec
DELETE FROM session_tokens
WHERE expires_at < NOW() - INTERVAL '1 day';

-- name: GetSessionByRotatedFrom :one
SELECT * FROM session_tokens WHERE rotated_from_jti = $1;

-- name: RevokeAllUserSessionsUnconditional :exec
UPDATE session_tokens
SET revoked_at = NOW()
WHERE user_id = $1 AND revoked_at IS NULL;
