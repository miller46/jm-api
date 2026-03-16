package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/jack/jm-api-go/internal/service"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWebhookHandler_Verify(t *testing.T) {
	h := NewWebhookHandler(nil, nil)
	router := chi.NewRouter()
	router.Post("/webhooks/verify", h.Verify)

	payload := json.RawMessage(`{"id":"evt_123","type":"bot.created"}`)
	secret := "supersecret"
	validSig := service.SignWebhookPayload(secret, payload)

	t.Run("valid signature", func(t *testing.T) {
		reqBody := map[string]any{
			"payload":   payload,
			"signature": validSig,
			"secret":    secret,
		}
		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPost, "/webhooks/verify", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		res := httptest.NewRecorder()

		router.ServeHTTP(res, req)

		require.Equal(t, http.StatusOK, res.Code)
		var resp map[string]bool
		require.NoError(t, json.NewDecoder(res.Body).Decode(&resp))
		assert.True(t, resp["valid"])
	})

	t.Run("invalid signature", func(t *testing.T) {
		reqBody := map[string]any{
			"payload":   payload,
			"signature": "sha256=invalid",
			"secret":    secret,
		}
		body, _ := json.Marshal(reqBody)
		req := httptest.NewRequest(http.MethodPost, "/webhooks/verify", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		res := httptest.NewRecorder()

		router.ServeHTTP(res, req)

		require.Equal(t, http.StatusOK, res.Code)
		var resp map[string]bool
		require.NoError(t, json.NewDecoder(res.Body).Decode(&resp))
		assert.False(t, resp["valid"])
	})
}

func TestWebhookHandler_Verify_BadRequest(t *testing.T) {
	h := NewWebhookHandler(nil, nil)
	router := chi.NewRouter()
	router.Post("/webhooks/verify", h.Verify)

	tests := []struct {
		name string
		body string
	}{
		{name: "missing payload", body: `{"signature":"sha256=abc","secret":"secret"}`},
		{name: "missing signature", body: `{"payload":{"id":"evt"},"secret":"secret"}`},
		{name: "missing secret", body: `{"payload":{"id":"evt"},"signature":"sha256=abc"}`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/webhooks/verify", bytes.NewBufferString(tt.body))
			req.Header.Set("Content-Type", "application/json")
			res := httptest.NewRecorder()

			router.ServeHTTP(res, req)
			require.Equal(t, http.StatusBadRequest, res.Code)
		})
	}
}
