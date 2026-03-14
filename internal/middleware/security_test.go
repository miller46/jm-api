package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jack/jm-api-go/internal/config"
	"github.com/stretchr/testify/assert"
)

func TestSecurityHeaders_SetsHeaders(t *testing.T) {
	cfg := &config.Config{
		SecurityHeadersEnabled:             true,
		SecurityHeaderXContentTypeOptions:  "nosniff",
		SecurityHeaderXFrameOptions:        "DENY",
		SecurityHeaderHSTSMaxAge:           31536000,
		SecurityHeaderHSTSIncludeSubdomains: true,
		SecurityHeaderHSTSPreload:          false,
		SecurityHeaderAdminCSP:             "default-src 'none'",
	}

	handler := SecurityHeaders(cfg)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/test", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, "nosniff", rr.Header().Get("X-Content-Type-Options"))
	assert.Equal(t, "DENY", rr.Header().Get("X-Frame-Options"))
	assert.Contains(t, rr.Header().Get("Strict-Transport-Security"), "max-age=31536000")
	assert.Contains(t, rr.Header().Get("Strict-Transport-Security"), "includeSubDomains")
	assert.Empty(t, rr.Header().Get("Content-Security-Policy"))
}

func TestSecurityHeaders_AdminCSP(t *testing.T) {
	cfg := &config.Config{
		SecurityHeadersEnabled: true,
		SecurityHeaderAdminCSP: "default-src 'none'",
	}

	handler := SecurityHeaders(cfg)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/admin/test", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, "default-src 'none'", rr.Header().Get("Content-Security-Policy"))
}

func TestSecurityHeaders_Disabled(t *testing.T) {
	cfg := &config.Config{SecurityHeadersEnabled: false}

	handler := SecurityHeaders(cfg)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest("GET", "/test", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Empty(t, rr.Header().Get("X-Content-Type-Options"))
}
