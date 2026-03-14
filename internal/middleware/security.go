package middleware

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/jack/jm-api-go/internal/config"
)

func SecurityHeaders(cfg *config.Config) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !cfg.SecurityHeadersEnabled {
				next.ServeHTTP(w, r)
				return
			}

			w.Header().Set("X-Content-Type-Options", cfg.SecurityHeaderXContentTypeOptions)
			w.Header().Set("X-Frame-Options", cfg.SecurityHeaderXFrameOptions)

			hsts := fmt.Sprintf("max-age=%d", cfg.SecurityHeaderHSTSMaxAge)
			if cfg.SecurityHeaderHSTSIncludeSubdomains {
				hsts += "; includeSubDomains"
			}
			if cfg.SecurityHeaderHSTSPreload {
				hsts += "; preload"
			}
			w.Header().Set("Strict-Transport-Security", hsts)

			if strings.HasPrefix(r.URL.Path, "/admin") {
				w.Header().Set("Content-Security-Policy", cfg.SecurityHeaderAdminCSP)
			}

			next.ServeHTTP(w, r)
		})
	}
}
