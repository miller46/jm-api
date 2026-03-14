package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestRequestTimeout_AllowsFastRequest(t *testing.T) {
	h := RequestTimeout(100 * time.Millisecond)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))

	req := httptest.NewRequest("GET", "/api/v1/test", nil)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Equal(t, "100ms", rr.Header().Get("X-Request-Timeout"))
	assert.JSONEq(t, `{"ok":true}`, rr.Body.String())
}

func TestRequestTimeout_TimesOutSlowRequest(t *testing.T) {
	h := RequestTimeout(10 * time.Millisecond)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(50 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))

	req := httptest.NewRequest("GET", "/api/v1/test", nil)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusGatewayTimeout, rr.Code)
	assert.Equal(t, "10ms", rr.Header().Get("X-Request-Timeout"))
	assert.JSONEq(t, `{"error":"Request timed out"}`, rr.Body.String())
}
