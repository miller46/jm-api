package middleware

import (
	"net"
	"net/http"
	"strings"
)

// TrustedHost returns middleware that validates the Host header against
// a list of allowed hosts. Rejects requests with invalid hosts with 421.
// Matches Starlette's TrustedHostMiddleware behavior.
func TrustedHost(allowedHosts []string) func(http.Handler) http.Handler {
	// Pre-compute lowercase allowed hosts
	allowed := make(map[string]bool, len(allowedHosts))
	allowAll := false
	for _, h := range allowedHosts {
		h = strings.ToLower(strings.TrimSpace(h))
		if h == "*" {
			allowAll = true
		}
		allowed[h] = true
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if allowAll {
				next.ServeHTTP(w, r)
				return
			}

			host := r.Host
			// Strip port if present
			if h, _, err := net.SplitHostPort(host); err == nil {
				host = h
			}
			host = strings.ToLower(host)

			if host == "" || !allowed[host] {
				http.Error(w, "Misdirected Request", http.StatusMisdirectedRequest)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}
