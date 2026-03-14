package middleware

import (
	"crypto/subtle"
	"net/http"
	"strings"
)

// CSRF validates that the X-CSRF-Token header matches the csrf_token cookie
// on all state-changing requests (POST, PATCH, PUT, DELETE).
func CSRF(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet, http.MethodHead, http.MethodOptions:
			next.ServeHTTP(w, r)
			return
		}

		cookie, err := r.Cookie("csrf_token")
		if err != nil || strings.TrimSpace(cookie.Value) == "" {
			writeAuthError(w, http.StatusForbidden, "missing CSRF cookie")
			return
		}

		header := strings.TrimSpace(r.Header.Get("X-CSRF-Token"))
		cookieVal := strings.TrimSpace(cookie.Value)
		if header == "" || subtle.ConstantTimeCompare([]byte(cookieVal), []byte(header)) != 1 {
			writeAuthError(w, http.StatusForbidden, "CSRF validation failed")
			return
		}

		next.ServeHTTP(w, r)
	})
}
