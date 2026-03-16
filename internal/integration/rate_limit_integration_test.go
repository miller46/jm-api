//go:build integration

package integration

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jack/jm-api-go/internal/middleware"
	"github.com/stretchr/testify/assert"
)

func TestRateLimit_RequestLifecycle(t *testing.T) {
	r := chi.NewRouter()
	rl := middleware.NewRateLimiter(nil, middleware.RateLimitConfig{PerMinute: 2, Window: 200 * time.Millisecond})
	r.Use(rl.Middleware)
	r.Get("/v1/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})

	for i := 0; i < 2; i++ {
		req := httptest.NewRequest(http.MethodGet, "/v1/health", nil)
		req.RemoteAddr = "10.10.10.10:4321"
		rr := httptest.NewRecorder()
		r.ServeHTTP(rr, req)

		assert.Equal(t, http.StatusOK, rr.Code)
		assert.Equal(t, "2", rr.Header().Get("X-RateLimit-Limit"))
		assert.NotEmpty(t, rr.Header().Get("X-RateLimit-Remaining"))
		assert.NotEmpty(t, rr.Header().Get("X-RateLimit-Reset"))
	}

	blockedReq := httptest.NewRequest(http.MethodGet, "/v1/health", nil)
	blockedReq.RemoteAddr = "10.10.10.10:4321"
	blockedRR := httptest.NewRecorder()
	r.ServeHTTP(blockedRR, blockedReq)

	assert.Equal(t, http.StatusTooManyRequests, blockedRR.Code)
	assert.NotEmpty(t, blockedRR.Header().Get("Retry-After"))

	time.Sleep(250 * time.Millisecond)

	refillReq := httptest.NewRequest(http.MethodGet, "/v1/health", nil)
	refillReq.RemoteAddr = "10.10.10.10:4321"
	refillRR := httptest.NewRecorder()
	r.ServeHTTP(refillRR, refillReq)

	assert.Equal(t, http.StatusOK, refillRR.Code)
}
