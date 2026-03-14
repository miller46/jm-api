package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestShutdownGuard_AllowsRequests(t *testing.T) {
	sg := NewShutdownGuard()
	handler := sg.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, int64(1), sg.ActiveRequests())
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Equal(t, int64(0), sg.ActiveRequests())
}

func TestShutdownGuard_RejectsDuringShutdown(t *testing.T) {
	sg := NewShutdownGuard()
	sg.StartShutdown()

	handler := sg.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("should not reach handler")
	}))

	req := httptest.NewRequest("GET", "/", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusServiceUnavailable, rr.Code)
}

func TestShutdownGuard_IsShuttingDown(t *testing.T) {
	sg := NewShutdownGuard()
	assert.False(t, sg.IsShuttingDown())
	sg.StartShutdown()
	assert.True(t, sg.IsShuttingDown())
}
