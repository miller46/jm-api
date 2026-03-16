package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestHealth_RedisOptionalFailure_DoesNotFailOverall(t *testing.T) {
	h := NewHealthHandler(nil, WithRedisCheck(func(_ context.Context) error {
		return errors.New("dial tcp: connection refused")
	}, false))

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	res := httptest.NewRecorder()
	h.Health(res, req)

	require.Equal(t, http.StatusOK, res.Code)
	var body map[string]any
	require.NoError(t, json.NewDecoder(res.Body).Decode(&body))
	assert.Equal(t, "ok", body["status"])

	checks := body["checks"].(map[string]any)
	redis := checks["redis"].(map[string]any)
	assert.Equal(t, "fail", redis["status"])
	assert.Contains(t, redis["error"], "connection refused")
}

func TestHealth_RedisRequiredFailure_FailsOverall(t *testing.T) {
	h := NewHealthHandler(nil, WithRedisCheck(func(_ context.Context) error {
		return errors.New("redis unavailable")
	}, true))

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	res := httptest.NewRecorder()
	h.Health(res, req)

	require.Equal(t, http.StatusServiceUnavailable, res.Code)
	var body map[string]any
	require.NoError(t, json.NewDecoder(res.Body).Decode(&body))
	assert.Equal(t, "fail", body["status"])

	checks := body["checks"].(map[string]any)
	redis := checks["redis"].(map[string]any)
	assert.Equal(t, "fail", redis["status"])
}

func TestHealth_RedisNotConfigured_IncludesStatus(t *testing.T) {
	h := NewHealthHandler(nil)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	res := httptest.NewRecorder()
	h.Health(res, req)

	require.Equal(t, http.StatusOK, res.Code)
	var body map[string]any
	require.NoError(t, json.NewDecoder(res.Body).Decode(&body))
	checks := body["checks"].(map[string]any)
	redis := checks["redis"].(map[string]any)
	assert.Equal(t, "not_configured", redis["status"])
}
