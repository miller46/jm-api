//go:build integration

package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/jack/jm-api-go/internal/db/sqlc"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/jack/jm-api-go/internal/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestTaskHandler_CreateAndGet_Integration(t *testing.T) {
	pool, cleanup := testutil.SetupTestPostgres(t)
	defer cleanup()

	queries := sqlc.New(pool)
	h := NewTaskHandler(queries)

	router := chi.NewRouter()
	router.Post("/tasks", h.Create)
	router.Get("/tasks/{id}", h.Get)

	createReq := map[string]any{
		"type":    "sync.bots",
		"payload": map[string]any{"source": "scheduler"},
	}
	body, _ := json.Marshal(createReq)

	createHTTPReq := httptest.NewRequest(http.MethodPost, "/tasks", bytes.NewReader(body))
	createHTTPReq.Header.Set("Content-Type", "application/json")
	createRes := httptest.NewRecorder()
	router.ServeHTTP(createRes, createHTTPReq)

	require.Equal(t, http.StatusCreated, createRes.Code)

	var created map[string]any
	require.NoError(t, json.NewDecoder(createRes.Body).Decode(&created))
	require.NotEmpty(t, created["id"])
	assert.Equal(t, "sync.bots", created["type"])
	assert.Equal(t, "queued", created["status"])

	id := created["id"].(string)
	getReq := httptest.NewRequest(http.MethodGet, "/tasks/"+id, nil)
	getRes := httptest.NewRecorder()
	router.ServeHTTP(getRes, getReq)

	require.Equal(t, http.StatusOK, getRes.Code)
	var fetched map[string]any
	require.NoError(t, json.NewDecoder(getRes.Body).Decode(&fetched))
	assert.Equal(t, id, fetched["id"])
	assert.Equal(t, "sync.bots", fetched["type"])
}

func TestBotHandler_CreateAndList_Integration(t *testing.T) {
	pool, cleanup := testutil.SetupTestPostgres(t)
	defer cleanup()

	queries := sqlc.New(pool)
	h := NewBotHandler(queries, nil)

	router := chi.NewRouter()
	router.Post("/bots", h.Create)
	router.Get("/bots", h.List)

	createReq := map[string]any{
		"rig_id":       "rig-nyc-1",
		"kill_switch":  true,
		"last_run_log": "boot ok",
	}
	body, _ := json.Marshal(createReq)

	createHTTPReq := httptest.NewRequest(http.MethodPost, "/bots", bytes.NewReader(body))
	createHTTPReq.Header.Set("Content-Type", "application/json")
	createRes := httptest.NewRecorder()
	router.ServeHTTP(createRes, createHTTPReq)

	require.Equal(t, http.StatusCreated, createRes.Code)

	listReq := httptest.NewRequest(http.MethodGet, "/bots?rig_id=rig-nyc-1&kill_switch=true", nil)
	listRes := httptest.NewRecorder()
	router.ServeHTTP(listRes, listReq)

	require.Equal(t, http.StatusOK, listRes.Code)
	var resp struct {
		Items []map[string]any `json:"items"`
		Total float64          `json:"total"`
	}
	require.NoError(t, json.NewDecoder(listRes.Body).Decode(&resp))
	require.Len(t, resp.Items, 1)
	assert.Equal(t, 1.0, resp.Total)
	assert.Equal(t, "rig-nyc-1", resp.Items[0]["rig_id"])
	assert.Equal(t, true, resp.Items[0]["kill_switch"])
}

func TestWebhookHandler_CreateAndList_Integration(t *testing.T) {
	pool, cleanup := testutil.SetupTestPostgres(t)
	defer cleanup()

	queries := sqlc.New(pool)
	h := NewWebhookHandler(queries, nil)

	user, err := queries.CreateUser(context.Background(), sqlc.CreateUserParams{
		ID:           "testuser000000000000000000000001",
		Email:        "test@example.com",
		PasswordHash: "hash",
		IsActive:     true,
		IsAdmin:      false,
	})
	require.NoError(t, err)

	router := chi.NewRouter()
	router.With(withUser(user.ID, user.Email, false)).Post("/webhooks", h.Create)
	router.With(withUser(user.ID, user.Email, false)).Get("/webhooks", h.List)

	createReq := map[string]any{
		"target_url":  "https://example.com/hook",
		"event_types": []string{"bot.created", "bot.updated"},
		"secret":      "supersecret123",
	}
	body, _ := json.Marshal(createReq)

	createHTTPReq := httptest.NewRequest(http.MethodPost, "/webhooks", bytes.NewReader(body))
	createHTTPReq.Header.Set("Content-Type", "application/json")
	createRes := httptest.NewRecorder()
	router.ServeHTTP(createRes, createHTTPReq)
	require.Equal(t, http.StatusCreated, createRes.Code)

	listReq := httptest.NewRequest(http.MethodGet, "/webhooks", nil)
	listRes := httptest.NewRecorder()
	router.ServeHTTP(listRes, listReq)
	require.Equal(t, http.StatusOK, listRes.Code)

	var webhooks []map[string]any
	require.NoError(t, json.NewDecoder(listRes.Body).Decode(&webhooks))
	require.Len(t, webhooks, 1)
	assert.Equal(t, user.ID, webhooks[0]["user_id"])
	assert.Equal(t, "https://example.com/hook", webhooks[0]["target_url"])
}

func withUser(id, email string, isAdmin bool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx := context.WithValue(r.Context(), middleware.UserContextKey{}, &middleware.AuthUser{
				ID:      id,
				Email:   email,
				IsAdmin: isAdmin,
			})
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
