package middleware

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestErrorHandler_RecoversPanicAndReturnsStandard500(t *testing.T) {
	h := ErrorHandler()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		panic("db connection failed")
	}))

	req := httptest.NewRequest("GET", "/panic", nil)
	req = req.WithContext(context.WithValue(req.Context(), RequestIDKey, "req-123"))
	rr := httptest.NewRecorder()

	h.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusInternalServerError, rr.Code)
	assert.Equal(t, "application/json", rr.Header().Get("Content-Type"))

	var body map[string]string
	err := json.Unmarshal(rr.Body.Bytes(), &body)
	assert.NoError(t, err)
	assert.Equal(t, "Internal Server Error", body["error"])
}

func TestErrorHandler_LogsStructuredError(t *testing.T) {
	var buf bytes.Buffer
	orig := slog.Default()
	logger := slog.New(slog.NewJSONHandler(&buf, nil))
	slog.SetDefault(logger)
	t.Cleanup(func() { slog.SetDefault(orig) })

	h := ErrorHandler()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		panic("boom")
	}))

	req := httptest.NewRequest("POST", "/v1/tasks", nil)
	req = req.WithContext(context.WithValue(req.Context(), RequestIDKey, "req-456"))
	rr := httptest.NewRecorder()

	h.ServeHTTP(rr, req)

	logLine := buf.String()
	assert.Contains(t, logLine, "unhandled panic in request")
	assert.Contains(t, logLine, "\"request_id\":\"req-456\"")
	assert.Contains(t, logLine, "\"method\":\"POST\"")
	assert.Contains(t, logLine, "\"path\":\"/v1/tasks\"")
}
